# Sprint 1 calibration dogfood — runbook

**Purpose**: Sprint 1 ships 21 `(initial estimate)` constants. §7 exit gate
requires ≥80% of those estimates to have at least one recorded
observation. This document walks through two runs — one toy project, one
real — that generate those observations.

This is **calibration work, not feature work**. The goal is not to ship a
product; the goal is to learn whether our thresholds are correct.

## Prerequisites

- Claim ledger (`mcp/samvil_mcp/claim_ledger.py`) implemented — ✅ Sprint 1
- Gate framework (`mcp/samvil_mcp/gates.py`) implemented — ✅ Sprint 1
- `references/gate_config.yaml` exists — ✅ Sprint 1
- `.samvil/experiments.jsonl` seeded — run `python3 scripts/seed-experiments.py` if empty
- Glossary green — run `./scripts/check-glossary.sh`

## Run 1 — toy project (~30 min)

### Setup

1. Pick a tiny scope: "1-page countdown timer".
2. Start a fresh project dir: `mkdir -p /tmp/samvil-toy && cd /tmp/samvil-toy`.
3. Run `/samvil "countdown timer"` in Claude Code.

### What to measure

| Experiment id pattern | What to record |
|-----------------------|----------------|
| `exp_gate_interview_to_seed_<tier>_seed_readiness` | The `ambiguity_score` at interview completion vs the per-tier floor. |
| `exp_gate_build_to_qa_<tier>_implementation_rate` | The actual `implementation_rate` emitted by `build_stage_complete`. |
| `exp_handoff_*` (wall_time / llm_calls / cost) | Wall time, model calls, approximate cost. |

For each gate the harness evaluates during the run, the skill should
append the resulting `GateVerdict` as a `gate_verdict` claim via
`claim_post`. Wire this in when editing the skills for Sprint 1 final
polish; for Sprint 1 manual dogfood it is acceptable to post the claims
by hand using the MCP tool from the Claude Code session.

### Record observations

After the run:

```bash
python3 scripts/view-claims.py --type gate_verdict
python3 scripts/view-gates.py --samvil-tier <your_tier>
python3 scripts/samvil-status.py
```

Then append observations to the experiment rows:

```python
# pseudo — run in a Python REPL from the repo root
import json
from pathlib import Path

rows = []
for line in Path(".samvil/experiments.jsonl").read_text().splitlines():
    if line.strip():
        rows.append(json.loads(line))
for r in rows:
    if r["name"] == "build_to_qa:standard:implementation_rate":
        r["observations"].append({
            "ts": "<iso>",
            "value_seen": 0.82,
            "verdict": "block",
            "note": "toy run 1 — standard floor 0.85",
        })
Path(".samvil/experiments.jsonl").write_text(
    "\n".join(json.dumps(r) for r in rows) + "\n"
)
```

(This is deliberately manual in Sprint 1. Sprint 5a automates
observation-collection via the retro pipeline.)

## Run 2 — real project (~2–3 hours)

Pick a small but real target. Suggestions:

- A single `/samvil "focus timer with leaderboard"` run on `thorough` tier.
- Re-running an existing v3.1 toy (e.g. a prior dogfood from v3.1) on
  v3.2 — compare observations against the baseline.

Record the same three metrics. For the real run, also capture:

- Whether any escalation check fired (`ac_testability`,
  `lifecycle_coverage`, `decision_boundary_clarity`).
- Whether the same check escalated twice (should trigger user-decision
  per §3.⑥).
- Whether Graceful Degradation (P8) was invoked (MCP down, etc.). Log the
  category per `references/gate-vs-degradation.md`.

## Exit-gate check

Run the verification script:

```bash
python3 scripts/check-exit-gate-sprint1.py
```

PASS criteria:

- [ ] Empty project round-trips the skeleton: claim_post → claim_verify
      → gate_check → view-gates show sensible output.
- [ ] `./scripts/check-glossary.sh` → `green`.
- [ ] ≥80% of rows in `.samvil/experiments.jsonl` carry ≥1 observation.
- [ ] `mcp/tests/test_claim_ledger.py` + `mcp/tests/test_gates.py` pass.

Record the result as a `policy_adoption` claim:

```python
claim_post(
    project_root=".",
    claim_type="policy_adoption",
    subject="sprint1_exit_gate",
    statement="Sprint 1 exit gate passed on <date>",
    authority_file=".samvil/state.json",
    claimed_by="agent:dogfood-operator",
    evidence_json='["scripts/check-exit-gate-sprint1.py:run"]',
)
```

## If the exit gate fails

- If coverage is <80%, add synthetic observations by running the toy
  project on additional tiers (e.g., `minimal`, `full`, `deep`) to touch
  more per-tier thresholds. Do not make up observations — the point is
  learning.
- If the glossary check fails, address the violation; never annotate
  `# glossary-allow` without updating `references/glossary.md`.
- If tests fail, treat it as a mechanical failure (K3 Error Philosophy).
  Fix first; do not record as a retro observation.

## What ships to Sprint 2

Sprint 2 uses the calibrated numbers — not the initial estimates — as the
default for `references/gate_config.yaml` overrides. Any constant that
stays in `experimental` stage at the end of Sprint 3 is a candidate for
Policy-experiment Promotion Failure (§9 open risk #6) and triggers a
`high` stagnation retro observation.
