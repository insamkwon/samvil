---
name: samvil-analyze
description: "기존 프로젝트 코드 분석. 구조 파악 → 역방향 seed 생성 → gap 분석. Brownfield 모드의 첫 단계."
---

# SAMVIL Analyze — 기존 프로젝트 코드 분석

기존 코드베이스를 분석해서 현재 상태를 이해하고, 역방향으로 seed.json을 생성한다. Brownfield 모드의 첫 단계.

**모든 대화는 한국어로.** 코드와 기술 용어만 영어.

## 언제 사용

- `/samvil` → "기존 프로젝트 개선" 선택 시 자동 호출
- `/samvil:analyze` 로 직접 호출 가능
- 기존 프로젝트에 SAMVIL 파이프라인을 적용하고 싶을 때

## Step 0: Git 안전망

분석 시작 전, 프로젝트의 git 상태를 확인하여 데이터 손실을 방지한다.

경로 확인 후 (Step 1 이후) 바로 실행:

```bash
cd <project-path>
git status --porcelain 2>/dev/null
GIT_EXIT=$?
```

| 결과 | 행동 |
|------|------|
| `$GIT_EXIT != 0` (git 아님) | `[SAMVIL] ⚠️ Git 저장소가 아닙니다. git init을 권장합니다.` → AskUserQuestion: "git init 할까요?" (예/아니오, 진행) |
| `git status --porcelain` 출력 없음 (clean) | `[SAMVIL] ✓ Git: clean` → 진행 |
| `git status --porcelain` 출력 있음 (dirty) | `[SAMVIL] ⚠️ Git: uncommitted changes 감지` → AskUserQuestion: "커밋하고 진행할까요?" (커밋 후 진행 / 그냥 진행 / 중단) |

**"커밋 후 진행"** 선택 시:
```bash
git add -A && git commit -m "chore: save state before SAMVIL analyze"
```

## Step 1: 프로젝트 경로 확인

AskUserQuestion으로:
```
question: "분석할 프로젝트 경로를 알려주세요"
header: "프로젝트"
options:
  - label: "현재 디렉토리" — description: pwd 결과 표시
  - label: "경로 직접 입력" — Other로 입력
```

경로 확인 후:
```bash
test -d "<path>" && echo "EXISTS" || echo "NOT FOUND"
test -f "<path>/package.json" && echo "HAS_PACKAGE_JSON" || echo "NO_PACKAGE_JSON"
```

**→ Step 0 (Git 안전망) 실행 후 Step 2로 진행.**

## Step 2: 프레임워크 감지

```bash
cd <project-path>
```

### 2a. package.json 분석

```bash
cat package.json
```

감지 항목:
- `dependencies`에서 프레임워크: next, react, vue, svelte, express 등
- `devDependencies`에서 도구: typescript, tailwindcss, eslint 등
- `scripts`에서 빌드/실행 명령

### 2b. 설정 파일 감지

```bash
ls -la next.config.* tsconfig.json tailwind.config.* postcss.config.* .eslintrc* vite.config.* 2>/dev/null
```

### 2c. 프레임워크 판정

| 감지 | 판정 |
|------|------|
| next in deps + next.config.* | Next.js |
| react in deps + vite.config.* | React (Vite) |
| vue in deps | Vue.js |
| express in deps | Express/Node |
| 없음 | 정적 HTML 또는 식별 불가 |

## Step 3: 코드 구조 분석

### 3a. 디렉토리 구조

```bash
# 전체 구조 (node_modules 제외)
find . -type f -not -path '*/node_modules/*' -not -path '*/.next/*' -not -path '*/.git/*' -not -name '*.lock' | head -100
```

### 3b. 페이지/라우트 파악

```bash
# Next.js App Router
find app -name "page.tsx" -o -name "page.ts" -o -name "page.jsx" 2>/dev/null

# Next.js Pages Router
find pages -name "*.tsx" -o -name "*.ts" -o -name "*.jsx" 2>/dev/null

# 일반 React
find src -name "*.tsx" -o -name "*.jsx" 2>/dev/null | head -30
```

### 3c. 컴포넌트 파악

```bash
# components 폴더
find components -name "*.tsx" -o -name "*.jsx" 2>/dev/null

# src/components
find src/components -name "*.tsx" -o -name "*.jsx" 2>/dev/null
```

### 3d. 상태관리 감지

