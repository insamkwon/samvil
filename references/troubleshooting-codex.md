# Troubleshooting Codex on SAMVIL v4.33

This guide covers the native Codex plugin candidate. It distinguishes repository
readiness, profile activation, MCP transition behavior, and actual CLI runtime
authentication; a green result in one layer does not prove another.

## Read-only checks first

```bash
codex --version
bash scripts/setup-codex.sh codex --check
python3 scripts/codex-native-e2e.py --check
python3 scripts/check-host-parity.py --strict
```

`--check` does not modify the Codex profile. The installer must see the relative
`.codex-plugin/plugin.json`, `.codex-mcp.json`, and exactly three public skills:
`run`, `resume`, and `status`.

## Safe installation

```bash
bash scripts/setup-codex.sh codex --install
```

The native path registers the repository marketplace and `samvil@samvil` plugin.
It does not install a global `AGENTS.md` or append an absolute MCP block. The
installer passes an explicit `CODEX_HOME` to every child command, preserves
unrelated marketplace/plugin entries, backs up the registry, and verifies that
personal skill names and hashes are unchanged.

Use `--migrate` only for artifacts already classified as generated legacy state.
Ambiguous user-modified files are blockers and must remain byte-identical.

## `invalid_grant: Invalid refresh token`

This is a Codex authentication blocker, not a SAMVIL stage PASS. Reauthorize the
Codex CLI using the login flow supported by the installed Codex version, then run
the real runtime smoke again. Do not convert repository readiness or Desktop MCP
evidence into a CLI runtime receipt.

The current persisted CLI evidence is intentionally classified `blocked_auth` in
`docs/evidence/codex-native-autonomy/cli-runtime.json`.

## Stage does not start or resumes the wrong run

1. Call `samvil:status` and inspect the returned `run_id`, stage, revision, and
   stop reason.
2. Reread `.samvil/next-skill.json`, `project.state.json`, and the transition
   receipt/journal. Do not repair them from conversation history.
3. A fresh envelope must create a session before `begin_stage`; an empty `run_id`
   is invalid.
4. A marker or receipt owned by another run/session must fail closed.

## Duplicate commit or event concern

Retry the exact same transition with the same fixed `transition_id`. The second
call must return the same receipt and must not add another DB event, JSONL event,
claim, marker revision, or project-state advancement. A new `transition_id` is a
new operation, not an idempotency retry.

## QA remains in QA

Missing, corrupt, or failing QA evidence must not advance the run. The controller
keeps the stage in QA until trusted synthesis chooses Deploy, Evolve, or Retro.
User text cannot mint a gate override or irreversible approval claim.

## Runtime harness reports `not implemented`

`--scenario` and `--all` currently fail closed because the scripts do not yet
execute a full host scenario matrix. Only `--check` is a readiness check. This is
intentional: an unexecuted scenario must never produce a green runtime claim.

## Evidence classifications

- `machine_runtime`: actual host process completed the claimed flow.
- `manual_desktop`: observed in Codex Desktop; useful but not CLI parity.
- `structural`: manifests, tools, and references are wired.
- `blocked_auth`: the real host started but authentication prevented completion.

Always report the narrowest classification supported by the receipt.
