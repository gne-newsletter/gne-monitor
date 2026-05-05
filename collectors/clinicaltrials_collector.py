"""ClinicalTrials.gov collector for GNE myopathy studies via v2 API."""

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ClinicalTrial:
    nct_id: str
    brief_title: str
    official_title: str
    overall_status: str
    phases: list[str]
    study_type: str
    conditions: list[str]
    interventions: list[dict]   # [{"type": ..., "name": ...}]
    lead_sponsor: str
    sponsor_class: str
    brief_summary: str
    eligibility_criteria: str
    enrollment: Optional[int]
    start_date: Optional[str]
    primary_completion_date: Optional[str]
    completion_date: Optional[str]
    last_update_date: Optional[str]
    primary_outcomes: list[str]
    locations: list[dict]       # [{"country": ..., "facility": ...}]
    fetched_at: datetime = field(default_factory=datetime.now)


class ClinicalTrialsCollector:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path) as f:
            cfg = yaml.safe_load(f)

        self._cfg = cfg["clinicaltrials"]
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
            CREATE TABLE IF NOT EXISTS clinical_trials (
                nct_id                  TEXT PRIMARY KEY,
                brief_title             TEXT,
                official_title          TEXT,
                overall_status          TEXT,
                phases                  TEXT,   -- JSON array
                study_type              TEXT,
                conditions              TEXT,   -- JSON array
                interventions           TEXT,   -- JSON array of {type, name}
                lead_sponsor            TEXT,
                sponsor_class           TEXT,
                brief_summary           TEXT,
                eligibility_criteria    TEXT,
                enrollment              INTEGER,
                start_date              TEXT,
                primary_completion_date TEXT,
                completion_date         TEXT,
                last_update_date        TEXT,
                primary_outcomes        TEXT,   -- JSON array
                locations               TEXT,   -- JSON array of {country, facility}
                query_label             TEXT,
                fetched_at              TEXT
            );

            CREATE TABLE IF NOT EXISTS clinicaltrials_runs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                query_label  TEXT,
                ran_at       TEXT,
                new_trials   INTEGER,
                total_found  INTEGER
            );
        """)
        conn.commit()
        return conn

    def _known_nct_ids(self) -> set[str]:
        rows = self._conn.execute("SELECT nct_id FROM clinical_trials").fetchall()
        return {r["nct_id"] for r in rows}

    def _save_trials(self, trials: list[ClinicalTrial], query_label: str) -> int:
        new_count = 0
        for t in trials:
            try:
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO clinical_trials VALUES
                      (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        t.nct_id,
                        t.brief_title,
                        t.official_title,
                        t.overall_status,
                        json.dumps(t.phases, ensure_ascii=False),
                        t.study_type,
                        json.dumps(t.conditions, ensure_ascii=False),
                        json.dumps(t.interventions, ensure_ascii=False),
                        t.lead_sponsor,
                        t.sponsor_class,
                        t.brief_summary,
                        t.eligibility_criteria,
                        t.enrollment,
                        t.start_date,
                        t.primary_completion_date,
                        t.completion_date,
                        t.last_update_date,
                        json.dumps(t.primary_outcomes, ensure_ascii=False),
                        json.dumps(t.locations, ensure_ascii=False),
                        query_label,
                        t.fetched_at.isoformat(),
                    ),
                )
                if self._conn.execute("SELECT changes()").fetchone()[0]:
                    new_count += 1
            except sqlite3.Error as e:
                logger.warning("DB insert failed for %s: %s", t.nct_id, e)

        self._conn.commit()
        return new_count

    def _log_run(self, query_label: str, new_trials: int, total_found: int):
        self._conn.execute(
            "INSERT INTO clinicaltrials_runs (query_label, ran_at, new_trials, total_found) VALUES (?,?,?,?)",
            (query_label, datetime.now().isoformat(), new_trials, total_found),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def _get(self, params: dict) -> dict:
        base_url = self._cfg["base_url"]
        retries = self._cfg["fetch"]["retries"]
        retry_delay = self._cfg["fetch"]["retry_delay"]
        url = f"{base_url}?{urlencode(params)}"

        for attempt in range(1, retries + 1):
            try:
                with urlopen(url, timeout=30) as resp:
                    return json.loads(resp.read())
            except HTTPError as e:
                logger.warning("HTTP %s on attempt %d/%d", e.code, attempt, retries)
                if attempt < retries:
                    time.sleep(retry_delay * attempt)
            except URLError as e:
                logger.warning("URLError on attempt %d/%d: %s", attempt, retries, e)
                if attempt < retries:
                    time.sleep(retry_delay * attempt)

        raise RuntimeError(f"Failed to fetch ClinicalTrials.gov after {retries} attempts")

    def _fetch_query(self, query: dict) -> list[ClinicalTrial]:
        page_size = self._cfg["fetch"]["page_size"]
        max_results = query.get("max_results", 500)
        label = query["label"]

        params: dict = {
            "format": "json",
            "pageSize": min(page_size, max_results),
            "countTotal": "true",
        }
        if "cond" in query:
            params["query.cond"] = query["cond"]
        if "term" in query:
            params["query.term"] = query["term"]

        trials: list[ClinicalTrial] = []
        total_found = 0
        page = 0

        while True:
            page += 1
            data = self._get(params)
            time.sleep(self._delay)

            if page == 1:
                total_found = data.get("totalCount", 0)
                logger.info("[%s] Total found: %d", label, total_found)

            studies = data.get("studies", [])
            for study in studies:
                try:
                    trials.append(self._parse_study(study))
                except Exception as e:
                    nct = study.get("protocolSection", {}).get(
                        "identificationModule", {}
                    ).get("nctId", "?")
                    logger.warning("Parse error for %s: %s", nct, e)

            next_token = data.get("nextPageToken")
            if not next_token or len(trials) >= max_results:
                break

            params["pageToken"] = next_token
            params.pop("countTotal", None)  # only needed on first page

        return trials[:max_results], total_found

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_study(self, study: dict) -> ClinicalTrial:
        proto = study["protocolSection"]

        id_mod = proto.get("identificationModule", {})
        status_mod = proto.get("statusModule", {})
        design_mod = proto.get("designModule", {})
        desc_mod = proto.get("descriptionModule", {})
        cond_mod = proto.get("conditionsModule", {})
        arms_mod = proto.get("armsInterventionsModule", {})
        sponsor_mod = proto.get("sponsorCollaboratorsModule", {})
        outcomes_mod = proto.get("outcomesModule", {})
        elig_mod = proto.get("eligibilityModule", {})
        loc_mod = proto.get("contactsLocationsModule", {})

        nct_id = id_mod.get("nctId", "")
        brief_title = id_mod.get("briefTitle", "")
        official_title = id_mod.get("officialTitle", "")

        overall_status = status_mod.get("overallStatus", "")
        start_date = status_mod.get("startDateStruct", {}).get("date")
        primary_completion_date = status_mod.get("primaryCompletionDateStruct", {}).get("date")
        completion_date = status_mod.get("completionDateStruct", {}).get("date")
        last_update_date = status_mod.get("lastUpdateSubmitDate")

        phases = design_mod.get("phases", [])
        study_type = design_mod.get("studyType", "")
        enrollment = design_mod.get("enrollmentInfo", {}).get("count")

        conditions = cond_mod.get("conditions", [])

        interventions = [
            {"type": iv.get("type", ""), "name": iv.get("name", "")}
            for iv in arms_mod.get("interventions", [])
        ]

        lead_sponsor = sponsor_mod.get("leadSponsor", {}).get("name", "")
        sponsor_class = sponsor_mod.get("leadSponsor", {}).get("class", "")

        brief_summary = desc_mod.get("briefSummary", "").strip()
        eligibility_criteria = elig_mod.get("eligibilityCriteria", "").strip()

        primary_outcomes = [
            o.get("measure", "")
            for o in outcomes_mod.get("primaryOutcomes", [])
            if o.get("measure")
        ]

        locations = [
            {
                "country": loc.get("country", ""),
                "facility": loc.get("facility", ""),
                "city": loc.get("city", ""),
                "status": loc.get("status", ""),
            }
            for loc in loc_mod.get("locations", [])
        ]

        return ClinicalTrial(
            nct_id=nct_id,
            brief_title=brief_title,
            official_title=official_title,
            overall_status=overall_status,
            phases=phases,
            study_type=study_type,
            conditions=conditions,
            interventions=interventions,
            lead_sponsor=lead_sponsor,
            sponsor_class=sponsor_class,
            brief_summary=brief_summary,
            eligibility_criteria=eligibility_criteria,
            enrollment=enrollment,
            start_date=start_date,
            primary_completion_date=primary_completion_date,
            completion_date=completion_date,
            last_update_date=last_update_date,
            primary_outcomes=primary_outcomes,
            locations=locations,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def collect(self, query_label: Optional[str] = None) -> dict:
        queries = self._cfg["queries"]
        if query_label:
            queries = [q for q in queries if q["label"] == query_label]
            if not queries:
                raise ValueError(f"Unknown query label: {query_label}")

        incremental = self._cfg["storage"]["incremental"]
        known = self._known_nct_ids() if incremental else set()
        summary = {}

        for query in queries:
            label = query["label"]
            logger.info("[%s] Starting ClinicalTrials.gov collection", label)

            trials, total_found = self._fetch_query(query)

            if incremental:
                new_trials = [t for t in trials if t.nct_id not in known]
                logger.info("[%s] %d new (incremental)", label, len(new_trials))
            else:
                new_trials = trials

            new_count = self._save_trials(new_trials, label)
            known.update(t.nct_id for t in trials)

            self._log_run(label, new_count, total_found)
            summary[label] = {
                "total_found": total_found,
                "fetched": len(trials),
                "new": new_count,
            }
            logger.info("[%s] Done — %d new trials saved", label, new_count)

        return summary

    def stats(self) -> dict:
        rows = self._conn.execute("""
            SELECT
                query_label,
                COUNT(*)                                        AS count,
                SUM(overall_status = 'RECRUITING')             AS recruiting,
                SUM(overall_status = 'COMPLETED')              AS completed,
                SUM(overall_status = 'ACTIVE_NOT_RECRUITING')  AS active,
                MAX(fetched_at)                                AS last_fetched
            FROM clinical_trials
            GROUP BY query_label
        """).fetchall()

        runs = self._conn.execute("""
            SELECT query_label, MAX(ran_at) AS last_run, SUM(new_trials) AS total_new
            FROM clinicaltrials_runs
            GROUP BY query_label
        """).fetchall()

        run_map = {r["query_label"]: dict(r) for r in runs}
        result = {}
        for row in rows:
            label = row["query_label"]
            result[label] = {
                "trial_count": row["count"],
                "recruiting": row["recruiting"],
                "completed": row["completed"],
                "active_not_recruiting": row["active"],
                "last_fetched": row["last_fetched"],
                "last_run": run_map.get(label, {}).get("last_run"),
            }

        total = self._conn.execute("SELECT COUNT(*) FROM clinical_trials").fetchone()[0]
        result["_total"] = total
        return result

    def search_local(self, keyword: str, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT nct_id, brief_title, overall_status, phases,
                   lead_sponsor, start_date, completion_date, interventions
            FROM clinical_trials
            WHERE brief_title        LIKE ?
               OR brief_summary      LIKE ?
               OR conditions         LIKE ?
               OR interventions      LIKE ?
               OR eligibility_criteria LIKE ?
            ORDER BY start_date DESC
            LIMIT ?
            """,
            (*(f"%{keyword}%",) * 5, limit),
        ).fetchall()

        results = []
        for r in rows:
            d = dict(r)
            d["phases"] = json.loads(d["phases"] or "[]")
            d["interventions"] = json.loads(d["interventions"] or "[]")
            results.append(d)
        return results

    def recruiting(self) -> list[dict]:
        """Return all currently recruiting trials."""
        rows = self._conn.execute(
            """
            SELECT nct_id, brief_title, phases, lead_sponsor,
                   start_date, primary_completion_date, locations, interventions
            FROM clinical_trials
            WHERE overall_status = 'RECRUITING'
            ORDER BY start_date DESC
            """
        ).fetchall()

        results = []
        for r in rows:
            d = dict(r)
            d["phases"] = json.loads(d["phases"] or "[]")
            d["locations"] = json.loads(d["locations"] or "[]")
            d["interventions"] = json.loads(d["interventions"] or "[]")
            results.append(d)
        return results

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