Grep으로 감지:
```
zustand → "from 'zustand'" 또는 "from \"zustand\""
redux → "from '@reduxjs/toolkit'" 또는 "from 'redux'"
recoil → "from 'recoil'"
jotai → "from 'jotai'"
context → "createContext"
useState만 → 별도 상태관리 없음
```

### 3e. 데이터 소스 감지

```
localStorage → "localStorage.getItem" 또는 "localStorage.setItem"
supabase → "from '@supabase'"
prisma → "from '@prisma/client'"
firebase → "from 'firebase'"
API routes → app/api/ 또는 pages/api/ 존재 여부
fetch/axios → "fetch(" 또는 "from 'axios'"
```

### 3f. UI 라이브러리 감지

```
tailwind → tailwind.config.* 존재
shadcn/ui → components/ui/ 존재 + components.json
MUI → "@mui/material"
Chakra → "@chakra-ui/react"
CSS Modules → *.module.css 존재
Styled Components → "styled-components"
```

## Step 4: 분석 결과 표시

```
[SAMVIL] 프로젝트 분석 결과
━━━━━━━━━━━━━━━━━━━━━━━━━━━

경로: ~/dev/<project>/
프레임워크: Next.js 14 (App Router)
언어: TypeScript

구조:
  페이지: 5개 (/, /about, /dashboard, /settings, /api/tasks)
  컴포넌트: 12개 (components/)
  UI 컴포넌트: 4개 (components/ui/ — shadcn/ui 감지)
  lib: 3개 파일

상태관리: zustand (lib/store.ts)
데이터: localStorage + API Routes
UI: Tailwind CSS + shadcn/ui
인증: 없음

기존 기능 (감지됨):
  1. task-crud — TaskForm, TaskList 컴포넌트
  2. dashboard — DashboardPage
  3. settings — SettingsPage

외부 라이브러리:
  - @hello-pangea/dnd (드래그앤드롭)
  - date-fns (날짜 처리)
  - nanoid (ID 생성)

코딩 컨벤션:
  컴포넌트: 함수형 (export function)
  파일명: PascalCase.tsx
  폴더: feature별
  API: fetch + try-catch

재사용 가능:
  UI: Button, Card, Input (shadcn/ui)
  훅: useAuth, useToast
  유틸: cn(), formatDate()

통합 포인트:
  페이지: app/<feature>/page.tsx
  메뉴: Sidebar.tsx → navItems[]
  스토어: lib/store.ts
  타입: lib/types.ts

의존성 영향:
  고: layout.tsx(5p), store.ts(8c), types.ts(12f)
  중: Button(15), Card(8)
```

## Step 4b: 코딩 컨벤션 자동 감지

기존 코드의 스타일을 파악해서, 새 코드도 같은 스타일로 작성하도록.

### 컴포넌트 패턴

```bash
# 함수형 vs 화살표 — 다수결로 판정
grep -r "^export function\|^export default function" --include="*.tsx" . | grep -v node_modules | wc -l
grep -r "^export const.*=.*=>" --include="*.tsx" . | grep -v node_modules | wc -l
# 많은 쪽이 이 프로젝트의 컨벤션
```

### 파일/폴더 규칙

```bash
# 파일명 패턴 — PascalCase? kebab-case? camelCase?
ls components/**/*.tsx 2>/dev/null | head -20
# TaskCard.tsx → PascalCase | task-card.tsx → kebab | taskCard.tsx → camelCase

# 폴더 구조 — feature별? 유형별?
ls -d components/*/ 2>/dev/null | head -10
# components/tasks/, components/auth/ → feature별
# components/buttons/, components/forms/ → 유형별

# index.ts barrel export 사용 여부
find . -name "index.ts" -not -path "*/node_modules/*" | wc -l
```

### API/데이터 패턴

```bash
# fetch vs axios vs React Query
grep -r "from 'axios'" --include="*.ts" --include="*.tsx" . | grep -v node_modules | wc -l
grep -r "@tanstack/react-query\|from 'swr'" --include="*.ts" --include="*.tsx" . | grep -v node_modules | wc -l
grep -r "fetch(" --include="*.ts" --include="*.tsx" . | grep -v node_modules | wc -l
```

### export 패턴

```bash
# default export vs named export
grep -r "^export default" --include="*.tsx" . | grep -v node_modules | wc -l
grep -r "^export function\|^export const" --include="*.tsx" . | grep -v node_modules | wc -l
```

