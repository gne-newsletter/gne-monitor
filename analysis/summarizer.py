"""Claude API-based AI summarizer for PubMed articles."""

import json
import logging
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic
import yaml

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """당신은 GNE 근육병(GNE Myopathy, GNEM) 연구를 전문으로 모니터링하는 의학 연구 분석가입니다.

GNE 근육병 배경 지식:
- GNE 근육병(Nonaka 근병증, 유전성 봉입체 근병증)은 UDP-GlcNAc 2-epimerase/ManNAc kinase(GNE) 유전자 돌연변이로 인한 희귀 근육질환입니다.
- 원위부 근육(발, 다리)부터 시작해 점진적으로 진행하며 사두근은 비교적 보존됩니다.
- 시알산(sialic acid) 결핍이 핵심 병리 기전이며, 시알산 보충/전구체 투여가 주요 치료 전략입니다.
- 현재 승인된 치료제 없음. 유전자 치료, 기질 보충 요법(ManNAc, Neu5Ac), 안티센스 올리고뉴클레오타이드 등 연구 중입니다.
- 주요 연구 기관: NIH(National Institutes of Health), 일본 NCNP, 이스라엘 Hadassah 의대.

각 논문 abstract를 분석하여 다음 JSON만 반환하세요 (다른 텍스트 없이):

{
  "summary_ko": "한국어 3-4줄 요약 (핵심 연구 목적, 방법, 결과/결론)",
  "relevance_score": 1~10 정수,
  "relevance_reason": "관련도 점수 이유 1-2문장 (한국어)",
  "patient_significance": "관련도가 9점 이상일 때만 생성. 환자 입장에서 이 연구가 왜 중요한지 1~2문장으로 쉽게 설명. 9점 미만이면 null."
}

관련도 점수 기준:
- 9-10: GNE 근육병 직접 연구 (GNE 환자 코호트, 임상시험, GNE 유전자·단백질 직접 분석)
- 7-8: 핵심 관련 주제 (시알산 대사 경로, GNE 단백질 기능, 봉입체 근병증 병리)
- 5-6: 간접 관련 (유사 근육병증 치료, 희귀 근신경 질환 전략, 관련 당생물학)
- 3-4: 낮은 관련도 (일반 원위부 근육병증, 무관한 신경근육질환 일반 기전)
- 1-2: 거의 무관 (일반 근육생리학, GNE 근육병과 무관한 연구)"""


