# GNE Monitor - 작업 현황

**최종 업데이트**: 2026-05-18

---

## ✅ 완료 (최근 → 과거)

### 2026-05-18 — index.html UI 개선 (로고 교체 + 색감 + 반응형 테이블)
- [x] **네비게이션 로고 교체**: `가로로고.jpeg` → `KGNEM가로로고.png` (누끼 작업, 402×103px)
- [x] **히어로 반투명 배경 이미지 교체**: `스크린샷.png` → `KGNEM심볼.png` (트리밍)
- [x] **전체 색감 개선** (참고.txt 기반 B안 적용)
  - 배경: 단색 → 블루-퍼플 그라데이션 (`#f0f4ff → #e0e7ff`)
  - Primary 강화 (`#3b82f6 → #2563eb`), Accent 추가 (`#10b981`)
  - 버튼: 그라데이션 + 그림자 강화
- [x] **히어로 카드 스타일 개선**
  - 제목 텍스트 그라데이션, 박스 테두리 `#c3d4ff`, 뱃지 그라데이션
  - 반투명 심볼 z-index 조정 (텍스트 위에 겹치지 않도록)
- [x] **4개 네비게이션 카드** 파랑→초록 그라데이션 반투명 배경, 아이콘/텍스트 크기 확대
- [x] **링크 수정**: 뉴스 기사 파란색, "전체 뉴스 보기" → `archive.html` 연결
- [x] **논문 테이블 모바일 반응형** (680px 이하)
  - `paper-table` 클래스 + `data-label` 속성으로 카드형 변환
  - 날짜/저널/관련도/저자/링크: 라벨-값 2열 정렬
  - 제목: 라벨 + 요약+환자의미 포함 블록 표시
- [x] **Claude Code 자동화 설정**
  - SQLite MCP 설치 (`mcp-sqlite`)
  - `.env` 파일 편집 차단 훅 추가

### 2026-05-15 — 콘텐츠 구조 재편 + 뉴스레터 포맷 확립
- [x] **전략 확정**: 홈(상세 콘텐츠 허브) + 뉴스레터(요약 발행) 이원 구조
  - 워크플로우: 홈 업데이트 먼저 → 뉴스레터 요약 제작 → 발행
- [x] **`latest.html` 뉴스레터 포맷으로 전환** (759줄 → 357줄)
  - 추가: 환우회 소식 섹션 (뉴스레터 창간 + 환자 데이터 주권 발표 예정 문구)
  - 추가: "더 자세한 내용은 홈에서" 링크 블록 4개
  - 삭제: Chart.js 인라인, KPI 카드, 뉴스 전체 목록, 데이터 시각화, 임상시험 상세
  - 피드백: 3버튼 → "제안하기" 링크 1개로 단순화 (URL 미연결 상태)
- [x] **`index.html` 링크 정리** — `latest.html` 링크 5개 → 홈 내 앵커로 교체
  - "리포트 전체 보기" → "뉴스레터 보기"로 변경 (latest.html 유지)
- [x] **홈 콘텐츠 정리**
  - "이 프로젝트는 무엇을 목표로?" 섹션 3개 박스 삭제 (문구는 유지)
  - 히어로 문구 단축 ("복잡한 논문과..." 문장 삭제)
- [x] **디자인 시안 3개 제작** (검토 중)
  - `design_a.html`: 다크 슬레이트 (네이비 + 하늘색)
  - `design_b.html`: 클린 미니멀 (흰 배경 + 보라색)
  - `design_c.html`: 볼드 그라디언트 (인디고 헤더 + 흰 카드)

### 2026-05-13 — GitHub Pages 콘텐츠 채우기 1단계
- [x] **about.html 완성** — GNE 근육병 전체 내용
  - 섹션: 정의 / 원인 / 증상 / 진단 / 치료 / 경과
  - 섹션 네비게이션 + 스크롤 애니메이션 적용
- [x] **community.html 완성** — 환우회 소개 페이지
  - 섹션 네비게이션: 소개 / 연혁 / 온라인채널
  - 연혁 타임라인 직접 표시 (PDF → HTML, 2016~2025)
  - 네이버 카페 + 네이버 블로그 링크
