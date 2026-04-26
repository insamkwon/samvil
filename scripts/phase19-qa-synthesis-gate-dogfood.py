#!/usr/bin/env python3
"""Run Phase 19 QA synthesis gate dogfood scenarios."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.qa_synthesis import synthesize_qa_evidence  # noqa: E402


def _base(pass2_items: list[dict], pass3: dict | None = None) -> dict:
    return {
        "iteration": 1,
        "max_iterations": 3,
        "pass1": {"status": "PASS"},
        "pass2": {"items": pass2_items},
        "pass3": pass3 or {"verdict": "PASS"},
    }


def _assert_case(name: str, evidence: dict, expected: str, expected_action: str) -> dict:
    result = synthesize_qa_evidence(evidence)
    if result["verdict"] != expected:
        raise AssertionError(f"{name}: expected {expected}, got {result}")
    if result["next_action"] != expected_action:
        raise AssertionError(f"{name}: expected action {expected_action!r}, got {result}")
    return {
        "name": name,
        "verdict": result["verdict"],
        "reason": result["reason"],
        "next_action": result["next_action"],
        "pass2_counts": result["pass2"]["counts"],
        "ownership_violations": len(result["ownership_violations"]),
    }


def run_cases() -> list[dict]:
    pass_with_partial = _assert_case(
        "pass-with-partial-evidence",
        _base([
            {"id": "AC-1", "criterion": "Create task", "verdict": "PASS", "evidence": ["app/page.tsx:10"]},
            {"id": "AC-2", "criterion": "Drag feel", "verdict": "PARTIAL", "reason": "runtime feel"},
        ]),
        "PASS",
        "proceed to deploy or evolve offer",
    )
    unimplemented_revise = _assert_case(
        "unimplemented-non-core-revise",
        _base([
            {"id": "AC-3", "criterion": "AI summary", "verdict": "UNIMPLEMENTED", "reason": "stub response"},
        ]),
        "REVISE",
        "replace stubs or hardcoded paths with real implementation",
    )
    quality_revise = _assert_case(
        "quality-only-revise",
        _base([
            {"id": "AC-1", "criterion": "Create task", "verdict": "PASS", "evidence": ["app/page.tsx:10"]},
        ], pass3={"verdict": "REVISE", "issues": ["missing focus state"]}),
        "REVISE",
        "fix quality issues without changing functional verdicts",
    )
    ownership_revise = _base([
        {"id": "AC-1", "criterion": "Create task", "verdict": "PASS", "evidence": ["app/page.tsx:10"]},
    ])
    ownership_revise["agent_writes"] = [{"agent": "qa-functional", "path": ".samvil/qa-report.md"}]
    ownership = _assert_case(
        "independent-protected-write-revise",
        ownership_revise,
        "REVISE",
        "discard protected writes and rerun central synthesis",
    )
    core_fail = _assert_case(
        "core-unimplemented-fail",
        _base([
            {
                "id": "AC-core",
                "criterion": "Primary flow",
                "verdict": "UNIMPLEMENTED",
                "reason": "TODO path",
                "is_core_experience": True,
            },
        ]),
        "FAIL",
        "report core implementation failure to user",
    )
    return [pass_with_partial, unimplemented_revise, quality_revise, ownership, core_fail]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--json", action="store_true", help="print JSON summary")
    args = parser.parse_args()

    try:
        results = run_cases()
    except AssertionError as exc:
        if args.json:
            print(json.dumps({"status": "fail", "error": str(exc)}, indent=2))
        else:
            print(f"FAIL: phase19 QA synthesis gate dogfood failed: {exc}")
        return 1

    if args.json:
        print(json.dumps({"status": "ok", "results": results}, indent=2))
    else:
        print("OK: phase19 QA synthesis gate dogfood passed")
        for result in results:
            print(
                f"{result['name']}: verdict={result['verdict']} "
                f"reason='{result['reason']}' next_action='{result['next_action']}'"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
