"""Scheduled job implementations."""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


def _load_cfg(config_path: str) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def _db_conn(cfg: dict) -> sqlite3.Connection:
    conn = sqlite3.connect(Path(cfg["database"]["path"]))
    conn.row_factory = sqlite3.Row
    return conn


# ------------------------------------------------------------------
# Individual jobs
# ------------------------------------------------------------------

def job_collect_pubmed(config_path: str, state: dict, notifier) -> dict:
    """Collect new PubMed articles and return summary."""
    logger.info("[job] PubMed 수집 시작")
    from collectors import PubMedCollector

    prev_count = state.get("pubmed_article_count", 0)

    with PubMedCollector(config_path) as c:
        summary = c.collect()

    cfg = _load_cfg(config_path)
    with _db_conn(cfg) as conn:
        current_count = conn.execute("SELECT COUNT(*) FROM pubmed_articles").fetchone()[0]
        new_articles = _fetch_recent_articles(conn, prev_count)

    total_new = sum(s["new"] for s in summary.values())
    logger.info("[job] PubMed 수집 완료 — 신규 %d건", total_new)

    if total_new > 0:
        notifier.notify_new_findings(
            pubmed_new=total_new,
            ct_new=0,
            pubmed_details=new_articles,
            ct_details=[],
        )

    state["pubmed_article_count"] = current_count
    state["last_pubmed_run"] = datetime.now().isoformat()
    return {"new": total_new, "total": current_count}


def job_collect_ct(config_path: str, state: dict, notifier) -> dict:
    """Collect new ClinicalTrials and return summary."""
    logger.info("[job] ClinicalTrials 수집 시작")
    from collectors import ClinicalTrialsCollector

    prev_count = state.get("ct_trial_count", 0)

    with ClinicalTrialsCollector(config_path) as c:
        summary = c.collect()

    cfg = _load_cfg(config_path)
    with _db_conn(cfg) as conn:
        current_count = conn.execute("SELECT COUNT(*) FROM clinical_trials").fetchone()[0]
        new_trials = _fetch_recent_trials(conn, prev_count)

    total_new = sum(s["new"] for s in summary.values())
    logger.info("[job] ClinicalTrials 수집 완료 — 신규 %d건", total_new)

    if total_new > 0:
        notifier.notify_new_findings(
            pubmed_new=0,
            ct_new=total_new,
            pubmed_details=[],
            ct_details=new_trials,
        )

    state["ct_trial_count"] = current_count
    state["last_ct_run"] = datetime.now().isoformat()
    return {"new": total_new, "total": current_count}


def job_collect_news(config_path: str, state: dict, notifier) -> dict:
    """Collect news articles from RSS feeds."""
    logger.info("[job] 뉴스 수집 시작")
    from collectors import NewsCollector

    with NewsCollector(config_path) as c:
        summary = c.collect()

    total_new = sum(s["new"] for s in summary.values())
    logger.info("[job] 뉴스 수집 완료 — 신규 %d건", total_new)
    state["last_news_run"] = datetime.now().isoformat()
    return {"new": total_new}


def job_run_analysis(config_path: str, state: dict) -> Optional[Path]:
    """Run full analysis pipeline and return HTML report path."""
    logger.info("[job] 분석 파이프라인 시작")
    from analysis import AnalysisPipeline

    pipeline = AnalysisPipeline(config_path)
    pipeline.run(export_json=True, export_html=True)

    # Find the most recent HTML report
    cfg = _load_cfg(config_path)
    export_dir = Path(cfg.get("export", {}).get("output_dir", "exports/"))
    htmls = sorted(export_dir.glob("report_*.html"), key=lambda p: p.stat().st_mtime)
    report_path = htmls[-1] if htmls else None

    state["last_analysis_run"] = datetime.now().isoformat()
    logger.info("[job] 분석 완료 — %s", report_path)
    return report_path


def job_monthly_report(config_path: str, state: dict, notifier):
    """Generate and email the monthly report."""
    logger.info("[job] 월간 리포트 생성 시작")
    report_path = job_run_analysis(config_path, state)
    notifier.notify_monthly_report(report_html=report_path)
    state["last_monthly_report"] = datetime.now().isoformat()
    logger.info("[job] 월간 리포트 완료")
    return str(report_path) if report_path else None


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _fetch_recent_articles(conn: sqlite3.Connection, prev_rowcount: int) -> list[dict]:
    """Fetch articles added after prev_rowcount (approximate via ROWID)."""
    import json as _json
    rows = conn.execute(
        "SELECT pmid, title, journal, pub_date, authors, doi FROM pubmed_articles ORDER BY rowid DESC LIMIT 20"
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["authors"] = _json.loads(d["authors"] or "[]")
        result.append(d)
    return result


def _fetch_recent_trials(conn: sqlite3.Connection, prev_rowcount: int) -> list[dict]:
    import json as _json
    rows = conn.execute(
        "SELECT nct_id, brief_title, overall_status, phases, lead_sponsor FROM clinical_trials ORDER BY rowid DESC LIMIT 10"
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["phases"] = _json.loads(d["phases"] or "[]")
        result.append(d)
    return result