- [x] **전 페이지 네비게이션 통일** — 홈 / GNE 근육병이란? / 환우회 소개 / 아카이브
- [x] **가로형 로고** 네비게이션에 적용 (`assets/images/icons/가로로고.jpeg`)
- [x] **홈 히어로 워터마크** — KGNEM 심볼 배경 (opacity 0.3)
- [x] **통계 카드 테두리 강화** — 워터마크 진해진 후 가독성 개선
- [x] **assets/ 폴더 구조** 생성 및 자료 업로드
  - docs/guidelines/: 리플렛.pdf, 연혁.pdf, 소개 문서
  - images/icons/: 가로로고, 심볼 로고
- [x] 모든 변경사항 GitHub push 완료 (commit: b95b2f4)

### 2026-05-12 (오후 세션)
- [x] **GitHub Pages 완전 배포 완료** 🎉
  - 랜딩 페이지 + 네비게이션 5개 페이지 구축
  - index.html: 통계 업데이트 (35/35/22/10)
  - latest.html: 최신 리포트 연결 (report_20260510_2315.html)
  - archive.html: 리포트 목록 페이지 생성
  - about.html: GNE 근육병 설명 페이지 (준비중)
  - community.html: 환우회 정보 페이지 (준비중)
  - Commit: `8e4a700` - "feat: 랜딩페이지 + 네비게이션 5개 추가"
  - 모든 네비게이션 링크 작동, 404 에러 없음
  - 사이트: https://gne-newsletter.github.io/gne-monitor/

### 2026-05-12 (오전 세션)
- [x] GitHub Pages 연결 완료
  - `gh` CLI 설치 (v2.92.0) → GitHub 인증
  - `git remote add origin https://github.com/gne-newsletter/gne-monitor.git`
  - `git push --force origin main` — 로컬 코드 전체 업로드
  - `index.html` (report_20260510_2315) push → GitHub Pages 배포

### 2026-05-10
- [x] 행동 가이드 섹션 완전 제거 (`pipeline.py`) — 한국 환자 기준 무관한 정보
- [x] DB 스키마 확장 — layer 컬럼 추가 (pubmed_articles 7개, news_articles 2개)
- [x] AI 요약 17건 완료 (→ 롤백으로 현재 10건 상태, 재실행 필요)
- [x] Layer 2/3 구조 시도 → 복잡성으로 롤백 (교훈 CLAUDE.md에 기록)
- [x] git commit: `feat: 행동 가이드 섹션 제거` (1ab96d9)

### 2026-05-09 (오후 세션)
- [x] HTML 리포트 템플릿 교체 (`improved_newsletter_template.html` 디자인 적용)
  - 3존 구조: 30초 Hero / 2분 Quick Scan+행동가이드 / 10분 Collapsible
  - 피드백 버튼 (👍😐💡), localStorage 저장
  - 보라색 테마, CSS 변수 시스템, line 차트
- [x] 'GNE 근육병' 용어 전면 통일
  - 소스 파일 4개 + DB 14건(summary 8 + patient_significance 6) 업데이트
- [x] 작업 종료 프로토콜 설정 (Claude memory 저장)

### 2026-05-09 (오전 세션)
- [x] Obsidian Vault 워크플로우 단순화
  - CLAUDE.md (개념) + STATUS.md (현황) 2개 파일만 유지
  - 과도한 폴더 구조 제거
- [x] Vault 폴더 구조 생성
- [x] 대화 기록 문서화
  - 2026-05-08_확장성_논의.md
  - 2026-05-09_워크플로우_논의.md

### 2026-05-08
- [x] HTML 리포트 모바일 반응형 CSS
- [x] Chart.js 오프라인 인라인 (238KB 단일 파일)
- [x] 차트 흰 화면 버그 수정

### 2026-05-06
- [x] 데이터 수집 시스템 (PubMed, ClinicalTrials, News)
- [x] AI 요약 (관련도 점수, 환자 의미)
- [x] HTML 리포트 생성
- [x] 자동 스케줄러 (매주 월요일 08:00)

---

## 🔄 진행 중

### gne-webapp — 환우 데이터 플랫폼 (2026-05-16 시작, 현재 최우선)

