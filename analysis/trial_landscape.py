"""Clinical trial landscape analysis over ClinicalTrials.gov data."""

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Optional

import yaml


_STATUS_LABELS = {
    "RECRUITING": "모집 중",
    "NOT_YET_RECRUITING": "모집 예정",
    "ACTIVE_NOT_RECRUITING": "진행 중 (모집 완료)",
    "COMPLETED": "완료",
    "TERMINATED": "조기 종료",
    "WITHDRAWN": "철회",
    "SUSPENDED": "중단",
    "UNKNOWN": "미확인",
}


class TrialLandscape:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        db_path = Path(cfg["database"]["path"])
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row

    def _all_trials(self) -> list[sqlite3.Row]:
        return self._conn.execute("SELECT * FROM clinical_trials").fetchall()

    # ------------------------------------------------------------------
    # Status & Phase
    # ------------------------------------------------------------------

    def status_breakdown(self) -> dict[str, int]:
        rows = self._conn.execute("""
            SELECT overall_status, COUNT(*) n
            FROM clinical_trials
            GROUP BY overall_status
            ORDER BY n DESC
        """).fetchall()
        return {r["overall_status"]: r["n"] for r in rows}

    def phase_distribution(self) -> dict[str, int]:
        counter: Counter = Counter()
        for trial in self._all_trials():
            phases = json.loads(trial["phases"] or "[]")
            label = "/".join(phases) if phases else "N/A"
            counter[label] += 1
        return dict(counter.most_common())

    def study_type_breakdown(self) -> dict[str, int]:
        rows = self._conn.execute("""
            SELECT study_type, COUNT(*) n
            FROM clinical_trials
            GROUP BY study_type ORDER BY n DESC
        """).fetchall()
        return {r["study_type"]: r["n"] for r in rows}

    # ------------------------------------------------------------------
    # Interventions
    # ------------------------------------------------------------------

    def top_interventions(self, n: int = 15) -> list[tuple[str, int]]:
        counter: Counter = Counter()
        for trial in self._all_trials():
            for iv in json.loads(trial["interventions"] or "[]"):
                name = iv.get("name", "").strip()
                if name:
                    counter[name] += 1
        return counter.most_common(n)

    def intervention_type_breakdown(self) -> dict[str, int]:
        counter: Counter = Counter()
        for trial in self._all_trials():
            for iv in json.loads(trial["interventions"] or "[]"):
                t = iv.get("type", "UNKNOWN").strip()
                counter[t] += 1
        return dict(counter.most_common())

    def drug_trials(self) -> list[dict]:
        """Trials with DRUG or BIOLOGICAL interventions."""
        results = []
        for trial in self._all_trials():
            ivs = json.loads(trial["interventions"] or "[]")
            drug_ivs = [iv for iv in ivs if iv.get("type") in ("DRUG", "BIOLOGICAL")]
            if drug_ivs:
                results.append({
                    "nct_id": trial["nct_id"],
                    "brief_title": trial["brief_title"],
                    "overall_status": trial["overall_status"],
                    "phases": json.loads(trial["phases"] or "[]"),
                    "drugs": [iv["name"] for iv in drug_ivs],
                    "lead_sponsor": trial["lead_sponsor"],
                    "start_date": trial["start_date"],
                    "enrollment": trial["enrollment"],
                })
        return sorted(results, key=lambda x: x["start_date"] or "", reverse=True)

    # ------------------------------------------------------------------
    # Sponsors & geography
    # ------------------------------------------------------------------

    def sponsor_breakdown(self) -> dict[str, int]:
        rows = self._conn.execute("""
            SELECT sponsor_class, COUNT(*) n
            FROM clinical_trials
            GROUP BY sponsor_class ORDER BY n DESC
        """).fetchall()
        return {r["sponsor_class"]: r["n"] for r in rows}

    def top_sponsors(self, n: int = 10) -> list[tuple[str, int]]:
        rows = self._conn.execute("""
            SELECT lead_sponsor, COUNT(*) n
            FROM clinical_trials
            GROUP BY lead_sponsor ORDER BY n DESC
            LIMIT ?
        """, (n,)).fetchall()
        return [(r["lead_sponsor"], r["n"]) for r in rows]

    def geographic_distribution(self) -> dict[str, int]:
        counter: Counter = Counter()
        for trial in self._all_trials():
            locs = json.loads(trial["locations"] or "[]")
            countries = {loc["country"] for loc in locs if loc.get("country")}
            for c in countries:
                counter[c] += 1
        return dict(counter.most_common())

    # ------------------------------------------------------------------
    # Timeline & pipeline
    # ------------------------------------------------------------------

    def timeline(self) -> list[dict]:
        rows = self._conn.execute("""
            SELECT nct_id, brief_title, overall_status, phases,
                   start_date, primary_completion_date, completion_date,
                   lead_sponsor, enrollment
            FROM clinical_trials
            WHERE start_date IS NOT NULL
            ORDER BY start_date
        """).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["phases"] = json.loads(d["phases"] or "[]")
            results.append(d)
        return results

    def pipeline_by_year(self) -> dict[str, int]:
        """New trials started per year."""
        rows = self._conn.execute("""
            SELECT substr(start_date, 1, 4) AS year, COUNT(*) n
            FROM clinical_trials
            WHERE start_date IS NOT NULL
            GROUP BY year ORDER BY year
        """).fetchall()
        return {r["year"]: r["n"] for r in rows}

    def active_pipeline(self) -> list[dict]:
        """Trials that are recruiting or active."""
        active_statuses = ("RECRUITING", "NOT_YET_RECRUITING", "ACTIVE_NOT_RECRUITING")
        results = []
        for trial in self._all_trials():
            if trial["overall_status"] not in active_statuses:
                continue
            results.append({
                "nct_id": trial["nct_id"],
                "brief_title": trial["brief_title"],
                "overall_status": trial["overall_status"],
                "status_kr": _STATUS_LABELS.get(trial["overall_status"], ""),
                "phases": json.loads(trial["phases"] or "[]"),
                "lead_sponsor": trial["lead_sponsor"],
                "sponsor_class": trial["sponsor_class"],
                "interventions": [
                    iv["name"] for iv in json.loads(trial["interventions"] or "[]")
                ],
                "enrollment": trial["enrollment"],
                "start_date": trial["start_date"],
                "primary_completion_date": trial["primary_completion_date"],
                "locations": json.loads(trial["locations"] or "[]"),
            })
        return sorted(results, key=lambda x: x["start_date"] or "")

    def enrollment_stats(self) -> dict:
        rows = self._conn.execute("""
            SELECT enrollment FROM clinical_trials WHERE enrollment IS NOT NULL
        """).fetchall()
        sizes = [r["enrollment"] for r in rows]
        if not sizes:
            return {}
        return {
            "count": len(sizes),
            "total_enrolled": sum(sizes),
            "mean": round(sum(sizes) / len(sizes), 1),
            "min": min(sizes),
            "max": max(sizes),
        }

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        return {
            "total_trials": self._conn.execute("SELECT COUNT(*) FROM clinical_trials").fetchone()[0],
            "status_breakdown": self.status_breakdown(),
            "phase_distribution": self.phase_distribution(),
            "sponsor_breakdown": self.sponsor_breakdown(),
            "top_interventions": self.top_interventions(10),
            "geographic_distribution": self.geographic_distribution(),
            "enrollment_stats": self.enrollment_stats(),
            "active_pipeline": self.active_pipeline(),
            "pipeline_by_year": self.pipeline_by_year(),
        }

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
