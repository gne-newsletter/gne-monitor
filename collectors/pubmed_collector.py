"""PubMed collector for GNE myopathy research articles via NCBI E-utilities."""

import logging
import sqlite3
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

import yaml

logger = logging.getLogger(__name__)


@dataclass
class Article:
    pmid: str
    title: str
    abstract: str
    summary: str          # abstract 첫 300자 (검색·표시용)
    authors: list[str]
    journal: str
    pub_date: Optional[date]
    doi: Optional[str]
    mesh_terms: list[str]
    publication_types: list[str]
    keywords: list[str]
    fetched_at: datetime = field(default_factory=datetime.now)


class PubMedCollector:
    ESEARCH_URL = "{base}/esearch.fcgi"
    EFETCH_URL = "{base}/efetch.fcgi"

    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path) as f:
            cfg = yaml.safe_load(f)

        self._cfg = cfg["pubmed"]
        self._db_path = Path(cfg["database"]["path"])
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._base = self._cfg["base_url"]
        self._api_key = self._cfg.get("api_key", "")
        self._email = self._cfg["email"]
        self._delay = float(self._cfg["rate_limit_delay"])

        # Faster rate with API key
        if self._api_key:
            self._delay = 0.11

        self._conn = self._init_db()

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    def _init_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS pubmed_articles (
                pmid             TEXT PRIMARY KEY,
                title            TEXT,
                abstract         TEXT,
                summary          TEXT,   -- abstract 첫 300자
                authors          TEXT,   -- JSON array
                journal          TEXT,
                pub_date         TEXT,   -- ISO-8601
                doi              TEXT,
                mesh_terms       TEXT,   -- JSON array
                publication_types TEXT,  -- JSON array
                keywords         TEXT,   -- JSON array
                query_label      TEXT,
                fetched_at       TEXT
            );

            CREATE TABLE IF NOT EXISTS pubmed_runs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                query_label  TEXT,
                ran_at       TEXT,
                new_articles INTEGER,
                total_found  INTEGER
            );
        """)
        # 기존 DB에 summary 컬럼 없으면 추가 (마이그레이션)
        existing = [r[1] for r in conn.execute("PRAGMA table_info(pubmed_articles)").fetchall()]
        if "summary" not in existing:
            conn.execute("ALTER TABLE pubmed_articles ADD COLUMN summary TEXT")
            conn.execute("""
                UPDATE pubmed_articles
                SET summary = substr(abstract, 1, 300)
                WHERE summary IS NULL AND abstract IS NOT NULL
            """)
            logger.info("pubmed_articles.summary 컬럼 추가 및 기존 데이터 백필 완료")

        conn.commit()
        return conn

    def _known_pmids(self) -> set[str]:
        rows = self._conn.execute("SELECT pmid FROM pubmed_articles").fetchall()
        return {r["pmid"] for r in rows}

    def _save_articles(self, articles: list[Article], query_label: str) -> int:
        import json

        new_count = 0
        for art in articles:
            try:
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO pubmed_articles
                      (pmid, title, abstract, summary, authors, journal, pub_date,
                       doi, mesh_terms, publication_types, keywords,
                       query_label, fetched_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        art.pmid,
                        art.title,
                        art.abstract,
                        art.summary,
                        json.dumps(art.authors, ensure_ascii=False),
                        art.journal,
                        art.pub_date.isoformat() if art.pub_date else None,
                        art.doi,
                        json.dumps(art.mesh_terms, ensure_ascii=False),
                        json.dumps(art.publication_types, ensure_ascii=False),
                        json.dumps(art.keywords, ensure_ascii=False),
                        query_label,
                        art.fetched_at.isoformat(),
                    ),
                )
                if self._conn.execute("SELECT changes()").fetchone()[0]:
                    new_count += 1
            except sqlite3.Error as e:
                logger.warning("DB insert failed for PMID %s: %s", art.pmid, e)

        self._conn.commit()
        return new_count

    def _log_run(self, query_label: str, new_articles: int, total_found: int):
        self._conn.execute(
            "INSERT INTO pubmed_runs (query_label, ran_at, new_articles, total_found) VALUES (?,?,?,?)",
            (query_label, datetime.now().isoformat(), new_articles, total_found),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # NCBI E-utilities
    # ------------------------------------------------------------------

    def _get(self, url: str, params: dict) -> bytes:
        params["tool"] = "gne-monitor"
        params["email"] = self._email
        if self._api_key:
            params["api_key"] = self._api_key

        full_url = f"{url}?{urlencode(params)}"
        retries = self._cfg["fetch"]["retries"]
        retry_delay = self._cfg["fetch"]["retry_delay"]

        for attempt in range(1, retries + 1):
            try:
                with urlopen(full_url, timeout=30) as resp:
                    return resp.read()
            except HTTPError as e:
                logger.warning("HTTP %s on attempt %d/%d: %s", e.code, attempt, retries, url)
                if attempt < retries:
                    time.sleep(retry_delay * attempt)
            except URLError as e:
                logger.warning("URLError on attempt %d/%d: %s", attempt, retries, e)
                if attempt < retries:
                    time.sleep(retry_delay * attempt)

        raise RuntimeError(f"Failed to fetch {url} after {retries} attempts")

    def _esearch(self, term: str, max_results: int) -> tuple[list[str], int]:
        """Return (pmid_list, total_count)."""
        url = self.ESEARCH_URL.format(base=self._base)
        params = {
            "db": "pubmed",
            "term": term,
            "retmax": max_results,
            "retmode": "xml",
            "sort": "date",
            "usehistory": "n",
        }
        raw = self._get(url, params)
        root = ET.fromstring(raw)

        total = int(root.findtext("Count") or 0)
        pmids = [id_el.text for id_el in root.findall(".//Id") if id_el.text]
        return pmids, total

    def _efetch_batch(self, pmids: list[str]) -> list[Article]:
        url = self.EFETCH_URL.format(base=self._base)
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "rettype": "abstract",
        }
        raw = self._get(url, params)
        time.sleep(self._delay)
        return self._parse_pubmed_xml(raw)

    # ------------------------------------------------------------------
    # XML parsing
    # ------------------------------------------------------------------

    def _parse_pubmed_xml(self, raw: bytes) -> list[Article]:
        root = ET.fromstring(raw)
        articles = []

        for record in root.findall(".//PubmedArticle"):
            try:
                articles.append(self._parse_record(record))
            except Exception as e:
                pmid = record.findtext(".//PMID") or "?"
                logger.warning("Parse error for PMID %s: %s", pmid, e)

        return articles

    def _parse_record(self, record: ET.Element) -> Article:
        citation = record.find("MedlineCitation")
        article_el = citation.find("Article")

        pmid = citation.findtext("PMID")
        title = article_el.findtext("ArticleTitle") or ""
        title = _strip_tags(title)

        # Abstract — may have multiple structured sections
        abstract_parts = []
        for text_el in article_el.findall(".//AbstractText"):
            label = text_el.get("Label")
            text = _strip_tags(ET.tostring(text_el, encoding="unicode"))
            if label:
                abstract_parts.append(f"{label}: {text}")
            else:
                abstract_parts.append(text)
        abstract = "\n".join(abstract_parts)

        # Authors
        authors = []
        for author in article_el.findall(".//Author"):
            last = author.findtext("LastName") or ""
            fore = author.findtext("ForeName") or author.findtext("Initials") or ""
            name = f"{last} {fore}".strip()
            if name:
                authors.append(name)

        # Journal
        journal = article_el.findtext(".//Journal/Title") or \
                  article_el.findtext(".//Journal/ISOAbbreviation") or ""

        # Publication date
        pub_date = self._parse_date(article_el)

        # DOI
        doi = None
        for loc_id in article_el.findall(".//ELocationID"):
            if loc_id.get("EIdType") == "doi":
                doi = loc_id.text
                break

        # MeSH terms
        mesh_terms = [
            mh.findtext("DescriptorName") or ""
            for mh in citation.findall(".//MeshHeading")
        ]
        mesh_terms = [m for m in mesh_terms if m]

        # Publication types
        pub_types = [
            pt.text for pt in article_el.findall(".//PublicationType") if pt.text
        ]

        # Keywords
        keywords = [
            kw.text for kw in citation.findall(".//Keyword") if kw.text
        ]

        summary = abstract[:300].rstrip() + ("…" if len(abstract) > 300 else "")

        return Article(
            pmid=pmid,
            title=title,
            abstract=abstract,
            summary=summary,
            authors=authors,
            journal=journal,
            pub_date=pub_date,
            doi=doi,
            mesh_terms=mesh_terms,
            publication_types=pub_types,
            keywords=keywords,
        )

    def _parse_date(self, article_el: ET.Element) -> Optional[date]:
        # Try ArticleDate first (electronic pub), then Journal/PubDate
        for date_el in [
            article_el.find(".//ArticleDate"),
            article_el.find(".//Journal/JournalIssue/PubDate"),
        ]:
            if date_el is None:
                continue
            year = date_el.findtext("Year")
            month = date_el.findtext("Month") or "1"
            day = date_el.findtext("Day") or "1"
            if year:
                try:
                    month_num = _month_to_num(month)
                    return date(int(year), month_num, int(day))
                except (ValueError, TypeError):
                    pass
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def collect(self, query_label: Optional[str] = None) -> dict:
        """
        Run configured queries. If query_label is given, run only that query.
        Returns summary dict.
        """
        queries = self._cfg["queries"]
        if query_label:
            queries = [q for q in queries if q["label"] == query_label]
            if not queries:
                raise ValueError(f"Unknown query label: {query_label}")

        summary = {}
        incremental = self._cfg["storage"]["incremental"]
        known = self._known_pmids() if incremental else set()

        for query in queries:
            label = query["label"]
            term = query["term"].strip().replace("\n", " ")
            max_results = query.get("max_results", 500)

            logger.info("[%s] Searching PubMed: %s", label, term[:80])
            pmids, total = self._esearch(term, max_results)
            logger.info("[%s] Found %d total, retrieved %d PMIDs", label, total, len(pmids))
            time.sleep(self._delay)

            if incremental:
                pmids = [p for p in pmids if p not in known]
                logger.info("[%s] %d new (incremental)", label, len(pmids))

            articles = self._fetch_articles(pmids, label)
            new_count = self._save_articles(articles, label)
            known.update(a.pmid for a in articles)

            self._log_run(label, new_count, total)
            summary[label] = {"total_found": total, "fetched": len(articles), "new": new_count}
            logger.info("[%s] Done — %d new articles saved", label, new_count)

        return summary

    def _fetch_articles(self, pmids: list[str], label: str) -> list[Article]:
        if not pmids:
            return []

        batch_size = self._cfg["fetch"]["batch_size"]
        articles = []

        for i in range(0, len(pmids), batch_size):
            batch = pmids[i : i + batch_size]
            logger.info("[%s] Fetching batch %d-%d / %d", label, i + 1, i + len(batch), len(pmids))
            batch_articles = self._efetch_batch(batch)
            articles.extend(batch_articles)

        return articles

    def stats(self) -> dict:
        """Return collection statistics from the database."""
        import json

        rows = self._conn.execute("""
            SELECT
                query_label,
                COUNT(*) AS count,
                MIN(pub_date) AS oldest,
                MAX(pub_date) AS newest,
                MAX(fetched_at) AS last_fetched
            FROM pubmed_articles
            GROUP BY query_label
        """).fetchall()

        runs = self._conn.execute("""
            SELECT query_label, MAX(ran_at) AS last_run, SUM(new_articles) AS total_new
            FROM pubmed_runs
            GROUP BY query_label
        """).fetchall()

        run_map = {r["query_label"]: dict(r) for r in runs}

        result = {}
        for row in rows:
            label = row["query_label"]
            result[label] = {
                "article_count": row["count"],
                "oldest_pub": row["oldest"],
                "newest_pub": row["newest"],
                "last_fetched": row["last_fetched"],
                "last_run": run_map.get(label, {}).get("last_run"),
                "total_new_ever": run_map.get(label, {}).get("total_new"),
            }

        total = self._conn.execute("SELECT COUNT(*) FROM pubmed_articles").fetchone()[0]
        result["_total"] = total
        return result

    def search_local(self, keyword: str, limit: int = 20) -> list[dict]:
        """Full-text search across locally stored articles."""
        import json

        rows = self._conn.execute(
            """
            SELECT pmid, title, journal, pub_date, authors, doi
            FROM pubmed_articles
            WHERE title LIKE ? OR abstract LIKE ? OR keywords LIKE ?
            ORDER BY pub_date DESC
            LIMIT ?
            """,
            (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", limit),
        ).fetchall()

        results = []
        for r in rows:
            d = dict(r)
            d["authors"] = json.loads(d["authors"] or "[]")
            results.append(d)
        return results

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _strip_tags(xml_str: str) -> str:
    """Remove XML/HTML tags from a string."""
    import re
    return re.sub(r"<[^>]+>", "", xml_str).strip()


_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

def _month_to_num(month: str) -> int:
    try:
        return int(month)
    except ValueError:
        return _MONTH_MAP.get(month.lower()[:3], 1)