- 별도 레포 (`~/gne-webapp`), gne-monitor와 독립 운영
- Next.js + Supabase + Claude AI 기본 구조 완성
- Supabase 프로젝트 생성 완료 (Seoul, ref: mmvxcvgocbiuowmfsezr)
- 환자 코드 로그인 → AI 대화 → Supabase 저장 흐름 완성
- **막힌 것**: ANTHROPIC_API_KEY 교체 필요 (기존 키 인증 실패)
- **다음**: API 키 교체 → 추적 항목 확정 → Vercel 배포

---

## 📋 다음 할 일 (우선순위)

### 바로 다음
1. **제안하기 링크 연결** (최우선)
   - [ ] 게시판/블로그 URL 확정 (네이버 카페, 구글 폼 등)
   - [ ] `latest.html`의 `href="#"` → 실제 URL 교체

2. **홈 디자인 시안 결정** (검토 중)
   - [ ] design_a/b/c.html 중 방향 선택
   - [ ] 선택 후 index.html에 적용

3. **로고 누끼따기**
   - [ ] `가로로고.jpeg` 배경 제거 후 PNG로 저장 → 네비게이션 교체

4. **community.html 추가 섹션** (예정)
   - [ ] 회장인사말
   - [ ] 정기총회 기록
   - [ ] 후원 안내
   - [ ] 회계 공시 PDF (비영리단체 공개 의무)

### 이번 주
4. **자동화 스크립트** (나중에)
   - [ ] 리포트 생성 → latest.html 자동 복사
   - [ ] archive.html 자동 업데이트 (새 리포트 추가)
   - [ ] GitHub 자동 push 스크립트

### 다음 주
5. **환우회 제안서 완성**
   - [ ] 초안 다듬기
   - [ ] 데모 준비
   - [ ] 미팅 일정 요청

---

## ⚠️ 막힌 것

(없음)

---

## 💡 최근 결정 사항

- **워크플로우**: CLAUDE.md + STATUS.md 2개 파일만
- **확장 전략**: Python 유지, config.yaml 기반
- **전달 방식**: GitHub Pages → 이메일 구독 → 플랫폼 (단계적)
- **첫 목표**: GNE 환우회 파일럿
- **웹사이트 구조**: 작동하는 것 먼저 → 콘텐츠는 나중에 채우기

---

## 📊 현재 데이터

- 논문: 35건 (2025년 이후, Layer 1만)
- 뉴스: 19건 (Layer 1만)
- 임상시험: 22건
- AI 요약: 10/35건 완료 (롤백으로 복원, 재실행 필요)
- 데이터 기준: 2026-05-06 (6일 전)

---

## 🔗 중요 경로

- 프로젝트: `~/gne-monitor`
- 데이터베이스: `data/gne_monitor.db`
- 리포트: `exports/report_*.html`
- 설정: `config.yaml`
- **웹사이트**: https://gne-newsletter.github.io/gne-monitor/

---

## 📝 오늘 작업 요약 (2026-05-12 오후)

### 목표
GitHub Pages에 완전히 작동하는 웹사이트 배포

### 작업 내용
1. **index.html 통계 업데이트**
   - 128/73/12 → 35/35/22/10 (실제 데이터 반영)

2. **네비게이션 페이지 4개 생성**
   - latest.html: 최신 리포트 (report_20260510_2315.html 복사)
   - archive.html: 리포트 목록 (현재 1개 표시)
   - about.html: GNE 근육병 설명 ("준비중" 페이지)
   - community.html: 환우회 정보 ("준비중" 페이지)

3. **Git 배포**
   - 5개 파일 커밋 및 푸시
   - Commit ID: 8e4a700
   - 모든 링크 작동 확인

### 결과
✅ 완전히 작동하는 웹사이트 완성
✅ 모든 네비게이션 링크 404 에러 없음
✅ 나중에 콘텐츠만 채우면 됨

### 다음 작업
- 옵션 1: 새 데이터 수집 + AI 요약 + 리포트 생성
- 옵션 2: about/community 콘텐츠 작성
- 옵션 3: 자동화 스크립트 개발