### 컨벤션 결과

```
[SAMVIL] 코딩 컨벤션
  컴포넌트: 함수형 선언 (export function X)
  파일명: PascalCase.tsx
  폴더: feature별 (components/tasks/, components/auth/)
  export: named export
  API: fetch + try-catch
  상태: Zustand slice 패턴
  index.ts: 사용 안 함
```

→ `interview-summary.md`에 컨벤션 섹션 추가, build 스킬이 참조.

## Step 4c: 재사용 가능 컴포넌트 맵

이미 만들어진 것을 파악해서 중복 생성 방지.

### UI 컴포넌트

```bash
# shadcn/ui 컴포넌트 (components/ui/)
ls components/ui/*.tsx 2>/dev/null
# → Button.tsx, Card.tsx, Input.tsx, Dialog.tsx 등

# 커스텀 공통 컴포넌트
ls components/*.tsx 2>/dev/null | grep -v -E "page|layout"
```

### 커스텀 훅

```bash
find . -name "use*.ts" -o -name "use*.tsx" | grep -v node_modules | grep -v ".d.ts"
# → useAuth.ts, useToast.ts, useFetch.ts 등
```

### 유틸리티

```bash
ls lib/*.ts 2>/dev/null
# → utils.ts (cn()), types.ts, store.ts, storage.ts 등
```

### 레이아웃 컴포넌트

```bash
# layout.tsx 계층
find app -name "layout.tsx" 2>/dev/null
# 공통 레이아웃 컴포넌트
grep -rl "Header\|Sidebar\|Footer\|Navbar\|Navigation" --include="*.tsx" components/ 2>/dev/null
```

### 재사용 맵 결과

```
[SAMVIL] 재사용 가능 컴포넌트
  UI (shadcn): Button, Card, Input, Dialog, Toast
  훅: useAuth(), useToast(), useMediaQuery()
  유틸: cn(), formatDate(), getItems(), setItems()
  레이아웃: Header, Sidebar, MainLayout
  
  → 새 기능 구현 시 위 컴포넌트를 우선 사용. 직접 만들지 말 것.
```

## Step 4d: 통합 포인트 제안

새 기능을 추가할 때 **어떤 파일을 어디에** 추가/수정해야 하는지 분석.

### 라우팅 분석

```bash
# App Router 구조 — 새 페이지 추가 위치
find app -name "page.tsx" -o -name "route.ts" | sort
# → app/page.tsx, app/dashboard/page.tsx, app/settings/page.tsx
# → 새 페이지는 app/<feature>/page.tsx에 추가
```

### 네비게이션 분석

```bash
# 메뉴/네비게이션 항목이 정의된 파일 찾기
grep -rl "navItems\|menuItems\|routes\|navigation\|sidebar.*items\|menu.*links" --include="*.tsx" --include="*.ts" . | grep -v node_modules
# → 이 파일에 새 메뉴 항목 추가
```

### 데이터 레이어 분석

```bash
# store 파일에서 기존 slice/state 구조 파악
cat lib/store.ts 2>/dev/null | head -50
# → 새 기능의 상태를 여기에 추가

# types 파일에서 기존 인터페이스 파악
cat lib/types.ts 2>/dev/null
# → 새 기능의 타입을 여기에 추가
```

### 통합 포인트 결과

```
[SAMVIL] 통합 포인트 (새 기능 추가 시)
  페이지 추가: app/<feature>/page.tsx
  메뉴 추가: components/Sidebar.tsx → navItems[] 배열
  스토어 추가: lib/store.ts → 새 slice 추가
  타입 추가: lib/types.ts → 새 interface 추가
  API 추가: app/api/<feature>/route.ts
  컴포넌트: components/<feature>/<Component>.tsx
```

## Step 4e: 의존성 영향 분석

기존 파일을 수정하면 **어디가 영향받는지** 파악.

### 공유 파일 영향도

핵심 공유 파일별 import 역추적:

```bash
# layout.tsx를 import하는 곳 (자동 — App Router 하위 모든 page)
find app -name "page.tsx" | wc -l
# → layout.tsx 수정 시 N개 페이지 영향

# store.ts를 import하는 곳
grep -rl "from.*store\|from.*lib/store" --include="*.tsx" --include="*.ts" . | grep -v node_modules | wc -l

# types.ts를 import하는 곳
grep -rl "from.*types\|from.*lib/types" --include="*.tsx" --include="*.ts" . | grep -v node_modules | wc -l

# 각 컴포넌트의 사용처
for comp in $(ls components/ui/*.tsx 2>/dev/null | xargs -I{} basename {} .tsx); do
  count=$(grep -rl "$comp" --include="*.tsx" . | grep -v node_modules | wc -l | tr -d ' ')
  echo "  $comp: ${count}곳에서 사용"
done
```

