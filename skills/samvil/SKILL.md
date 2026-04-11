---
name: samvil
description: "AI vibe-coding harness. One-line prompt → full web app. Pipeline: Interview → Seed → Scaffold → Build → QA → Retro."
---

# SAMVIL — Main Orchestrator

You are the SAMVIL orchestrator. Take the user's one-line app idea and guide it through 5 stages to produce a working Next.js application.

## Pipeline

```
[1] Interview → [2] Seed → [Gate A] Council → [Design] Blueprint → [3] Scaffold → [4] Build → [5] QA → [Evolve] → [Auto] Retro
                              ↑ Council skip if minimal    ↑ Gate B if thorough+    ↑ parallel if standard+  ↑ optional
```

## How to Run

### Step 0: Health Check

시작 전 환경 점검. 각 항목을 Bash로 체크하고 결과 표시. 문제 있으면 안내 + 해결 방법 제공.

```
[SAMVIL] 🔍 환경 점검 중...
```

아래 항목을 순서대로 체크. **없는 도구는 자동 설치를 시도한다.**

**1. Node.js** (필수 — 없으면 앱을 빌드할 수 없음)
```bash
node --version 2>/dev/null
```
- ✅ 있음 → `[SAMVIL] ✓ Node.js {version}`
- ❌ 없음 → 자동 설치 시도:
  ```bash
  # macOS: brew 있으면 자동 설치
  if command -v brew &>/dev/null; then
    brew install node
  fi
  ```
  brew도 없으면: `[SAMVIL] ✗ Node.js가 필요합니다. https://nodejs.org 에서 LTS를 설치해주세요.` → **진행 불가**

**2. npm** — Node.js 설치하면 함께 설치됨. 별도 체크 불필요.

**3. Python** (MCP 서버용)
```bash
python3 --version 2>/dev/null
```
- ✅ 있음 → `[SAMVIL] ✓ Python {version}`
- ❌ 없음 → 자동 설치 시도:
  ```bash
  if command -v brew &>/dev/null; then
    brew install python@3.12
  fi
  ```
  실패 시: `[SAMVIL] ⚠️ Python 없음. MCP 없이 진행.` → 멈추지 않고 계속

**4. uv** — SessionStart hook (`setup-mcp.sh`)이 자동 설치. Health Check에서는 결과만 표시:
- ✅ 있음 → `[SAMVIL] ✓ uv 설치됨`
- 없음 → 표시 안 함 (setup-mcp.sh가 처리)

**5. GitHub CLI** (선택 — 업데이트 체크용)
```bash
gh --version 2>/dev/null
```
- ✅ 있음 → `[SAMVIL] ✓ GitHub CLI 설치됨`
- 없음 → 표시 안 함 (비필수, 없어도 기능에 영향 없음)

**6. SAMVIL 버전 + 업데이트 체크**

현재 버전:
```bash
# 최신 캐시 폴더의 plugin.json만 읽기 (여러 버전 폴더 충돌 방지)
LATEST_CACHE=$(ls -td ~/.claude/plugins/cache/samvil/samvil/*/ 2>/dev/null | head -1)
cat "${LATEST_CACHE}.claude-plugin/plugin.json" 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin)['version'])" 2>/dev/null
```

GitHub 최신 버전 (gh 있을 때만):
```bash
gh api repos/insamkwon/samvil/contents/.claude-plugin/plugin.json --jq '.content' 2>/dev/null | base64 -d | python3 -c "import json,sys; print(json.load(sys.stdin)['version'])" 2>/dev/null
```

- 동일 → `[SAMVIL] ✓ 최신 버전 (v{version})`
- 업데이트 있음 → AskUserQuestion: "새 버전 v{latest} 있음. 업데이트할까?" → "지금" or "나중에"
- 확인 실패 → 무시하고 진행

**7. MCP 서버** — SessionStart hook이 자동 설치. 여기서는 결과만 확인:

- ✅ 연결됨 → `[SAMVIL] ✓ MCP 서버 연결됨`
- ⚠️ 없음 → `[SAMVIL] ⚠️ MCP 없음 (기본 모드)` → 멈추지 않고 바로 진행

