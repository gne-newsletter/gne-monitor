"""CLI for the GNE monitor scheduler daemon."""

import argparse
import getpass
import json
import logging
import sys
from pathlib import Path

import yaml


def setup_logging(config_path: str, foreground: bool = False):
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    log_cfg = cfg["logging"]
    Path(log_cfg["file"]).parent.mkdir(parents=True, exist_ok=True)

    from logging.handlers import RotatingFileHandler
    handlers = [
        RotatingFileHandler(
            log_cfg["file"],
            maxBytes=log_cfg["max_size_mb"] * 1024 * 1024,
            backupCount=log_cfg["backup_count"],
        )
    ]
    if foreground:
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=getattr(logging, log_cfg["level"]),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        handlers=handlers,
    )


def main():
    parser = argparse.ArgumentParser(description="GNE 모니터링 — 스케줄러")
    parser.add_argument("--config", default="config.yaml")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # start
    p_start = sub.add_parser("start", help="스케줄러 데몬 시작")
    p_start.add_argument(
        "--foreground", "-f", action="store_true",
        help="포그라운드 실행 (로그를 터미널에 출력)"
    )
    p_start.add_argument(
        "--smtp-password", metavar="PW",
        help="Gmail 앱 비밀번호 (생략 시 인터랙티브 입력)"
    )
    p_start.add_argument(
        "--no-email", action="store_true",
        help="이메일 알림 비활성화"
    )

    # stop
    sub.add_parser("stop", help="스케줄러 데몬 중지")

    # status
    sub.add_parser("status", help="스케줄러 상태 확인")

    # run-now: 즉시 잡 실행 (테스트용)
    p_run = sub.add_parser("run-now", help="특정 잡을 즉시 실행")
    p_run.add_argument(
        "job",
        choices=["pubmed", "ct", "news", "analysis", "monthly"],
        help="실행할 잡",
    )
    p_run.add_argument("--smtp-password", metavar="PW")
    p_run.add_argument("--no-email", action="store_true", help="이메일 알림 비활성화")

    # next: 다음 실행 시간 목록
    sub.add_parser("next", help="등록된 잡의 다음 실행 시간 출력")

    args = parser.parse_args()

    if args.cmd == "start":
        setup_logging(args.config, foreground=args.foreground)
        pw = None
        if not args.no_email:
            pw = args.smtp_password or _ask_password()
        _cmd_start(args.config, pw)

    elif args.cmd == "stop":
        from scheduler import stop_daemon
        stop_daemon(args.config)

    elif args.cmd == "status":
        _cmd_status(args.config)

    elif args.cmd == "run-now":
        setup_logging(args.config, foreground=True)
        pw = None if args.no_email else (args.smtp_password or None)
        _cmd_run_now(args.config, args.job, pw)

    elif args.cmd == "next":
        _cmd_next(args.config)


# ------------------------------------------------------------------
# Command implementations
# ------------------------------------------------------------------

def _ask_password() -> str:
    print("Gmail 앱 비밀번호를 입력하세요 (이메일 알림 생략은 Enter):")
    try:
        return getpass.getpass("비밀번호: ")
    except (EOFError, KeyboardInterrupt):
        return ""


def _cmd_start(config_path: str, smtp_password: str):
    from scheduler import run_daemon
    print("스케줄러를 시작합니다...")
    run_daemon(config_path, smtp_password=smtp_password or None)


def _cmd_status(config_path: str):
    import os
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    pid_file = Path(cfg["scheduler"]["pid_file"])
    state_file = Path(cfg["scheduler"]["state_file"])

    pid = None
    running = False
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            running = True
        except (ValueError, OSError):
            pass

    state = {}
    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)

    print("\n=== 스케줄러 상태 ===")
    print(f"  실행 중 : {'예 (PID ' + str(pid) + ')' if running else '아니오'}")
    print(f"\n=== 최근 실행 기록 ===")
    print(f"  PubMed 수집    : {state.get('last_pubmed_run', '미실행')}")
    print(f"  ClinTrials 수집: {state.get('last_ct_run', '미실행')}")
    print(f"  뉴스 수집      : {state.get('last_news_run', '미실행')}")
    print(f"  분석           : {state.get('last_analysis_run', '미실행')}")
    print(f"  월간 리포트    : {state.get('last_monthly_report', '미실행')}")
    print(f"\n=== DB 현황 ===")
    print(f"  PubMed 논문    : {state.get('pubmed_article_count', '?')}건")
    print(f"  임상시험       : {state.get('ct_trial_count', '?')}건")

    print(f"\n=== 설정된 잡 ===")
    jobs_cfg = cfg["scheduler"]["jobs"]
    for name, jc in jobs_cfg.items():
        enabled = jc.get("enabled", True)
        every = jc.get("every", "week")
        day = jc.get("day", "")
        t = jc.get("time", "")
        schedule_str = f"매주 {day} {t}" if every == "week" else f"매월 1일 {t}"
        print(f"  {name:<22} {'활성' if enabled else '비활성'}  {schedule_str}")
    print()


def _cmd_run_now(config_path: str, job: str, smtp_password: str):
    from scheduler.notifier import Notifier
    from scheduler.jobs import (
        job_collect_pubmed, job_collect_ct,
        job_run_analysis, job_monthly_report,
    )
    import json, yaml
    from pathlib import Path

    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    state_file = Path(cfg["scheduler"]["state_file"])
    state = {}
    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)

    notifier = Notifier(config_path)
    if smtp_password:
        notifier.set_password(smtp_password)

    from scheduler.jobs import (
        job_collect_pubmed, job_collect_ct, job_collect_news,
        job_run_analysis, job_monthly_report,
    )
    fn_map = {
        "pubmed":   lambda: job_collect_pubmed(config_path, state, notifier),
        "ct":       lambda: job_collect_ct(config_path, state, notifier),
        "news":     lambda: job_collect_news(config_path, state, notifier),
        "analysis": lambda: job_run_analysis(config_path, state),
        "monthly":  lambda: job_monthly_report(config_path, state, notifier),
    }

    print(f"\n[즉시 실행] {job} ...")
    try:
        result = fn_map[job]()
        print(f"완료: {result}")
    except Exception as e:
        print(f"실패: {e}")
    finally:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)


def _cmd_next(config_path: str):
    """Load config and print scheduled times without running the daemon."""
    import schedule as sched
    from scheduler.daemon import _register_jobs, _load_state
    from scheduler.notifier import Notifier
    from pathlib import Path

    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    state_file = Path(cfg["scheduler"]["state_file"])
    state = _load_state(state_file)
    notifier = Notifier(config_path)

    _register_jobs(cfg, config_path, state, notifier)

    print("\n=== 등록된 잡 및 다음 실행 시간 ===")
    for job in sched.jobs:
        print(f"  다음 실행: {job.next_run}  ({job.interval} {job.unit})")


if __name__ == "__main__":
    main()
