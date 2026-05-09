# GNE 근육병 모니터링 시스템

## 프로젝트 개요

**목적**: GNE 근육병(GNE myopathy, HIBM) 관련 최신 정보를 자동으로 수집, 정리, 요약하는 시스템

**사용자**: Zerozero (GNE 근육병 환자, Obsidian 사용자)

**핵심 요구사항**:
- 매일/매주 자동 실행
- 학술 논문, 임상시험, 뉴스, 치료제 정보 수집
- AI가 자동으로 관련도 분류 및 요약
- Obsidian 지식 창고에 자동 통합
- **확장 가능**: 다른 키워드 추가만으로 재사용 가능

---

## 용어 정책

- **공식 한글 표기**: `GNE 근육병` (2026-05-09 확정)
- 코드, 리포트, AI 프롬프트, 이메일 알림 모두 통일
- 외부 뉴스 원문 제목은 변경 불가 (언론사 표기 그대로)

---

## 모니터링 대상

### 직접 관련 키워드
- `GNE myopathy`
- `GNE 근육병` (한글 공식 표기)
- `HIBM` (Hereditary Inclusion Body Myopathy)
- `Distal myopathy with rimmed vacuoles` (DMRV)
- `Nonaka disease`
- `sialic acid deficiency`

### 간접 관련 (치료법/연구)
- `GNE gene therapy`
- `ManNAc` (치료제 후보)
- `sialic acid supplementation`
- `rare neuromuscular disease`
- `orphan drug muscular dystrophy`

### 데이터 소스 (구현 완료)
1. **학술 논문**
   - PubMed API (2025년 이후, 3개 쿼리)
   - 35건 수집 완료
   
2. **임상시험**
   - ClinicalTrials.gov API v2
   - 22건 등록
   
3. **뉴스**
   - Google News RSS (5개 피드)
     - `"GNE myopathy"` (영문)
     - `"GNE 근병증"` (한글)
     - `"HIBM"` (단독)
     - `"hereditary inclusion body myopathy"` (전체명)
     - `Ultragenyx AND (UX016 OR GNEM)` (제약사)
   - 20건 수집 (오탐 필터링 완료)

---

## 시스템 구조

```
gne-monitor/
├── config.yaml                      # 설정 파일 (키워드, 소스, 스케줄)
├── collect.py                       # 데이터 수집 CLI
├── analyze.py                       # 분석 및 리포트 생성 CLI
├── run_scheduler.py                 # 자동 스케줄러 실행
├── collectors/                      # 데이터 수집 모듈
│   ├── __init__.py
│   ├── pubmed_collector.py         # PubMed API
│   ├── clinicaltrials_collector.py # ClinicalTrials.gov API
│   └── news_collector.py           # Google News RSS (5개 피드)
├── analysis/                        # 분석 모듈
│   ├── __init__.py
│   ├── pipeline.py                 # 메인 분석 파이프라인
│   ├── publication_trend.py        # 논문 트렌드 분석
│   ├── trial_landscape.py          # 임상시험 현황 분석
│   └── summarizer.py               # Claude API 요약 (관련도+환자의미)
├── data/                            # SQLite 데이터베이스
│   ├── gne_monitor.db
│   └── chart.umd.min.js            # Chart.js 오프라인 번들 (205KB)
├── exports/                         # 생성된 리포트
│   ├── report_YYYYMMDD_HHMM.json
│   └── report_YYYYMMDD_HHMM.html   # 주간 하이라이트 포함
├── logs/                            # 실행 로그
└── scheduler/                       # 스케줄러 설정
```

---

## 현재 상태

**Phase**: 운영 준비 완료 ✅

**완료**:
- [x] 프로젝트 기획 및 설계
- [x] config.yaml 설계 및 구현
- [x] 데이터 수집 모듈
  - [x] PubMed collector (2025년 이후 논문)
  - [x] ClinicalTrials.gov collector
  - [x] News collector (Google News RSS, 5개 피드)
- [x] AI 분석 시스템
  - [x] Claude API 요약 (claude-opus-4-7)
  - [x] 관련도 점수 (1-10점)
  - [x] "환자에게 의미" 자동 생성 (9점 이상만)