**8. 이전 프로젝트 확인**

같은 이름의 프로젝트가 `~/dev/`에 있는지 → Step 3 (Resume)에서 처리.

### 점검 결과 요약

모든 체크가 끝나면 한눈에 보여줌:

```
[SAMVIL] 환경 점검 결과
━━━━━━━━━━━━━━━━━━━━━━
  ✓ Node.js v20.11.0
  ✓ npm 10.2.4
  ✓ Python 3.12.12
  ✓ uv 설치됨
  ✓ GitHub CLI 2.45.0
  ✓ SAMVIL v0.1.0 (최신)
  ✓ MCP 서버 연결됨
━━━━━━━━━━━━━━━━━━━━━━
  준비 완료! 파이프라인을 시작합니다.
```

또는 자동 설치가 발생한 경우:
```
[SAMVIL] 환경 점검 결과
━━━━━━━━━━━━━━━━━━━━━━
  ✓ Node.js v20.11.0 (자동 설치됨)
  ✓ Python 3.12.12
  ✓ MCP 서버 연결됨
  ✓ SAMVIL v0.1.0 (최신)
━━━━━━━━━━━━━━━━━━━━━━
```

**원칙: Node.js만 진짜 필수. 나머지는 없으면 자동 설치하거나 기본 모드로 진행.**

### Step 1: Project Mode Selection

Health Check 후 AskUserQuestion으로 프로젝트 모드 선택:

```
question: "어떤 작업을 할까요?"
header: "프로젝트 모드"
options:
  - label: "새 프로젝트"
    description: "아이디어부터 시작. 인터뷰 → 설계 → 빌드 → 검증 전체 파이프라인."
  - label: "기존 프로젝트 개선"
    description: "이미 있는 코드를 분석하고 개선/확장. 기능 추가, 리팩토링, QA 등."
  - label: "단일 단계만 실행"
    description: "특정 단계만 실행 (QA만, 빌드만, 진화만 등)"
```

#### Mode A: 새 프로젝트 (Greenfield)

기존 흐름 그대로 → Step 2로 진행.

#### Mode B: 기존 프로젝트 개선 (Brownfield)

AskUserQuestion으로 상세 파악:

```
question: "기존 프로젝트에 대해 알려주세요"
header: "브라운필드"
options:
  - label: "기능 추가"
    description: "기존 앱에 새 기능 추가. 코드 분석 후 seed에 기능 추가."
  - label: "리팩토링/개선"
    description: "기존 코드 품질 개선. QA → 문제 발견 → 수정."
  - label: "디자인 개선"
    description: "기존 앱의 UI/UX 개선. shadcn/ui 적용 등."
  - label: "테스트/검증만"
    description: "기존 코드에 대해 QA 3-pass만 실행."
```

**Brownfield 프로세스:**

Invoke the Skill tool with skill: `samvil-analyze`

analyze 스킬이 전체를 처리:
1. 프로젝트 경로 확인
2. 프레임워크/구조/상태관리/UI 자동 감지
3. 역방향 seed.json 생성
4. 유저 검토
5. Gap 분석 (원하는 개선 파악)
6. 적절한 다음 스킬로 체인 (build/qa/design)

#### Mode C: 단일 단계만 실행

AskUserQuestion으로 어떤 단계:
```
question: "어떤 단계를 실행할까요?"
header: "단계 선택"
options:
  - label: "인터뷰" → samvil-interview
  - label: "QA 검증" → samvil-qa
  - label: "진화 (Evolve)" → samvil-evolve
  - label: "회고 (Retro)" → samvil-retro
```

프로젝트 경로와 seed.json을 물어본 후 해당 스킬만 invoke.

---

### Step 2: Extract the App Idea (Mode A만)

The user invoked `/samvil` with a prompt (e.g., `/samvil "todo app"`). Extract the app idea from the arguments.

If no argument provided, ask: "뭘 만들까요? 한 줄로 설명해주세요."

