#!/usr/bin/env python3
"""Replay a tiny Phase 2 continuation flow across host strategies."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.host import chain_strategy, resolve_host_capability  # noqa: E402

FIXTURE = REPO / "mcp" / "tests" / "fixtures" / "phase2" / "small-web-app"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _next_after_seed(tier: str) -> tuple[str, str]:
    if tier == "minimal":
        return "samvil-design", "minimal tier skips council"
    return "samvil-council", f"{tier} tier routes through council"


def _marker(host: str, next_skill: str, reason: str, from_stage: str, created_by: str) -> dict:
    return {
        "schema_version": "1.0",
        "chain_via": "file_marker",
        "host": host,
        "next_skill": next_skill,
        "reason": reason,
        "from_stage": from_stage,
        "created_by": created_by,
    }


def _continue(project_root: Path, host: str, next_skill: str, reason: str, from_stage: str) -> dict:
    cap = resolve_host_capability(host)
    strategy = chain_strategy(cap)
    created_by = f"samvil-{from_stage}"
    normalized = _marker(cap.name, next_skill, reason, from_stage, created_by)

    if strategy == "file_marker":
        marker_path = project_root / ".samvil" / "next-skill.json"
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")
        persisted = _load_json(marker_path)
        if persisted != normalized:
            raise AssertionError("persisted marker differs from normalized marker")
    elif strategy != "skill_tool":
        raise AssertionError(f"unknown chain strategy: {strategy}")

    return {
        "host": cap.name,
        "chain_via": strategy,
        "next_skill": next_skill,
        "normalized_marker": normalized,
    }


def replay_host(host: str) -> dict:
    with tempfile.TemporaryDirectory(prefix=f"samvil-{host}-") as tmp:
        project_root = Path(tmp) / "small-web-app"
        shutil.copytree(FIXTURE, project_root)
        config = _load_json(project_root / "project.config.json")
        seed = _load_json(project_root / "project.seed.json")
        if seed["name"] != "small-web-app":
            raise AssertionError("fixture seed did not load")

        seed_next, seed_reason = _next_after_seed(config["samvil_tier"])
        seed_result = _continue(project_root, host, seed_next, seed_reason, "seed")
        design_result = _continue(
            project_root,
            host,
            "samvil-scaffold",
            "design completed",
            "design",
        )
        return {"seed": seed_result, "design": design_result}


def main() -> int:
    claude = replay_host("claude_code")
    codex = replay_host("codex_cli")

    for stage in ("seed", "design"):
        if claude[stage]["next_skill"] != codex[stage]["next_skill"]:
            print(f"FAIL: {stage} next_skill differs", file=sys.stderr)
            return 1
        if claude[stage]["normalized_marker"]["next_skill"] != codex[stage]["normalized_marker"]["next_skill"]:
            print(f"FAIL: {stage} normalized marker differs", file=sys.stderr)
            return 1

    print("OK: cross-host continuation replay passed")
    print(f"seed_next: {codex['seed']['next_skill']}")
    print(f"design_next: {codex['design']['next_skill']}")
    print(f"hosts: {claude['seed']['chain_via']}, {codex['seed']['chain_via']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
