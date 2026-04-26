---
name: samvil-analyze
description: "기존 프로젝트 코드 분석. 구조 파악 → 역방향 seed 생성 → gap 분석. Brownfield 모드의 첫 단계."
---

# samvil-analyze (ultra-thin)

Adopt the **Brownfield Analyzer** role. Reverse-engineer an existing codebase
into a v3.0 seed, present confidence-tagged findings + auto-generated
ADR-EXISTING-NNN entries to the user, then route to build / qa / design based
on the gap. Detection logic (framework + UI + state + data + module → feature
mapping) lives in `mcp__samvil_mcp__analyze_brownfield_project` — this skill
owns git safety, AskUserQuestion checkpoints, and atomic write of
`project.seed.json` / `decisions.log`. Full Korean prose, grep recipes,
quality-scan patterns, dependency-impact heuristics in `SKILL.legacy.md`.

**모든 대화는 한국어로.** 코드와 기술 용어만 영어.

## Boot Sequence (INV-1)

1. `mcp__samvil_mcp__save_event(session_id="<sid>", event_type="analyze_start", stage="analyze", data="{}")` — best-effort, auto-claim writes `evidence_posted subject="stage:analyze"`. If no session yet, defer until Step 4.
2. Files are SSOT — caller passes `project_root`, or AskUserQuestion (Step 1) collects it.

## Step 1 — Project path + Git safety net

1. AskUserQuestion: `분석할 프로젝트 경로를 알려주세요` (current dir / 직접 입력). Capture `<project_root>`. Verify `test -d "<project_root>"` and (`package.json` OR `pyproject.toml`); if neither manifest, AskUserQuestion `manifest 파일이 없습니다. 계속할까요?` (yes / 취소).
2. Git safety — `cd <project_root> && git status --porcelain 2>/dev/null; echo $?`:
   - exit ≠ 0 → `⚠️ Git 저장소가 아닙니다.` AskUserQuestion `git init 할까요?` (yes / no / 중단). yes → `git init && git add -A && git commit -m "chore: pre-samvil baseline"`.
   - empty → `✓ Git: clean`. Non-empty → `⚠️ uncommitted changes`. AskUserQuestion `커밋하고 진행?` (커밋 / 그냥 / 중단). 커밋 → `git add -A && git commit -m "chore: save state before SAMVIL analyze"`.

## Step 2 — MCP analysis pass

```
mcp__samvil_mcp__analyze_brownfield_project(
  project_root="<absolute path>",
  project_name="")  // empty = let MCP infer from package.json/dirname
```

Parse the returned JSON. Top-level fields:
- `framework`, `ui_library`, `state_management`, `data_sources` — detected stacks + signal strings.
- `solution_type` + `solution_type_confidence` — high/medium/low.
- `module_count`, `feature_count`.
- `seed` — complete v3.0 seed dict ready to write.
- `confidence_tags` — `{framework, ui, state, solution_type, features}` each ∈ {high, medium, low}.
- `adrs` — list of ADR-EXISTING-NNN dicts (one per heuristic decision).
- `summary_lines` — pre-formatted Korean lines.
- `warnings` — items the user must re-confirm before proceeding.

If returned JSON has top-level `error` key → print `[SAMVIL] ⚠️ Analyze MCP failed: <error>`, AskUserQuestion: `재시도 / 수동으로 seed 작성 / 중단`. Do not auto-proceed.

## Step 3 — Render analysis + user review

Render `[SAMVIL] 프로젝트 분석 결과` block: `경로`, every `result.summary_lines` line (indented), `신뢰도 (confidence_tags)` block listing each of the 5 keys with its level, `추론된 기능 (status: existing): <N>개` followed by per-feature `name · first AC description · first evidence`, `자동 생성 ADR: <len(adrs)>개` listing each `id · title · confidence`, and `⚠️ 경고` block listing every `warnings[i]` (or `(없음)`).

Then AskUserQuestion `이 분석이 정확한가요? (확인 후 project.seed.json + decisions.log 작성)`: `맞아, 진행` (→ Step 4) / `수정 필요` (sub-AskUserQuestion: framework / solution_type / features / 기타 → 수정 후 재확인) / `중단` (exit). If `warnings` non-empty, surface them in the question header so the user explicitly addresses each.

## Step 4 — Persist seed + ADRs + state (atomic, INV-1)

After user approval:

1. `project.seed.json` — atomic-write `result.seed` verbatim. If file already exists, AskUserQuestion `덮어쓸까요?` (백업 후 덮어쓰기 / 병합 / 취소). 백업: `cp project.seed.json project.seed.backup-<ts>.json`.
2. `interview-summary.md` — Bash `cat >>` (never Write tool) a header `# 프로젝트 분석 요약 (Brownfield)` followed by bullets: `프레임워크`, `solution_type` + confidence, `추론된 기능` count, then each `summary_line`.
3. `decisions.log` — append each `result.adrs[i]` as one JSON row (append-only array). `mcp__samvil_mcp__claim_post(...)` best-effort per row; MCP fail → decisions.log is fallback truth (P8/INV-5).
4. If no `session_id` yet: `mcp__samvil_mcp__create_session(project_name="<seed.name>", samvil_tier="<config or 'standard'>")` and capture session_id.
5. `project.state.json` — init/merge with `session_id`, `current_stage: "analyze"`, `_analysis_source: "brownfield"`. Do not clobber existing fields.
6. `mcp__samvil_mcp__save_event(session_id="<sid>", event_type="analyze_complete", stage="<next_stage>", data='{"framework":"<framework>","feature_count":<N>,"warnings":<len(warnings)>}')` and `mcp__samvil_mcp__save_seed_version(session_id="<sid>", version=1, seed_json='<JSON-escaped seed>', change_summary="Reverse-engineered from existing codebase")` — both best-effort.

## Step 5 — Gap analysis + chain (INV-4)

AskUserQuestion (multiSelect) `이 프로젝트에서 뭘 하고 싶으세요?`: `기능 추가` (sub-question 어떤 기능? → seed.features에 새 entry status:"new" 추가 → samvil-build) / `코드 품질 개선` (→ samvil-qa) / `디자인 개선` (→ samvil-design) / `QA 검증` (→ samvil-qa).

Append Analyze section to `.samvil/handoff.md` via Bash `cat >>` or Edit (never Write tool): framework · feature_count · warnings count · chosen route. Print `[SAMVIL] Analyze complete. Routing to <skill>...` and invoke Skill tool with the chosen skill name.

## Anti-Patterns

1. Modifying or deleting existing source files during analyze — read-only phase. Write only to `project.seed.json` / `decisions.log` / `interview-summary.md` / `.samvil/`. 2. Forcing framework conversion (e.g., React→Next.js auto-rewrite) — not analyze's job. 3. Skipping the user-review checkpoint after Step 2 — features inferred from heuristics MUST be confirmed (P2 Description vs Prescription). 4. Proceeding with `solution_type_confidence: low` without re-asking the user. 5. Dropping `warnings` from the render block — every warning must surface. 6. Using Write tool for handoff.md (Bash `cat >>` or Edit only). 7. Persisting seed before user approval (INV-1, irreversibility-aware P10).

## Legacy reference

Full Korean prose (Step 4b/c/d/e/f code-quality grep recipes, dependency-impact heuristics, integration-point analysis, original reverse-seed JSON shape, anti-pattern rationale) in `SKILL.legacy.md`. Consult only when analyze regresses or is extended.