### Step 3: Create Project Directory (Mode A만)

Derive a kebab-case project name from the app idea.

```bash
mkdir -p ~/dev/<project-name>/.samvil
```

Initialize `project.state.json`:

```json
{
  "session_id": null,
  "seed_version": 1,
  "current_stage": "interview",
  "completed_stages": [],
  "completed_features": [],
  "in_progress": null,
  "failed": [],
  "build_retries": 0,
  "qa_history": [],
  "retro_count": 0
}
```

Write this to `~/dev/<project-name>/project.state.json`.

**Checkpoint 원칙 (INV-6):** 각 스킬은 자신의 스테이지를 완료한 직후 `project.state.json`을 업데이트해야 한다:
1. `completed_stages` 배열에 스테이지명 추가 (중복 방지: 이미 있으면 스킵)
2. `current_stage`를 다음 스테이지로 업데이트
3. 파일에 즉시 저장 (MCP 장애와 무관하게 항상 파일에 기록)

```python
# Checkpoint 예시 (각 스킬 종료 시)
state = read_json("project.state.json")
stage_name = "interview"
if stage_name not in state["completed_stages"]:
    state["completed_stages"].append(stage_name)
state["current_stage"] = "<next_stage>"
write_json("project.state.json", state)
```

**Initialize `.samvil/metrics.json`** — 관측성 대시보드용 메트릭 초기화:

```json
{
  "session_id": null,
  "version": "<current version from plugin.json>",
  "stages": {},
  "total_duration_ms": null,
  "timestamp": "<ISO 8601 now>"
}
```

각 스테이지는 시작/종료 시 이 파일의 `stages.<stage_name>` 필드를 업데이트한다:
- **스테이지 시작 시**: `stages.<stage_name>.started_at = <ISO timestamp>`
- **스테이지 종료 시**: `stages.<stage_name>.ended_at = <ISO timestamp>` + 스테이지별 메트릭 기록
- `duration_ms`는 `ended_at - started_at`으로 자동 계산

Write this to `~/dev/<project-name>/.samvil/metrics.json`.

**MCP (best-effort):** Create a SAMVIL session for event tracking:

```
mcp__samvil_mcp__create_session(project_name="<project-name>", agent_tier="<selected_tier>")
```

Parse the returned `session_id` and update `project.state.json` → set `session_id` to the returned value.

### Step 4: Check for Resume

**Resume 트리거 조건** — 다음 중 하나라도 해당하면 Resume 모드를 제안:
- `/samvil --resume` 또는 `/samvil --continue` 플래그 사용
- `project.state.json` 파일이 이미 존재
- `.samvil/` 디렉토리가 이미 존재

#### 4-A: State 파일 기반 Resume

`project.state.json`이 이미 존재하면:

```
[SAMVIL] 이전 실행을 감지했습니다: ~/dev/<project-name>/
  완료된 단계: interview, seed, scaffold
  현재 단계: build
  이어서 진행할까요?
```

AskUserQuestion:
```
question: "이전 프로젝트를 이어서 진행할까요?"
header: "이어하기"
options:
  - label: "이어서 진행 (Resume)"
    description: "마지막 완료 단계(build)부터 재시작"
  - label: "처음부터 다시 (Fresh)"
    description: "기존 state를 초기화하고 새로 시작"
```

Resume 선택 시 `state.completed_stages`를 읽어서 다음 스테이지의 스킬을 바로 invoke.

#### 4-B: 산출물 기반 자동 감지

`project.state.json`이 없지만 프로젝트 디렉토리에 산출물이 있으면 자동으로 복구:

```bash
# 산출물 존재 여부 체크
PROJECT_DIR=~/dev/<project-name>

# 1. seed.json 존재 → interview + seed 완료로 간주
test -f "$PROJECT_DIR/seed.json" && echo "seed:found"

# 2. blueprint.json 존재 → design 완료로 간주
test -f "$PROJECT_DIR/blueprint.json" && echo "blueprint:found"

# 3. package.json 존재 → scaffold 완료로 간주
test -f "$PROJECT_DIR/package.json" && echo "scaffold:found"

# 4. src/ 디렉토리 존재 + 파일 수 > 5 → build 진행 중으로 간주
test -d "$PROJECT_DIR/src" && echo "src:found"
```

