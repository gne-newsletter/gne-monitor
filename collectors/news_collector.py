"""News collector: fetches GNE myopathy news via Google News RSS feeds."""

import hashlib
import logging
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

import yaml

logger = logging.getLogger(__name__)


@dataclass
class NewsArticle:
    article_id: str        # SHA256(title + pub_date)
    title: str
    url: str               # Google News redirect URL
    source: str            # 언론사명
    language: str
    pub_date: Optional[datetime]
    summary: str           # RSS description (HTML 제거)
    query_label: str
    fetched_at: datetime = field(default_factory=datetime.now)


class NewsCollector:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path) as f:
            cfg = yaml.safe_load(f)

        self._cfg = cfg["news"]
        self._db_path = Path(cfg["database"]["path"])
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._delay = float(self._cfg["rate_limit_delay"])
        self._conn = self._init_db()

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    def _init_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS news_articles (
                article_id   TEXT PRIMARY KEY,  -- SHA256(title+pub_date)
                title        TEXT,
                url          TEXT,
                source       TEXT,
                language     TEXT,
                pub_date     TEXT,              -- ISO-8601
                summary      TEXT,
                query_label  TEXT,
                fetched_at   TEXT
            );

            CREATE TABLE IF NOT EXISTS news_runs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                query_label TEXT,
                ran_at      TEXT,
                new_articles INTEGER,
                total_found  INTEGER
            );
        """)
        conn.commit()
        return conn

    def _known_ids(self) -> set[str]:
        rows = self._conn.execute("SELECT article_id FROM news_articles").fetchall()
        return {r["article_id"] for r in rows}

    def _save_articles(self, articles: list[NewsArticle]) -> int:
        new_count = 0
        for a in articles:
            try:
                self._conn.execute(
                    """INSERT OR IGNORE INTO news_articles
                       (article_id, title, url, source, language,
                        pub_date, summary, query_label, fetched_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        a.article_id, a.title, a.url, a.source,
                        a.language,
                        a.pub_date.isoformat() if a.pub_date else None,
                        a.summary, a.query_label, a.fetched_at.isoformat(),
                    ),
                )
                if self._conn.execute("SELECT changes()").fetchone()[0]:
                    new_count += 1
            except sqlite3.Error as e:
                logger.warning("DB insert failed for %s: %s", a.article_id, e)
        self._conn.commit()
        return new_count

    def _log_run(self, label: str, new_articles: int, total_found: int):
        self._conn.execute(
            "INSERT INTO news_runs (query_label, ran_at, new_articles, total_found) VALUES (?,?,?,?)",
            (label, datetime.now().isoformat(), new_articles, total_found),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Fetch RSS
    # ------------------------------------------------------------------

    def _fetch_feed(self, url: str) -> bytes:
        retries = self._cfg["fetch"]["retries"]
        retry_delay = self._cfg["fetch"]["retry_delay"]
        timeout = self._cfg["fetch"]["timeout"]

        req = Request(url, headers={"User-Agent": self._cfg["user_agent"]})
        for attempt in range(1, retries + 1):
            try:
                with urlopen(req, timeout=timeout) as resp:
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

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_feed(self, raw: bytes, label: str, language: str) -> list[NewsArticle]:
        max_age_days = self._cfg["storage"].get("max_age_days", 365)
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=max_age_days)

        root = ET.fromstring(raw)
        items = root.findall(".//item")
        articles = []

        for item in items:
            try:
                article = self._parse_item(item, label, language)
                if article.pub_date and article.pub_date < cutoff:
                    continue
                articles.append(article)
            except Exception as e:
                logger.warning("Parse error in feed %s: %s", label, e)

        return articles

    def _parse_item(self, item: ET.Element, label: str, language: str) -> NewsArticle:
        title = item.findtext("title") or ""
        url = item.findtext("link") or ""
        guid = item.findtext("guid") or url

        source_el = item.find("source")
        source = source_el.text.strip() if source_el is not None and source_el.text else _extract_source(url)

        pub_date_str = item.findtext("pubDate") or ""
        pub_date = _parse_rfc2822(pub_date_str)

        raw_desc = item.findtext("description") or ""
        summary = _strip_html(raw_desc).strip()

        article_id = hashlib.sha256(f"{title}{pub_date_str}".encode()).hexdigest()[:32]

        return NewsArticle(
            article_id=article_id,
            title=title,
            url=url,
            source=source,
            language=language,
            pub_date=pub_date,
            summary=summary,
            query_label=label,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def collect(self, query_label: Optional[str] = None) -> dict:
        feeds = self._cfg["feeds"]
        if query_label:
            feeds = [f for f in feeds if f["label"] == query_label]
            if not feeds:
                raise ValueError(f"Unknown feed label: {query_label}")

        incremental = self._cfg["storage"]["incremental"]
        known = self._known_ids() if incremental else set()
        summary = {}

        for feed in feeds:
            label = feed["label"]
            language = feed.get("language", "en")
            logger.info("[%s] Fetching RSS: %s", label, feed["url"][:70])

            raw = self._fetch_feed(feed["url"])
            time.sleep(self._delay)

            articles = self._parse_feed(raw, label, language)
            total_found = len(articles)

            if incremental:
                articles = [a for a in articles if a.article_id not in known]
                logger.info("[%s] %d new (incremental)", label, len(articles))

            new_count = self._save_articles(articles)
            known.update(a.article_id for a in articles)

            self._log_run(label, new_count, total_found)
            summary[label] = {"total_found": total_found, "new": new_count}
            logger.info("[%s] Done — %d new articles saved", label, new_count)

        return summary

    def stats(self) -> dict:
        rows = self._conn.execute("""
            SELECT query_label, language, COUNT(*) n,
                   MAX(pub_date) newest, MAX(fetched_at) last_fetched
            FROM news_articles GROUP BY query_label
        """).fetchall()

        runs = self._conn.execute("""
            SELECT query_label, MAX(ran_at) last_run, SUM(new_articles) total_new
            FROM news_runs GROUP BY query_label
        """).fetchall()
        run_map = {r["query_label"]: dict(r) for r in runs}

        result = {}
        for row in rows:
            label = row["query_label"]
            result[label] = {
                "article_count": row["n"],
                "language": row["language"],
                "newest_pub": row["newest"],
                "last_fetched": row["last_fetched"],
                "last_run": run_map.get(label, {}).get("last_run"),
            }

        total = self._conn.execute("SELECT COUNT(*) FROM news_articles").fetchone()[0]
        result["_total"] = total
        return result

    def search_local(self, keyword: str, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            """SELECT article_id, title, source, language, pub_date, url, summary
               FROM news_articles
               WHERE title LIKE ? OR summary LIKE ?
               ORDER BY pub_date DESC LIMIT ?""",
            (f"%{keyword}%", f"%{keyword}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def recent(self, days: int = 30, language: Optional[str] = None, limit: int = 50) -> list[dict]:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        if language:
            rows = self._conn.execute(
                """SELECT * FROM news_articles
                   WHERE pub_date >= ? AND language = ?
                   ORDER BY pub_date DESC LIMIT ?""",
                (cutoff, language, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT * FROM news_articles
                   WHERE pub_date >= ?
                   ORDER BY pub_date DESC LIMIT ?""",
                (cutoff, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def top_sources(self, n: int = 10) -> list[tuple[str, int]]:
        rows = self._conn.execute(
            """SELECT source, COUNT(*) n FROM news_articles
               GROUP BY source ORDER BY n DESC LIMIT ?""",
            (n,),
        ).fetchall()
        return [(r["source"], r["n"]) for r in rows]

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text).strip()


def _parse_rfc2822(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        return None


def _extract_source(url: str) -> str:
    m = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1) if m else "unknown"