- [x] HTML 리포트 생성
  - [x] "📬 이번 주 핵심 소식" 섹션 (지난 7일)
  - [x] 데이터 시각화 (Chart.js)
  - [x] 반응형 디자인 (모바일 완전 지원)
    - [x] 768px 이하: 테이블 → 카드 변환, KPI 2열, 차트 축소
    - [x] 480px 이하: KPI 1열
    - [x] Chart.js 오프라인 인라인 삽입 (data/chart.umd.min.js)
- [x] 뉴스 필터링 개선
  - [x] 정확한 구문 검색 (따옴표 추가)
  - [x] 오탐 제거 (무관한 뉴스 필터링)
- [x] 자동 스케줄러 설정 (매주 월요일 08:00)
- [x] API 키 보안 처리 (환경 변수)

**진행 중**:
- [ ] 나머지 35건 논문 AI 요약 (10/35 완료)
- [ ] Obsidian 자동 연동

**예정**:
- [ ] 이메일 알림 기능
- [ ] 간접 관련 키워드 추가 (유전자 치료 일반, 희귀병 신약)
- [ ] GitHub Actions 자동화 (선택)

---

## 기술 스택

**개발 환경**: Mac 로컬 + Claude Code
**언어**: Python 3.11+
**주요 라이브러리**:
- `anthropic` - Claude API (claude-opus-4-7, 프롬프트 캐싱)
- `requests` - API 호출
- `feedparser` - RSS 파싱
- `pyyaml` - 설정 파일 관리
- `sqlite3` - 로컬 데이터베이스
- `schedule` - 자동 스케줄러

**실행 환경**:
- Mac 로컬 (수동/자동 스케줄)
- 매주 월요일 08:00 자동 실행

**API 키 관리**:
- `~/.zshrc`에 환경 변수로 저장
- 모든 프로젝트에서 공유 가능

---

## 출력 형식 (HTML 리포트)

> **디자인 기준**: `improved_newsletter_template.html` (2026-05-09 적용)
> **색상 테마**: 보라색 계열 (`--primary: #8b5cf6`)
> **구현 위치**: `analysis/pipeline.py` → `_write_html()`

### 3존(Zone) 계층 구조

#### ⚡ ZONE 1 — 30초 스캔 (hero-zone)
- KPI 카드 4개 (총 논문 / 최근 5년 / 임상시험 / AI 요약 완료)
- **Hero 섹션**: AI 최고 관련도 논문 1건 — 제목 + 별점 + 요약 + 💡 환자에게 의미
- 황금색 그라디언트 배경 (`#fef3c7 → #fde68a`)

#### 📖 ZONE 2 — 2분 핵심 (quick-scan)
- **Quick Scan 카드**: 다음 2건 핵심 논문 (관련도 점수 + 요약)
- **행동 가이드**: 모집 중/예정 임상시험 바로가기 링크 (파란 그라디언트)

#### 🔬 ZONE 3 — 10분 심층 (collapsible, 기본 접힘)
- 📰 최근 30일 뉴스 전체
- 📊 데이터 시각화 + 전체 논문 목록
  - 연도별 출판 추이 (line 차트)
  - Top 15 MeSH 용어 (bar 차트, 수평)
  - 임상시험 Status 분포 (doughnut 차트)
  - Top 10 임상 중재 (bar 차트, 수평)
- 🧪 활성 임상시험 파이프라인 전체

### 인터랙션
- **접기/펼치기**: `toggleCollapse()` — CSS `max-height` 트랜지션
- **피드백 버튼**: 👍 유용했어요 / 😐 별로였어요 / 💡 제안 있어요 → `localStorage` 저장

### 모바일 반응형
- 768px 이하: 테이블 → 카드 변환 (`data-label` 속성), KPI 2열
- 480px 이하: KPI 2열 유지

### 예시 - "환자에게 의미" 표시

```html
💡 환자에게 의미
하루 총 용량을 줄이면서도 약효는 더 높일 수 있습니다.
복용 편의성도 개선될 가능성이 있습니다.
```

**특징:**
- 관련도 9점 이상만 자동 생성 (비용 절감)
- 전문 용어를 쉽게 풀어서 설명
- 환자 관점에서 실질적 의미 전달

---

## 확장성 설계

### 다른 키워드 추가 예시

