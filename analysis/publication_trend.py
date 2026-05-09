"""Publication trend analysis over PubMed articles."""

import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import yaml


class PublicationTrend:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        db_path = Path(cfg["database"]["path"])
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row

    # ------------------------------------------------------------------
    # Core counts
    # ------------------------------------------------------------------

    def yearly_counts(self) -> dict[str, int]:
        rows = self._conn.execute("""
            SELECT substr(pub_date, 1, 4) AS year, COUNT(*) AS n
            FROM pubmed_articles
            WHERE pub_date IS NOT NULL AND substr(pub_date,1,4) >= '1980'
            GROUP BY year
            ORDER BY year
        """).fetchall()
        return {r["year"]: r["n"] for r in rows}

    def cumulative_counts(self) -> dict[str, int]:
        yearly = self.yearly_counts()
        total = 0
        result = {}
        for year, n in sorted(yearly.items()):
            total += n
            result[year] = total
        return result

    def growth_rate(self, window: int = 5) -> dict[str, float]:
        """CAGR of publications per rolling window (years)."""
        yearly = self.yearly_counts()
        years = sorted(yearly)
        rates = {}
        for i, yr in enumerate(years):
            if i < window:
                continue
            prev_yr = years[i - window]
            n_now = yearly[yr]
            n_prev = yearly[prev_yr]
            if n_prev > 0:
                rates[yr] = round((n_now / n_prev) ** (1 / window) - 1, 4)
        return rates

    # ------------------------------------------------------------------
    # Authors & journals
    # ------------------------------------------------------------------

    def top_authors(self, n: int = 20) -> list[tuple[str, int]]:
        counter: Counter = Counter()
        rows = self._conn.execute("SELECT authors FROM pubmed_articles WHERE authors != '[]'").fetchall()
        for row in rows:
            for author in json.loads(row["authors"]):
                if author.strip():
                    counter[author.strip()] += 1
        return counter.most_common(n)

    def top_journals(self, n: int = 15) -> list[tuple[str, int]]:
        rows = self._conn.execute("""
            SELECT journal, COUNT(*) AS n
            FROM pubmed_articles
            WHERE journal IS NOT NULL AND journal != ''
            GROUP BY journal
            ORDER BY n DESC
            LIMIT ?
        """, (n,)).fetchall()
        return [(r["journal"], r["n"]) for r in rows]

    # ------------------------------------------------------------------
    # Keywords & MeSH
    # ------------------------------------------------------------------

    def top_mesh_terms(self, n: int = 30) -> list[tuple[str, int]]:
        counter: Counter = Counter()
        rows = self._conn.execute("SELECT mesh_terms FROM pubmed_articles WHERE mesh_terms != '[]'").fetchall()
        for row in rows:
            for term in json.loads(row["mesh_terms"]):
                if term.strip():
                    counter[term.strip()] += 1
        return counter.most_common(n)

    def top_keywords(self, n: int = 30) -> list[tuple[str, int]]:
        counter: Counter = Counter()
        rows = self._conn.execute("SELECT keywords FROM pubmed_articles WHERE keywords != '[]'").fetchall()
        for row in rows:
            for kw in json.loads(row["keywords"]):
                if kw.strip():
                    counter[kw.strip().lower()] += 1
        return counter.most_common(n)

    def title_word_frequency(self, n: int = 40, min_len: int = 4) -> list[tuple[str, int]]:
        """Most frequent meaningful words in article titles."""
        STOPWORDS = {
            "with", "from", "this", "that", "have", "been", "were", "their",
            "which", "into", "also", "more", "than", "such", "after", "during",
            "using", "patients", "patient", "study", "analysis", "case",
            "report", "review", "data", "based", "associated", "induced",
        }
        counter: Counter = Counter()
        rows = self._conn.execute("SELECT title FROM pubmed_articles WHERE title IS NOT NULL").fetchall()
        for row in rows:
            words = re.findall(r"[a-zA-Z]{%d,}" % min_len, row["title"].lower())
            for w in words:
                if w not in STOPWORDS:
                    counter[w] += 1
        return counter.most_common(n)

    # ------------------------------------------------------------------
    # Publication types
    # ------------------------------------------------------------------

    def publication_type_breakdown(self) -> dict[str, int]:
        counter: Counter = Counter()
        rows = self._conn.execute(
            "SELECT publication_types FROM pubmed_articles WHERE publication_types != '[]'"
        ).fetchall()
        for row in rows:
            for pt in json.loads(row["publication_types"]):
                counter[pt] += 1
        return dict(counter.most_common())

    def clinical_evidence_count(self) -> dict[str, int]:
        """Count RCTs, clinical trials, and systematic reviews."""
        clinical_types = {
            "Randomized Controlled Trial": 0,
            "Clinical Trial": 0,
            "Systematic Review": 0,
            "Meta-Analysis": 0,
            "Case Reports": 0,
            "Observational Study": 0,
        }
        rows = self._conn.execute(
            "SELECT publication_types FROM pubmed_articles WHERE publication_types != '[]'"
        ).fetchall()
        for row in rows:
            for pt in json.loads(row["publication_types"]):
                if pt in clinical_types:
                    clinical_types[pt] += 1
        return {k: v for k, v in clinical_types.items() if v > 0}

    # ------------------------------------------------------------------
    # Trend over time
    # ------------------------------------------------------------------

    def keyword_trend(self, keyword: str) -> dict[str, int]:
        """Papers per year mentioning keyword in title or abstract."""
        rows = self._conn.execute("""
            SELECT substr(pub_date, 1, 4) AS year, COUNT(*) AS n
            FROM pubmed_articles
            WHERE (title LIKE ? OR abstract LIKE ?)
              AND pub_date IS NOT NULL
            GROUP BY year
            ORDER BY year
        """, (f"%{keyword}%", f"%{keyword}%")).fetchall()
        return {r["year"]: r["n"] for r in rows}

    def recent_papers(self, years_back: int = 3, limit: int = 20) -> list[dict]:
        from datetime import date
        cutoff = str(date.today().year - years_back)
        rows = self._conn.execute("""
            SELECT pmid, title, journal, pub_date, authors, doi, summary, relevance_score
            FROM pubmed_articles
            WHERE pub_date >= ?
            ORDER BY pub_date DESC
            LIMIT ?
        """, (cutoff, limit)).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["authors"] = json.loads(d["authors"] or "[]")
            results.append(d)
        return results

    def summary(self) -> dict:
        yearly = self.yearly_counts()
        recent_years = {y: n for y, n in yearly.items() if y >= "2020"}
        return {
            "total_articles": sum(yearly.values()),
            "year_range": (min(yearly), max(yearly)) if yearly else (None, None),
            "recent_5y_count": sum(recent_years.values()),
            "top_journals": self.top_journals(5),
            "top_authors": self.top_authors(5),
            "top_mesh": self.top_mesh_terms(10),
            "pub_types": self.clinical_evidence_count(),
            "yearly_counts": yearly,
        }

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
