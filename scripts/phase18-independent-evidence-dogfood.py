#!/usr/bin/env python3
"""Validate the Phase 18 Independent Evidence contract across skill docs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

REPO = Path(__file__).resolve().parent.parent


def _read(relative: str) -> str:
    return (REPO / relative).read_text(encoding="utf-8")


def _line_number(text: str, needle: str) -> int:
    index = text.find(needle)
    if index < 0:
        raise AssertionError(f"missing required text: {needle!r}")
    return text[:index].count("\n") + 1


def _require(text: str, needles: Iterable[str], *, label: str) -> list[str]:
    found: list[str] = []
    for needle in needles:
        if needle not in text:
            raise AssertionError(f"{label}: missing {needle!r}")
        found.append(needle)
    return found


def _require_order(text: str, needles: list[str], *, label: str) -> dict[str, int]:
    positions: dict[str, int] = {}
    last = -1
    for needle in needles:
        index = text.find(needle)
        if index < 0:
            raise AssertionError(f"{label}: missing ordered text {needle!r}")
        if index <= last:
            raise AssertionError(f"{label}: {needle!r} is out of order")
        last = index
        positions[needle] = _line_number(text, needle)
    return positions


def check_design() -> dict[str, object]:
    thin = _read("skills/samvil-design/SKILL.md")
    legacy = _read("skills/samvil-design/SKILL.legacy.md")
    _require(thin, ["feasibility review before user checkpoint"], label="design thin skill")
    order = _require_order(
        legacy,
        [
            "## Step 3: Gate B",
            "## Step 3b: Blueprint Feasibility Check",
            "## Step 4: User Checkpoint",
        ],
        label="design legacy skill",
    )
    _require(
        legacy,
        [
            "blueprint_feasibility_checked",
            "blueprint_concern",
            "post-feasibility blueprint",
            "The main session remains the only writer",
        ],
        label="design legacy skill",
    )
    return {"status": "pass", "ordered_lines": order}


def check_build_events() -> dict[str, object]:
    text = _read("skills/samvil-build/SKILL.md")
    categories = [
        "`import_error`",
        "`type_error`",
        "`config_error`",
        "`runtime_error`",
        "`dependency_error`",
        "`unknown`",
    ]
    _require(text, categories, label="build event categories")
    _require(
        text,
        [
            'event_type="build_pass"',
            'event_type="build_fail"',
            'event_type="fix_applied"',
            '"error_signature"',
            '"error_category"',
            '"scope":"core"',
            '"scope":"feature:<name>"',
            '"scope":"integration"',
            '"touched_files"',
        ],
        label="build event contract",
    )
    return {"status": "pass", "categories": [item.strip("`") for item in categories]}


def check_qa_taxonomy() -> dict[str, object]:
    paths = [
        "references/qa-checklist.md",
        "skills/samvil-qa/SKILL.md",
        "agents/qa-functional.md",
    ]
    verdicts = ["PASS", "PARTIAL", "UNIMPLEMENTED", "FAIL"]
    for path in paths:
        text = _read(path)
        _require(text, verdicts, label=f"qa taxonomy {path}")
    functional = _read("agents/qa-functional.md")
    _require(
        functional,
        [
            "UNIMPLEMENTED = 0.0",
            "PASS (all PASS/PARTIAL)",
            "REVISE (any UNIMPLEMENTED)",
            "FAIL (any FAIL)",
            "do not output branch-level verdicts",
        ],
        label="qa-functional synthesis contract",
    )
    quality = _read("agents/qa-quality.md")
    _require(
        quality,
        [
            "Don't reclassify Pass 2 functional states",
            "flag it as a quality concern",
            "let the main session reconcile it with Pass 2 evidence",
        ],
        label="qa-quality synthesis contract",
    )
    return {"status": "pass", "files": paths}


def check_independent_qa() -> dict[str, object]:
    text = _read("skills/samvil-qa/SKILL.md")
    order = _require_order(
        text,
        [
            "### `minimal` — Inline QA",
            "### `standard` / `thorough` / `full` — Independent Evidence",
            "### Spawn Pass 2 Independent Agent",
            "### Spawn Pass 3 Independent Agent",
            "### Central Synthesis Rules",
        ],
        label="qa tier flow",
    )
    _require(
        text,
        [
            "The main session is the ONLY writer",
            "Independent agents gather evidence only. They do not write files.",
            "<paste agents/qa-functional.md>",
            "<paste agents/qa-quality.md>",
            "mcp__samvil_mcp__synthesize_qa_evidence",
            "mcp__samvil_mcp__materialize_qa_synthesis",
            "central source of truth",
            "append QA events",
        ],
        label="independent qa ownership",
    )
    return {"status": "pass", "ordered_lines": order}


def check_evolve_context() -> dict[str, object]:
    evolve = _read("skills/samvil-evolve/SKILL.md")
    wonder = _read("agents/wonder-analyst.md")
    _require(
        evolve,
        [
            "events.jsonl — structured build/QA event trail",
            "repeated error signatures",
            "repeated error categories",
            "workaround patterns",
        ],
        label="evolve structured context",
    )
    _require(
        wonder,
        [
            ".samvil/events.jsonl",
            "Build Failure Patterns",
            "repeating errors",
            "frequently touched files",
        ],
        label="wonder structured context",
    )
    return {"status": "pass"}


def run_checks() -> dict[str, object]:
    checks = {
        "design_feasibility": check_design(),
        "build_events": check_build_events(),
        "qa_taxonomy": check_qa_taxonomy(),
        "independent_qa": check_independent_qa(),
        "evolve_context": check_evolve_context(),
    }
    return {"status": "ok", "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--json", action="store_true", help="print JSON summary")
    args = parser.parse_args()

    try:
        result = run_checks()
    except AssertionError as exc:
        if args.json:
            print(json.dumps({"status": "fail", "error": str(exc)}, indent=2))
        else:
            print(f"FAIL: phase18 independent evidence dogfood failed: {exc}")
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("OK: phase18 independent evidence dogfood passed")
        for name in result["checks"]:
            print(f"{name}: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
