---
name: samvil-evolve
description: "Seed evolution loop. Wonder → Reflect → new seed version. Repeat until convergence or user stops."
---

# SAMVIL Evolve — Seed Evolution Loop

Improve the seed based on QA feedback. Spawn wonder + reflect agents, generate a better seed version, check convergence.

## When to Run

- After QA PASS with quality notes → user opts in to evolve
- After QA FAIL (Ralph exhausted) → evolve may fix the root cause
- **Auto-trigger (v0.3.2 신규):** Read `project.state.json` and check:
  - `build_retries ≥ 5` (빌드가 고생했으면 시드에 문제가 있을 가능성 높음)
  - `qa_history.length ≥ 2` (QA를 여러 번 돌렸으면 구조적 개선 필요)
  - `partial_count ≥ 5` (PARTIAL이 많으면 AC 정의가 모호할 수 있음)
  - **둘 중 하나라도 충족하면** QA PASS 후 Evolve 제안을 자동으로 활성화 (사용자 확인 1회)
  ```
  [SAMVIL] Evolve 자동 제안 (build_retries=12 ≥ 5)
    빌드가 12번 재시도되었습니다. 시드 진화로 근본 원인을 개선할 수 있습니다.
    Evolve 진행? (yes / no)
  ```
- User explicitly invokes `/samvil:evolve`

## Boot Sequence (INV-1)

1. Read `project.seed.json` → current seed
2. Read `project.state.json` → current stage, qa_history, `session_id`
3. Read `project.config.json` → `evolve_max_cycles`, `evolve_mode`, `max_total_builds`
4. Read `.samvil/qa-report.md` → QA results
5. Read `decisions.log` → binding decisions (if exists)

## Step 0: Mode Selection

Read `config.evolve_mode`:

### Mode: `spec-only` (기본값)

명세만 진화. 빌드는 수렴 후 한 번만.

```
Wonder("뭘 아직 모르나?") → Reflect("seed 어떻게 바꿀까?") → seed 수정
→ 수렴 체크: seed 변경 없으면 종료
→ 수렴 후 마지막에 한 번만 Build → QA
→ max: config.evolve_max_cycles
```

### Mode: `full`

매 세대마다 빌드 + QA 포함.

```
Wonder → Reflect → seed 수정 → Build → QA
→ max: config.evolve_max_cycles
```

**전체 빌드 횟수 추적**: `state.build_retries`가 `config.max_total_builds`에 도달하면 모드와 무관하게 강제 종료.

## Step 1: Gather Context

**MCP (best-effort):** Call `mcp__samvil_mcp__get_evolve_context`:
```
mcp__samvil_mcp__get_evolve_context(session_id="<session_id>", qa_result='<qa-report JSON summary>')
→ Returns: current seed, QA result, convergence trend, previous changes
```

## Step 1b: 4차원 진화 평가

Wonder/Reflect 전에 현재 상태를 4차원으로 평가한다:

| 차원 | 질문 | 체크 방법 |
|------|------|----------|
| **Quality** | 코드가 제대로 동작하는가? | QA 결과 (이미 있음) |
| **Intent** | 사용자의 원래 의도를 충족하는가? | interview-summary의 "핵심 문제"와 실제 구현 비교 |
| **Purpose** | 제품의 존재 이유를 달성하는가? | seed.description이 약속한 가치가 실제로 전달되는가? |
| **Beyond** | 더 나아질 수 있는가? | 첫 30초 경험, 바이럴 포인트, 리텐션 요소 |

각 차원 1~5 점수. **3/5 이하인 차원이 있으면 해당 차원에 집중하여 Wonder/Reflect 진행.**
모두 4/5 이상이면 → 수렴 가능성 높음.

```
[SAMVIL] Evolve 평가:
  Quality: 4/5 (QA PASS)
  Intent:  3/5 — "합격률을 높이는" 기능이 stub 수준
  Purpose: 3/5 — ATS 호환 PDF가 실제 ATS 통과하는지 미검증
  Beyond:  2/5 — 첫 30초에 빈 폼만 보임, 가이드 없음
  → Intent, Purpose, Beyond 중심으로 진화
```

