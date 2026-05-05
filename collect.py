"""CLI entry point: PubMed and ClinicalTrials.gov collectors."""

import argparse
import logging
import sys
from pathlib import Path

import yaml


def setup_logging(config_path: str):
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    log_cfg = cfg["logging"]
    Path(log_cfg["file"]).parent.mkdir(parents=True, exist_ok=True)

    from logging.handlers import RotatingFileHandler
    handlers = [
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler(
            log_cfg["file"],
            maxBytes=log_cfg["max_size_mb"] * 1024 * 1024,
            backupCount=log_cfg["backup_count"],
        ),
    ]
    logging.basicConfig(
        level=getattr(logging, log_cfg["level"]),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        handlers=handlers,
    )


def main():
    parser = argparse.ArgumentParser(description="GNE 모니터링 — 데이터 수집기")
    parser.add_argument("--config", default="config.yaml", help="설정 파일 경로")
    sub = parser.add_subparsers(dest="source", required=True)

    # ── PubMed ──────────────────────────────────────────────────────────
    pm = sub.add_parser("pubmed", help="PubMed 논문 수집")
    pm_sub = pm.add_subparsers(dest="cmd", required=True)

    pm_collect = pm_sub.add_parser("collect", help="PubMed에서 논문 수집")
    pm_collect.add_argument("--query", help="특정 쿼리 레이블만 실행")

    pm_sub.add_parser("stats", help="PubMed DB 현황")

    pm_search = pm_sub.add_parser("search", help="로컬 PubMed DB 검색")
    pm_search.add_argument("keyword")
    pm_search.add_argument("--limit", type=int, default=10)

    # ── ClinicalTrials ───────────────────────────────────────────────────
    ct = sub.add_parser("ct", help="ClinicalTrials.gov 임상시험 수집")
    ct_sub = ct.add_subparsers(dest="cmd", required=True)

    ct_collect = ct_sub.add_parser("collect", help="ClinicalTrials.gov 수집")
    ct_collect.add_argument("--query", help="특정 쿼리 레이블만 실행")

    ct_sub.add_parser("stats", help="ClinicalTrials DB 현황")

    ct_search = ct_sub.add_parser("search", help="로컬 ClinicalTrials DB 검색")
    ct_search.add_argument("keyword")
    ct_search.add_argument("--limit", type=int, default=10)

    ct_sub.add_parser("recruiting", help="현재 모집 중인 임상시험 목록")

    # ── News ────────────────────────────────────────────────────────────
    nw = sub.add_parser("news", help="뉴스 RSS 수집")
    nw_sub = nw.add_subparsers(dest="cmd", required=True)

    nw_collect = nw_sub.add_parser("collect", help="뉴스 RSS 수집")
    nw_collect.add_argument("--feed", help="특정 피드 레이블만 실행")

    nw_sub.add_parser("stats", help="뉴스 DB 현황")

    nw_search = nw_sub.add_parser("search", help="로컬 뉴스 DB 검색")
    nw_search.add_argument("keyword")
    nw_search.add_argument("--limit", type=int, default=10)

    nw_recent = nw_sub.add_parser("recent", help="최근 뉴스 목록")
    nw_recent.add_argument("--days", type=int, default=30)
    nw_recent.add_argument("--lang", choices=["en", "ko"], help="언어 필터")
    nw_recent.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()
    setup_logging(args.config)

    if args.source == "pubmed":
        _run_pubmed(args)
    elif args.source == "ct":
        _run_ct(args)
    elif args.source == "news":
        _run_news(args)


# ── PubMed handlers ──────────────────────────────────────────────────────

def _run_pubmed(args):
    from collectors import PubMedCollector

    with PubMedCollector(args.config) as c:
        if args.cmd == "collect":
            summary = c.collect(query_label=args.query)
            print("\n=== PubMed 수집 완료 ===")
            for label, info in summary.items():
                print(f"  {label}: 신규 {info['new']}건 / 총 발견 {info['total_found']}건")

        elif args.cmd == "stats":
            stats = c.stats()
            total = stats.pop("_total")
            print(f"\n=== PubMed DB 현황 (총 {total}건) ===")
            for label, info in stats.items():
                print(f"\n[{label}]")
                for k, v in info.items():
                    print(f"  {k}: {v}")

        elif args.cmd == "search":
            results = c.search_local(args.keyword, args.limit)
            print(f"\n=== PubMed '{args.keyword}' 검색 결과 ({len(results)}건) ===\n")
            for r in results:
                authors = ", ".join(r["authors"][:3])
                if len(r["authors"]) > 3:
                    authors += " et al."
                print(f"PMID {r['pmid']}  [{r['pub_date']}]  {r['journal']}")
                print(f"  {r['title']}")
                print(f"  {authors}")
                if r["doi"]:
                    print(f"  DOI: {r['doi']}")
                print()