### 영향도 결과

```
[SAMVIL] 의존성 영향 분석
  고영향 (수정 주의):
    layout.tsx → 5개 페이지 영향
    store.ts → 8개 컴포넌트가 import
    types.ts → 12개 파일이 참조
    
  중영향:
    Button → 15곳에서 사용
    Card → 8곳에서 사용
    
  저영향 (안전하게 수정 가능):
    components/settings/ → 1개 페이지에서만 사용
    
  → 고영향 파일 수정 시 관련 페이지 전체 확인 필요
```

## Step 4f: 코드 품질 스캔 (기존)

Grep으로 자동 감지하는 코드 품질 지표:

### 기술 부채 감지

```bash
# TypeScript any 사용
grep -r ":\s*any" --include="*.ts" --include="*.tsx" . | grep -v node_modules | wc -l

# console.log 잔존
grep -r "console\.log" --include="*.ts" --include="*.tsx" . | grep -v node_modules | wc -l

# TODO/FIXME/HACK 코멘트
grep -rE "TODO|FIXME|HACK|XXX" --include="*.ts" --include="*.tsx" . | grep -v node_modules | wc -l

# 미사용 import (간이 체크 — 정확도 80%)
# eslint가 있으면 eslint --quiet로 대체
```

### 보안 리스크 감지

```bash
# dangerouslySetInnerHTML
grep -r "dangerouslySetInnerHTML" --include="*.tsx" . | grep -v node_modules

# 하드코딩된 시크릿 후보
grep -rE "(password|secret|api_key|token|PRIVATE)" --include="*.ts" --include="*.tsx" --include="*.env*" . | grep -v node_modules | grep -v ".env.example"

# .env 파일이 gitignore에 있는지
grep "\.env" .gitignore 2>/dev/null
```

### 구조 리스크 감지

```bash
# 200줄 넘는 컴포넌트 (분리 필요 신호)
find . -name "*.tsx" -not -path "*/node_modules/*" -exec wc -l {} + | sort -rn | head -10

# 에러 핸들링 부재 (try-catch 없는 fetch/API 호출)
grep -r "fetch(" --include="*.ts" --include="*.tsx" . | grep -v node_modules | wc -l
grep -r "try" --include="*.ts" --include="*.tsx" . | grep -v node_modules | wc -l
```

### 자동 GAP 감지

코드에서 **빠져있을 가능성이 높은 것** 자동 탐지:

```bash
# 빈 상태 처리 여부 (리스트 컴포넌트에 length === 0 체크)
grep -r "length === 0\|\.length === 0\|isEmpty\|no.*items\|no.*data" --include="*.tsx" . | grep -v node_modules | wc -l

# 로딩 상태 (Skeleton, Loading, Spinner)
grep -rE "loading|isLoading|Skeleton|Spinner" --include="*.tsx" . | grep -v node_modules | wc -l

# 에러 상태 (Error Boundary, error state)
grep -rE "ErrorBoundary|error\.\|isError\|onError" --include="*.tsx" . | grep -v node_modules | wc -l

# 반응형 (sm:|md:|lg: Tailwind 클래스)
grep -rE "sm:|md:|lg:|xl:" --include="*.tsx" . | grep -v node_modules | wc -l

# 접근성 (aria-label, role=)
grep -rE "aria-|role=" --include="*.tsx" . | grep -v node_modules | wc -l
```

### 품질 리포트 형식

분석 결과에 추가:

```
[SAMVIL] 코드 품질 스캔
━━━━━━━━━━━━━━━━━━━━━━

기술 부채:
  any 사용: 3곳 ⚠️
  console.log: 7곳 ⚠️
  TODO/FIXME: 2곳

보안:
  dangerouslySetInnerHTML: 0곳 ✓
  하드코딩 시크릿: 0곳 ✓
  .env gitignore: ✓

구조:
  200줄 초과 컴포넌트: 1개 (TaskBoard.tsx: 312줄) ⚠️
  fetch without try-catch: 2곳 ⚠️

GAP (누락 가능성):
  빈 상태 처리: 1곳만 발견 ⚠️ (리스트 5개 중 1개만)
  로딩 상태: 0곳 ❌
  에러 처리: 0곳 ❌
  반응형 클래스: 12곳 ✓
  접근성: 3곳 ⚠️

→ 개선 추천: 로딩/에러 상태 추가, console.log 정리, TaskBoard 분리
```

