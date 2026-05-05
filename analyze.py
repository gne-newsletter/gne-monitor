"""CLI entry point for the analysis pipeline."""

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
    logging.basicConfig(
        level=getattr(logging, log_cfg["level"]),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            RotatingFileHandler(
                log_cfg["file"],
                maxBytes=log_cfg["max_size_mb"] * 1024 * 1024,
                backupCount=log_cfg["backup_count"],
            ),
        ],
    )


def main():
    parser = argparse.ArgumentParser(description="GNE 모니터링 — 분석 파이프라인")
    parser.add_argument("--config", default="config.yaml")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # report: 전체 리포트
    p_report = sub.add_parser("report", help="전체 분석 리포트 생성 (콘솔 + JSON + HTML)")
    p_report.add_argument("--no-json", action="store_true", help="JSON 저장 생략")
    p_report.add_argument("--no-html", action="store_true", help="HTML 저장 생략")

    # pub: PubMed 분석만
    p_pub = sub.add_parser("pub", help="PubMed 출판 트렌드 분석")
    p_pub.add_argument("--keyword-trend", metavar="KEYWORD", help="특정 키워드 연도별 트렌드")
    p_pub.add_argument("--top", type=int, default=15, help="상위 N개 출력")

    # ct: ClinicalTrials 분석만
    p_ct = sub.add_parser("ct", help="임상시험 현황 분석")
    p_ct.add_argument("--pipeline", action="store_true", help="활성 파이프라인만 출력")

    # treatment: 치료 연구 현황
    sub.add_parser("treatment", help="치료 접근법 연구 현황")

    args = parser.parse_args()
    setup_logging(args.config)

    from analysis import AnalysisPipeline, PublicationTrend, TrialLandscape

    if args.cmd == "report":
        pipeline = AnalysisPipeline(args.config)
        pipeline.run(
            export_json=not args.no_json,
            export_html=not args.no_html,
        )

    elif args.cmd == "pub":
        with PublicationTrend(args.config) as pt:
            if args.keyword_trend:
                trend = pt.keyword_trend(args.keyword_trend)
                print(f"\n=== '{args.keyword_trend}' 연도별 트렌드 ===")
                max_n = max(trend.values()) if trend else 1
                for year in sorted(trend):
                    n = trend[year]
                    bar = "█" * round(n / max_n * 25)
                    print(f"  {year}  {bar:<25} {n}")
            else:
                s = pt.summary()
                print(f"\n총 논문: {s['total_articles']}건  ({s['year_range'][0]}~{s['year_range'][1]})")
                print(f"최근 5년: {s['recent_5y_count']}건\n")
                print("Top 저널:")
                for j, n in s["top_journals"][:args.top]:
                    print(f"  {j:<45} {n}")
                print("\nTop MeSH:")
                for t, n in s["top_mesh"][:args.top]:
                    print(f"  {t:<40} {n}")

    elif args.cmd == "ct":
        with TrialLandscape(args.config) as tl:
            if args.pipeline:
                active = tl.active_pipeline()
                print(f"\n=== 활성 파이프라인 ({len(active)}건) ===\n")
                for t in active:
                    phases = "/".join(t["phases"]) if t["phases"] else "N/A"
                    drugs = ", ".join(t["interventions"][:3])
                    print(f"{t['nct_id']}  [{t['status_kr']}]  Phase {phases}")
                    print(f"  {t['brief_title']}")
                    print(f"  Sponsor : {t['lead_sponsor']}")
                    if drugs:
                        print(f"  중재    : {drugs}")
                    print(f"  기간    : {t['start_date']} ~ {t['primary_completion_date']}\n")
            else:
                s = tl.summary()
                print(f"\n총 임상시험: {s['total_trials']}건")
                print("\nStatus:", s["status_breakdown"])
                print("Phase:", s["phase_distribution"])
                print("Sponsor:", s["sponsor_breakdown"])
                print("\nTop 중재:")
                for iv, n in s["top_interventions"][:10]:
                    print(f"  {iv:<30} {n}")
                print("\n지리 분포:")
                for c, n in s["geographic_distribution"].items():
                    print(f"  {c:<25} {n}")

    elif args.cmd == "treatment":
        pipeline = AnalysisPipeline(args.config)
        t = pipeline.treatment_landscape()
        print("\n=== 치료 접근법 연구 현황 ===\n")
        print("[PubMed 키워드 언급]")
        for drug, n in sorted(t["keyword_mentions_in_pubmed"].items(), key=lambda x: -x[1]):
            if n:
                print(f"  {drug:<32} {n}건")
        print("\n[임상시험 중재 (상위 10)]")
        for iv, n in list(t["trial_interventions_ranked"].items())[:10]:
            print(f"  {iv:<32} {n}건")
        print(f"\n[약물 임상시험 목록] ({len(t['drug_trials'])}건)")
        for trial in t["drug_trials"]:
            phases = "/".join(trial["phases"]) if trial["phases"] else "N/A"
            drugs = ", ".join(trial["drugs"])
            print(f"  {trial['nct_id']}  [{trial['overall_status']}]  Phase {phases}")
            print(f"    {trial['brief_title'][:65]}")
            print(f"    {drugs}  |  {trial['lead_sponsor']}")
            print()


if __name__ == "__main__":
    main()
