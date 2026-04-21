# Interview Question Bank (v3.1.0, Sprint 1)

> Purpose: samvil-interview가 phase별로 실제 물어볼 질문 pool. Domain별 25~30개 Q 포함. v3-022 fix (f) "Domain pack 확장" 구현.
>
> **중요**: 이 파일은 예시 pool이다. 실제 인터뷰에서는 사용자 맥락에 맞게 agent가 재구성하되, 여기 질문 카테고리를 참조해 빠짐 없이 커버해야 한다.

---

## Common Pool (모든 solution_type 공통)

### Non-functional (Phase 2.6 — thorough+ 의무)

1. **Performance**: "첫 화면 로딩 목표 시간이 있나요? (기본: 2.5초 이내)"
2. **Accessibility**: "키보드만으로 모든 기능이 동작해야 하나요? (WCAG AA)"
3. **Security**: "이 앱이 다루는 가장 민감한 데이터는? (개인정보/결제/기업 기밀/없음)"
4. **Data retention**: "사용자가 탈퇴하면 데이터는 몇 일 후 삭제되나요?"
5. **Offline**: "네트워크 끊어져도 기본 동작해야 하나요?"
6. **i18n**: "한국어 외 언어 지원이 필요한가요? (영어/일본어/중국어/없음)"
7. **Error UX**: "치명적 에러 발생 시 사용자에게 어떻게 보여줄까요? (toast / full-page / inline)"

### Inversion (Phase 2.7 — thorough+ 의무)

8. **Failure Path**: "이 앱이 6개월 후 폐기된다면, 가장 가능성 높은 이유 3가지는?" (multiSelect)
9. **Exclusions**: "이 앱이 **절대로** 다루지 않을 것은?" (multiSelect)
10. **Anti-requirements**: "사용자가 **못 하게** 막아야 할 것은?" (예: 중복가입, 권한 escalation)
11. **Abuse vectors**: "악의적 사용자가 어떻게 남용할 수 있을까요?" (spam/자동화 봇/결제 우회)

### Stakeholder / JTBD (Phase 2.8 — full+ 의무)

12. **Primary user JTBD**: "매일 여는 주 사용자의 상황을 1문장으로: When <상황>, I want to <동기>, so I can <결과>."
13. **Secondary user**: "가끔 협업/관리하는 다른 역할이 있나요? (admin/reviewer/관찰자/없음)"
14. **Decision maker**: "누가 이 앱 사용을 결정하나요? (사용자 본인/팀장/회사 IT/개인)"
15. **Payer**: "결제가 필요하다면 누가 돈을 내나요? (사용자/회사/무료)"
16. **Motivation vs Means**: "엑셀/노션/종이 대신 이 앱을 써야 하는 결정적 이유는?"

### Customer Lifecycle (Phase 2.9 — standard+ 의무, 8단계)

17. **Discovery**: "사용자가 이 앱을 어떻게 알게 되나요? (검색/추천/광고/지인/오프라인 미팅)"
18. **First Open**: "처음 5초에 뭘 보나요? 로그인 없이 볼 수 있나요? empty state는?"
19. **Onboarding**: "가입 강제? tutorial? sample data? — 어떤 조합?"
20. **Activation (Aha moment)**: "사용자가 '아 이거 좋네'라고 느끼는 순간을 1문장으로 표현하면?"
21. **Habit**: "매일/매주 다시 오는 이유는? push/email 알림 정책?"
22. **Completion**: "다 쓰면? (게임 클리어/할일 완수/콘텐츠 소진) — 다음 행동은?"
23. **Re-engagement**: "한 달 떠난 사용자 win-back 전략 — 아예 없음/이메일/할인/개인화?"
24. **Churn**: "이탈 신호 감지 방법? 이탈 시 데이터 정책은? (즉시 삭제/30일 유예)"

---

## Domain Pack: Web App (solution_type: web-app)

기본 Phase 1~2 질문 (5개) + 도메인 특화 15개.

### Data & Persistence

25. **Storage**: "데이터를 어디에 저장하나요? (localStorage/Supabase/직접 DB/다른 서비스)"
26. **Auth**: "로그인이 필요한가요? 어떤 방식? (없음/이메일/OAuth/magic link)"
27. **Real-time**: "여러 사용자가 같은 데이터를 동시에 보나요? (솔로/읽기 공유/동시 편집)"
28. **Export**: "사용자가 자기 데이터를 내보낼 방법이 있나요? (CSV/JSON/PDF/없음)"

### UI / UX

29. **Layout**: "데스크톱 vs 모바일 비중은? (모바일 우선/둘 다/데스크톱 우선)"
30. **Dark mode**: "다크 모드 지원이 필요한가요?"
31. **Navigation**: "메뉴 구조는 어떤 형태? (탑 네비/사이드바/명령 팔레트/검색 중심)"
32. **Empty state**: "처음 열었을 때 빈 화면에 뭘 보여줄까요? (sample/온보딩/빈 상태 안내)"

