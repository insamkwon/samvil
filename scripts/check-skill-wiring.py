#!/usr/bin/env python3
"""Skill wiring smoke test (v3.2 β plan, post-Sprint 6).

Verifies each stage SKILL.md mentions the Contract Layer Protocol and
contains the minimal MCP tool references it should. Grep-based — no
runtime execution. The point is to catch "someone edited a skill and
forgot to call the post_stage gate" before it regresses silently.

Rules:
  * Every stage skill that changed in the β wiring must mention
    `contract-layer-protocol.md`.
  * Each skill must reference the specific MCP tools it was supposed
    to wire up.

Not checked here (runtime):
  * Do the tools actually get called when the skill runs?
    → requires real `/samvil` invocation (dogfood).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

CHECKS: list[tuple[str, str, tuple[str, ...]]] = [
    # (skill_name, skill_path, required substrings)
    (
        "samvil",
        "skills/samvil/SKILL.md",
        ("contract-layer-protocol", "check_jurisdiction",),
    ),
    (
        "samvil-interview",
        "skills/samvil-interview/SKILL.md",
        (
            "contract-layer-protocol",
            "compute_seed_readiness",
            "gate_check",
            "interview_to_seed",
            "render_domain_context",
        ),
    ),
    (
        "samvil-build",
        "skills/samvil-build/SKILL.md",
        (
            "SKILL.legacy.md",
            "aggregate_build_phase_a",
            "dispatch_build_batch",
            "finalize_build_phase_z",
            "claim_post",
            "gate_check",
            "build_to_qa",
            "write_leaf_checkpoint",
            "trace_write",
            "index_ac_tree",
            "search_ac_tree_by_feature",
        ),
    ),
    (
        "samvil-qa",
        "skills/samvil-qa/SKILL.md",
        (
            "contract-layer-protocol",
            "route_task",
            "validate_role_separation",
            "claim_verify",
            "consensus_trigger",
            "qa_to_deploy",
            "render_pattern_context",
            "render_domain_context",
            "aggregate_qa_boot_context",
            "dispatch_qa_pass1_batch",
            "finalize_qa_verdict",
            "SKILL.legacy.md",
        ),
    ),
    (
        "samvil-council",
        "skills/samvil-council/SKILL.md",
        (
            "council_deprecation_warning",
            "council-retirement-migration",
            "--council",
            "synthesize_council_verdicts",
            "SKILL.legacy.md",
        ),
    ),
    (
        "samvil-design",
        "skills/samvil-design/SKILL.md",
        (
            "SKILL.legacy.md",
            "get_orchestration_state",
            "stage_can_proceed",
            "host_chain_strategy",
            "complete_stage",
            "next-skill.json",
            "render_domain_context",
        ),
    ),
    (
        "samvil-update",
        "skills/samvil-update/SKILL.md",
        (
            "migrate_plan",
            "migrate_apply",
            "--migrate v3.2",
            "v3.1 → v3.2",
        ),
    ),
    (
        "samvil-retro",
        "skills/samvil-retro/SKILL.md",
        (
            "narrate_build_prompt",
            "narrate_parse",
        ),
    ),
    (
        "samvil-scaffold",
        "skills/samvil-scaffold/SKILL.md",
        (
            "SKILL.legacy.md",
            "evaluate_scaffold_target",
            "version_pins",
            "sanity_checks",
            "scaffold_started",
            "scaffold_complete",
        ),
    ),
    (
        "samvil-resume",
        "skills/samvil-resume/SKILL.md",
        (
            "resume_session",
            "save_event",
            "samvil-interview",
            "AskUserQuestion",
            "in_progress_leaf",
        ),
    ),
]


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}")


# Tools that are referenced in tests but not yet wired to any skill.
# These are intentional "pending wiring" items — tracked in ISS-TOOL-BLOAT.
# Adding a new tool here requires a comment explaining why it's deferred.
# Removing from this list requires either wiring it to a skill OR deleting the tool.
REVERSE_CHECK_ALLOWLIST: frozenset[str] = frozenset(
    [
        # Pipeline orchestration tools — replaced by HostCapability / aggregator pattern
        "advance_chain",
        "get_chain_continuation",
        "get_next_stage",
        "get_pipeline_status",
        "should_skip_stage",
        # Session/checkpoint tools — useful for debugging, no skill wiring yet
        "get_session",
        "list_sessions",
        "list_checkpoints",
        "load_checkpoint",
        "session_status",
        # Build recovery subsystem — Mountain M1-M4, not yet wired to samvil-build
        "aggregate_module_state",
        "aggregate_regression_state",
        "build_final_e2e_bundle",
        "build_post_rebuild_qa",
        "build_qa_recovery_routing",
        "build_rebuild_reentry",
        "clear_leaf_checkpoint",
        "evaluate_qa_convergence",
        "evaluate_stuck_recovery",
        "materialize_final_e2e_bundle",
        "materialize_post_rebuild_qa",
        "materialize_rebuild_reentry",
        "read_leaf_checkpoint",
        "render_progress_panel",
        # Research/format tools — PATH 4 not wired beyond SKILL.legacy.md
        "extract_query",
        "format_research",
        # AC analysis tools — planned for samvil-build but not wired
        "analyze_ac_dependencies",
        "compare_generations",
        "compute_parallel_safety",
        "load_external_satisfactions",
        "synthesize_qa_evidence",
        "update_progress",
        # Evolve tools — not yet wired in samvil-evolve thin skill
        "get_evolve_context",
        "get_tier_phases",
        # Council tools — consensus prompts not yet wired in ultra-thin council
        "consensus_judge_prompt",
        "consensus_reviewer_prompt",
        # QA/budget tools — referenced in legacy but not in ultra-thin SKILL.md
        "aggregate_run_feedback",
        "check_stall",
        "meta_probe_prompt",
        "rate_budget_acquire",
        "validate_profiles",
        "validate_state",
        # Adversarial testing — standalone diagnostic, not part of pipeline
        "adversarial_prompt",
        # Event/loop tools — utility helpers not yet wired to any skill body
        "get_events",
        "loop_should_stop",
    ]
)


def _collect_all_skill_text() -> str:
    """Concatenate all skill SKILL.md and codex-commands/*.md files."""
    parts: list[str] = []
    for skill_dir in (REPO / "skills").iterdir():
        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            parts.append(skill_md.read_text(errors="ignore"))
    codex_dir = REPO / "references" / "codex-commands"
    if codex_dir.exists():
        for f in codex_dir.glob("*.md"):
            parts.append(f.read_text(errors="ignore"))
    return "\n".join(parts)


def _collect_mcp_tools() -> list[str]:
    """Extract all @mcp.tool() function names from server.py."""
    import re
    server = REPO / "mcp" / "samvil_mcp" / "server.py"
    if not server.exists():
        return []
    text = server.read_text(errors="ignore")
    return re.findall(r"@mcp\.tool\(\)\s*\nasync def (\w+)", text)


def main() -> int:
    all_green = True
    for skill_name, rel_path, required in CHECKS:
        path = REPO / rel_path
        if not path.exists():
            _fail(f"{skill_name}: file missing ({rel_path})")
            all_green = False
            continue
        text = path.read_text()
        missing = [token for token in required if token not in text]
        if missing:
            _fail(f"{skill_name}: missing tokens {missing}")
            all_green = False
        else:
            _ok(f"{skill_name}: all {len(required)} tokens present")

    # Reverse check: every @mcp.tool() must be referenced in at least one skill/codex file
    print()
    print("Reverse check: all @mcp.tool() referenced in skills or codex-commands ...")
    skill_text = _collect_all_skill_text()
    mcp_tools = _collect_mcp_tools()
    unreferenced = [t for t in mcp_tools if t not in skill_text and t not in REVERSE_CHECK_ALLOWLIST]
    if unreferenced:
        _fail(f"{len(unreferenced)} @mcp.tool() functions not referenced in any skill (and not in allowlist): {sorted(unreferenced)}")
        all_green = False
    else:
        allowlisted = [t for t in mcp_tools if t not in skill_text and t in REVERSE_CHECK_ALLOWLIST]
        _ok(f"all non-allowlisted @mcp.tool() functions referenced ({len(allowlisted)} allowlisted pending-wiring tools skipped)")

    print()
    print("Summary:", "PASS" if all_green else "FAIL")
    return 0 if all_green else 1


if __name__ == "__main__":
    sys.exit(main())