이 품질 리포트는 `.samvil/analysis-report.md`에 저장하고, QA/Build 단계에서 참조.

## Step 5: 역방향 Seed 생성

분석 결과를 기반으로 seed.json을 역으로 구성:

```json
{
  "name": "<project-name>",
  "description": "<package.json description 또는 추론>",
  "mode": "web",
  "tech_stack": {
    "framework": "<감지된 프레임워크>",
    "ui": "<감지된 UI 라이브러리>",
    "state": "<감지된 상태관리>",
    "router": "<감지된 라우터>"
  },
  "core_experience": {
    "description": "<메인 페이지 분석 기반 추론>",
    "primary_screen": "<메인 컴포넌트>",
    "key_interactions": ["<감지된 인터랙션>"]
  },
  "features": [
    { "name": "<감지된 기능>", "priority": 1, "independent": true, "status": "existing" }
  ],
  "acceptance_criteria": ["<기존 기능 기반 AC>"],
  "constraints": ["<감지된 제약>"],
  "out_of_scope": [],
  "version": 1,
  "_analysis": {
    "source": "brownfield",
    "analyzed_at": "<timestamp>",
    "files_scanned": "<count>",
    "framework_detected": "<framework>"
  }
}
```

**주의: features에 `"status": "existing"` 추가** — 기존에 있는 기능과 새로 추가할 기능 구분.

## Step 6: 유저 검토

```
[SAMVIL] 역방향 Seed 생성 완료
━━━━━━━━━━━━━━━━━━━━━━━━━━━

<seed JSON 표시>

이 분석이 맞나요?
```

AskUserQuestion:
```
question: "분석 결과가 정확한가요?"
options:
  - "맞아, 진행해" → Step 7
  - "수정할 부분 있어" → 수정 후 재확인
```

## Step 7: Gap 분석 — 원하는 개선 파악

AskUserQuestion:
```
question: "이 프로젝트에서 뭘 하고 싶으세요?"
header: "개선 목표"
options:
  - label: "기능 추가"
    description: "새 기능을 추가합니다"
  - label: "코드 품질 개선"
    description: "리팩토링, 타입 정리, 구조 개선"
  - label: "디자인 개선"
    description: "UI/UX 개선, shadcn/ui 적용"
  - label: "QA 검증"
    description: "현재 코드의 품질을 검증합니다"
multiSelect: true
```

선택에 따라:
- **기능 추가**: "어떤 기능?" 추가 질문 → seed.features에 새 기능 추가 (status: "new")
- **코드 품질**: → `samvil-qa` 로 체인 (3-pass 검증)
- **디자인**: → `samvil-design` 로 체인 (블루프린트 + shadcn 적용)
- **QA**: → `samvil-qa` 로 직접 체인

## Step 8: 저장 + 체인

1. `project.seed.json` 저장 (역방향 seed + 새 기능)
2. `project.state.json` 초기화
3. `.samvil/` 디렉토리 생성
4. `interview-summary.md` — 분석 결과를 인터뷰 요약 형태로 저장 (INV-3)

선택한 개선에 따라 적절한 스킬로 체인:
- 기능 추가 → `samvil-build` (scaffold 스킵, 기존 코드에 추가)
- 코드 품질 → `samvil-qa`
- 디자인 → `samvil-design`
- QA → `samvil-qa`

## Rules

1. **기존 코드를 절대 삭제하지 않는다** — 추가/수정만. 삭제는 유저 승인 후에만.
2. **역방향 seed에 기존 기능은 `status: "existing"`** — build 시 이미 있는 기능은 스킵.
3. **프레임워크 강제 변환 금지** — React 프로젝트를 Next.js로 바꾸지 않는다.
4. **package.json 분석이 핵심** — 여기서 대부분의 정보가 나온다.
5. **모르는 건 물어본다** — 자동 감지로 판단 불가한 것은 유저에게 확인.
6. **분석은 Read-only** — 분석 단계에서 파일 수정 없음. 수정은 build/qa 단계에서.