### 기타

33. **SEO**: "검색 엔진에 노출돼야 하나요? (yes=SSR 필요)"
34. **Analytics**: "사용 행동을 측정할 이벤트 3개를 꼽으면?"
35. **Notifications**: "사용자에게 알림이 필요한가요? (이메일/브라우저 push/인앱 배너)"

---

## Domain Pack: Game (solution_type: game) — v3-013/014/015 반영

Phaser 3 기반 웹 게임. 기본 Phase 1~2 (4개) + 도메인 특화 25개.

### Architecture (v3-013)

36. **Single vs Multi**: "혼자 플레이? 같이 플레이? (solo / 로컬 2P / 온라인 멀티)"
37. **Account**: "로그인이 필요한가요? (익명/guest/이메일/OAuth/없음)"
38. **Data storage**: "진행 상황을 어디에 저장? (localStorage만/cloud 동기화/서버 필수)"
39. **Save policy**: "언제 저장되나요? (auto-save/수동/체크포인트)"
40. **Leaderboard**: "랭킹 시스템이 있나요? (글로벌/친구/없음)"
41. **Shop / IAP**: "아이템 상점이나 결제 요소가 있나요? (없음/단일 구매/소모재/구독)"
42. **Matchmaking**: "멀티라면 매칭을 어떻게? (친구 초대/랜덤/실력 기반)"

### Technical Spec (v3-014)

43. **Resolution**: "해상도 preset? (720x1280 portrait/1080x1920 portrait/1920x1080 landscape/태블릿)"
44. **Orientation**: "화면 방향? (세로 고정/가로 고정/둘 다)"
45. **Input**: "조작 방법은? (키보드/마우스/터치/멀티터치/게임패드)"
46. **Supported devices**: "iOS/Android/태블릿/데스크톱 중 어디를 지원?"
47. **Offline play**: "인터넷 끊어져도 플레이 가능해야 하나요?"
48. **Asset size budget**: "초기 로딩 데이터 크기 제한이 있나요? (~5MB / ~20MB / 무제한)"

### Art & Design (v3-015)

49. **Art style**: "캐릭터 아트 방향? (pixel 8-bit/16-bit/cartoon/심볼릭/3D render)"
50. **UI tone**: "UI 스타일? (minimal clean/판타지/SF/귀여운 파스텔/retro)"
51. **Animation level**: "애니메이션 수준? (정적/Tween만/스프라이트 시트/particle 포함)"
52. **Sound policy**: "BGM / SFX 정책? (풀 사운드/SFX만/음소거 기본)"
53. **HUD layout**: "HUD에 뭐가 보여야 하나요? (점수/체력/타이머/미니맵/인벤토리)"
54. **Character count**: "고유 캐릭터 수? (1명/2~5명/6+ /커스터마이징)"

### Gameplay

55. **Difficulty**: "난이도? (casual/normal/hard/난이도 선택 가능)"
56. **Level count**: "레벨이 몇 개? (1개/5~10/20+/프로시저 생성)"
57. **Game length**: "한 판 평균 플레이 시간? (<3분/3~10분/10~30분/무제한)"
58. **Replayability**: "재플레이 요소? (랜덤/업적/스코어 경쟁/없음)"
59. **Progression**: "성장 시스템? (경험치/언락/장비 강화/없음)"
60. **Enemy / obstacle**: "적/장애물 타입? (추격/패턴 공격/퍼즐/환경)"

---

## Domain Pack: Automation (solution_type: automation) — v3-025 반영

Python/Node.js script. 기본 Phase 1~2 (3개) + 도메인 특화 20개.

### Trigger & Schedule

61. **Trigger**: "언제 실행되나요? (수동/cron/webhook/파일 변경 감지)"
62. **Frequency**: "cron이면 몇 분/시간/일마다?"
63. **Concurrency**: "동시에 여러 instance 실행 가능? (아니면 lock 필요)"

### Input / Output

64. **Input source**: "입력 데이터는 어디서? (API/파일/DB/메시지 큐)"
65. **Input format**: "입력 포맷? (JSON/CSV/XML/YAML/기타)"
66. **Output destination**: "결과를 어디로? (파일/Slack/이메일/DB/다음 pipeline)"
67. **Output format**: "결과 포맷? (보고서/로그/알림 메시지/DB row)"

### External Integration (v3-025)

68. **AI / LLM API**: "LLM 호출이 필요? 어떤 모델? (Gemini/Claude/OpenAI/로컬)"
69. **Model version**: "모델 ID를 환경변수로? 버전 업데이트 대응은?"
70. **Rate limit**: "API rate limit 대응 전략? (exponential backoff/queue/무시)"
71. **Cost budget**: "월 API 비용 상한이 있나요? 초과 시 동작?"
72. **Slack / Discord**: "메시지 전송? 메시지 수신? 어떤 channel 정책?"