```yaml
# config.yaml

profiles:
  gne_myopathy:
    enabled: true
    keywords: [...]
    sources: [...]
    
  node_capitalism:  # 나중에 추가
    enabled: true
    keywords:
      - "decentralization"
      - "Peter Thiel"
    sources:
      - twitter
      - hackernews
      
  ai_safety:  # 또 추가 가능
    enabled: false  # 비활성화 가능
    keywords: [...]
```

---

## 사용 방법

### 1. 데이터 수집
```bash
# 뉴스 수집 (매일)
python3 collect.py news collect

# PubMed 논문 수집 (매주)
python3 collect.py pubmed collect

# 임상시험 수집 (매주)
python3 collect.py ct collect
```

### 2. AI 요약 생성
```bash
# 미요약 논문 전체 요약
python3 analyze.py summarize

# 10건만 테스트
python3 analyze.py summarize --limit 10

# 9점 이상만 재요약 (환자 의미 추가)
python3 analyze.py summarize --force --min-score 9.0

# 요약 통계 확인
python3 analyze.py summarize --stats
```

### 3. 리포트 생성
```bash
# HTML + JSON 리포트 생성
python3 analyze.py report

# HTML만 생성
python3 analyze.py report --no-json
```

### 4. 자동 스케줄러
```bash
# 스케줄러 시작 (백그라운드)
python3 run_scheduler.py &

# 매주 월요일 08:00 자동 실행:
# - 뉴스/논문/임상시험 수집
# - AI 요약 (신규 논문만)
# - HTML 리포트 생성
```

### 5. 생성된 리포트 확인
```bash
# 최신 리포트 열기
open exports/report_*.html
```

---

## 참고 사항

### 비용
- **Claude API**: 월 $2~3 예상
  - 관련도 9점 이상만 "환자 의미" 생성 (비용 절감)
  - 주당 신규 논문 5~10건 × $0.01~0.02/건
- **무료**: PubMed, ClinicalTrials.gov, Google News RSS

### API 키 설정
```bash
# ~/.zshrc에 영구 저장 (한 번만 실행)
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.zshrc
source ~/.zshrc

# 확인
echo $ANTHROPIC_API_KEY
```

### 실행 주기
- **뉴스**: 매일 06:00 (자동)
- **논문/임상시험**: 매주 월요일 08:00 (자동)
- **수동 실행**: 언제든지 가능

### 데이터 보관
- **SQLite DB**: `data/gne_monitor.db`
- **리포트**: `exports/` 폴더 (JSON + HTML)
- **로그**: `logs/` 폴더

### 뉴스 필터링
- 정확한 구문 검색 (`"GNE myopathy"`)
- 오탐 방지 (무관한 뉴스 제거)
- 중복 제거 (SHA256 해시)

---

## 변경 이력

### 2026-05-06 (Phase 1 완료)
- **프로젝트 생성 및 기초 설계**
  - Claude.md 작성
  - config.yaml 설계
  
- **데이터 수집 시스템 구축**
  - PubMed collector (2025년 이후 필터링)
  - ClinicalTrials.gov collector
  - News collector (Google News RSS 5개 피드)
  - 뉴스 필터링 개선 (정확한 구문 검색, 오탐 제거)

- **AI 분석 시스템**
  - Claude API 통합 (claude-opus-4-7)
  - 관련도 점수 1-10점 자동 평가
  - "환자에게 의미" 자동 생성 (9점 이상)
  - 프롬프트 캐싱 적용

- **리포트 생성 시스템**
  - HTML 리포트 (Chart.js 시각화)
  - "📬 이번 주 핵심 소식" 섹션 추가 (지난 7일)
  - 보라색 그라데이션 헤더
  - 💡 "환자에게 의미" 초록 박스 표시

- **자동화**
  - 스케줄러 설정 (매주 월요일 08:00)
  - API 키 환경 변수 설정

- **현재 데이터**
  - 논문: 35건 (2025년 이후)
  - 뉴스: 20건
  - 임상시험: 22건
  - AI 요약: 10건 (10점 3건, 9점 5건, 8점 1건, 7점 1건)

### 2026-05-08 (HTML 리포트 모바일 반응형 완성)

