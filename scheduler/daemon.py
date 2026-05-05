"""Scheduler daemon: registers and runs all jobs via the schedule library."""

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import schedule
import yaml

from .jobs import job_collect_pubmed, job_collect_ct, job_collect_news, job_run_analysis, job_monthly_report
from .notifier import Notifier

logger = logging.getLogger(__name__)

_SHUTDOWN = False


def _handle_signal(signum, _frame):
    global _SHUTDOWN
    logger.info("Signal %s received — shutting down", signum)
    _SHUTDOWN = True


# ------------------------------------------------------------------
# State persistence
# ------------------------------------------------------------------

def _load_state(state_file: Path) -> dict:
    if state_file.exists():
        try:
            with open(state_file) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_state(state: dict, state_file: Path):
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ------------------------------------------------------------------
# PID management
# ------------------------------------------------------------------

def _write_pid(pid_file: Path):
    pid_file.write_text(str(os.getpid()))
    logger.info("PID %d → %s", os.getpid(), pid_file)


def _remove_pid(pid_file: Path):
    pid_file.unlink(missing_ok=True)


def _read_pid(pid_file: Path) -> Optional[int]:
    if pid_file.exists():
        try:
            return int(pid_file.read_text().strip())
        except ValueError:
            pass
    return None


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


# ------------------------------------------------------------------
# Job wrappers with error handling
# ------------------------------------------------------------------

def _safe_run(name: str, fn, notifier, *args, **kwargs):
    logger.info("── 잡 시작: %s ──", name)
    start = time.monotonic()
    try:
        result = fn(*args, **kwargs)
        elapsed = time.monotonic() - start
        logger.info("── 잡 완료: %s (%.1fs) ──", name, elapsed)
        return result
    except Exception as e:
        logger.exception("── 잡 실패: %s — %s ──", name, e)
        notifier.notify_job_failure(name, str(e))
        return None


# ------------------------------------------------------------------
# Schedule registration
# ------------------------------------------------------------------

_DAY_MAP = {
    "monday": schedule.every().monday,
    "tuesday": schedule.every().tuesday,
    "wednesday": schedule.every().wednesday,
    "thursday": schedule.every().thursday,
    "friday": schedule.every().friday,
    "saturday": schedule.every().saturday,
    "sunday": schedule.every().sunday,
}


def _register_jobs(cfg: dict, config_path: str, state: dict, notifier: Notifier):
    jobs_cfg = cfg["scheduler"]["jobs"]

    def make_pubmed():
        return lambda: _safe_run(
            "pubmed_collect", job_collect_pubmed, notifier,
            config_path, state, notifier,
        )

    def make_ct():
        return lambda: _safe_run(
            "ct_collect", job_collect_ct, notifier,
            config_path, state, notifier,
        )

    def make_news():
        return lambda: _safe_run(
            "news_collect", job_collect_news, notifier,
            config_path, state, notifier,
        )

    def make_analysis():
        return lambda: _safe_run(
            "analysis", job_run_analysis, notifier,
            config_path, state,
        )

    def make_monthly():
        return lambda: _safe_run(
            "monthly_report", job_monthly_report, notifier,
            config_path, state, notifier,
        )

    # PubMed collect
    jc = jobs_cfg.get("pubmed_collect", {})
    if jc.get("enabled", True):
        day = jc.get("day", "monday")
        t = jc.get("time", "02:00")
        _DAY_MAP[day].at(t).do(make_pubmed())
        logger.info("등록: pubmed_collect — 매주 %s %s", day, t)

    # News collect
    jc = jobs_cfg.get("news_collect", {})
    if jc.get("enabled", True):
        t = jc.get("time", "06:00")
        schedule.every().day.at(t).do(make_news())
        logger.info("등록: news_collect — 매일 %s", t)

    # ClinicalTrials collect
    jc = jobs_cfg.get("ct_collect", {})
    if jc.get("enabled", True):
        day = jc.get("day", "monday")
        t = jc.get("time", "02:30")
        _DAY_MAP[day].at(t).do(make_ct())
        logger.info("등록: ct_collect — 매주 %s %s", day, t)

    # Analysis
    jc = jobs_cfg.get("analysis", {})
    if jc.get("enabled", True):
        day = jc.get("day", "monday")
        t = jc.get("time", "03:00")
        _DAY_MAP[day].at(t).do(make_analysis())
        logger.info("등록: analysis — 매주 %s %s", day, t)

    # Monthly report — runs on day=1 of each month, checked every day
    jc = jobs_cfg.get("monthly_report", {})
    if jc.get("enabled", True):
        t = jc.get("time", "08:00")

        def _monthly_guard():
            if date.today().day == 1:
                last = state.get("last_monthly_report", "")
                if not last or last[:7] != date.today().strftime("%Y-%m"):
                    _safe_run("monthly_report", job_monthly_report, notifier,
                              config_path, state, notifier)

        schedule.every().day.at(t).do(_monthly_guard)
        logger.info("등록: monthly_report — 매월 1일 %s", t)


# ------------------------------------------------------------------
# Main loop
# ------------------------------------------------------------------

def run_daemon(config_path: str = "config.yaml", smtp_password: Optional[str] = None):
    global _SHUTDOWN

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    sched_cfg = cfg["scheduler"]
    pid_file = Path(sched_cfg["pid_file"])
    state_file = Path(sched_cfg["state_file"])

    # Guard: already running?
    existing_pid = _read_pid(pid_file)
    if existing_pid and _is_running(existing_pid):
        print(f"스케줄러가 이미 실행 중입니다 (PID {existing_pid})", file=sys.stderr)
        sys.exit(1)

    _write_pid(pid_file)
    state = _load_state(state_file)

    notifier = Notifier(config_path)
    if smtp_password:
        notifier.set_password(smtp_password)

    _register_jobs(cfg, config_path, state, notifier)

    logger.info("스케줄러 시작 — PID %d", os.getpid())
    logger.info("등록된 잡 수: %d", len(schedule.jobs))
    for job in schedule.jobs:
        logger.info("  다음 실행: %s", job.next_run)

    try:
        while not _SHUTDOWN:
            schedule.run_pending()
            _save_state(state, state_file)
            time.sleep(30)
    finally:
        _save_state(state, state_file)
        _remove_pid(pid_file)
        logger.info("스케줄러 종료")


# ------------------------------------------------------------------
# Status & control helpers
# ------------------------------------------------------------------

def status(config_path: str = "config.yaml") -> dict:
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    sched_cfg = cfg["scheduler"]
    pid_file = Path(sched_cfg["pid_file"])
    state_file = Path(sched_cfg["state_file"])

    pid = _read_pid(pid_file)
    running = pid is not None and _is_running(pid)
    state = _load_state(state_file)

    return {
        "running": running,
        "pid": pid if running else None,
        "state": state,
        "jobs": [
            {"job": str(j.job_func.__name__), "next_run": str(j.next_run), "last_run": str(j.last_run)}
            for j in schedule.jobs
        ],
    }


def stop_daemon(config_path: str = "config.yaml"):
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    pid_file = Path(cfg["scheduler"]["pid_file"])
    pid = _read_pid(pid_file)
    if pid and _is_running(pid):
        os.kill(pid, signal.SIGTERM)
        print(f"종료 신호 전송 (PID {pid})")
    else:
        print("실행 중인 스케줄러가 없습니다")
