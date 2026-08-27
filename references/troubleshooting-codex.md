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

If `--check` reports `legacy migration required`, use the explicit migration
mode once instead of manually moving files:

```bash
bash scripts/setup-codex.sh codex --migrate
```

The wrapper first performs a read-only inventory and seals its SHA-256, then
applies that exact plan under an exclusive profile lock. Only byte-identical
legacy SAMVIL skill trees, a known generated global `AGENTS.md`, and the exact
installer-generated direct MCP block are eligible. Originals move to
`backups/legacy-migrations/<timestamp>-<plan>-<id>/`; unrelated config meaning,
comments, and personal skill bytes stay unchanged. Codex may normalize config
line endings during a successful registry update. A normal failure before native
activation completes restores every staged legacy object and restores exact
config bytes when safe. If activation completed but final proof is uncertain, or
unrelated config changed concurrently, the installer preserves the current state,
backup, and recovery journal instead of guessing. Ambiguous or user-modified state
blocks before artifact mutation. Repeating the same sealed plan returns the stored
receipt without running Codex commands again.

Migration reads the actual `codex plugin marketplace list --json` and
`codex plugin list --json` state before profile writes and again after taking the
profile lock. Missing CLI evidence or any of its three integrity digests blocks
the operation. Only the explicitly selected `CODEX_HOME` is handled; repeat the
check separately for each profile you intentionally manage.

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