- **모바일 반응형 CSS 추가** (`analysis/pipeline.py` → `_write_html`)
  - 768px 이하: 테이블 → 카드 변환 (`.table-responsive` + `data-label` 속성)
    - 뉴스, 임상시험 파이프라인, AI 고관련도 논문, 최근 논문 4개 테이블 적용
  - 768px 이하: KPI 그리드 4열 → 2열
  - 480px 이하: KPI 그리드 1열
  - 모바일 padding/font 최적화

- **Chart.js 차트 반응형 개선**
  - `.chart-container` CSS 클래스 도입 (position:relative, height:300px → 240px on mobile)
  - 인라인 스타일 제거, 미디어쿼리로 모바일 차트 높이 제어 가능하도록 변경
  - `responsive: true`, `maintainAspectRatio: false` 각 차트 옵션에 추가
  - `window.addEventListener('load', ...)` 래핑으로 렌더링 안정화

- **모바일 차트 흰 화면 버그 수정**
  - 원인: CSS `max-height`가 Chart.js JS 렌더링 버퍼와 충돌 → 모바일에서 빈 캔버스
  - canvas CSS에서 `max-height`/`max-width` 제거, `display: block`만 유지
  - Chart.js가 컨테이너 크기를 온전히 제어하도록 수정

- **Chart.js 오프라인 인라인 삽입**
  - `chart.js@4.4.0` (205KB) → `data/chart.umd.min.js`로 저장
  - `_write_html` 시작 시 파일 읽어 `<script>` 태그에 직접 삽입
  - CDN 없이 오프라인 환경에서도 차트 정상 표시
  - 생성된 HTML 파일 크기: **238KB** (자급자족 단일 파일)
### 2026-05-09 (HTML 리포트 템플릿 교체 + 용어 통일)

- **HTML 리포트 3존 구조 도입** (`analysis/pipeline.py` → `_write_html()` 전면 교체)
  - ZONE 1 (30초): Hero zone — AI 최고 관련도 논문, 황금색 그라디언트
  - ZONE 2 (2분): Quick scan 카드 2개 + 파란 행동 가이드 (모집 중 임상시험)
  - ZONE 3 (10분): 3개 collapsible — 뉴스 / 차트+논문 / 임상시험 파이프라인
  - 피드백 버튼 3개 (유용했어요 / 별로였어요 / 제안 있어요), localStorage 저장
  - 연도별 차트 bar → line 변경
  - 색상 테마: 파란색 → 보라색 (`#8b5cf6`)
  - CSS 변수 시스템 (`--primary`, `--secondary` 등) 도입

- **'GNE 근육병' 용어 전면 통일**
  - 수정 파일: `pipeline.py`, `notifier.py`, `summarizer.py`, `config.yaml`
  - DB 일괄 업데이트: `summary` 8건, `patient_significance` 6건
  - 외부 뉴스 원문 제목은 변경 불가 (언론사 표기)

- **작업 종료 프로토콜 확립**
  - 트리거: "작업 저장해줘" / "오늘 여기까지"
  - Claude memory에 저장 → 세션 간 지속
  - CLAUDE.md(전략) / STATUS.md(현황) 자동 업데이트

### 2026-05-09 (Obsidian Vault 워크플로우 구축)

- **프로젝트 관리 시스템 개선**
  - Obsidian Vault 구조 생성 (5개 폴더)
  - CLAUDE.md를 vault 루트로 이동
  - 대화 기록 문서화 시작
    - 2026-05-08_확장성_논의.md
    - 2026-05-09_워크플로우_논의.md

- **워크플로우 확정**
  - Cyril 시스템 분석 및 적용 방안 결정
  - 채택: Obsidian Vault, 주간 회고, 문서화
  - 미채택: 일일 브리핑, N8N (현 단계 불필요)
  - Python + config.yaml 확장 전략 유지

- **Vault 구조**
vault/
├── CLAUDE.md              # 프로젝트 컨텍스트 (이 파일)
├── 00_Project/            # 프로젝트 관리
├── 01_Ideas/              # 아이디어 메모
├── 02_Reports/            # 리포트 분석
├── 03_Research/           # 연구 정리
├── 04_Conversations/      # Claude 대화 기록
└── templates/             # 문서 템플릿

- **다음 단계**
  - [ ] 00_Project 폴더 문서 작성
  - [ ] GitHub Pages 정적 사이트 구축
  - [ ] 환우회 제안서 완성
