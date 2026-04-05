# App Type Presets

> 앱 유형별 기본값. 인터뷰에서 preset 매칭 시 질문을 줄이고 품질을 높임.
> preset 없는 앱 유형은 competitor-analyst가 실시간 서치.

## todo / task-manager
- **추천 스택**: nextjs (SSR/SEO 불필요하면 vite-react도 가능)
- **기본 기능**: CRUD, 목록 보기, 완료 토글, 정렬/필터
- **자주 추가**: 칸반, 태그, 마감일, 우선순위, 반복
- **data model**: `{ id, title, status, priority, dueDate, tags[], createdAt }`
- **추천 state**: zustand (persist)
- **추천 UI preset**: productivity
- **흔한 함정**:
  - 수정(Update) 빼먹음 — CRUD에서 U
  - 빈 상태 안 만듦 — 할일 0개일 때 안내 없음
  - 삭제 확인 없음 — 실수로 지움
  - 데이터 유지 안 됨 — 새로고침하면 사라짐
- **Pre-mortem**: "1주 후 삭제 이유?" → 동기화 안 됨, 너무 복잡, 알림 없음

## dashboard / analytics
- **추천 스택**: nextjs (API routes + SSR)
- **기본 기능**: 요약 카드, 차트, 기간 필터, 테이블
- **자주 추가**: 실시간 갱신, CSV 내보내기, 드릴다운
- **data model**: `{ metric, value, date, category }`
- **추천 state**: zustand + API fetching
- **추천 UI preset**: productivity
- **흔한 함정**:
  - 데이터 없을 때 빈 차트
  - 로딩 상태 없음
  - 모바일에서 테이블 깨짐
- **Pre-mortem**: "안 쓰게 되는 이유?" → 데이터 수동 입력 귀찮음, 인사이트 부족

## landing-page
- **추천 스택**: astro (정적, 빠른 로딩)
- **기본 기능**: 히어로, 기능 소개 3-4개, CTA, 소셜 프루프, 푸터
- **자주 추가**: 가격표, FAQ, 뉴스레터 구독, 데모 비디오
- **data model**: 없음 (정적)
- **추천 state**: 없음
- **추천 UI preset**: minimal 또는 creative
- **흔한 함정**:
  - CTA 링크 없음
  - 모바일 반응형 빠뜨림
  - 로딩 느림 (이미지 최적화 안 함)
- **Pre-mortem**: "전환율 0%인 이유?" → 가치 제안 불명확, CTA 안 보임

## blog / content
- **추천 스택**: nextjs (SSR + SEO)
- **기본 기능**: 글 목록, 글 상세, 카테고리, 마크다운 렌더링
- **자주 추가**: 검색, 태그, 댓글, RSS
- **data model**: `{ id, title, content, category, tags[], publishedAt }`
- **추천 state**: zustand 또는 API
- **추천 UI preset**: creative
- **흔한 함정**:
  - 마크다운 렌더링 라이브러리 선택 안 함
  - SEO 메타데이터 빠뜨림
  - 글이 0개일 때 빈 화면

## e-commerce / shop
- **추천 스택**: nextjs (SSR + API routes)
- **기본 기능**: 상품 목록, 상품 상세, 장바구니, 체크아웃
- **자주 추가**: 검색, 필터, 위시리스트, 리뷰
- **data model**: `{ id, name, price, image, category, stock, description }`
- **추천 state**: zustand (cart persist)
- **추천 UI preset**: minimal
- **흔한 함정**:
  - 결제 연동 복잡도 과소평가
  - 재고 관리 안 함
  - 모바일 상품 이미지 최적화
- **Pre-mortem**: "구매 전환 0%인 이유?" → 결제 복잡, 신뢰 부족, 배송 정보 없음

## calculator / utility
- **추천 스택**: vite-react (가벼움, SSR 불필요)
- **기본 기능**: 입력 인터페이스, 계산 로직, 결과 표시
- **자주 추가**: 히스토리, 단위 변환, 테마
- **data model**: 없음 또는 minimal
- **추천 state**: useState (단순)
- **추천 UI preset**: minimal
- **흔한 함정**:
  - 키보드 입력 안 됨
  - 0 나누기 에러 처리 없음
  - 소수점 처리 부정확

## kanban / project-board
- **추천 스택**: nextjs (상태 복잡 → zustand persist)
- **기본 기능**: 칼럼 CRUD, 카드 CRUD, 드래그앤드롭
- **자주 추가**: 라벨, 담당자, 마감일, 필터
- **data model**: `{ board: { columns: [{ id, title, cards: [{ id, title, description }] }] } }`
- **추천 state**: zustand (persist)
- **추천 UI preset**: productivity
- **추천 library**: @hello-pangea/dnd
- **흔한 함정**:
  - 모바일 터치 DnD 안 됨
  - 칼럼 삭제 시 카드 처리 정책 없음
  - 카드 순서 persist 안 됨

## chat / messaging
- **추천 스택**: nextjs (API routes + 실시간)
- **기본 기능**: 메시지 입력, 메시지 목록, 타임스탬프
- **자주 추가**: 실시간, 읽음 표시, 이미지/파일, 이모지
- **data model**: `{ id, sender, content, timestamp, type }`
- **추천 state**: zustand + WebSocket (또는 polling)
- **추천 UI preset**: minimal
- **흔한 함정**:
  - 자동 스크롤 안 됨 (새 메시지가 보이지 않음)
  - 메시지 시간순 정렬 오류
  - 긴 메시지 레이아웃 깨짐

## portfolio / personal-site
- **추천 스택**: astro (정적, SEO 우수)
- **기본 기능**: 소개, 프로젝트 갤러리, 연락처, 이력
- **자주 추가**: 블로그, 다크모드, 애니메이션
- **data model**: 없음 (정적) 또는 minimal
- **추천 state**: 없음
- **추천 UI preset**: creative
- **흔한 함정**:
  - 프로젝트 이미지 최적화 안 됨
  - 모바일 내비게이션 없음
  - 연락처 폼 동작 안 함

## form-builder / survey
- **추천 스택**: nextjs (복잡한 상태 관리)
- **기본 기능**: 질문 추가/편집, 폼 미리보기, 응답 수집
- **자주 추가**: 조건 분기, 파일 업로드, 결과 통계
- **data model**: `{ form: { questions: [{ id, type, label, options?, required }] }, responses: [] }`
- **추천 state**: zustand (persist)
- **추천 UI preset**: minimal
- **흔한 함정**:
  - 질문 유형별 UI 미구현
  - 유효성 검사 빠뜨림
  - 응답 데이터 export 없음

---

## Preset 매칭 방법

인터뷰 시작 시 앱 아이디어에서 키워드 매칭:

```
"할일" / "todo" / "task" → todo
"대시보드" / "dashboard" / "analytics" → dashboard
"랜딩" / "landing" / "소개 페이지" → landing-page
"블로그" / "blog" / "글" → blog
"쇼핑" / "상점" / "e-commerce" → e-commerce
"계산기" / "calculator" / "변환기" → calculator
"칸반" / "kanban" / "보드" → kanban
"채팅" / "chat" / "메시징" → chat
"포트폴리오" / "portfolio" / "개인 사이트" → portfolio
"폼" / "설문" / "survey" → form-builder
```

매칭 안 되면 → competitor-analyst로 서치 → 결과 기반 임시 preset 생성.
