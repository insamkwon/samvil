# Gate (⑥) vs Graceful Degradation (P8) — boundary decision table

**Apparent conflict**: §3.⑥ says *every stage gate is Hard by default*. P8
(one of the ten core principles) says *"some components fail, pipeline
continues"*. These look contradictory at first read.

**Resolution** (from §6.3 of the v3.2 decisions handoff):

| Rule | When it applies |
|------|-----------------|
| **Graceful Degradation (P8)** | The failure affects *infrastructure components* — MCP server down, external HTTP 500, cache miss, a secondary observability write. The pipeline falls back to file-only mode; the known-true result is eventually recorded. |
| **Gate-Hard (⑥)** | The failure affects a *contract verification* — seed not ready, build log shows an error, QA evidence missing, implementation_rate below floor. These cannot be fallback-eligible; they change the truth of a claim. |

**The boundary, in one sentence**: if the failure changes the truth of a
claim, it's a gate failure (hard). If it only slows down observation of a
known-true claim, it's graceful degradation.

## Decision table

Use this when adding new failure-handling code. If you can't place a case
confidently in one row, escalate via retro `observation[severity: high]`
and update this table in the same PR.

| Scenario | Category | Why | What happens |
|---------|---------|-----|-----------------------|
| MCP server unreachable during `save_event` | Degradation | The event is still true; we just can't post it. | Write to `events.jsonl` locally, log `mcp-health.jsonl` failure, continue pipeline. |
| MCP server unreachable during `claim_verify` | Degradation | Ledger is file-first (`.samvil/claims.jsonl`). Retry/queue. | Write claim row to JSONL, queue verification attempt, continue. When MCP returns, re-verify. |
| `npm run build` fails with compile error | Gate (Hard) | Build fails → `build_to_qa` gate cannot PASS. The claim "build works" is false. | Block. Required action: `fix_build` (handled by build-worker Repairer role in Sprint 3+). |
| `implementation_rate = 0.70` on `samvil_tier=standard` | Gate (Hard) | Floor is 0.85. Claim "enough features implemented" is false. | Block with `failed_checks=["implementation_rate"]`. Required action: continue build. |
| `ac_testability` score below floor in `samvil_tier=thorough` | Gate (Escalate) | Testability is an escalation-eligible check above `minimal`. | `verdict=escalate`, `required_action=split_ac`. Route subject to stronger model; same check escalating twice forces user decision. |
| Playwright smoke-run cannot reach `localhost:3000` | Degradation | Observability gap, not truth change. | Fall back to static-analysis QA Pass. Log gap. Downstream claim notes the fallback. |
| Seed file absent when skill expects it | Gate (Hard) | No seed → no truth to verify. | Block `seed_to_council`. Required action: `fix_schema` or user re-interview. |
| Retro MCP write times out | Degradation | Retro observations are also appended locally. | Local file wins; MCP retried on next call. |
| Council Round-1 Agent times out | Context-dependent | If it's the *only* reviewer agent (minimal tier), the verdict is incomplete → Gate. If it's one of N (standard+), N-1 verdicts are still truthful → Degradation. | See below. |
| Deploy step fails halfway | Gate (Hard, P10) | Irreversible action with partial state; auto-continuing could mask data loss. | Block. Require user decision. |
| Glossary check fails in CI | Gate (Hard) | Vocabulary collision is a contract violation. | Block merge. |
| `ClickHouse` / `PostHog` analytics write fails | Degradation | Telemetry layer, not contract layer. | Log and continue. |

### The Council case in more detail

Council is a reviewer pool. If `samvil_tier=minimal` runs with one
reviewer and that reviewer times out, there is no verdict to record — the
`council_to_design` gate **blocks**. If `samvil_tier=standard` runs with
two or more reviewers and one times out, the quorum rule determines the
verdict; a timeout is logged as a degradation note. Same failure, different
category, because the *availability of truth* differs.

## How this maps to code

1. Gate logic lives in `mcp/samvil_mcp/gates.py`. Every skill that needs to
   pass a gate calls `gate_check(name, samvil_tier=..., metrics=...)` and
   branches on `verdict`.
2. Degradation logic is scattered across skills and MCP tools. Pattern:
   ```
   write to local file (always)
   try: MCP call (best-effort)
   on failure: log to .samvil/mcp-health.jsonl; continue
   ```
   This pattern was adopted in v2.2.0 as INV-5 and is preserved verbatim
   in v3.2.
3. When a skill has to choose between "block" and "continue with
   degradation", the order of operations is:
   - If the contract can be verified → continue.
   - If the contract can't be verified and the failure is an *observation*
     gap → continue and annotate.
   - If the contract can't be verified and the failure changes truth →
     block via `gate_check`.

## Anti-patterns

- **Using degradation to hide a gate failure**: e.g., pretending
  `implementation_rate=0.70` passes because "the build compiled". No —
  the floor exists for a reason.
- **Hard-blocking a purely telemetry failure**: e.g., failing the pipeline
  because PostHog is down. Telemetry is never contract-layer.
- **Silent degradation**: every degradation write must hit
  `.samvil/mcp-health.jsonl` (or equivalent) so retro can see it. If it's
  silent, it's a hidden gate bypass.

## Retro hook

Sprint 5a's `observations[]` schema includes a `category` field. Operators
seeing unexpected behavior at this boundary should file
`{ category: "gate_vs_p8_boundary", severity: high, subject: <failing
code path> }` so the decision table above stays alive.
