"""Main analysis pipeline: combines PubMed trends and ClinicalTrials landscape."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import yaml

from .publication_trend import PublicationTrend
from .trial_landscape import TrialLandscape


def _bar(value: int, max_value: int, width: int = 30) -> str:
    filled = round(value / max_value * width) if max_value else 0
    return "█" * filled + "░" * (width - filled)


def _table(rows: list[tuple], col_widths: list[int], headers: list[str]) -> str:
    sep = "  "
    lines = []
    header = sep.join(str(h).ljust(w) for h, w in zip(headers, col_widths))
    lines.append(header)
    lines.append("-" * (sum(col_widths) + len(sep) * (len(col_widths) - 1)))
    for row in rows:
        lines.append(sep.join(str(v).ljust(w) for v, w in zip(row, col_widths)))
    return "\n".join(lines)


class AnalysisPipeline:
    def __init__(self, config_path: str = "config.yaml"):
        self._config_path = config_path
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        self._export_dir = Path(cfg.get("export", {}).get("output_dir", "exports/"))
        self._export_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Cross-source analysis
    # ------------------------------------------------------------------

    def research_velocity(self) -> dict:
        """Publications per 5-year period with acceleration marker."""
        with PublicationTrend(self._config_path) as pt:
            yearly = pt.yearly_counts()

        periods = {}
        for year, n in yearly.items():
            decade = f"{year[:3]}0s"
            periods[decade] = periods.get(decade, 0) + n

        five_yr: dict[str, int] = {}
        for year, n in yearly.items():
            yr = int(year)
            start = (yr // 5) * 5
            key = f"{start}-{start+4}"
            five_yr[key] = five_yr.get(key, 0) + n

        return {
            "by_decade": periods,
            "by_5yr_period": dict(sorted(five_yr.items())),
        }

    def evidence_to_trial_gap(self) -> list[dict]:
        """For each trial, count publications in the 5 years before its start."""
        with PublicationTrend(self._config_path) as pt:
            yearly = pt.yearly_counts()
        with TrialLandscape(self._config_path) as tl:
            timeline = tl.timeline()

        result = []
        for trial in timeline:
            if not trial["start_date"]:
                continue
            start_year = int(trial["start_date"][:4])
            pubs_5yr_before = sum(
                n for y, n in yearly.items()
                if start_year - 5 <= int(y) < start_year
            )
            result.append({
                "nct_id": trial["nct_id"],
                "brief_title": trial["brief_title"],
                "start_year": start_year,
                "pubs_5yr_before_trial": pubs_5yr_before,
            })
        return result

    def treatment_landscape(self) -> dict:
        """Combine drug mentions in PubMed titles and CT interventions."""
        KEY_DRUGS = [
            "sialic acid", "ManNAc", "N-acetylmannosamine",
            "gene therapy", "AAV", "substrate reduction",
            "aceneuramic acid", "Ace-ER",
        ]

        with PublicationTrend(self._config_path) as pt:
            drug_pubs = {drug: sum(pt.keyword_trend(drug).values()) for drug in KEY_DRUGS}

        with TrialLandscape(self._config_path) as tl:
            drug_trials = tl.drug_trials()
            top_ivs = dict(tl.top_interventions(15))

        return {
            "keyword_mentions_in_pubmed": drug_pubs,
            "trial_interventions_ranked": top_ivs,
            "drug_trials": drug_trials,
        }

    def _news_summary(self) -> dict:
        try:
            from collectors import NewsCollector
            with NewsCollector(self._config_path) as nc:
                stats = nc.stats()
                total = stats.pop("_total", 0)
                recent = nc.recent(days=30, limit=20)
                top_sources = nc.top_sources(10)
            return {"total": total, "stats": stats, "recent": recent, "top_sources": top_sources}
        except Exception:
            return {"total": 0, "stats": {}, "recent": [], "top_sources": []}

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    def run(self, export_json: bool = True, export_html: bool = True) -> dict:
        print("\n" + "=" * 65)
        print("  GNE 근병증 연구 현황 분석 리포트")
        print(f"  생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 65)

        with PublicationTrend(self._config_path) as pt:
            pub_summary = pt.summary()
            recent_papers = pt.recent_papers(years_back=2, limit=10)
            mesh_terms = pt.top_mesh_terms(20)
            yearly = pt.yearly_counts()
            title_words = pt.title_word_frequency(20)
            pub_types = pt.publication_type_breakdown()

        with TrialLandscape(self._config_path) as tl:
            ct_summary = tl.summary()

        news_summary = self._news_summary()
        velocity = self.research_velocity()
        treatment = self.treatment_landscape()

        # ── 1. 출판 트렌드 ─────────────────────────────────────────────
        print("\n\n── 1. 출판 트렌드 ─────────────────────────────────────────")
        print(f"  총 논문 수      : {pub_summary['total_articles']}건")
        print(f"  연도 범위       : {pub_summary['year_range'][0]} ~ {pub_summary['year_range'][1]}")
        print(f"  최근 5년 (2020~): {pub_summary['recent_5y_count']}건")

        print("\n  [연도별 출판 추이 — 최근 15년]")
        recent_yearly = {y: n for y, n in yearly.items() if y >= "2010"}
        max_n = max(recent_yearly.values()) if recent_yearly else 1
        for year in sorted(recent_yearly):
            n = recent_yearly[year]
            print(f"  {year}  {_bar(n, max_n, 25)} {n:>3}")

        print("\n  [5년 주기 연구 증가]")
        five_yr = velocity["by_5yr_period"]
        max_v = max(five_yr.values()) if five_yr else 1
        for period, n in sorted(five_yr.items()):
            print(f"  {period}  {_bar(n, max_v, 25)} {n:>3}")

        # ── 2. 주요 저널 & 저자 ───────────────────────────────────────
        print("\n\n── 2. 주요 저널 & 저자 ────────────────────────────────────")
        print("\n  [Top 10 저널]")
        print(_table(
            [(j, n) for j, n in pub_summary["top_journals"][:10]],
            [48, 6], ["저널명", "논문수"]
        ))
        print("\n  [Top 10 저자]")
        print(_table(
            pub_summary["top_authors"][:10],
            [30, 6], ["저자명", "논문수"]
        ))

        # ── 3. 연구 토픽 ──────────────────────────────────────────────
        print("\n\n── 3. 연구 토픽 ────────────────────────────────────────────")
        print("\n  [Top 15 MeSH 용어]")
        max_m = mesh_terms[0][1] if mesh_terms else 1
        for term, n in mesh_terms[:15]:
            print(f"  {term:<40} {_bar(n, max_m, 20)} {n}")

        print("\n  [제목 핵심 단어 Top 20]")
        max_w = title_words[0][1] if title_words else 1
        for word, n in title_words[:20]:
            print(f"  {word:<25} {_bar(n, max_w, 20)} {n}")

        # ── 4. 증거 수준 ──────────────────────────────────────────────
        print("\n\n── 4. 증거 수준 분포 ───────────────────────────────────────")
        ev_map = {
            "Randomized Controlled Trial": "RCT",
            "Clinical Trial": "임상시험",
            "Systematic Review": "체계적 고찰",
            "Meta-Analysis": "메타분석",
            "Case Reports": "증례 보고",
            "Observational Study": "관찰 연구",
        }
        for pt_name, kr in ev_map.items():
            n = pub_types.get(pt_name, 0)
            if n:
                print(f"  {kr:<15} ({pt_name:<30}) : {n}건")

        # ── 5. 임상시험 현황 ──────────────────────────────────────────
        print("\n\n── 5. 임상시험 현황 ────────────────────────────────────────")
        print(f"  총 임상시험     : {ct_summary['total_trials']}건")

        print("\n  [Status 분포]")
        STATUS_KR = {
            "COMPLETED": "완료", "RECRUITING": "모집 중",
            "ACTIVE_NOT_RECRUITING": "진행 중(모집 완료)",
            "NOT_YET_RECRUITING": "모집 예정",
            "TERMINATED": "조기 종료", "WITHDRAWN": "철회",
            "UNKNOWN": "미확인",
        }
        for status, n in ct_summary["status_breakdown"].items():
            kr = STATUS_KR.get(status, status)
            print(f"  {kr:<20} : {n}건")

        print("\n  [Phase 분포]")
        for phase, n in ct_summary["phase_distribution"].items():
            print(f"  {phase:<20} : {n}건")

        enr = ct_summary["enrollment_stats"]
        if enr:
            print(f"\n  [등록 규모]")
            print(f"  총 등록 대상    : {enr['total_enrolled']}명")
            print(f"  시험당 평균     : {enr['mean']}명  (최소 {enr['min']} / 최대 {enr['max']})")

        print("\n  [Sponsor 유형]")
        SPONSOR_KR = {"NIH": "NIH", "INDUSTRY": "산업체", "OTHER_GOV": "정부기관",
                      "NETWORK": "연구네트워크", "OTHER": "기타"}
        for cls, n in ct_summary["sponsor_breakdown"].items():
            print(f"  {SPONSOR_KR.get(cls, cls):<20} : {n}건")

        print("\n  [지리적 분포]")
        for country, n in ct_summary["geographic_distribution"].items():
            print(f"  {country:<25} : {n}건")

        # ── 6. 활성 파이프라인 ────────────────────────────────────────
        active = ct_summary["active_pipeline"]
        print(f"\n\n── 6. 활성 파이프라인 ({len(active)}건) ─────────────────────────")
        for t in active:
            phases = "/".join(t["phases"]) if t["phases"] else "N/A"
            drugs = ", ".join(t["interventions"][:3])
            print(f"\n  {t['nct_id']}  [{t['status_kr']}]  Phase {phases}")
            print(f"  제목: {t['brief_title'][:70]}")
            print(f"  Sponsor: {t['lead_sponsor']}")
            if drugs:
                print(f"  중재: {drugs}")
            print(f"  기간: {t['start_date']} ~ {t['primary_completion_date']}")
            countries = list({loc["country"] for loc in t["locations"] if loc.get("country")})
            if countries:
                print(f"  국가: {', '.join(countries)}")

        # ── 7. 치료 연구 현황 ────────────────────────────────────────
        print("\n\n── 7. 치료 접근법 연구 현황 ────────────────────────────────")
        print("\n  [PubMed 키워드 언급 빈도]")
        for drug, n in sorted(treatment["keyword_mentions_in_pubmed"].items(), key=lambda x: -x[1]):
            if n > 0:
                print(f"  {drug:<30} : {n}건")

        print("\n  [임상시험 중재 Top 10]")
        for iv, n in list(treatment["trial_interventions_ranked"].items())[:10]:
            print(f"  {iv:<30} : {n}건")

        # ── 8. 최근 뉴스 ─────────────────────────────────────────────
        recent_news = news_summary.get("recent", [])
        news_total = news_summary.get("total", 0)
        print(f"\n\n── 8. 최근 30일 뉴스 ({len(recent_news)}건 / DB {news_total}건) ────────────")
        if recent_news:
            for n in recent_news[:10]:
                date = n['pub_date'][:10] if n.get('pub_date') else '?'
                lang = "🇰🇷" if n.get('language') == 'ko' else "🇺🇸"
                print(f"\n  {lang} [{date}] {n.get('source', '')}")
                print(f"  {n.get('title', '')[:72]}")
                print(f"  {n.get('url', '')[:72]}")
        else:
            print("  (수집된 뉴스 없음 — python3 collect.py news collect 실행 필요)")

        # ── 9. 최근 논문 ─────────────────────────────────────────────
        print(f"\n\n── 9. 최근 2년 주요 논문 ({len(recent_papers)}건) ──────────────────")
        for p in recent_papers[:10]:
            authors = ", ".join(p["authors"][:2])
            if len(p["authors"]) > 2:
                authors += " et al."
            print(f"\n  [{p['pub_date']}] {p['journal']}")
            print(f"  {p['title'][:72]}")
            print(f"  {authors}")
            if p["doi"]:
                print(f"  https://doi.org/{p['doi']}")

        print("\n" + "=" * 65 + "\n")

        # ── Full report dict ──────────────────────────────────────────
        report = {
            "generated_at": datetime.now().isoformat(),
            "publication_summary": {
                **pub_summary,
                "top_journals": pub_summary["top_journals"],
                "top_authors": pub_summary["top_authors"],
                "top_mesh": [{"term": t, "count": n} for t, n in mesh_terms],
                "title_words": [{"word": w, "count": n} for w, n in title_words],
            },
            "trial_summary": ct_summary,
            "velocity": velocity,
            "treatment_landscape": {
                "keyword_mentions": treatment["keyword_mentions_in_pubmed"],
                "top_interventions": treatment["trial_interventions_ranked"],
                "drug_trials": treatment["drug_trials"],
            },
            "recent_papers": recent_papers,
            "news_summary": news_summary,
        }

        # Make lists JSON-serializable
        report["publication_summary"]["top_journals"] = [
            {"journal": j, "count": n} for j, n in pub_summary["top_journals"]
        ]
        report["publication_summary"]["top_authors"] = [
            {"author": a, "count": n} for a, n in pub_summary["top_authors"]
        ]
        report["trial_summary"]["top_interventions"] = [
            {"intervention": iv, "count": n}
            for iv, n in ct_summary["top_interventions"]
        ]

        if export_json:
            path = self._export_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)
            print(f"  JSON 리포트 저장: {path}")

        if export_html:
            path = self._export_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.html"
            _write_html(report, path)
            print(f"  HTML 리포트 저장: {path}")

        return report


# ------------------------------------------------------------------
# HTML report
# ------------------------------------------------------------------

def _write_html(report: dict, path: Path):
    yearly = report["publication_summary"]["yearly_counts"]
    year_labels = sorted(yearly.keys())
    year_values = [yearly[y] for y in year_labels]

    mesh_data = report["publication_summary"]["top_mesh"][:15]
    mesh_labels = [d["term"] for d in mesh_data]
    mesh_values = [d["count"] for d in mesh_data]

    status_data = report["trial_summary"]["status_breakdown"]
    iv_data = report["trial_summary"]["top_interventions"][:10]

    active = report["trial_summary"]["active_pipeline"]
    news_recent = report.get("news_summary", {}).get("recent", [])
    news_total = report.get("news_summary", {}).get("total", 0)
    recent = report["recent_papers"][:8]

    STATUS_KR = {
        "COMPLETED": "완료", "RECRUITING": "모집 중",
        "ACTIVE_NOT_RECRUITING": "진행 중(모집 완료)",
        "NOT_YET_RECRUITING": "모집 예정",
        "TERMINATED": "조기 종료", "UNKNOWN": "미확인",
    }

    def badge(status):
        colors = {
            "RECRUITING": "#22c55e", "NOT_YET_RECRUITING": "#3b82f6",
            "ACTIVE_NOT_RECRUITING": "#f59e0b", "COMPLETED": "#6b7280",
            "TERMINATED": "#ef4444", "UNKNOWN": "#9ca3af",
        }
        color = colors.get(status, "#9ca3af")
        label = STATUS_KR.get(status, status)
        return f'<span style="background:{color};color:#fff;padding:2px 8px;border-radius:9999px;font-size:12px">{label}</span>'

    active_rows = ""
    for t in active:
        phases = "/".join(t["phases"]) if t["phases"] else "N/A"
        drugs = ", ".join(t["interventions"][:3]) or "-"
        countries = ", ".join({loc["country"] for loc in t["locations"] if loc.get("country")}) or "-"
        active_rows += f"""
        <tr>
          <td><a href="https://clinicaltrials.gov/study/{t['nct_id']}" target="_blank">{t['nct_id']}</a></td>
          <td>{t['brief_title'][:60]}</td>
          <td>{badge(t['overall_status'])}</td>
          <td>Phase {phases}</td>
          <td>{t['lead_sponsor'][:25]}</td>
          <td>{drugs}</td>
          <td>{t['start_date']}</td>
          <td>{t['primary_completion_date'] or '-'}</td>
          <td>{countries}</td>
        </tr>"""

    news_rows = ""
    for n in news_recent[:15]:
        date = n['pub_date'][:10] if n.get('pub_date') else '?'
        lang_badge = "🇰🇷" if n.get('language') == 'ko' else "🇺🇸"
        news_rows += f"""
        <tr>
          <td>{date}</td>
          <td>{lang_badge} {n.get('source','')}</td>
          <td><a href="{n.get('url','')}" target="_blank">{n.get('title','')[:75]}</a></td>
        </tr>"""

    paper_rows = ""
    for p in recent:
        authors = ", ".join(p["authors"][:2])
        if len(p["authors"]) > 2:
            authors += " et al."
        doi_link = f'<a href="https://doi.org/{p["doi"]}" target="_blank">DOI</a>' if p.get("doi") else ""
        paper_rows += f"""
        <tr>
          <td>{p['pub_date']}</td>
          <td>{p['journal']}</td>
          <td>{p['title'][:75]}</td>
          <td>{authors}</td>
          <td>{doi_link}</td>
        </tr>"""

    total_pubs = report["publication_summary"]["total_articles"]
    recent_5y = report["publication_summary"]["recent_5y_count"]
    total_trials = report["trial_summary"]["total_trials"]
    enr = report["trial_summary"]["enrollment_stats"]
    total_enrolled = enr.get("total_enrolled", 0)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>GNE 근병증 연구 현황 리포트</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, sans-serif; background: #f8fafc; color: #1e293b; }}
    header {{ background: #1e40af; color: white; padding: 2rem; }}
    header h1 {{ font-size: 1.6rem; }}
    header p {{ opacity: .8; font-size: .9rem; margin-top: .3rem; }}
    .kpis {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 1rem; padding: 1.5rem 2rem; }}
    .kpi {{ background: white; border-radius: 12px; padding: 1.2rem; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
    .kpi .num {{ font-size: 2rem; font-weight: 700; color: #1e40af; }}
    .kpi .label {{ font-size: .85rem; color: #64748b; margin-top: .2rem; }}
    .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; padding: 0 2rem 1rem; }}
    .grid1 {{ padding: 0 2rem 1rem; }}
    .card {{ background: white; border-radius: 12px; padding: 1.2rem; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
    .card h2 {{ font-size: 1rem; font-weight: 600; margin-bottom: 1rem; color: #334155; border-bottom: 2px solid #e2e8f0; padding-bottom: .5rem; }}
    canvas {{ max-height: 280px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: .85rem; }}
    th {{ background: #f1f5f9; text-align: left; padding: .5rem .7rem; font-weight: 600; }}
    td {{ padding: .45rem .7rem; border-bottom: 1px solid #f1f5f9; vertical-align: top; }}
    tr:last-child td {{ border-bottom: none; }}
    a {{ color: #1e40af; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    footer {{ text-align: center; padding: 1.5rem; color: #94a3b8; font-size: .8rem; }}
    @media(max-width:768px) {{ .kpis,.grid2 {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
<header>
  <h1>GNE 근병증 연구 현황 분석 리포트</h1>
  <p>생성일시: {report['generated_at'][:16]}  |  데이터: PubMed + ClinicalTrials.gov</p>
</header>

<div class="kpis">
  <div class="kpi"><div class="num">{total_pubs}</div><div class="label">총 수집 논문</div></div>
  <div class="kpi"><div class="num">{recent_5y}</div><div class="label">최근 5년 논문 (2020~)</div></div>
  <div class="kpi"><div class="num">{total_trials}</div><div class="label">임상시험 총계</div></div>
  <div class="kpi"><div class="num">{news_total}</div><div class="label">수집 뉴스 총계</div></div>
</div>

<div class="grid2">
  <div class="card">
    <h2>연도별 출판 추이</h2>
    <canvas id="yearChart"></canvas>
  </div>
  <div class="card">
    <h2>Top 15 MeSH 용어</h2>
    <canvas id="meshChart"></canvas>
  </div>
</div>

<div class="grid2">
  <div class="card">
    <h2>임상시험 Status 분포</h2>
    <canvas id="statusChart"></canvas>
  </div>
  <div class="card">
    <h2>Top 10 임상 중재</h2>
    <canvas id="ivChart"></canvas>
  </div>
</div>

<div class="grid1">
  <div class="card">
    <h2>최근 30일 뉴스 (총 {news_total}건)</h2>
    <table>
      <thead><tr><th>날짜</th><th>출처</th><th>제목</th></tr></thead>
      <tbody>{news_rows or "<tr><td colspan='3' style='text-align:center;color:#94a3b8'>수집된 뉴스 없음</td></tr>"}</tbody>
    </table>
  </div>
</div>

<div class="grid1">
  <div class="card">
    <h2>활성 임상시험 파이프라인</h2>
    <table>
      <thead><tr>
        <th>NCT ID</th><th>제목</th><th>Status</th><th>Phase</th>
        <th>Sponsor</th><th>중재</th><th>시작일</th><th>종료예정</th><th>국가</th>
      </tr></thead>
      <tbody>{active_rows or "<tr><td colspan='9' style='text-align:center;color:#94a3b8'>활성 시험 없음</td></tr>"}</tbody>
    </table>
  </div>
</div>

<div class="grid1">
  <div class="card">
    <h2>최근 2년 주요 논문</h2>
    <table>
      <thead><tr><th>날짜</th><th>저널</th><th>제목</th><th>저자</th><th>링크</th></tr></thead>
      <tbody>{paper_rows}</tbody>
    </table>
  </div>
</div>

<footer>GNE 근병증 모니터링 시스템 | 데이터 출처: PubMed (NCBI), ClinicalTrials.gov</footer>

<script>
const yearLabels = {json.dumps(year_labels)};
const yearValues = {json.dumps(year_values)};
const meshLabels = {json.dumps(mesh_labels)};
const meshValues = {json.dumps(mesh_values)};
const statusLabels = {json.dumps(list(status_data.keys()))};
const statusValues = {json.dumps(list(status_data.values()))};
const ivLabels = {json.dumps([d['intervention'] for d in iv_data])};
const ivValues = {json.dumps([d['count'] for d in iv_data])};

new Chart(document.getElementById('yearChart'), {{
  type: 'bar',
  data: {{ labels: yearLabels, datasets: [{{
    label: '논문 수', data: yearValues,
    backgroundColor: '#3b82f6', borderRadius: 3,
  }}]}},
  options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ beginAtZero: true }} }} }}
}});

new Chart(document.getElementById('meshChart'), {{
  type: 'bar',
  data: {{ labels: meshLabels, datasets: [{{
    label: '빈도', data: meshValues,
    backgroundColor: '#8b5cf6', borderRadius: 3,
  }}]}},
  options: {{
    indexAxis: 'y',
    plugins: {{ legend: {{ display: false }} }},
    scales: {{ x: {{ beginAtZero: true }} }}
  }}
}});

const STATUS_COLORS = {{
  COMPLETED: '#6b7280', RECRUITING: '#22c55e',
  ACTIVE_NOT_RECRUITING: '#f59e0b', NOT_YET_RECRUITING: '#3b82f6',
  TERMINATED: '#ef4444', UNKNOWN: '#9ca3af',
}};
new Chart(document.getElementById('statusChart'), {{
  type: 'doughnut',
  data: {{ labels: statusLabels, datasets: [{{
    data: statusValues,
    backgroundColor: statusLabels.map(s => STATUS_COLORS[s] || '#94a3b8'),
  }}]}},
  options: {{ plugins: {{ legend: {{ position: 'right' }} }} }}
}});

new Chart(document.getElementById('ivChart'), {{
  type: 'bar',
  data: {{ labels: ivLabels, datasets: [{{
    label: '건수', data: ivValues,
    backgroundColor: '#f59e0b', borderRadius: 3,
  }}]}},
  options: {{
    indexAxis: 'y',
    plugins: {{ legend: {{ display: false }} }},
    scales: {{ x: {{ beginAtZero: true }} }}
  }}
}});
</script>
</body>
</html>"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
