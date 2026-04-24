#!/usr/bin/env python3
"""Sprint 6 final-gate check.

Per HANDOFF-v3.2-DECISIONS.md §7:

  Final gate — v3.1 project upgrades cleanly; sample run stays within
  budget; all promised docs (§8) exist.

Automated checks:

  A — version synced to 3.2.0 across plugin.json / __init__.py / README.
  B — every Promised Deliverable (§8) file exists.
  C — end-to-end migration: scaffold a fake v3.1 project, run
      apply_migration, assert schema bumped + artifacts created.
  D — budget evaluator handles the full dimension matrix.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.migrate_v3_2 import V32_SCHEMA_VERSION, apply_migration  # noqa: E402
from samvil_mcp.performance_budget import (  # noqa: E402
    DEFAULT_BUDGET,
    Consumption,
    evaluate_status,
)


PROMISED_DELIVERABLES = [
    "references/model-routing-guide.md",
    "references/model-profiles-schema.md",
    "references/troubleshooting-codex.md",
    "references/interview-levels.md",
    "references/jurisdiction-boundary-cases.md",
    "references/migration-v3.1-to-v3.2.md",
    "references/glossary.md",
    "references/gate-vs-degradation.md",
    "references/council-retirement-migration.md",
]


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}")


def check_a_versions() -> bool:
    print("A) Version synced to 3.2.0")
    paths = {
        "plugin.json": REPO / ".claude-plugin" / "plugin.json",
        "__init__.py": REPO / "mcp" / "samvil_mcp" / "__init__.py",
        "README.md": REPO / "README.md",
    }
    versions: dict[str, str | None] = {}
    plugin_json = json.loads(paths["plugin.json"].read_text())
    versions["plugin.json"] = plugin_json.get("version")
    init_text = paths["__init__.py"].read_text()
    m = re.search(r'__version__\s*=\s*"([^"]+)"', init_text)
    versions["__init__.py"] = m.group(1) if m else None
    readme = paths["README.md"].read_text()
    m = re.search(r"`v(\d+\.\d+\.\d+)`", readme)
    versions["README.md"] = m.group(1) if m else None

    expected = "3.2.0"
    for label, v in versions.items():
        if v != expected:
            _fail(f"{label}: {v!r} (expected {expected!r})")
            return False
    _ok(f"all three synced at {expected}")
    return True


def check_b_promised_docs() -> bool:
    print("B) Promised deliverables present")
    missing: list[str] = []
    for rel in PROMISED_DELIVERABLES:
        p = REPO / rel
        if not p.exists():
            missing.append(rel)
    if missing:
        for m in missing:
            _fail(f"missing: {m}")
        return False
    _ok(f"{len(PROMISED_DELIVERABLES)} docs all present")
    return True


def check_c_end_to_end_migration() -> bool:
    print("C) v3.1 → v3.2 migration end-to-end")
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        (project / "project.seed.json").write_text(
            json.dumps(
                {
                    "schema_version": "3.1",
                    "name": "demo",
                    "agent_tier": "standard",  # glossary-allow: v3.1 test fixture
                    "features": [
                        {
                            "name": "login",
                            "acceptance_criteria": [
                                {
                                    "id": "AC-1.1",
                                    "intent": "user logs in",
                                    "verification": "login returns 200",
                                    "children": [],
                                }
                            ],
                        }
                    ],
                }
            )
        )

        plan = apply_migration(project, dry_run=False)
        if plan.dry_run:
            _fail("apply returned dry-run despite dry_run=False")
            return False
        migrated = json.loads((project / "project.seed.json").read_text())
        if migrated.get("schema_version") != V32_SCHEMA_VERSION:
            _fail(f"schema not bumped: {migrated.get('schema_version')}")
            return False
        if "samvil_tier" not in migrated:
            _fail("samvil_tier not added")
            return False
        if not (project / ".samvil" / "claims.jsonl").exists():
            _fail("claims.jsonl not created")
            return False
        if not (project / "project.v3-1.backup.json").exists():
            _fail("backup not written")
            return False
        if not (project / ".samvil" / "rollback" / "v3_2_0" / "manifest.json").exists():
            _fail("rollback snapshot missing")
            return False
    _ok("migration: schema + tier rename + claims + backup + rollback")
    return True


def check_d_budget_evaluator() -> bool:
    print("D) Budget evaluator handles full tier matrix")
    for tier, ok_budget in (
        ("minimal", Consumption(wall_time_minutes=5, llm_calls=10, estimated_cost_usd=0.1)),
        ("standard", Consumption(wall_time_minutes=20, llm_calls=80, estimated_cost_usd=1)),
        ("thorough", Consumption(wall_time_minutes=40, llm_calls=200, estimated_cost_usd=4)),
        ("full", Consumption(wall_time_minutes=90, llm_calls=500, estimated_cost_usd=10)),
        ("deep", Consumption(wall_time_minutes=150, llm_calls=1000, estimated_cost_usd=20)),
    ):
        s = evaluate_status(budget=DEFAULT_BUDGET, samvil_tier=tier, consumed=ok_budget)
        if s.hard_stop:
            _fail(f"{tier}: within-budget consumption triggered hard_stop")
            return False
    _ok("5 tiers evaluated; no false hard-stop")
    return True


def main() -> int:
    results = {
        "A": check_a_versions(),
        "B": check_b_promised_docs(),
        "C": check_c_end_to_end_migration(),
        "D": check_d_budget_evaluator(),
    }
    print()
    print("Summary")
    for k, v in results.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