# ── ClinicalTrials handlers ──────────────────────────────────────────────

def _run_ct(args):
    from collectors import ClinicalTrialsCollector

    with ClinicalTrialsCollector(args.config) as c:
        if args.cmd == "collect":
            summary = c.collect(query_label=args.query)
            print("\n=== ClinicalTrials 수집 완료 ===")
            for label, info in summary.items():
                print(f"  {label}: 신규 {info['new']}건 / 총 발견 {info['total_found']}건")

        elif args.cmd == "stats":
            stats = c.stats()
            total = stats.pop("_total")
            print(f"\n=== ClinicalTrials DB 현황 (총 {total}건) ===")
            for label, info in stats.items():
                print(f"\n[{label}]")
                for k, v in info.items():
                    print(f"  {k}: {v}")

        elif args.cmd == "search":
            results = c.search_local(args.keyword, args.limit)
            print(f"\n=== CT '{args.keyword}' 검색 결과 ({len(results)}건) ===\n")
            for r in results:
                phases = "/".join(r["phases"]) if r["phases"] else "N/A"
                drugs = ", ".join(iv["name"] for iv in r["interventions"][:3])
                print(f"{r['nct_id']}  [{r['overall_status']}]  Phase {phases}")
                print(f"  {r['brief_title']}")
                print(f"  Sponsor: {r['lead_sponsor']}")
                if drugs:
                    print(f"  Interventions: {drugs}")
                print(f"  Start: {r['start_date']}  /  Completion: {r['completion_date']}")
                print()

        elif args.cmd == "recruiting":
            results = c.recruiting()
            print(f"\n=== 현재 모집 중인 임상시험 ({len(results)}건) ===\n")
            for r in results:
                phases = "/".join(r["phases"]) if r["phases"] else "N/A"
                countries = list({loc["country"] for loc in r["locations"] if loc["country"]})
                drugs = ", ".join(iv["name"] for iv in r["interventions"][:3])
                print(f"{r['nct_id']}  Phase {phases}  |  {r['lead_sponsor']}")
                print(f"  {r['brief_title']}")
                if drugs:
                    print(f"  Interventions: {drugs}")
                print(f"  Start: {r['start_date']}  →  {r['primary_completion_date']}")
                print(f"  Countries: {', '.join(countries) or 'N/A'}")
                print()


# ── News handlers ───────────────────────────────────────────────────────

def _run_news(args):
    from collectors import NewsCollector

    with NewsCollector(args.config) as c:
        if args.cmd == "collect":
            summary = c.collect(query_label=args.feed)
            print("\n=== 뉴스 수집 완료 ===")
            for label, info in summary.items():
                print(f"  {label}: 신규 {info['new']}건 / 피드 내 {info['total_found']}건")

        elif args.cmd == "stats":
            stats = c.stats()
            total = stats.pop("_total")
            print(f"\n=== 뉴스 DB 현황 (총 {total}건) ===")
            for label, info in stats.items():
                print(f"\n[{label}]")
                for k, v in info.items():
                    print(f"  {k}: {v}")

        elif args.cmd == "search":
            results = c.search_local(args.keyword, args.limit)
            print(f"\n=== 뉴스 '{args.keyword}' 검색 결과 ({len(results)}건) ===\n")
            for r in results:
                print(f"[{r['pub_date'][:10] if r['pub_date'] else '?'}] {r['source']}  ({r['language']})")
                print(f"  {r['title']}")
                if r['summary']:
                    print(f"  {r['summary'][:100]}")
                print(f"  {r['url'][:80]}")
                print()

        elif args.cmd == "recent":
            results = c.recent(days=args.days, language=args.lang, limit=args.limit)
            lang_str = f" ({args.lang})" if args.lang else ""
            print(f"\n=== 최근 {args.days}일 뉴스{lang_str} ({len(results)}건) ===\n")
            for r in results:
                date = r['pub_date'][:10] if r['pub_date'] else '?'
                lang_badge = "🇰🇷" if r['language'] == 'ko' else "🇺🇸"
                print(f"{lang_badge} [{date}] {r['source']}")
                print(f"  {r['title']}")
                print(f"  {r['url'][:80]}")
                print()


if __name__ == "__main__":
    main()