### Error Handling

73. **Retry policy**: "일시적 에러 재시도? (없음/3회 linear/exponential)"
74. **Permanent error**: "영구 에러 시? (로그만/알림/중단/건너뛰기)"
75. **Dead letter queue**: "실패한 항목을 모아서 수동 처리할 곳이 필요?"
76. **Monitoring**: "실행 성공/실패를 어떻게 관찰? (로그 파일/Sentry/대시보드)"

### Runtime

77. **Environment**: "어디서 실행? (로컬 Python/Docker/cloud function/GitHub Actions)"
78. **Secret management**: "API 키를 어떻게 보관? (.env/password manager/vault)"
79. **Dependencies**: "외부 패키지 제약? (벤더 lock 회피/언어 버전 고정)"
80. **Logging**: "로그를 파일로? stdout? structured JSON?"

---

## Domain Pack: Mobile (solution_type: mobile-app)

Expo React Native. 기본 Phase 1~2 (3개) + 도메인 특화 15개.

### Platform

81. **Target OS**: "iOS만/Android만/둘 다? iOS 최소 버전?"
82. **Device type**: "phone만/tablet 포함/foldable 고려?"
83. **Orientation**: "portrait 고정/landscape/auto-rotate?"
84. **Web preview**: "Claude Code 환경에서 웹 미리보기 활용?"

### Native Features

85. **Camera**: "카메라 사용? 사진/동영상/QR 스캔?"
86. **GPS**: "위치 권한 필요? foreground only / background?"
87. **Push**: "푸시 알림? remote (FCM/APNs) / local only?"
88. **Sensors**: "가속도/자이로/생체인증 사용?"
89. **Storage**: "로컬 저장소? AsyncStorage / SQLite / MMKV?"
90. **Background task**: "백그라운드 실행 필요? (iOS 제약 알림)"

### UX

91. **Navigation**: "네비게이션 패턴? (bottom tabs/drawer/stack)"
92. **Deep linking**: "외부 URL로 앱 내 특정 화면 열기 필요?"
93. **Haptic feedback**: "햅틱(진동) 피드백 사용?"
94. **Gesture**: "제스처(pinch/swipe) 필요?"
95. **Theme**: "라이트/다크 모드 동시 지원?"

---

## Domain Pack: Dashboard (solution_type: dashboard)

Next.js + chart 라이브러리. 기본 Phase 1~2 (3개) + 도메인 특화 15개.

### Data Source

96. **Source**: "데이터 출처? (DB/API/CSV upload/여러 소스)"
97. **Refresh**: "데이터 새로고침 주기? (realtime/polling 30s/daily)"
98. **Time range**: "기본 표시 기간? (today/7d/30d/사용자 선택)"
99. **Granularity**: "aggregation 단위? (minute/hour/day/week/month)"

### Visualization

100. **Chart types**: "주로 쓸 차트? (line/bar/pie/heatmap/table)"
101. **Drill-down**: "세부 데이터 보기 필요? (expand row / drawer / 별도 페이지)"
102. **Filtering**: "필터 차원? (날짜/카테고리/사용자/국가)"
103. **Comparison**: "전주 대비 / 전월 대비 비교 표시?"
104. **Alerts**: "임계값 초과 시 알림?"

### Export & Share

105. **Export format**: "PDF / CSV / 스크린샷?"
106. **Share**: "공유 링크 생성 (public URL)?"
107. **Schedule**: "정기 이메일 리포트?"

### Users

108. **Viewer vs Editor**: "역할 구분? (viewer/editor/admin)"
109. **Team**: "여러 팀/워크스페이스 분리?"
110. **SSO**: "기업 SSO 필요? (SAML/OIDC)"

---

## 사용 방법 (agent용)

1. 이 파일을 agent persona가 직접 참조 (read) — 전체 110개를 매번 로드하지 않음
2. `solution_type`이 결정되면 common(24) + 해당 domain pack만 읽기
3. Phase 순서는 SKILL.md의 Phase 1 → 2 → 2.5 → 2.6 → 2.7 → 2.8 → 2.9 → 3 순서 준수
4. tier 매트릭스(`interview-frameworks.md` § 7)에 따라 Phase 활성화 여부 결정
5. 실제 질문은 **사용자 맥락에 맞게 agent가 재문장화** — 이 파일의 문구를 그대로 읽지 않음
6. **한 번에 하나씩** — Phase 내에서도 multiSelect로 합치되 서로 다른 카테고리는 섞지 않음

---

_작성: 2026-04-21 · v3.1.0 Sprint 1_
