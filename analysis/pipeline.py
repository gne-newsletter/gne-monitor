"""Main analysis pipeline: combines PubMed trends and ClinicalTrials landscape."""

import json
import sqlite3
from datetime import datetime, timedelta
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

    def _get_weekly_highlights(self) -> dict:
        """지난 7일간의 핵심 소식 추출"""
        cutoff = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        # 논문
        with PublicationTrend(self._config_path) as pt:
            recent_papers = pt.recent_papers(years_back=1, limit=100)
        
        weekly_papers = [p for p in recent_papers if p.get('pub_date', '') >= cutoff]
        
        # 뉴스
        try:
            from collectors import NewsCollector
            with NewsCollector(self._config_path) as nc:
                weekly_news = nc.recent(days=7, limit=20)
        except:
            weekly_news = []
        
        # 임상시험 (최근 업데이트)
        with TrialLandscape(self._config_path) as tl:
            all_trials = tl.active_pipeline()
        
        weekly_trials = [t for t in all_trials if t.get('last_update_posted', '') >= cutoff]
        
        return {
            "papers": weekly_papers,
            "news": weekly_news,
            "trials": weekly_trials,
            "date_range": f"{cutoff} ~ {datetime.now().strftime('%Y-%m-%d')}"
        }

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    def run(self, export_json: bool = True, export_html: bool = True) -> dict:
        print("\n" + "=" * 65)
        print("  GNE 근육병 연구 현황 분석 리포트")
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

        from .summarizer import ArticleSummarizer
        with ArticleSummarizer(self._config_path) as sm:
            ai_stats = sm.stats()
            top_relevant = sm.top_relevant(n=10, min_score=8.0)

        news_summary = self._news_summary()
        velocity = self.research_velocity()
        treatment = self.treatment_landscape()
        weekly_highlights = self._get_weekly_highlights()

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
                print(f"  {kr:<20} {n:>3}건")

        # ── 5. 임상시험 현황 ──────────────────────────────────────────
        print("\n\n── 5. 임상시험 현황 ────────────────────────────────────────")
        print(f"  총 등록 시험: {ct_summary['total_trials']}건")
        print("\n  [Status 분포]")
        for st, n in ct_summary["status_breakdown"].items():
            print(f"  {st:<30} {n}")
        print("\n  [Phase 분포]")
        for ph, n in ct_summary["phase_distribution"].items():
            print(f"  {ph:<20} {n}")

        print("\n  [Top 10 중재]")
        for iv, n in ct_summary["top_interventions"][:10]:
            print(f"  {iv:<35} {n}")

        # ── 6. 치료 접근법 ────────────────────────────────────────────
        print("\n\n── 6. 치료 접근법 연구 현황 ────────────────────────────────")
        print("\n  [PubMed 키워드 언급]")
        for drug, n in sorted(treatment["keyword_mentions_in_pubmed"].items(), key=lambda x: -x[1]):
            if n:
                print(f"  {drug:<32} {n:>3}건")

        print("\n  [약물 임상시험]")
        print(f"  총 {len(treatment['drug_trials'])}건 진행")

        # ── 7. AI 요약 현황 ───────────────────────────────────────────
        print("\n\n── 7. AI 요약 현황 ─────────────────────────────────────────")
        print(f"  전체 논문       : {ai_stats.get('total', 0)}건")
        print(f"  요약 완료       : {ai_stats.get('summarized', 0)}건")
        print(f"  평균 관련도     : {ai_stats.get('avg_relevance_score', 0):.1f}/10")
        print(f"  고관련도 (≥7점): {ai_stats.get('high_relevance_count', 0)}건")

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
            "ai_summary": {
                "stats": ai_stats,
                "top_relevant": top_relevant,
            },
            "weekly_highlights": weekly_highlights,
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
    _chartjs_path = Path(__file__).parent.parent / "data" / "chart.umd.min.js"
    _chartjs_inline = _chartjs_path.read_text(encoding="utf-8")

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
    ai_stats = report.get("ai_summary", {}).get("stats", {})
    top_relevant = report.get("ai_summary", {}).get("top_relevant", [])

    weekly = report.get("weekly_highlights", {})
    weekly_papers = weekly.get("papers", [])[:5]
    weekly_news = weekly.get("news", [])[:5]
    weekly_trials = weekly.get("trials", [])[:3]
    date_range = weekly.get("date_range", "")

    STATUS_KR = {
        "COMPLETED": "완료", "RECRUITING": "모집 중",
        "ACTIVE_NOT_RECRUITING": "진행 중(모집 완료)",
        "NOT_YET_RECRUITING": "모집 예정",
        "TERMINATED": "조기 종료", "UNKNOWN": "미확인",
    }
    STATUS_BADGE_CLASS = {
        "RECRUITING": "badge-success",
        "NOT_YET_RECRUITING": "badge-info",
        "ACTIVE_NOT_RECRUITING": "badge-warning",
        "COMPLETED": "badge-neutral",
        "TERMINATED": "badge-danger",
        "UNKNOWN": "badge-neutral",
    }

    def status_badge(status):
        label = STATUS_KR.get(status, status)
        cls = STATUS_BADGE_CLASS.get(status, "badge-neutral")
        return f'<span class="badge {cls}">{label}</span>'

    def score_badge_html(score):
        if score is None:
            return ""
        if score >= 10:
            cls = "badge-score-10"
        elif score >= 9:
            cls = "badge-score-9"
        else:
            cls = "badge-score-8"
        return f'<span class="badge {cls}">{int(score)}/10</span>'

    def patient_box(ps):
        if not ps:
            return ""
        return (
            f'<div class="patient-meaning">'
            f'<div class="patient-meaning-title">💡 환자에게 의미</div>'
            f'<div class="patient-meaning-content">{ps}</div>'
            f'</div>'
        )

    total_pubs = report["publication_summary"]["total_articles"]
    recent_5y = report["publication_summary"]["recent_5y_count"]
    total_trials = report["trial_summary"]["total_trials"]
    generated_at = report['generated_at'][:16]

    # ── ZONE 1 Hero: AI 최고 관련도 논문 ──────────────────────────────
    hero_paper = top_relevant[0] if top_relevant else None
    if hero_paper:
        sc = hero_paper.get("relevance_score") or 0
        stars = "⭐" * int(sc)
        hero_html = f"""
  <div class="hero-zone">
    <div class="hero-badge">🔥 이번 주 가장 중요한 소식</div>
    <div class="hero-title">{hero_paper.get('title', '')}</div>
    <div class="relevance-bar">
      <span class="star">{stars}</span>
      <span class="score">관련도: {int(sc)}/10</span>
    </div>
    <div class="hero-summary">{hero_paper.get('summary', '')}</div>
    {patient_box(hero_paper.get('patient_significance'))}
  </div>"""
    else:
        hero_html = f"""
  <div class="hero-zone">
    <div class="hero-badge">📊 이번 주 현황</div>
    <div class="hero-title">GNE 근육병 연구 현황 리포트</div>
    <div class="hero-summary">총 {total_pubs}건의 논문과 {total_trials}건의 임상시험이 수집되었습니다. AI 요약을 실행하면 핵심 논문이 여기에 표시됩니다.</div>
  </div>"""

    # ── ZONE 2 Quick Scan: 다음 2~3 고관련도 논문 ────────────────────
    quick_papers = top_relevant[1:3] if len(top_relevant) > 1 else weekly_papers[:2]
    quick_items_html = ""
    for p in quick_papers:
        sc = p.get("relevance_score")
        sc_label = f"{int(sc)}점" if sc else ""
        quick_items_html += f"""
      <div class="quick-item">
        {"<div class='quick-score'>" + sc_label + "</div>" if sc_label else ""}
        <div class="quick-title">{p.get('title','')[:80]}</div>
        <div class="quick-summary">{p.get('summary','')[:200]}{"..." if len(p.get('summary',''))>200 else ""}</div>
      </div>"""

    if not quick_items_html:
        quick_items_html = '<div class="quick-item"><div class="quick-summary" style="color:#94a3b8">AI 요약 데이터 없음 — python3 analyze.py summarize 실행 필요</div></div>'

    # ── 행동 가이드: 모집 중인 임상시험 ──────────────────────────────
    recruiting = [t for t in active if t.get("overall_status") in ("RECRUITING", "NOT_YET_RECRUITING")]
    action_items_html = ""
    for t in recruiting[:2]:
        phases = "/".join(t.get("phases", [])) or "N/A"
        action_items_html += f"""
    <div class="action-item">
      <div class="action-label">✅ {STATUS_KR.get(t['overall_status'], t['overall_status'])} 임상시험</div>
      <div class="action-content">
        <strong>{t['nct_id']}</strong> — {t['brief_title'][:70]}<br>
        Phase {phases} · {t['lead_sponsor'][:40]}
        {f"<br>시작일: {t['start_date']}" if t.get('start_date') else ""}
      </div>
      <a href="https://clinicaltrials.gov/study/{t['nct_id']}" target="_blank" class="action-button">자세히 보기 →</a>
    </div>"""

    if not action_items_html:
        action_items_html = '<div class="action-item"><div class="action-content">현재 모집 중인 임상시험이 없습니다.</div></div>'

    # ── Collapsible 1: 뉴스 ───────────────────────────────────────────
    news_rows = ""
    for n in news_recent[:15]:
        date = n['pub_date'][:10] if n.get('pub_date') else '?'
        lang_flag = "🇰🇷" if n.get('language') == 'ko' else "🇺🇸"
        news_rows += f"""
            <tr>
              <td data-label="날짜">{date}</td>
              <td data-label="출처">{lang_flag} {n.get('source','')}</td>
              <td data-label="제목"><a href="{n.get('url','')}" target="_blank">{n.get('title','')[:75]}</a></td>
            </tr>"""
    if not news_rows:
        news_rows = "<tr><td colspan='3' style='text-align:center;color:#94a3b8;padding:1.5rem'>수집된 뉴스 없음</td></tr>"

    # ── Collapsible 2: 전체 데이터 (차트 + 논문) ─────────────────────
    all_relevant_rows = ""
    for p in top_relevant:
        doi_link = f'<a href="https://doi.org/{p["doi"]}" target="_blank">DOI</a>' if p.get("doi") else ""
        all_relevant_rows += f"""
            <tr>
              <td data-label="날짜">{p.get('pub_date','')}</td>
              <td data-label="제목">{p.get('title','')[:80]}
                <div style="font-size:.8rem;color:#64748b;margin-top:.25rem;line-height:1.5">{p.get('summary','')[:150]}{"..." if len(p.get('summary',''))>150 else ""}</div>
                {patient_box(p.get('patient_significance'))}
              </td>
              <td data-label="저널">{p.get('journal','')[:30]}</td>
              <td data-label="관련도">{score_badge_html(p.get('relevance_score'))}</td>
              <td data-label="링크">{doi_link}</td>
            </tr>"""

    recent_paper_rows = ""
    for p in recent:
        authors = ", ".join(p["authors"][:2]) + (" et al." if len(p["authors"]) > 2 else "")
        doi_link = f'<a href="https://doi.org/{p["doi"]}" target="_blank">DOI</a>' if p.get("doi") else ""
        sc = p.get("relevance_score")
        sc_html = score_badge_html(sc) + " " if sc is not None else ""
        summary_html = f'<div style="font-size:.8rem;color:#64748b;margin-top:.25rem;line-height:1.5">{p["summary"]}</div>' if p.get("summary") else ""
        recent_paper_rows += f"""
            <tr>
              <td data-label="날짜">{p['pub_date']}</td>
              <td data-label="저널">{p['journal'][:30]}</td>
              <td data-label="제목">{sc_html}{p['title'][:80]}{summary_html}</td>
              <td data-label="저자">{authors}</td>
              <td data-label="링크">{doi_link}</td>
            </tr>"""

    # ── Collapsible 3: 임상시험 파이프라인 전체 ──────────────────────
    active_rows = ""
    for t in active:
        phases = "/".join(t["phases"]) if t["phases"] else "N/A"
        drugs = ", ".join(t["interventions"][:3]) or "-"
        countries = ", ".join({loc["country"] for loc in t["locations"] if loc.get("country")}) or "-"
        active_rows += f"""
            <tr>
              <td data-label="NCT ID"><a href="https://clinicaltrials.gov/study/{t['nct_id']}" target="_blank">{t['nct_id']}</a></td>
              <td data-label="제목">{t['brief_title'][:60]}</td>
              <td data-label="Status">{status_badge(t['overall_status'])}</td>
              <td data-label="Phase">Phase {phases}</td>
              <td data-label="Sponsor">{t['lead_sponsor'][:25]}</td>
              <td data-label="중재">{drugs}</td>
              <td data-label="시작일">{t['start_date']}</td>
              <td data-label="종료예정">{t['primary_completion_date'] or '-'}</td>
              <td data-label="국가">{countries}</td>
            </tr>"""
    if not active_rows:
        active_rows = "<tr><td colspan='9' style='text-align:center;color:#94a3b8;padding:1.5rem'>활성 시험 없음</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GNE 근육병 연구 현황 리포트</title>
  <script>{_chartjs_inline}</script>
  <style>
    *, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}

    :root {{
      --primary: #8b5cf6;
      --primary-dark: #7c3aed;
      --secondary: #10b981;
      --danger: #ef4444;
      --warning: #f59e0b;
      --info: #3b82f6;
      --bg-light: #f8fafc;
      --bg-card: #ffffff;
      --text-primary: #1e293b;
      --text-secondary: #64748b;
      --text-muted: #94a3b8;
      --border: #e2e8f0;
      --shadow: 0 1px 3px rgba(0,0,0,0.1);
      --shadow-lg: 0 10px 25px rgba(0,0,0,0.1);
    }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background: var(--bg-light);
      color: var(--text-primary);
      line-height: 1.6;
    }}

    a {{ color: var(--primary); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}

    /* ── Header ── */
    .header {{
      background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
      color: white; padding: 2rem 1rem; text-align: center;
      box-shadow: var(--shadow-lg);
    }}
    .header h1 {{ font-size: 1.8rem; font-weight: 700; margin-bottom: 0.5rem; }}
    .header .meta {{ font-size: 0.9rem; opacity: 0.9; }}
    .header .issue-badge {{
      display: inline-block;
      background: rgba(255,255,255,0.2);
      padding: 0.25rem 0.75rem;
      border-radius: 9999px;
      margin-top: 0.5rem;
      font-size: 0.85rem;
    }}

    /* ── Container ── */
    .container {{ max-width: 1200px; margin: 0 auto; padding: 1.5rem; }}

    /* ── Section ── */
    .section {{ margin-bottom: 2rem; }}
    .section-header {{
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 1rem; padding-bottom: 0.5rem;
      border-bottom: 2px solid var(--border);
    }}
    .section-title {{
      font-size: 1.3rem; font-weight: 600; color: var(--text-primary);
      display: flex; align-items: center; gap: 0.5rem;
    }}
    .section-badge {{
      font-size: 0.75rem; background: var(--bg-light);
      color: var(--text-muted); padding: 0.25rem 0.5rem; border-radius: 4px;
    }}

    /* ── Card ── */
    .card {{
      background: var(--bg-card); border-radius: 12px;
      padding: 1.5rem; box-shadow: var(--shadow); margin-bottom: 1rem;
    }}

    /* ── ZONE 1: Hero (30초) ── */
    .hero-zone {{
      background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
      border-radius: 16px; padding: 2rem; margin-bottom: 2rem;
      box-shadow: var(--shadow-lg);
    }}
    .hero-badge {{
      display: inline-block; background: var(--danger); color: white;
      padding: 0.5rem 1rem; border-radius: 9999px;
      font-weight: 600; font-size: 0.9rem; margin-bottom: 1rem;
    }}
    .hero-title {{
      font-size: 1.6rem; font-weight: 700; color: var(--text-primary);
      margin-bottom: 0.75rem; line-height: 1.3;
    }}
    .relevance-bar {{
      display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1rem;
    }}
    .star {{ color: #f59e0b; font-size: 1.2rem; }}
    .score {{ font-weight: 700; font-size: 1.1rem; color: var(--text-primary); }}
    .hero-summary {{
      font-size: 1rem; color: var(--text-secondary);
      margin-bottom: 1rem; line-height: 1.7;
    }}
    .patient-meaning {{
      background: #ecfdf5; border-left: 4px solid var(--secondary);
      padding: 1rem; border-radius: 0 8px 8px 0; margin-top: 1rem;
    }}
    .patient-meaning-title {{
      font-weight: 700; color: #065f46; margin-bottom: 0.5rem;
      display: flex; align-items: center; gap: 0.5rem;
    }}
    .patient-meaning-content {{ color: #065f46; font-size: 0.95rem; line-height: 1.6; }}

    /* ── KPI 카드 ── */
    .kpi-grid {{
      display: grid; grid-template-columns: repeat(4, 1fr);
      gap: 1rem; margin-bottom: 2rem;
    }}
    .kpi-card {{
      background: var(--bg-card); border-radius: 12px;
      padding: 1.25rem; box-shadow: var(--shadow);
      border-top: 3px solid var(--primary);
    }}
    .kpi-num {{ font-size: 2rem; font-weight: 800; color: var(--primary); }}
    .kpi-label {{ font-size: 0.82rem; color: var(--text-secondary); margin-top: 0.2rem; }}

    /* ── ZONE 2: Quick Scan (2분) ── */
    .quick-scan-grid {{
      display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 1rem; margin-bottom: 2rem;
    }}
    .quick-item {{
      background: var(--bg-card); border-radius: 12px;
      padding: 1.25rem; box-shadow: var(--shadow);
      transition: transform 0.2s, box-shadow 0.2s; cursor: default;
    }}
    .quick-item:hover {{ transform: translateY(-2px); box-shadow: var(--shadow-lg); }}
    .quick-score {{
      display: inline-block; background: var(--secondary); color: white;
      padding: 0.25rem 0.5rem; border-radius: 6px;
      font-size: 0.75rem; font-weight: 600; margin-bottom: 0.5rem;
    }}
    .quick-title {{ font-weight: 600; font-size: 1rem; margin-bottom: 0.5rem; color: var(--text-primary); }}
    .quick-summary {{ font-size: 0.85rem; color: var(--text-secondary); line-height: 1.5; }}

    /* ── 행동 가이드 ── */
    .action-guide {{
      background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
      border-radius: 12px; padding: 1.5rem; margin-bottom: 2rem;
    }}
    .action-title {{ font-size: 1.2rem; font-weight: 600; color: var(--text-primary); margin-bottom: 1rem; }}
    .action-item {{
      background: white; border-radius: 8px;
      padding: 1rem; margin-bottom: 0.75rem; box-shadow: var(--shadow);
    }}
    .action-item:last-child {{ margin-bottom: 0; }}
    .action-label {{
      font-weight: 600; color: var(--text-primary);
      margin-bottom: 0.5rem; display: flex; align-items: center; gap: 0.5rem;
    }}
    .action-content {{ color: var(--text-secondary); font-size: 0.9rem; line-height: 1.5; }}
    .action-button {{
      display: inline-block; background: var(--primary); color: white;
      padding: 0.5rem 1rem; border-radius: 6px;
      font-size: 0.85rem; font-weight: 600; margin-top: 0.5rem;
      cursor: pointer; border: none; transition: background 0.2s;
    }}
    .action-button:hover {{ background: var(--primary-dark); text-decoration: none; color: white; }}

    /* ── ZONE 3: Collapsible (10분) ── */
    .collapsible {{ margin-bottom: 1.5rem; }}
    .collapsible-header {{
      background: var(--bg-card); border-radius: 12px;
      padding: 1.25rem; cursor: pointer;
      display: flex; align-items: center; justify-content: space-between;
      box-shadow: var(--shadow); transition: box-shadow 0.2s;
    }}
    .collapsible-header:hover {{ box-shadow: var(--shadow-lg); }}
    .collapsible-title {{
      font-size: 1.1rem; font-weight: 600; color: var(--text-primary);
      display: flex; align-items: center; gap: 0.5rem;
    }}
    .collapsible-icon {{
      font-size: 1.2rem; color: var(--text-muted); transition: transform 0.3s;
    }}
    .collapsible.open .collapsible-icon {{ transform: rotate(180deg); }}
    .collapsible-content {{
      max-height: 0; overflow: hidden; transition: max-height 0.3s ease-out;
    }}
    .collapsible.open .collapsible-content {{
      max-height: 20000px; transition: max-height 0.5s ease-in;
    }}
    .collapsible-body {{
      padding: 1.5rem; background: var(--bg-card);
      border-radius: 0 0 12px 12px; margin-top: -12px;
    }}

    /* ── Chart ── */
    .chart-container {{ position: relative; height: 300px; margin-top: 1rem; }}
    .grid-2 {{
      display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
      gap: 1.5rem; margin-bottom: 1.5rem;
    }}

    /* ── Table ── */
    table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
    thead {{ background: var(--bg-light); }}
    th {{
      padding: 0.75rem; text-align: left; font-weight: 600;
      color: var(--text-secondary); font-size: 0.85rem;
      border-bottom: 2px solid var(--border);
    }}
    td {{ padding: 0.75rem; border-bottom: 1px solid var(--border); font-size: 0.9rem; vertical-align: top; }}
    tr:hover {{ background: var(--bg-light); }}

    /* ── Badges ── */
    .badge {{
      display: inline-block; padding: 0.25rem 0.75rem;
      border-radius: 9999px; font-size: 0.75rem; font-weight: 600;
    }}
    .badge-success  {{ background: var(--secondary); color: white; }}
    .badge-warning  {{ background: var(--warning);   color: white; }}
    .badge-info     {{ background: var(--info);       color: white; }}
    .badge-danger   {{ background: var(--danger);     color: white; }}
    .badge-neutral  {{ background: #6b7280;            color: white; }}
    .badge-score-10 {{ background: #22c55e; color: white; }}
    .badge-score-9  {{ background: #84cc16; color: white; }}
    .badge-score-8  {{ background: #eab308; color: white; }}

    /* ── Feedback ── */
    .feedback-section {{
      background: var(--bg-card); border-radius: 12px;
      padding: 1.5rem; text-align: center;
      box-shadow: var(--shadow); margin-top: 2rem;
    }}
    .feedback-title {{ font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem; }}
    .feedback-buttons {{
      display: flex; justify-content: center; gap: 1rem; flex-wrap: wrap;
    }}
    .feedback-btn {{
      background: var(--bg-light); border: 2px solid var(--border);
      border-radius: 12px; padding: 1rem 1.5rem;
      cursor: pointer; transition: all 0.2s; font-size: 1rem;
    }}
    .feedback-btn:hover {{
      background: var(--primary); color: white;
      border-color: var(--primary); transform: translateY(-2px);
    }}
    .feedback-btn.selected-useful {{ background: #dcfce7; border-color: var(--secondary); }}
    .feedback-btn.selected-meh   {{ background: #fef9c3; border-color: var(--warning); }}
    .feedback-btn.selected-suggest {{ background: #ede9fe; border-color: var(--primary); }}
    .feedback-thanks {{
      display: none; margin-top: 1rem;
      font-weight: 600; color: var(--secondary);
    }}

    /* ── Footer ── */
    .footer {{
      background: var(--bg-card); border-top: 1px solid var(--border);
      padding: 2rem 1rem; text-align: center;
      margin-top: 3rem; color: var(--text-secondary); font-size: 0.9rem;
    }}
    .footer a {{ color: var(--primary); margin: 0 0.5rem; }}

    /* ── Mobile ── */
    @media (max-width: 768px) {{
      .header h1 {{ font-size: 1.4rem; }}
      .container {{ padding: 1rem; }}
      .hero-zone {{ padding: 1.5rem; }}
      .hero-title {{ font-size: 1.3rem; }}
      .quick-scan-grid {{ grid-template-columns: 1fr; }}
      .grid-2 {{ grid-template-columns: 1fr; }}
      .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
      .chart-container {{ height: 250px; }}
      .feedback-buttons {{ flex-direction: column; }}
      .feedback-btn {{ width: 100%; }}
      thead {{ display: none; }}
      tr {{ display: block; margin-bottom: 1rem; border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem; }}
      tr:hover {{ background: transparent; }}
      td {{ display: block; text-align: left; border: none; padding: 0.5rem 0; font-size: 0.85rem; }}
      td::before {{
        content: attr(data-label);
        font-weight: 600; display: inline-block;
        min-width: 90px; color: var(--text-secondary);
      }}
    }}
    @media (max-width: 480px) {{
      .kpi-grid {{ grid-template-columns: 1fr 1fr; gap: 0.6rem; }}
      .kpi-num {{ font-size: 1.7rem; }}
    }}
  </style>
</head>
<body>

<div class="header">
  <h1>GNE 근육병 연구 현황 리포트</h1>
  <div class="meta">생성일시: {generated_at}  ·  데이터: PubMed · ClinicalTrials.gov · News</div>
  <div class="issue-badge">기간: {date_range or generated_at[:10]}</div>
</div>

<div class="container">

  <!-- ── KPI ── -->
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-num">{total_pubs}</div>
      <div class="kpi-label">총 수집 논문</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-num">{recent_5y}</div>
      <div class="kpi-label">최근 5년 논문 (2020~)</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-num">{total_trials}</div>
      <div class="kpi-label">임상시험 총계</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-num">{ai_stats.get('summarized', 0)}</div>
      <div class="kpi-label">AI 요약 완료</div>
    </div>
  </div>

  <!-- ══ ZONE 1: 30초 스캔 ══ -->
  {hero_html}

  <!-- ══ ZONE 2: 2분 리뷰 ══ -->
  <div class="section">
    <div class="section-header">
      <div class="section-title">💡 주목할 연구</div>
      <div class="section-badge">관련도 상위</div>
    </div>
    <div class="quick-scan-grid">
      {quick_items_html}
    </div>
  </div>

  <!-- ── 행동 가이드 ── -->
  <div class="action-guide">
    <div class="action-title">🏥 이번 주 행동 가이드</div>
    {action_items_html}
  </div>

  <!-- ══ ZONE 3: 10분 심층 탐색 (접기/펼치기) ══ -->

  <!-- Collapsible 1: 뉴스 -->
  <div class="collapsible">
    <div class="collapsible-header" onclick="toggleCollapse(this.parentElement)">
      <div class="collapsible-title">📰 최근 30일 뉴스 ({news_total}건)</div>
      <div class="collapsible-icon">▼</div>
    </div>
    <div class="collapsible-content">
      <div class="collapsible-body">
        <table>
          <thead><tr><th>날짜</th><th>출처</th><th>제목</th></tr></thead>
          <tbody>{news_rows}</tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Collapsible 2: 전체 데이터 시각화 + 논문 -->
  <div class="collapsible">
    <div class="collapsible-header" onclick="toggleCollapse(this.parentElement)">
      <div class="collapsible-title">📊 전체 데이터 시각화 + 논문 목록</div>
      <div class="collapsible-icon">▼</div>
    </div>
    <div class="collapsible-content">
      <div class="collapsible-body">
        <div class="grid-2">
          <div class="card">
            <h3 style="font-weight:600;margin-bottom:0">연도별 출판 추이</h3>
            <div class="chart-container"><canvas id="yearChart"></canvas></div>
          </div>
          <div class="card">
            <h3 style="font-weight:600;margin-bottom:0">임상시험 Status 분포</h3>
            <div class="chart-container"><canvas id="statusChart"></canvas></div>
          </div>
        </div>
        <div class="grid-2">
          <div class="card">
            <h3 style="font-weight:600;margin-bottom:0">Top 15 MeSH 용어</h3>
            <div class="chart-container"><canvas id="meshChart"></canvas></div>
          </div>
          <div class="card">
            <h3 style="font-weight:600;margin-bottom:0">Top 10 임상 중재</h3>
            <div class="chart-container"><canvas id="ivChart"></canvas></div>
          </div>
        </div>

        {"<div class='card'><h3 style='font-weight:600'>🤖 AI 고관련도 논문 (관련도 ≥8점)</h3><table><thead><tr><th>날짜</th><th>제목 / AI 요약</th><th>저널</th><th>관련도</th><th>링크</th></tr></thead><tbody>" + all_relevant_rows + "</tbody></table></div>" if all_relevant_rows else ""}

        <div class="card" style="margin-top:1rem">
          <h3 style="font-weight:600">📚 최근 2년 주요 논문</h3>
          <table>
            <thead><tr><th>날짜</th><th>저널</th><th>제목 / AI 요약</th><th>저자</th><th>링크</th></tr></thead>
            <tbody>{recent_paper_rows or "<tr><td colspan='5' style='text-align:center;color:#94a3b8;padding:1.5rem'>논문 없음</td></tr>"}</tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <!-- Collapsible 3: 임상시험 파이프라인 -->
  <div class="collapsible">
    <div class="collapsible-header" onclick="toggleCollapse(this.parentElement)">
      <div class="collapsible-title">🧪 활성 임상시험 파이프라인 ({len(active)}건)</div>
      <div class="collapsible-icon">▼</div>
    </div>
    <div class="collapsible-content">
      <div class="collapsible-body">
        <table>
          <thead><tr>
            <th>NCT ID</th><th>제목</th><th>Status</th><th>Phase</th>
            <th>Sponsor</th><th>중재</th><th>시작일</th><th>종료예정</th><th>국가</th>
          </tr></thead>
          <tbody>{active_rows}</tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- ── 피드백 ── -->
  <div class="feedback-section">
    <div class="feedback-title">💬 이번 주 리포트 어땠나요?</div>
    <div class="feedback-buttons">
      <button class="feedback-btn" id="fb-useful" onclick="sendFeedback('useful')">👍 유용했어요</button>
      <button class="feedback-btn" id="fb-meh"    onclick="sendFeedback('meh')">😐 별로였어요</button>
      <button class="feedback-btn" id="fb-suggest" onclick="sendFeedback('suggest')">💡 제안 있어요</button>
    </div>
    <div class="feedback-thanks" id="feedback-thanks">피드백 감사합니다!</div>
  </div>

</div>

<div class="footer">
  <p>GNE 근육병 모니터링 시스템 · 데이터: PubMed (NCBI) · ClinicalTrials.gov</p>
  <p style="margin-top:0.75rem;font-size:0.85rem;color:var(--text-muted)">
    자동 생성: {generated_at}
  </p>
</div>

<script>
  // 접기/펼치기
  function toggleCollapse(el) {{
    el.classList.toggle('open');
  }}

  // 피드백
  function sendFeedback(type) {{
    ['useful','meh','suggest'].forEach(function(t) {{
      document.getElementById('fb-' + t).classList.remove('selected-useful','selected-meh','selected-suggest');
    }});
    document.getElementById('fb-' + type).classList.add('selected-' + type);
    document.getElementById('feedback-thanks').style.display = 'block';
    try {{ localStorage.setItem('gne_feedback_' + new Date().toISOString().slice(0,10), type); }} catch(e) {{}}
  }}

  // 차트
  const yearLabels   = {json.dumps(year_labels)};
  const yearValues   = {json.dumps(year_values)};
  const meshLabels   = {json.dumps(mesh_labels)};
  const meshValues   = {json.dumps(mesh_values)};
  const statusLabels = {json.dumps(list(status_data.keys()))};
  const statusValues = {json.dumps(list(status_data.values()))};
  const ivLabels     = {json.dumps([d['intervention'] for d in iv_data])};
  const ivValues     = {json.dumps([d['count'] for d in iv_data])};

  const STATUS_COLORS = {{
    COMPLETED:'#6b7280', RECRUITING:'#22c55e',
    ACTIVE_NOT_RECRUITING:'#f59e0b', NOT_YET_RECRUITING:'#3b82f6',
    TERMINATED:'#ef4444', UNKNOWN:'#9ca3af',
  }};

  window.addEventListener('load', function() {{
    new Chart(document.getElementById('yearChart'), {{
      type: 'line',
      data: {{ labels: yearLabels, datasets: [{{
        label: '논문 발표 수', data: yearValues,
        borderColor: '#8b5cf6', backgroundColor: 'rgba(139,92,246,0.1)',
        tension: 0.4, fill: true,
      }}]}},
      options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{ y: {{ beginAtZero: true }} }}
      }}
    }});

    new Chart(document.getElementById('meshChart'), {{
      type: 'bar',
      data: {{ labels: meshLabels, datasets: [{{
        label: '빈도', data: meshValues,
        backgroundColor: '#8b5cf6', borderRadius: 4,
      }}]}},
      options: {{
        responsive: true, maintainAspectRatio: false,
        indexAxis: 'y',
        plugins: {{ legend: {{ display: false }} }},
        scales: {{ x: {{ beginAtZero: true }} }}
      }}
    }});

    new Chart(document.getElementById('statusChart'), {{
      type: 'doughnut',
      data: {{ labels: statusLabels, datasets: [{{
        data: statusValues,
        backgroundColor: statusLabels.map(function(s) {{ return STATUS_COLORS[s] || '#94a3b8'; }}),
      }}]}},
      options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ position: 'right' }} }}
      }}
    }});

    new Chart(document.getElementById('ivChart'), {{
      type: 'bar',
      data: {{ labels: ivLabels, datasets: [{{
        label: '건수', data: ivValues,
        backgroundColor: '#f59e0b', borderRadius: 4,
      }}]}},
      options: {{
        responsive: true, maintainAspectRatio: false,
        indexAxis: 'y',
        plugins: {{ legend: {{ display: false }} }},
        scales: {{ x: {{ beginAtZero: true }} }}
      }}
    }});
  }});
</script>
</body>
</html>"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