산출물 기반 감지 결과로 `completed_stages`를 자동 복원:

```
[SAMVIL] 산출물 기반 자동 감지:
  ✓ seed.json 발견 → interview + seed 완료
  ✓ package.json 발견 → scaffold 완료
  ✓ src/ 발견 (23 files) → build 진행 중으로 추정
  → build 스테이지부터 재시작합니다
```

산출물이 감지되면 자동으로 `project.state.json`을 복원:
```json
{
  "session_id": null,
  "seed_version": 1,
  "current_stage": "build",
  "completed_stages": ["interview", "seed", "scaffold"],
  "completed_features": [],
  "in_progress": null,
  "failed": [],
  "build_retries": 0,
  "qa_history": [],
  "retro_count": 0
}
```

#### 4-C: Resume 실행

Resume이 확정되면:

1. `project.state.json` 읽기 → `completed_stages` 확인
2. `project.config.json` 읽기 → Tier, skip_stages 복원
3. `.samvil/metrics.json` 읽기 → 기존 메트릭 복원 (없으면 초기화)
4. 체인의 올바른 위치에서 바로 스킬 invoke

```
[SAMVIL] Resume 모드 활성화
  프로젝트: ~/dev/<project-name>/
  완료: interview → seed → scaffold
  재시작: build (Stage 4/5)
```

**파이프라인 스테이지 순서** (체인 복구용):
```
interview → seed → council → design → scaffold → build → qa → evolve → retro
```

`completed_stages`의 마지막 스테이지 다음 순서의 스킬을 invoke.
`skip_stages`에 포함된 스테이지는 건너뛰고 그 다음으로 진행.

### Step 4: Select Tier

Before starting interview, ask user to choose tier via AskUserQuestion:

