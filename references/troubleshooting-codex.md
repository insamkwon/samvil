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

The native path creates an isolated `samvil-codex` marketplace wrapper and
registers the `samvil@samvil-codex` plugin. The distinct marketplace name avoids
colliding with an existing Claude marketplace named `samvil`.
It does not install a global `AGENTS.md` or append an absolute MCP block. The
installer passes an explicit `CODEX_HOME` to every child command, preserves
unrelated marketplace/plugin entries, backs up the registry, and verifies that
personal skill names and hashes are unchanged.

Legacy `--migrate` is fail-closed in this candidate until the CLI can construct
provenance-backed actions for generated AGENTS, direct MCP blocks, and legacy
skills. Do not move those files manually; ambiguous user-modified files must
remain byte-identical.

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

Native stage transitions and runtime verification require an operating-system
interprocess file-lock backend. The current trusted runtime path supports the
`flock` backend used by macOS and Linux; when that backend is unavailable, SAMVIL
returns a blocked error before entering the protected state change instead of
silently weakening the lock to one process.

Native `build_to_qa`, `qa_to_evolve`, and `qa_to_deploy` transitions always
require a current subprocess runtime receipt. An in-flight project upgraded from
an older release is not rewritten or discarded; rerun the Build or QA mechanical
verification once before retrying the gate. The `any_to_retro` recovery route may
start without a receipt only when runtime verification never began. Once it has
begun for that session stage, the requirement remains in trusted storage across
replacement claims and missing projections.

## Duplicate commit or event concern

Retry the exact same transition with the same fixed `transition_id`. The second
call must return the same receipt and must not add another DB event, JSONL event,
claim, marker revision, or project-state advancement. A new `transition_id` is a
new operation, not an idempotency retry.

## QA remains in QA

Missing, corrupt, or failing QA evidence must not advance the run. The controller
keeps the stage in QA until trusted synthesis chooses Deploy, Evolve, or Retro.
User text cannot mint a gate override or irreversible approval claim.

When QA passes without an explicit safe route, the v4.33 candidate proceeds to
Retro. A Deploy request returns `waiting_user` because trusted irreversible-action
attestation is not implemented yet; choose Evolve or Retro to continue. Blocked or
failed convergence may route to Evolve/Retro only when persisted QA convergence
evidence says `blocked` or `failed`.

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
