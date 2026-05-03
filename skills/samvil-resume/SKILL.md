---
name: samvil-resume
description: "Resume an interrupted SAMVIL session. Reads project.state.json and jumps back to the last in-progress stage — no re-interview needed."
---

# SAMVIL Resume — Session Recovery Entry Point

Adopt the **SAMVIL Resumption** role. Read the interrupted project's state,
show a summary, and chain to the correct stage skill. Works on any host
that supports the Skill tool (Claude Code) or file-marker chain (Codex CLI).
For a brand-new project with no prior state, fall through to `samvil-interview`.

## Boot Sequence

1. `mcp__samvil_mcp__save_event(session_id="<sid-or-null>", event_type="stage_change", stage="resume", data='{"action":"resume_start"}')`
   — best-effort, non-fatal if no session_id yet.
2. `mcp__samvil_mcp__resume_session(project_root="<cwd>")` — reads state.json, handoff.md.
3. Branch on `found` (see Step 1 / Step 2 below).

## Step 1 — Not Resumable

If `resume_session.found == false`:

> **재개할 세션이 없습니다.**
> `.samvil/state.json` 또는 `project.state.json` 파일을 찾을 수 없어요.
> 새 프로젝트로 시작할게요.

Invoke `samvil-interview` via Skill tool and stop here.

## Step 2 — Session Found

If `resume_session.found == true`, render this summary panel:

```
╔══════════════════════════════════════════════════╗
║  SAMVIL — 이전 세션 발견                        ║
╠══════════════════════════════════════════════════╣
║  프로젝트   : <project_name or "(unnamed)">     ║
║  티어       : <samvil_tier>                     ║
║  마지막 단계: <last_stage>  (<stage_progress>)  ║
║  경과 시간  : <minutes_since>분 전 (없으면 "알 수 없음") ║
╚══════════════════════════════════════════════════╝
```

If `handoff_excerpt` is non-empty, print:

```
--- 마지막 핸드오프 메모 ---
<handoff_excerpt>
---
```

If `failed_acs` is non-empty, list up to 5 entries as:
> ⚠️ 이전 세션에서 실패한 AC: `<ac>`, `<ac>`, ...

Then AskUserQuestion:
> "**<next_skill>** 단계부터 이어갈까요?"
> Options:
>   1. 네, 이어서 진행 (→ invoke next_skill)
>   2. 처음부터 새로 시작 (→ invoke samvil-interview)
>   3. 특정 단계 선택 (→ user specifies, invoke that samvil-<stage>)

## Step 3 — Resume or Restart

On option 1 (resume):
- Do NOT overwrite `project.state.json`.
- `mcp__samvil_mcp__save_event(session_id="<sid-or-null>", event_type="stage_change", stage="<last_stage>", data='{"action":"resumed"}')`
- Invoke `<next_skill>` via Skill tool.

On option 2 (restart):
- AskUserQuestion: "state.json을 초기화할까요?" — if confirmed, `rm project.state.json` (P10: irreversible action).
- Invoke `samvil-interview` via Skill tool.

On option 3 (custom stage):
- Validate stage name is one of: interview, seed, council, design, scaffold, build, qa, deploy, evolve, retro.
- Invoke `samvil-<stage>` via Skill tool.

## Graceful Degradation (P8)

- MCP `resume_session` fails → treat as `found: false`, warn once, proceed to `samvil-interview`.
- `handoff.md` unreadable → skip excerpt silently.
- `minutes_since` null → show "경과 시간: 알 수 없음".
