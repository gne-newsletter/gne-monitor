# Layer 2/3 적용 가이드

## 📋 생성된 파일 목록

1. **config_extended.yaml** — 확장된 설정 파일
2. **pipeline_layer23_code.py** — pipeline.py에 삽입할 Python 코드
3. **layer23_styles.css** — pipeline.py에 추가할 CSS 스타일
4. **이 가이드 (LAYER23_GUIDE.md)**

---

## 🚀 적용 순서

### STEP 1: config.yaml 교체

```bash
# 백업
cp ~/gne-monitor/config.yaml ~/gne-monitor/config.yaml.backup

# 새 파일로 교체
cp config_extended.yaml ~/gne-monitor/config.yaml
```

**또는** 기존 config.yaml을 열어서 다음 섹션만 추가:

```yaml
keywords:
  direct: [...]  # 기존 유지
  
  # 새로 추가
  indirect_treatment:
    - "gene therapy muscular dystrophy"
    - "AAV myopathy"
    # ... (나머지는 config_extended.yaml 참고)
  
  indirect_ecosystem:
    - "AI drug discovery rare disease"
    # ... (나머지는 config_extended.yaml 참고)
```

---

### STEP 2: pipeline.py 수정

#### 2-1. CSS 추가

`analysis/pipeline.py` 파일을 열고, `<style>` 태그 안쪽 **맨 아래**에 `layer23_styles.css` 내용 전체를 복사해서 붙여넣기.

**위치:** (대략 500-600줄 근처)
```python
def _write_html(self, data: Dict[str, Any], output_path: str):
    ...
    html_parts.append("""
    <style>
      /* 기존 CSS */
      ...
      
      /* ✨ 여기에 layer23_styles.css 내용 붙여넣기 */
      
    </style>
    """)
```

#### 2-2. HTML 구조 수정

1. **행동 가이드 삭제**
   
   `pipeline.py`에서 이 부분 찾아서 **전체 삭제**:
   ```python
   # <!-- ── 행동 가이드 ── -->
   # <div class="action-guide">
   #   ...
   # </div>
   ```

2. **Layer 2/3 코드 삽입**
   
   `pipeline_layer23_code.py`의 내용을 복사해서:
   - Quick Scan 섹션 아래에 Layer 2 코드 삽입
   - Collapsible 3개 아래에 Layer 3 코드 삽입
   - 맨 아래에 현실 체크 섹션 삽입

**정확한 위치:**
```python
# Quick Scan 섹션 끝
html_parts.append("  </div>")  # quick-scan-grid 닫기
html_parts.append("</div>")    # section 닫기

# ✨ 여기에 Layer 2 코드 삽입

# ZONE 3 시작
html_parts.append("""
  <!-- ══ ZONE 3: 10분 심층 탐색 (접기/펼치기) ══ -->
""")
```

---

### STEP 3: 데이터베이스 스키마 업데이트

```bash
cd ~/gne-monitor

# SQLite 열기
sqlite3 data/gne_monitor.db

# 새 컬럼 추가
ALTER TABLE publications ADD COLUMN layer INTEGER DEFAULT 1;
ALTER TABLE publications ADD COLUMN gne_distance TEXT;
ALTER TABLE publications ADD COLUMN outcome_type TEXT;
ALTER TABLE publications ADD COLUMN positive_aspect TEXT;
ALTER TABLE publications ADD COLUMN limitation TEXT;
ALTER TABLE publications ADD COLUMN realistic_impact TEXT;
ALTER TABLE publications ADD COLUMN gne_perspective TEXT;

ALTER TABLE news ADD COLUMN layer INTEGER DEFAULT 1;
ALTER TABLE news ADD COLUMN gne_distance TEXT;

.quit
```

---

### STEP 4: 테스트

```bash
# 현재 데이터로 리포트 생성 (Layer 1만)
python3 analyze.py report

# HTML 확인
open exports/report_*.html
```

Layer 2/3 섹션이 비어있어도 정상입니다 (아직 데이터 없음).

---

## 📊 Layer 2/3 데이터 수집 (나중에)

### Phase 1: 수동 테스트

```bash
# Layer 2 논문 수집 (소량)
python3 collect.py pubmed collect --query "gene therapy muscular dystrophy" --limit 10

# Layer 3 뉴스 수집 (소량)
python3 collect.py news collect --query '"AI drug discovery" rare disease' --limit 5
```

### Phase 2: AI 요약 생성

`analysis/summarizer.py`에 Layer 2/3 전용 프롬프트 추가 필요.

**예시:**
```python
LAYER2_PROMPT = """
이 논문을 근육병 치료 기술 관점에서 분석하세요.

필수 항목:
1. GNE와 거리 (immediate / near_term / long_term / platform)
2. 결과 유형 (positive / negative / mixed / neutral)
3. 긍정적 측면 (무엇이 발전했나)
4. 제한점 (GNE 적용의 한계)
5. 현실적 영향 (언제, 어떻게 영향을 줄까)
"""
```

---

## ✅ 체크리스트

- [ ] config.yaml에 Layer 2/3 키워드 추가
- [ ] pipeline.py에 CSS 추가
- [ ] pipeline.py에 Layer 2 HTML 코드 삽입
- [ ] pipeline.py에 Layer 3 HTML 코드 삽입
- [ ] pipeline.py에 현실 체크 섹션 삽입
- [ ] 행동 가이드 섹션 삭제
- [ ] 데이터베이스 스키마 업데이트
- [ ] 테스트 리포트 생성
- [ ] Layer 2/3 데이터 수집 (선택)
- [ ] AI 요약 프롬프트 수정 (선택)

---

## 🚨 주의 사항

1. **백업 필수**
   ```bash
   cp config.yaml config.yaml.backup
   cp analysis/pipeline.py analysis/pipeline.py.backup
   ```

2. **단계별 적용**
   - CSS 추가 → 테스트
   - Layer 2 추가 → 테스트
   - Layer 3 추가 → 테스트

3. **에러 발생 시**
   - Python 문법 에러: 따옴표, 괄호 확인
   - CSS 깨짐: 기존 CSS와 충돌 확인
   - DB 에러: 컬럼 추가 확인

---

## 📞 다음 단계

지금은 **구조만 추가**한 상태입니다.

실제 Layer 2/3 콘텐츠를 채우려면:
1. 데이터 수집 (PubMed, News)
2. AI 요약 생성 (summarizer.py 수정)
3. 리포트 생성

**원하시면 이 부분도 도와드리겠습니다!**