**Tier 실적 조회**: `harness-feedback.log` (`harness-feedback.log (SAMVIL 플러그인 캐시 루트: `~/.claude/plugins/cache/samvil/samvil/*/harness-feedback.log`)`)를 읽어서 같은 앱 유형의 이전 실적이 있으면 Tier별 성공률을 표시한다.

```
question: "어떤 수준으로 만들까요?"
header: "Tier"
options:
  - label: "빠르게 (minimal)"
    description: "<이전 실적 있으면: 'todo 앱 92% 성공, ~3분' / 없으면: '질문 적게, Council 없이 바로 빌드. 프로토타입용.'>"
  - label: "일반 (standard)"  
    description: "<이전 실적 있으면: 'kanban 앱 100% 성공' / 없으면: '기본 검증 + Council 토론. 대부분의 프로젝트에 추천.'>"
  - label: "꼼꼼하게 (thorough)"
    description: "깊은 인터뷰 + 디자인 리뷰. 품질 중요할 때."
  - label: "풀옵션 (full)"
    description: "모든 에이전트 총동원. 큰 프로젝트용."
```

실적 데이터가 없으면 기존 설명 그대로 표시.

선택된 tier를 `project.state.json`에 `selected_tier` 필드로 저장.

**project.config.json 초기화** — Tier 선택 후 실행 설정 파일 생성:

```json
{
  "selected_tier": "<선택된 tier>",
  "evolve_max_cycles": 5,
  "evolve_mode": "spec-only",
  "qa_max_iterations": 3,
  "max_total_builds": 15,
  "max_parallel": 2,
  "model_routing": {
    "interview": "opus",
    "council": "sonnet",
    "council_research": "haiku",
    "build_worker": "sonnet",
    "qa": "sonnet",
    "evolve": "opus",
    "evolve_cycle": "sonnet",
    "design_reviewer": "haiku",
    "lint_fix": "haiku",
    "default": "sonnet"
  },
  "skip_stages": []
}
```

Write this to `~/dev/<project-name>/project.config.json`.

**3파일 분리 원칙:**
- `seed.json` = 명세 (what to build) — features, AC, constraints, tech_stack
- `config.json` = 실행 설정 (how to run) — evolve/qa/model/tier/skip 설정
- `state.json` = 현재 상태 (where we are) — current_stage, completed_features

인터뷰 스킬이 이 tier를 읽어서 질문 깊이를 조절.

### Step 5: Start the Chain

**파이프라인 진행 상황 등록** — TaskCreate 도구로 전체 단계를 생성한다. 사용자가 하단에서 진행 상황을 한눈에 볼 수 있도록:

```
TaskCreate: "Interview — 요구사항 인터뷰"
TaskCreate: "Seed — 설계서 생성"
TaskCreate: "Council — 설계 검토" (minimal이면 생략)
TaskCreate: "Design — 아키텍처 결정"
TaskCreate: "Scaffold — 프로젝트 뼈대 생성"
TaskCreate: "Build — 기능 구현"
TaskCreate: "QA — 3단계 검증"
TaskCreate: "Retro — 회고"
```

각 스킬 시작 시 해당 Task를 `in_progress`로, 완료 시 `completed`로 업데이트한다.

Print:
```
[SAMVIL] Starting pipeline for: "<app idea>"
[SAMVIL] Project: ~/dev/<project-name>/
[SAMVIL] Tier: <selected tier>
[SAMVIL] Stage 1/5: Interview...
```

**체인 스킵 체크**: `project.config.json`의 `skip_stages`를 읽는다. 체인 invoke 전에 다음 단계가 skip_stages에 포함되어 있으면 건너뛰고 그 다음 스킬로 직접 invoke한다.

```
예: skip_stages: ["council", "design"]
  → Seed 완료 후 council/design 스킵 → 바로 scaffold invoke
```

각 스킬도 체인 invoke 전에 동일하게 skip_stages를 확인한다.

**MCP (best-effort):** Save pipeline start event:

```
mcp__samvil_mcp__save_event(
  session_id="<session_id from state.json>",
  event_type="stage_change",
  stage="interview",
  data='{"app":"<app-idea>","tier":"<selected_tier>"}'
)
```

**MCP Event Rule (모든 스킬 공통) — Dual-Write Pattern:**
각 스킬이 상태를 변경할 때마다 다음 순서로 이벤트를 기록:

1. **항상 파일에 먼저 기록** — `.samvil/events.jsonl`에 append (절대 실패하지 않음)
2. **MCP는 best-effort** — `mcp__samvil_mcp__save_event` 호출 시도. 성공하면 좋고, 실패해도 파이프라인 계속 진행
3. **실패 시 기록** — MCP 호출이 실패하면 `.samvil/mcp-health.jsonl`에 `{status:"fail", tool:"<name>", error:"<msg>", timestamp:"..."}` append

```
# 파일 기록 (항상 실행)
append to .samvil/events.jsonl: {"event_type":"<type>","stage":"<stage>","data":{...},"timestamp":"<ISO>"}

# MCP 호출 (best-effort)
try:
  mcp__samvil_mcp__save_event(session_id=..., event_type=..., stage=..., data=...)
except:
  append to .samvil/mcp-health.jsonl: {"status":"fail","tool":"save_event","error":"<error>"}
```

**Retro에서 MCP 건강 리포트를 출력** — `.samvil/mcp-health.jsonl`이 있으면 성공률 집계.

Invoke the Skill tool: `samvil-interview`

The chain continues from there — each skill invokes the next (INV-4).

**Metrics Tracking (INV-5)** — 각 스테이지 시작/종료 시 `.samvil/metrics.json` 업데이트:

이 지시는 체인의 모든 스킬이 따라야 한다:

```
# 스테이지 시작 시 (각 스킬의 Boot Sequence에서):
metrics.json을 읽기
metrics.stages.<stage>.started_at = <ISO timestamp now>
metrics.json에 저장

# 스테이지 종료 시 (각 스킬이 다음 스킬 invoke 직전):
metrics.json을 읽기
metrics.stages.<stage>.ended_at = <ISO timestamp now>
metrics.stages.<stage>.duration_ms = ended_at - started_at (milliseconds)
# 스테이지별 추가 메트릭 기록 (아래 참고)
metrics.json에 저장
```

**스테이지별 메트릭 필드:**

| Stage | Fields |
|-------|--------|
| `interview` | `questions_asked` (int) |
| `seed` | _(duration만)_ |
| `council` | `agents_spawned` (int), `rounds_completed` (int) |
| `design` | `agents_spawned` (int), `blueprint_generated` (bool) |
| `scaffold` | `stack` (string), `files_created` (int) |
| `build` | `features_total` (int), `features_passed` (int), `features_failed` (int), `builds_run` (int), `agents_spawned` (int) |
| `qa` | `pass_rate` (float 0~1), `iterations` (int), `verdict` (PASS/REVISE/FAIL) |
| `evolve` | `cycles_run` (int), `seed_versions_created` (int) |

**체인 종료 시 (Retro 직전)** — 오케스트레이터 또는 마지막 스킬이:

```
metrics.json을 읽기
metrics.total_duration_ms = now - metrics.timestamp (milliseconds)
metrics.json에 저장
```

### Graceful Degradation (INV-7)

MCP 서버가 다운되거나 응답하지 않을 때 파일 기반으로 폴백하는 규칙.

**핵심 원칙:** `project.state.json`, `.samvil/metrics.json`, `.samvil/events.jsonl`은 항상 파일에 먼저 기록. MCP는 보조 채널.

#### MCP 장애 감지

MCP 호출 시 다음 증상이 나타나면 장애로 판단:
- `mcp__samvil_mcp__*` 도구가 응답하지 않음 (timeout)
- MCP 도구 호출 시 에러 반환
- `mcp__samvil_mcp__health_check` 실패

**초기 감지** (Health Check 시):
```bash
# MCP health check (best-effort)
# MCP 도구가 보이지 않으면 자동으로 파일 모드로 전환
```

장애 감지 시 출력:
```
[SAMVIL] MCP 서버 응답 없음. 파일 기반 추적으로 전환합니다.
  상태 파일: project.state.json
  메트릭: .samvil/metrics.json
  이벤트: .samvil/events.jsonl
```

#### 파일 기반 폴백 규칙

| 데이터 | MCP 도구 | 파일 폴백 |
|--------|----------|-----------|
| 세션 상태 | `create_session` / `get_session` | `project.state.json` |
| 이벤트 기록 | `save_event` | `.samvil/events.jsonl` (append) |
| 메트릭 | 없음 | `.samvil/metrics.json` (overwrite) |
| Seed 버전 | `save_seed_version` | `.samvil/seed-history/<version>.json` |
| 인터뷰 상태 | `score_ambiguity` | 인라인 계산 (threshold만 사용) |

**이벤트 파일 기록 형식:**
```
# .samvil/events.jsonl (한 줄에 하나의 JSON)
{"event_type":"stage_start","stage":"interview","data":{},"timestamp":"2024-01-01T00:00:00Z"}
{"event_type":"stage_end","stage":"interview","data":{"questions_asked":5},"timestamp":"2024-01-01T00:05:00Z"}
```

**MCP 건강 로깅** — MCP 호출 실패 시마다 `.samvil/mcp-health.jsonl`에 기록:
```
{"status":"fail","tool":"save_event","error":"connection refused","timestamp":"..."}
{"status":"fail","tool":"create_session","error":"timeout","timestamp":"..."}
```

Retro에서 `.samvil/mcp-health.jsonl`을 읽어 MCP 성공률 집계:
```
[SAMVIL] MCP 건강 리포트:
  총 호출: 18회
  성공: 15회 (83%)
  실패: 3회 (17%)
  실패 도구: save_event(2), create_session(1)
```

#### MCP 복구

체인 실행 중 MCP가 복구되면 자동으로 전환:
1. MCP 호출이 다시 성공하면 파일 기반 로깅과 병행
2. 파일에 기록된 이벤트를 MCP에 백필하지 않음 (중복 방지)
3. 이후 이벤트는 Dual-Write 패턴 유지

### Error Recovery

If the chain breaks (context compressed, skill fails, etc.):
1. Read `project.state.json` to determine `completed_stages` and `current_stage`
2. If `current_stage` not in `completed_stages` → retry that stage
3. If `current_stage` in `completed_stages` → invoke next stage
4. Each skill reads `project.state.json` and picks up where it left off

**Recovery 시나리오별 처리:**

| 시나리오 | 복구 방법 |
|----------|-----------|
| 컨텍스트 압축 | `project.state.json`의 `completed_stages`에서 다음 스테이지 invoke |
| 스킬 실행 중 에러 | `failed` 배열에 기록, 사용자에게 보고, 재시도 여부 확인 |
| 빌드 실패 | `build_retries` 증가, MAX_RETRIES(2) 초과 시 중단 |
| MCP 서버 다운 | INV-7 Graceful Degradation으로 파일 기반 폴백 |
| 사용자 중단 | `project.state.json`에 현재 상태 저장, `/samvil --resume`으로 복구 가능 |

### Progress Format

Each stage prints:
```
[SAMVIL] Stage N/5: <name>... <status>
```

### Output Format

This skill does not write files directly. It orchestrates other skills.
Outputs to the conversation:
- Health check result table (markdown)
- Tier selection confirmation: `[SAMVIL] Tier: <tier>`
- Pipeline start message: `[SAMVIL] Starting pipeline for: "<app idea>"`
- Progress: `[SAMVIL] Stage N/5: <name>...`

## Agent Tier Selection

After seed is approved, read `config.selected_tier` from `project.config.json`.

**Read `references/tier-definitions.md`** for the full agent list per tier.

#### Tier Resolution

```
1. Read config.selected_tier (from project.config.json)
2. Look up tier composition from tier-definitions.md
3. Log the result
```

#### Log Format

```
[SAMVIL] Agent Tier: standard (20 agents active)
  Planning:  socratic-interviewer, seed-architect, product-owner, simplifier, scope-guard
  Design:    ux-designer
  Dev:       tech-architect, scaffolder, orchestrator-agent, frontend-dev, backend-dev, infra-dev
  QA:        qa-mechanical, qa-functional, qa-quality, tech-lead, dog-fooder
  Evolution: wonder-analyst, reflect-proposer, retro-analyst
```

#### Gate A: Planning Council (M3+, 2-Round Structure)

Gate A runs between Seed approval and Scaffold. It uses a **2-round structure**:

```
Round 1: RESEARCH (parallel, information gathering)
  ├── competitor-analyst — "What exists in this market?"
  ├── business-analyst  — "What do the numbers say?"
  └── user-interviewer  — "What would a real user think?"
  → Results fed into Round 2

Round 2: REVIEW (parallel, seed quality validation)
  ├── product-owner  — "Are ACs testable? Stories complete?"
  ├── simplifier     — "Is scope minimal enough?"
  ├── scope-guard    — "Are dependencies honest?"
  └── ceo-advisor    — "Go/No-Go? Strategic risk?"
  → Synthesis: majority rules, conflicts to user
```

**Tier determines which rounds run:**
- minimal: No Gate A (skip to scaffold)
- standard: Round 2 only (PO + simplifier + scope-guard)
- thorough: Round 2 + business-analyst from Round 1
- full: Both rounds complete

#### Agent Usage by Stage

Currently (M2), agents are **logged but used as adopted roles** — the skill's inline behavior rules define the persona.

In future milestones:
- **M3+**: Council agents are spawned via CC Agent tool. Each receives its `agents/*.md` content as prompt.
- **M4+**: Worker agents are spawned for parallel feature builds.
- **M5+**: Gate B design council (ui-designer, ux-researcher, etc.)

#### How to Use Agent Personas (Current — Adopted Roles)

Each skill has inline behavior rules that define the persona. The `agents/*.md` files contain the **full detailed persona** used when agents are spawned (M3+).

For adopted roles, the skill's own instructions take precedence.