## Step 2: Wonder — "What did we miss?"

Spawn `wonder-analyst` agent:

```
Agent(
  description: "SAMVIL Evolve: wonder-analyst",
  model: current_cycle === 1 ? (config.model_routing.evolve || "opus") : (config.model_routing.evolve_cycle || "sonnet"),
  prompt: "You are wonder-analyst.
<paste agents/wonder-analyst.md>

## Context
Current seed (v{N}): <seed JSON>
QA Report: <qa-report.md content>
{convergence info if available}

## Additional Ground Truth
Read these files if they exist in ~/dev/<seed.name>/.samvil/:
- build.log — raw build output
- fix-log.md — applied fixes during build
- events.jsonl — structured build/QA event trail

Use them to identify:
- repeated error signatures
- repeated error categories
- reverted fixes
- workaround patterns that indicate a spec issue instead of an implementation issue

## Task
Analyze what was lacking. Find surprises and gaps.
Follow your Output Format. Under 400 words.",
  subagent_type: "general-purpose"
)
```

## Step 3: Reflect — "How to improve?"

Spawn `reflect-proposer` agent (sequentially, receives wonder output):

```
Agent(
  description: "SAMVIL Evolve: reflect-proposer",
  model: current_cycle === 1 ? (config.model_routing.evolve || "opus") : (config.model_routing.evolve_cycle || "sonnet"),
  prompt: "You are reflect-proposer.
<paste agents/reflect-proposer.md>

## Context
Current seed (v{N}): <seed JSON>
Wonder Analysis: <wonder output>
{convergence info}

## Task
Propose concrete seed changes. Follow your Output Format. Under 400 words.",
  subagent_type: "general-purpose"
)
```

## Step 4: Generate New Seed

Apply reflect-proposer's recommendations to create seed v(N+1):

1. Read current seed
2. **Backup current seed** (PHI-03):
   ```bash
   mkdir -p ~/dev/<seed.name>/seed_history
   cp ~/dev/<seed.name>/project.seed.json ~/dev/<seed.name>/seed_history/v${N}.json
   ```
3. Apply proposed changes
4. Increment version: `version: N+1`
4. **MCP (best-effort):** Validate evolved seed:
   ```
   mcp__samvil_mcp__validate_evolved_seed(original_seed='<current seed JSON>', evolved_seed='<new seed JSON>')
   ```
5. If validation fails: fix issues, re-validate

## Step 4b: MCP Event + Seed Version (필수)

```
mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="evolve_gen", stage="evolve", data='{"from_version":<N>,"to_version":<N+1>,"changes_count":<N>}')

mcp__samvil_mcp__save_seed_version(session_id="<session_id>", version=<N+1>, seed_json='<escaped new seed JSON>', change_summary="<brief changes>")
```

Save diff to file for posterity (PHI-05):
```bash
# After compare_seeds returns, save the diff
cat > ~/dev/<seed.name>/seed_history/v${N}_v${N+1}_diff.md << 'EOF'
## v{N} → v{N+1}
Similarity: <score>

<compare_seeds change list>
EOF
```

## Step 5: User Checkpoint

**MCP (best-effort):** Generate seed diff for display:
```
mcp__samvil_mcp__compare_seeds(seed_a='<previous seed JSON>', seed_b='<new seed JSON>')
→ Returns: similarity score and change list
```

Present the diff:

```
[SAMVIL] Seed Evolution: v{N} → v{N+1}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Wonder findings:
  1. [finding]
  2. [finding]

Proposed changes:
  1. [change]
  2. [change]

{If MCP: Convergence trend: [converging/diverging/stable]}

Apply this evolution? (yes / no / edit)
```

- **yes**: Save new seed, continue
- **no**: Keep current seed, stop evolving
- **edit**: User modifies, then save

## Step 6: Save and Check Convergence

