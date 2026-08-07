# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# pipeline.py의 _write_html() 함수 내부에 추가할 코드
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ============================================================
# STEP 1: Quick Scan 섹션 아래, 행동 가이드 삭제하고 Layer 2 추가
# ============================================================

# 기존 행동 가이드 섹션 전체 삭제:
# <!-- ── 행동 가이드 ── -->
# <div class="action-guide">
#   ...
# </div>

# 대신 아래 코드 삽입:

html_parts.append("""
  <!-- ══ LAYER 2: 근육병 치료 기술 흐름 ══ -->
  <div class="section layer2-section">
    <div class="section-header">
      <div class="section-title">🔬 근육병 치료 기술 흐름</div>
      <div class="section-badge warning">⚠️ 참고용 (GNE 직접 ≠)</div>
    </div>
    
    <div class="warning-banner">
      이 섹션은 GNE 외 근육병 전반의 치료 기술 동향입니다. 
      GNE 적용 가능성과 시간은 별도 평가가 필요합니다.
    </div>
""")

# Layer 2 데이터 조회 (DB에서)
layer2_publications = db.execute("""
    SELECT * FROM publications 
    WHERE layer = 2 AND relevance_score >= 5.0
    ORDER BY relevance_score DESC, pub_date DESC
    LIMIT 10
""").fetchall()

# 긍정적 신호 / 부정적 신호 분류
positive_signals = [p for p in layer2_publications if p['outcome_type'] == 'positive']
negative_signals = [p for p in layer2_publications if p['outcome_type'] == 'negative']

# 긍정적 신호 섹션
if positive_signals:
    html_parts.append("""
    <div class="tech-signals">
      <h4 class="signal-header positive">✅ 긍정적 신호</h4>
""")
    
    for pub in positive_signals[:3]:  # 상위 3개만
        distance_badge = {
            'immediate': ('high', '단기 (1-2년)'),
            'near_term': ('near', '중기 (3-5년)'),
            'long_term': ('long', '장기 (5-10년)'),
            'platform': ('platform', '플랫폼 (10년+)')
        }.get(pub['gne_distance'], ('low', '미확인'))
        
        html_parts.append(f"""
      <div class="tech-card">
        <div class="tech-card-header">
          <span class="tech-title">{pub['title']}</span>
          <span class="distance-badge {distance_badge[0]}">{distance_badge[1]}</span>
        </div>
        <div class="tech-card-body">
          <div class="tech-row">
            <span class="label green">긍정</span>
            {pub.get('positive_aspect', '발전된 기술/결과')}
          </div>
          <div class="tech-row">
            <span class="label orange">제한</span>
            {pub.get('limitation', 'GNE 직접 적용은 추가 연구 필요')}
          </div>
          <div class="tech-row">
            <span class="label gray">현실</span>
            {pub.get('realistic_impact', 'GNE 적용까지 시간 소요')}
          </div>
        </div>
      </div>
""")
    
    html_parts.append("    </div>")  # tech-signals 닫기

# 부정적 신호 섹션
if negative_signals:
    html_parts.append("""
    <div class="tech-signals">
      <h4 class="signal-header negative">⚠️ 주의 신호</h4>
""")
    
    for pub in negative_signals[:2]:  # 상위 2개만
        html_parts.append(f"""
      <div class="tech-card">
        <div class="tech-card-header">
          <span class="tech-title">{pub['title']}</span>
          <span class="distance-badge lesson">교훈</span>
        </div>
        <div class="tech-card-body">
          <div class="tech-row">
            <span class="label orange">제한</span>
            {pub.get('limitation', '실패/중단 사유')}
          </div>
          <div class="tech-row">
            <span class="label gray">GNE 관점</span>
            {pub.get('gne_perspective', '동일한 과제 예상')}
          </div>
        </div>
      </div>
""")
    
    html_parts.append("    </div>")  # tech-signals 닫기

# 기술-질환 거리 테이블
html_parts.append("""
    <div class="distance-table-wrapper">
      <h4>📊 기술-질환 거리 평가</h4>
      <table class="distance-table">
        <thead>
          <tr>
            <th>기술</th>
            <th>GNE와 거리</th>
            <th>현재 단계</th>
            <th>영향 시점</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>AAV 벡터 개선</td>
            <td><span class="badge-distance near">중기 가능성</span></td>
            <td>플랫폼 발전</td>
            <td>3-5년</td>
          </tr>
          <tr>
            <td>근육 타겟 LNP</td>
            <td><span class="badge-distance high">매우 중요</span></td>
            <td>전임상</td>
            <td>5-7년</td>
          </tr>
          <tr>
            <td>AI 단백질 예측</td>
            <td><span class="badge-distance low">간접 영향</span></td>
            <td>연구 도구</td>
            <td>진행 중</td>
          </tr>
          <tr>
            <td>CRISPR 근육 전달</td>
            <td><span class="badge-distance long">장기 가능성</span></td>
            <td>초기 연구</td>
            <td>10년+</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>  <!-- layer2-section 닫기 -->
""")


# ============================================================
# STEP 2: ZONE 3 Collapsible 섹션에 Layer 3 추가
# ============================================================

# 기존 Collapsible 3개 뒤에 추가:

# Layer 3 데이터 조회
layer3_news = db.execute("""
    SELECT * FROM news 
    WHERE layer = 3 
    ORDER BY published_date DESC
    LIMIT 10
""").fetchall()

html_parts.append("""
  <!-- Collapsible 4: 바이오 생태계 변화 -->
  <div class="collapsible">
    <div class="collapsible-header" onclick="toggleCollapse(this.parentElement)">
      <div class="collapsible-title">🌐 바이오 생태계 변화 (배경)</div>
      <div class="collapsible-badge">⚠️ 영향까지 5-10년</div>
      <div class="collapsible-icon">▼</div>
    </div>
    <div class="collapsible-content">
      <div class="collapsible-body">
        
        <div class="warning-banner">
          산업 투자 트렌드 ≠ 치료제 출시. 
          실제 환자 혜택까지는 긴 검증 시간이 필요합니다.
        </div>
        
        <div class="ecosystem-section">
          <h4>📈 투자 동향</h4>
""")

# Layer 3 투자 뉴스
investment_news = [n for n in layer3_news if 'investment' in n['title'].lower() or 'funding' in n['title'].lower()]
for news in investment_news[:3]:
    html_parts.append(f"""
          <div class="tech-card">
            <div class="tech-card-header">
              <span class="tech-title">{news['title']}</span>
            </div>
            <div class="tech-card-body">
              <div class="tech-row">
                <span class="label gray">GNE 관점</span>
                희귀병 신약개발 속도 증가 가능성
              </div>
              <div class="tech-row">
                <span class="label orange">현실</span>
                투자 → 승인까지 평균 10-15년 소요
              </div>
            </div>
          </div>
""")

html_parts.append("""
        </div>  <!-- ecosystem-section 닫기 -->
        
        <div class="ecosystem-section">
          <h4>🧬 플랫폼 기술</h4>
""")

# Layer 3 플랫폼 기술 뉴스
platform_news = [n for n in layer3_news if 'AI' in n['title'] or 'AlphaFold' in n['title'] or 'platform' in n['title'].lower()]
for news in platform_news[:3]:
    html_parts.append(f"""
          <div class="tech-card">
            <div class="tech-card-header">
              <span class="tech-title">{news['title']}</span>
            </div>
            <div class="tech-card-body">
              <div class="tech-row">
                <span class="label green">발전</span>
                {news.get('summary', '기술 발전 내용')}
              </div>
              <div class="tech-row">
                <span class="label orange">제한</span>
                기술 발전 ≠ 치료제 개발
              </div>
            </div>
          </div>
""")

html_parts.append("""
        </div>  <!-- ecosystem-section 닫기 -->
        
      </div>  <!-- collapsible-body 닫기 -->
    </div>  <!-- collapsible-content 닫기 -->
  </div>  <!-- collapsible 닫기 -->
""")


# ============================================================
# STEP 3: 현실 체크 섹션 추가 (맨 아래)
# ============================================================

html_parts.append("""
  <!-- ══ 현실 체크 섹션 ══ -->
  <div class="section reality-check-section">
    <div class="section-header">
      <div class="section-title">📏 현실 체크</div>
    </div>
    
    <div class="reality-grid">
      <div class="reality-card immediate">
        <div class="reality-header">
          <span class="reality-icon">✅</span>
          <span class="reality-title">실제로 곧 도움이 될 것</span>
        </div>
        <div class="reality-content">
          <ul>
""")

# 즉시 도움될 항목 (진행 중 임상시험 등)
recruiting_trials = db.execute("""
    SELECT * FROM clinical_trials 
    WHERE status IN ('RECRUITING', 'ENROLLING_BY_INVITATION')
    AND layer = 1
    LIMIT 3
""").fetchall()

for trial in recruiting_trials:
    html_parts.append(f"""
            <li>{trial['brief_title']} (모집 중)</li>
""")

if not recruiting_trials:
    html_parts.append("""
            <li>현재 없음</li>
""")

html_parts.append("""
          </ul>
        </div>
      </div>
      
      <div class="reality-card near-term">
        <div class="reality-header">
          <span class="reality-icon">🔶</span>
          <span class="reality-title">3-5년 내 가능성</span>
        </div>
        <div class="reality-content">
          <ul>
            <li>GNE 유전자치료 전임상 시작 (예정)</li>
            <li>AAV 전달 기술 플랫폼 발전</li>
            <li>근육 타겟 LNP 기술</li>
          </ul>
        </div>
      </div>
      
      <div class="reality-card long-term">
        <div class="reality-header">
          <span class="reality-icon">⏳</span>
          <span class="reality-title">10년 이상 걸릴 것</span>
        </div>
        <div class="reality-content">
          <ul>
            <li>AI 기반 맞춤 치료</li>
            <li>CRISPR 유전자 편집</li>
            <li>완전 치료법 개발</li>
          </ul>
        </div>
      </div>
    </div>
    
    <div class="reality-reminder">
      <h4>💡 기억하세요</h4>
      <ul>
        <li>연구 발표 → FDA 승인: 평균 10-15년</li>
        <li>투자 증가 ≠ 치료제 출시</li>
        <li>다른 질환 성공 ≠ GNE 적용 보장</li>
      </ul>
    </div>
  </div>
""")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 끝. 이 코드를 pipeline.py의 _write_html() 함수에 삽입
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
