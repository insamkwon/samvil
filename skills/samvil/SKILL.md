---
name: samvil
description: "AI vibe-coding harness. One-line prompt → full web app. Pipeline: Interview → Seed → Scaffold → Build → QA → Retro."
---

# SAMVIL — Main Orchestrator

You are the SAMVIL orchestrator. Take the user's one-line app idea and guide it through 5 stages to produce a working Next.js application.

## Pipeline

```
[1] Interview → [2] Seed → [Gate A] Council → [Design] Blueprint → [3] Scaffold → [4] Build → [5] QA → [Evolve] → [Auto] Retro
                              ↑ skip if minimal       ↑ Gate B if thorough+              ↑ parallel if standard+  ↑ optional
```

## How to Run

### Step 0: Health Check

시작 전 환경 점검. 문제 있으면 안내하고 해결 후 진행.

```
[SAMVIL] 환경 점검 중...
```

**1. MCP 서버 확인**

`score_ambiguity` MCP 도구가 사용 가능한지 확인. 사용 가능하면:
```
[SAMVIL] ✓ MCP 서버 연결됨 (고급 기능 활성화)
```

사용 불가능하면:
```
[SAMVIL] ⚠️ MCP 서버가 연결되지 않았습니다.
  고급 기능(모호도 수치, 세션 저장, 시드 진화)은 비활성화됩니다.
  기본 파이프라인은 문제없이 동작합니다.
```

AskUserQuestion으로:
```
question: "MCP 없이 진행할까요?"
options:
  - "MCP 없이 진행" → 계속
  - "MCP 설치 도움" → 설치 가이드 표시 후 "새 세션에서 다시 시작하세요" 안내
```

MCP 설치 가이드:
```bash
# 1. MCP 서버 설치
cd ~/.claude/plugins/cache/samvil/samvil/*/mcp
uv venv .venv && source .venv/bin/activate && uv pip install -e .

# 2. settings.json에 등록 (아래 JSON을 mcpServers에 추가)
"samvil-mcp": {
  "command": "<위 경로>/mcp/.venv/bin/python",
  "args": ["-m", "samvil_mcp.server"],
  "cwd": "<위 경로>/mcp"
}

# 3. 새 세션 열기
```

**2. Node.js 확인**

```bash
node --version
```
없으면: "Node.js가 필요합니다. https://nodejs.org 에서 설치해주세요."

**3. 이전 프로젝트 확인**

같은 이름의 프로젝트가 `~/dev/`에 있는지 확인 → Step 3 (Resume)에서 처리.

점검 완료:
```
[SAMVIL] ✓ 환경 점검 완료
```

### Step 1: Extract the App Idea

The user invoked `/samvil` with a prompt (e.g., `/samvil "todo app"`). Extract the app idea from the arguments.

If no argument provided, ask: "What app do you want to build? Describe it in one line."

### Step 2: Create Project Directory

Derive a kebab-case project name from the app idea.

```bash
mkdir -p ~/dev/<project-name>/.samvil
```

Initialize `project.state.json`:

```json
{
  "seed_version": 1,
  "current_stage": "interview",
  "completed_features": [],
  "in_progress": null,
  "failed": [],
  "build_retries": 0,
  "qa_history": [],
  "retro_count": 0
}
```

Write this to `~/dev/<project-name>/project.state.json`.

### Step 3: Check for Resume

If `project.state.json` already exists when `/samvil` is invoked:

```
[SAMVIL] Found existing project at ~/dev/<project-name>/
  Current stage: <stage> 
  Resume from here? Or start fresh?
```

Wait for user response. If resume: skip to the current stage's skill.

### Step 4: Select Tier

Before starting interview, ask user to choose tier via AskUserQuestion:

```
question: "어떤 수준으로 만들까요?"
header: "Tier"
options:
  - label: "빠르게 (minimal)"
    description: "질문 적게, Council 없이 바로 빌드. 프로토타입용."
  - label: "일반 (standard)"  
    description: "기본 검증 + Council 토론. 대부분의 프로젝트에 추천."
  - label: "꼼꼼하게 (thorough)"
    description: "깊은 인터뷰 + 디자인 리뷰. 품질 중요할 때."
  - label: "풀옵션 (full)"
    description: "모든 에이전트 총동원. 큰 프로젝트용."
```

선택된 tier를 `project.state.json`에 `selected_tier` 필드로 저장.
인터뷰 스킬이 이 tier를 읽어서 질문 깊이를 조절.

### Step 5: Start the Chain

Print:
```
[SAMVIL] Starting pipeline for: "<app idea>"
[SAMVIL] Project: ~/dev/<project-name>/
[SAMVIL] Tier: <selected tier>
[SAMVIL] Stage 1/5: Interview...
```

Invoke the Skill tool: `samvil:interview`

The chain continues from there — each skill invokes the next (INV-4).

### Error Recovery

If the chain breaks (context compressed, skill fails, etc.):
1. Read `project.state.json` to determine current stage
2. Invoke the appropriate skill directly
3. The skill reads state.json and picks up where it left off

### Progress Format

Each stage prints:
```
[SAMVIL] Stage N/5: <name>... <status>
```

### Agent Tier Selection

After seed is approved (between Step 4 Interview chain start and Scaffold), read `seed.agent_tier` and `seed.agent_overrides` from `project.seed.json`.

**Read `references/tier-definitions.md`** for the full agent list per tier.

#### Tier Resolution

```
1. Read seed.agent_tier (default: "standard")
2. Look up tier composition from tier-definitions.md
3. Apply agent_overrides:
   - add: include these agents even if not in tier
   - remove: exclude these agents even if in tier
4. Log the result
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