1. Write updated `project.seed.json`
2. **수렴 판정**: 새 seed와 이전 seed를 비교.
   - features, acceptance_criteria, constraints가 **모두 동일**이면 → 수렴
   - **MCP (best-effort):** `mcp__samvil_mcp__check_convergence(seed_history='<JSON array of seed dicts>')`

### If Converged (seed 변경 없음)

**MCP (best-effort):**
```
mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="evolve_converge", stage="evolve", data='{"final_version":<N+1>,"total_generations":<N>}')
```

```
[SAMVIL] Seed converged at v{N+1}. No further evolution needed.
```

**If mode is `spec-only`**: 수렴 후 최종 Build → QA 한 번 실행.
```
[SAMVIL] Spec converged. Running final build + QA...
```
Update `project.state.json`: set `current_stage` to `"build"`.
Invoke `samvil-build` → Build 완료 후 자동으로 QA 체인.

**If mode is `full`**: 이미 매 세대마다 빌드했으므로 바로 retro로.

### If Not Converged and iterations < config.evolve_max_cycles

```
[SAMVIL] Seed v{N+1} saved. Rebuilding changed features...
```
Rebuild only features that changed → re-QA → check results.
If QA passes: offer another evolve round.
If QA still fails: another wonder/reflect cycle.

### If Max Iterations Reached (config.evolve_max_cycles, default 5)

```
[SAMVIL] Max evolution iterations reached. Stopping.
  Current seed: v{N+1}
  Recommendation: Review the seed manually.
```

## Step 7: Chain

After evolve completes (converged, user stops, or max iterations):

**MCP (best-effort):** `mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="stage_change", stage="retro", data='{"reason":"evolve_complete"}')`
Invoke the Skill tool with skill: `samvil-retro`

If user chose to rebuild with new seed:
**MCP (best-effort):** `mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="stage_change", stage="scaffold", data='{"reason":"rebuild_with_evolved_seed"}')`
Invoke the Skill tool with skill: `samvil-scaffold`

## Output Format

Files modified per evolution cycle:
- `~/dev/<seed.name>/project.seed.json`: updated seed with `version: N+1`
- `~/dev/<seed.name>/seed_history/v{N}.json`: backup of previous seed
- `~/dev/<seed.name>/seed_history/v{N}_v{N+1}_diff.md`: change summary with similarity score

Console output per cycle:
```
[SAMVIL] Seed Evolution: v{N} -> v{N+1}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Wonder findings:
  1. <finding>

Proposed changes:
  1. <change>

{Convergence trend: converging/diverging/stable}
```

Agent output format (per agent):
- wonder-analyst: numbered findings list, under 400 words
- reflect-proposer: numbered change proposals with rationale, under 400 words

## Anti-Patterns

1. Do NOT add more than 2 new features per evolution cycle
2. Do NOT modify `name`, `mode`, or `core_experience` — evolve around the core
3. Do NOT skip the user checkpoint unless autonomous mode is explicitly requested

## Rules

1. **Wonder before Reflect** — always analyze before proposing
2. **Max 2 new features per evolution** — prevent scope explosion
3. **Preserve name, mode, core_experience** — evolve around the core, not through it
4. **User checkpoint** — 기본적으로 매 진화마다 사용자 승인. 단, 사용자가 "자율 진화", "알아서 해", "수렴할 때까지" 등으로 자율 모드를 지시하면 → 수렴까지 승인 없이 자동 진행. 자율 모드에서도 MAJOR 변경(feature 삭제, core_experience 변경)은 반드시 확인.
5. **convergence ≥ 0.95 = stop** — diminishing returns beyond this
6. **Max iterations = config.evolve_max_cycles (default 5)** — hard cap to prevent infinite loops

## Chain (Runtime-specific)

### Claude Code
- After evolve: Invoke the Skill tool with skill: `samvil-retro`
- If rebuild needed: Invoke the Skill tool with skill: `samvil-build`

### Codex CLI (future)
Read the appropriate next skill's SKILL.md based on outcome.