class ArticleSummarizer:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path) as f:
            cfg = yaml.safe_load(f)

        self._db_path = Path(cfg["database"]["path"])
        self._conn = self._init_db()

        api_key = os.environ.get("ANTHROPIC_API_KEY") or cfg.get("anthropic", {}).get("api_key", "")
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = "claude-opus-4-7"

    def _init_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")

        existing = [r[1] for r in conn.execute("PRAGMA table_info(pubmed_articles)").fetchall()]
        if "relevance_score" not in existing:
            conn.execute("ALTER TABLE pubmed_articles ADD COLUMN relevance_score REAL")
            logger.info("pubmed_articles.relevance_score 컬럼 추가")
        if "summarized_at" not in existing:
            conn.execute("ALTER TABLE pubmed_articles ADD COLUMN summarized_at TEXT")
            logger.info("pubmed_articles.summarized_at 컬럼 추가")
        if "patient_significance" not in existing:
            conn.execute("ALTER TABLE pubmed_articles ADD COLUMN patient_significance TEXT")
            logger.info("pubmed_articles.patient_significance 컬럼 추가")

        conn.commit()
        return conn

    def _pending(self, limit: Optional[int], force: bool, since_year: Optional[str] = None) -> list[dict]:
        conditions = ["abstract IS NOT NULL", "abstract != ''"]
        if since_year:
            conditions.append(f"substr(pub_date, 1, 4) >= '{since_year}'")
        if not force:
            conditions.append("summarized_at IS NULL")

        q = f"SELECT pmid, title, abstract FROM pubmed_articles WHERE {' AND '.join(conditions)} ORDER BY pub_date DESC"
        if limit:
            q += f" LIMIT {limit}"
        return [dict(r) for r in self._conn.execute(q).fetchall()]

    def _call_claude(self, pmid: str, title: str, abstract: str) -> Optional[dict]:
        user_msg = f"논문 제목: {title}\n\nAbstract:\n{abstract}\n\n위 논문을 분석하여 JSON으로 반환하세요."

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=[
                    {
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_msg}],
            )

            raw = ""
            for block in response.content:
                if block.type == "text":
                    raw = block.text.strip()
                    break

            # Strip markdown code fences if present
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw

            return json.loads(raw)

        except anthropic.RateLimitError:
            logger.warning("Rate limit — PMID %s: 60초 대기 후 재시도", pmid)
            time.sleep(60)
            return self._call_claude(pmid, title, abstract)
        except anthropic.APIError as e:
            logger.error("API 오류 — PMID %s: %s", pmid, e)
            return None
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("JSON 파싱 실패 — PMID %s: %s", pmid, e)
            return None

    def _save(self, pmid: str, result: dict):
        self._conn.execute(
            "UPDATE pubmed_articles SET summary = ?, relevance_score = ?, summarized_at = ?, patient_significance = ? WHERE pmid = ?",
            (
                result.get("summary_ko", ""),
                result.get("relevance_score"),
                datetime.now().isoformat(),
                result.get("patient_significance"),
                pmid,
            ),
        )
        self._conn.commit()

    def run(self, limit: Optional[int] = None, force: bool = False, since_year: Optional[str] = None) -> dict:
        articles = self._pending(limit, force, since_year)
        total = len(articles)

        if not articles:
            print("요약할 논문이 없습니다. (--force 옵션으로 재요약 가능)")
            return {"processed": 0, "success": 0, "failed": 0}

        print(f"AI 요약 시작: {total}건 (모델: {self._model})\n")
        success = failed = 0

        for i, art in enumerate(articles, 1):
            pmid = art["pmid"]
            title = (art["title"] or "")[:120]
            abstract = art["abstract"] or ""

            print(f"[{i}/{total}] PMID {pmid} — {title[:60]}...", end=" ", flush=True)

            result = self._call_claude(pmid, art["title"] or "", abstract)
            if result:
                self._save(pmid, result)
                score = result.get("relevance_score", "?")
                print(f"✓ (관련도 {score}/10)")
                success += 1
            else:
                print("✗ 실패")
                failed += 1

            # Polite delay between calls (cache hit = fast, still be courteous)
            if i < total:
                time.sleep(0.3)

        print(f"\n완료: {success}건 성공, {failed}건 실패 (총 {total}건)")
        return {"processed": total, "success": success, "failed": failed}

    def stats(self) -> dict:
        total = self._conn.execute("SELECT COUNT(*) FROM pubmed_articles").fetchone()[0]
        summarized = self._conn.execute(
            "SELECT COUNT(*) FROM pubmed_articles WHERE summarized_at IS NOT NULL"
        ).fetchone()[0]
        row = self._conn.execute(
            "SELECT AVG(relevance_score) FROM pubmed_articles WHERE relevance_score IS NOT NULL"
        ).fetchone()
        avg_score = round(row[0], 2) if row[0] else None
        high = self._conn.execute(
            "SELECT COUNT(*) FROM pubmed_articles WHERE relevance_score >= 7"
        ).fetchone()[0]

        return {
            "total": total,
            "summarized": summarized,
            "pending": total - summarized,
            "avg_relevance_score": avg_score,
            "high_relevance_count": high,
        }

    def top_relevant(self, n: int = 20, min_score: float = 7.0) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT pmid, title, journal, pub_date, relevance_score, summary, patient_significance
            FROM pubmed_articles
            WHERE relevance_score >= ?
            ORDER BY relevance_score DESC, pub_date DESC
            LIMIT ?
            """,
            (min_score, n),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
