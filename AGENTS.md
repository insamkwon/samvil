# SAMVIL — AI Vibe-Coding Harness (Codex / OpenCode / Gemini)

> One-line idea → self-correcting, production-ready app.

You are an AI assistant running the SAMVIL pipeline on a non-Claude-Code host
(Codex CLI, OpenCode, Gemini CLI, or similar). Read this file in full before
taking any action.

---

## 1. Always Check the Chain Marker First

SAMVIL uses a file marker at `.samvil/next-skill.json` to persist pipeline
state across sessions. Every skill writes the next skill before it exits.

**On every session start:**

```
1. Call MCP tool: read_chain_marker(project_root=".")
   • If marker exists → its `next_skill` field is your current task.
   • If no marker    → fresh start. Ask the user what they want to build.
```

The full marker schema is in `references/host-continuation.md`.

---

## 2. Skill Instruction Files

Each pipeline stage has a dedicated instruction file:

| Stage | Instruction file |
|---|---|
| Start (orchestrator) | `references/codex-commands/samvil.md` |
| Interview | `references/codex-commands/samvil-interview.md` |
| PM Interview | `references/codex-commands/samvil-pm-interview.md` |
| Seed | `references/codex-commands/samvil-seed.md` |
| Council | `references/codex-commands/samvil-council.md` |
| Design | `references/codex-commands/samvil-design.md` |
| Scaffold | `references/codex-commands/samvil-scaffold.md` |
| Build | `references/codex-commands/samvil-build.md` |
| QA | `references/codex-commands/samvil-qa.md` |
| Deploy | `references/codex-commands/samvil-deploy.md` |
| Evolve | `references/codex-commands/samvil-evolve.md` |
| Retro | `references/codex-commands/samvil-retro.md` |
| Analyze | `references/codex-commands/samvil-analyze.md` |
| Doctor | `references/codex-commands/samvil-doctor.md` |
| Update | `references/codex-commands/samvil-update.md` |

**Read the instruction file for the current `next_skill` before proceeding.**

---

## 3. MCP Tools Required

The `samvil-mcp` server must be running. Setup: `bash scripts/setup-codex.sh`.

Key tools used throughout the pipeline:

| Tool | Purpose |
|---|---|
| `read_chain_marker(project_root)` | Read current pipeline state |
| `write_chain_marker(project_root, host_name, current_skill)` | Advance to next stage |
| `score_ambiguity(interview_state, tier)` | Check if interview is complete |
| `validate_seed(seed_path)` | Validate seed.json |
| `snapshot_generation(project_root)` | Capture evolve cycle results (regression guard) |
| `get_health_tier_summary(project_root)` | MCP health: healthy / degraded / critical |

Use `host_name="codex_cli"` in `write_chain_marker` when running in Codex CLI.
Use `host_name="opencode"` for OpenCode, `host_name="gemini_cli"` for Gemini CLI.

---

## 4. Pipeline Flow

```
samvil → samvil-interview → samvil-seed → [samvil-council] → samvil-design
       → samvil-scaffold → samvil-build → samvil-qa → samvil-evolve → samvil-retro
```

`samvil-council` is skipped in `minimal` tier. The chain marker handles this
automatically — just follow `next_skill` from the marker.

---

## 5. Critical Rules

1. **Seed is SSOT** — always read `.samvil/project.seed.json` at each stage.
2. **Evidence-based assertions** — every PASS verdict needs a `file:line` reference (P1).
3. **Stub = FAIL** — hardcoded or mocked values trigger automatic FAIL (P8).
4. **Circuit Breaker** — same failure twice in a row → stop and report to user.
5. **Korean with user** — all user-facing messages in Korean; code/commits in English.
6. **Graceful degradation** — MCP call failure → fall back to file-based state (P8).

---

## 6. Project Files (SSOT)

| File | Contents |
|---|---|
| `.samvil/project.seed.json` | Requirements, features, ACs |
| `.samvil/project.state.json` | Current pipeline stage |
| `.samvil/handoff.md` | Cross-session continuation notes |
| `.samvil/qa-results.json` | QA pass/fail verdicts |
| `.samvil/events.jsonl` | Event audit log |
| `.samvil/next-skill.json` | Chain marker (current skill pointer) |
| `.samvil/claims.jsonl` | Contract ledger |

---

## 7. Gemini CLI Users

Gemini uses TOML command files instead of Markdown.
Command files are in `references/gemini-commands/`.
Use `host_name="gemini_cli"` in `write_chain_marker`.

---

## 8. Troubleshooting

- MCP not available → `bash scripts/setup-codex.sh`
- Chain marker validation → `python3 scripts/host-continuation-smoke.py .`
- Full diagnostics → follow `references/codex-commands/samvil-doctor.md`
- Codex-specific issues → `references/troubleshooting-codex.md`
