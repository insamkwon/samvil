# Council retirement — 2-phase migration

Per HANDOFF-v3.2-DECISIONS.md §3.⑨, Council Gate A as an always-on
pipeline stage is retiring. v3.2 keeps it available behind an opt-in
flag; v3.3 removes it entirely. Consensus in v3.2+ runs only as a
**dispute resolver** triggered by specific signals.

## Timeline

| Release | Council Gate A behavior | User action |
|---------|------------------------|-------------|
| **v3.1.x** | Always-on pipeline stage | none |
| **v3.2.0** (this release) | Opt-in via `--council`. Default OFF. Running with `--council` emits a deprecation warning. | no action required; scripts using Council stop triggering it automatically |
| **v3.3.0** | Removed. Consensus only as dispute resolver. | migrate any remaining dependency on Council Gate A |

## What changes for users

**The first time you run `/samvil` on v3.2.0:**

- If you do **nothing**, the pipeline runs without Council Gate A.
  You'll see a single `[INFO]` line: *"Council Gate A is now opt-in."*
- If you pass `--council`, the v3.1 pipeline runs (including the
  Research → Review rounds) and the MCP tool
  `council_deprecation_warning` surfaces the deprecation text.
- Consensus still runs automatically when a dispute is detected (⑨
  triggers). You do not need any flag for that.

## What changes for agents

The `samvil-council` skill has been re-scoped:

- Under v3.1 it ran as a standalone stage.
- Under v3.2 it runs either as a dispute resolver (called by ⑥
  escalation) or when `--council` is passed (legacy).

The Council 3-role agents (Advocate / Devil / Judge) are absorbed into
the ⑤ model-role system:

| v3.1 agent | v3.2 model_role | Notes |
|------------|-----------------|-------|
| `product-owner` | `judge` | unchanged behavior |
| `ceo-advisor` | `reviewer` | context-dependent; can still be spawned in Advocate mode during disputes |
| `growth-advisor` | `reviewer` | same |
| `business-analyst` | `reviewer` or `researcher` | depends on whether it's evaluating vs researching |
| `competitor-analyst` | `researcher` | unchanged |

Existing `.samvil/council/*.md` state files from v3.1 runs are preserved
read-only. On the first v3.2 load of a v3.1 project, the migration tool
(`samvil-update --migrate v3.2`) imports their content as
`retro.observations[]` so the decisions remain auditable.

## Dispute triggers (replaces always-on Council)

Consensus is invoked automatically when **any** of the following
happens:

1. **Generator / Judge mismatch** — Generator marks PASS, Judge marks
   PARTIAL or FAIL. Most common trigger; detects model disagreement
   early.
2. **Weak evidence** — a Reviewer flags evidence as insufficient while
   the claim still reads PASS.
3. **Evolve scope change** — `samvil-evolve` proposes adding or
   removing a feature. Scope changes deserve a second opinion.
4. **Repeated failure signature** — the same failure appears ≥ 2 times
   in a row. Also triggers ⑩ stagnation detection.
5. **Ambiguous intent after L4** — `interview_level=max` ran but
   `intent_clarity` stayed below 0.70.
6. **Unresolved architectural tradeoff** — e.g., Kafka vs SQS
   flagged by tech-architect or tech-lead.

All six triggers are pure-function detections (see
`mcp/samvil_mcp/consensus_v3_2.detect_dispute`). Triggers fire only
when conditions match; no trigger means no consensus call.

## Phase 1 simplification (Judge + Reviewer)

v3.2 ships the resolver with **two** roles, not three:

- **Reviewer** reads the claim history and evidence, returns an
  "accept / reject / escalate" position with a rationale.
- **Judge** reads the Reviewer's position and decides the final
  verdict.

The original three-role design (Advocate / Devil / Judge) is deferred.
Add Devil in v3.3 if dogfood shows Reviewer alone is too easily swayed
by the Generator's framing.

## How to migrate your scripts

If a downstream script depends on Council Gate A running every time:

```bash
# Old (v3.1):
/samvil "my project"

# New (v3.2):
/samvil "my project" --council    # keeps v3.1 behavior, emits warning

# Future (v3.3):
#   --council is removed. Remove the flag. Rely on automatic consensus
#   triggers (⑨). If you need forced consensus, use the experimental
#   override to set a `repeated_failure_signature` or similar trigger.
```

If you have a bespoke CI workflow that parses `.samvil/council/*.md`:

- v3.2: the files are still written when `--council` is active.
- v3.3: they're gone. Switch your parser to
  `.samvil/retro/retro-*.yaml` (the `observations[]` block), or
  `.samvil/claims.jsonl` (filter `type=consensus_verdict`).

## Rollback

If v3.2.0 behavior breaks your workflow, you can always re-enable the
old stage with `--council` for the full v3.2 minor window. The
warning is informational — nothing breaks. File a retro observation
(`category: council_retirement`) describing the gap so the v3.3
migration can account for it.
