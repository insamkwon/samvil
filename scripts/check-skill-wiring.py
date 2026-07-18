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

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

REFERENCE_TOOL_CALL_RE = re.compile(
    r"`((?:claim|gate|route|rate_budget|budget)_[a-z0-9_]+)\([^`]*\)`"
)
REFERENCE_TOOL_LABEL_RE = re.compile(
    r"`((?:claim|gate|route|rate_budget|budget)_[a-z0-9_]+)`\s+tool\b"
)

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
            "classify_build_failure",
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
            ".samvil/claims.jsonl",
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


# Boot contract (W3.1): every stage skill must emit a stage-entry event and
# declare a P8 fallback path. Normative doc: references/skill-boot-template.md
BOOT_CONTRACT_SKILLS: tuple[str, ...] = (
    "samvil",
    "samvil-interview",
    "samvil-pm-interview",
    "samvil-seed",
    "samvil-council",
    "samvil-design",
    "samvil-scaffold",
    "samvil-build",
    "samvil-qa",
    "samvil-deploy",
    "samvil-retro",
    "samvil-evolve",
    "samvil-analyze",
    "samvil-resume",
)


def check_boot_contract() -> bool:
    """Each stage skill: save_event present + legacy/P8 fallback present."""
    all_green = True
    for skill in BOOT_CONTRACT_SKILLS:
        path = REPO / "skills" / skill / "SKILL.md"
        if not path.exists():
            _fail(f"boot-contract {skill}: SKILL.md missing")
            all_green = False
            continue
        text = path.read_text(errors="ignore")
        missing = []
        if "save_event" not in text:
            missing.append("save_event (stage entry)")
        if "SKILL.legacy.md" not in text and "P8" not in text:
            missing.append("P8/legacy fallback")
        if "gate_override" not in text or "force_proceed" not in text:
            missing.append("explicit gate override policy")
        if missing:
            _fail(f"boot-contract {skill}: missing {missing}")
            all_green = False
    if all_green:
        _ok(f"boot contract: {len(BOOT_CONTRACT_SKILLS)} stage skills conform")
    return all_green


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
        # v4.26.0 G4.2 — mechanical.toml contract: shipped as opt-in.
        # Full SKILL wiring (samvil-scaffold writes, samvil-build/qa read)
        # is deferred to v4.27+ because each SKILL.md is at 120/120 thinness
        # and absorbing the integration requires compression elsewhere.
        # Tools are callable now via direct MCP; covered by pytest +
        # stdio roundtrip.
        "read_mechanical_toml",
        "write_default_mechanical_toml",
        "resolve_mechanical_command",
        # Chain marker tools — W2.2 made the marker subsystem load-bearing
        # (stage hooks write/clear .samvil/next-skill.json; resume reads it).
        # These wrappers are the direct-MCP interface for non-Skill hosts.
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
        "evaluate_stuck_recovery",
        "materialize_final_e2e_bundle",
        "materialize_post_rebuild_qa",
        "materialize_rebuild_reentry",
        "read_leaf_checkpoint",
        "render_progress_panel",
        # AC analysis tools — planned for samvil-build but not wired
        "analyze_ac_dependencies",
        "compare_generations",
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
        # Event/loop tools — utility helpers not yet wired to any skill body
        "get_events",
        # Background jobs (W4.1) — start/status/result wired in samvil-build;
        # cancel is a user-initiated escape hatch, no scripted call site.
        "job_cancel",
        # ── Sync tools below were invisible until the W1.4 regex fix
        # (async-only pattern missed plain `def` tools). Categorized here;
        # keep-or-delete is decided in W2.1 via docs/unused-tools-report.md.
        # Release/publish subsystem — driven by scripts/publish-verified-release.py
        # and samvil-publish flows, not skill bodies.
        "build_release_evidence_bundle",
        "build_release_report",
        "evaluate_release_gate",
        "read_release_report",
        "render_release_evidence_bundle",
        "render_release_report",
        "run_release_checks",
        # Run/repair report tools — benchmark + standalone QA reporting
        "build_run_report",
        "read_run_report",
        "render_run_report",
        # Retro observation pipeline — derive/append pair not yet in thin retro skill
        "append_retro_observations",
        "derive_retro_observations",
        # Decision Log ADR tools (v3.3 4-layer) — SSOT writers, no skill wiring yet
        "find_decision_adrs_referencing",
        "read_decision_adr",
        "supersede_decision_adr",
        "write_decision_adr",
        # Domain pack / pattern registry readers — render_* variants are wired,
        # raw read/list/match variants are not
        "list_domain_packs",
        "match_domain_packs",
        "read_domain_pack",
        "list_patterns",
        "read_pattern",
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
    # W5.3: tools live in server.py plus extracted tools_*.py modules.
    sources = [server] + sorted(server.parent.glob("tools_*.py"))
    names: list[str] = []
    for src in sources:
        text = src.read_text(errors="ignore")
        # Both `async def` and plain `def` tools — 31 tools are sync and
        # were invisible to the async-only pattern (W1.4 fix). Indented
        # defs (register-pattern modules) are matched too.
        names.extend(
            re.findall(r"@mcp\.tool\(\)\s*\n\s*(?:async )?def (\w+)", text)
        )
    return names


def find_unresolved_reference_tools(repo: Path = REPO) -> dict[str, list[str]]:
    """Find MCP-like tool references in ``references/`` with no registration."""
    server = repo / "mcp" / "samvil_mcp" / "server.py"
    sources = [server] + sorted(server.parent.glob("tools_*.py"))
    registered: set[str] = set()
    for source in sources:
        if not source.exists():
            continue
        registered.update(
            re.findall(
                r"@mcp\.tool\(\)\s*\n\s*(?:async )?def (\w+)",
                source.read_text(errors="ignore"),
            )
        )

    unresolved: dict[str, list[str]] = {}
    references = repo / "references"
    if not references.exists():
        return unresolved
    for path in sorted(references.rglob("*.md")):
        for lineno, line in enumerate(path.read_text(errors="ignore").splitlines(), start=1):
            candidates = set(REFERENCE_TOOL_CALL_RE.findall(line))
            candidates.update(REFERENCE_TOOL_LABEL_RE.findall(line))
            for name in sorted(candidates - registered):
                unresolved.setdefault(name, []).append(
                    f"{path.relative_to(repo)}:{lineno}"
                )
    return unresolved


def _collect_legacy_text() -> str:
    """Concatenate all SKILL.legacy.md files (P8 fallback bodies)."""
    parts: list[str] = []
    for skill_dir in (REPO / "skills").iterdir():
        legacy = skill_dir / "SKILL.legacy.md"
        if legacy.exists():
            parts.append(legacy.read_text(errors="ignore"))
    return "\n".join(parts)


def _collect_aux_text(subdir: str, patterns: tuple[str, ...]) -> str:
    base = REPO / subdir
    parts: list[str] = []
    self_path = Path(__file__).resolve()
    if base.exists():
        for pattern in patterns:
            for f in base.rglob(pattern):
                if "__pycache__" in f.parts or ".venv" in f.parts:
                    continue
                if f.resolve() == self_path:
                    # This script's own allowlist would mark every tool as
                    # "used by scripts" — exclude self.
                    continue
                parts.append(f.read_text(errors="ignore"))
    return "\n".join(parts)


def write_report(out_path: Path) -> None:
    """Write the unused-tool audit (W1.4) used to drive W2.1 deletion.

    For every @mcp.tool() not cited by an active SKILL.md / codex command,
    record where else it IS cited (legacy fallback, hooks, scripts, tests)
    so the deletion pass can separate dead tools from fallback-only tools.
    """
    mcp_tools = _collect_mcp_tools()
    skill_text = _collect_all_skill_text()
    legacy_text = _collect_legacy_text()
    hooks_text = _collect_aux_text("hooks", ("*.sh",))
    scripts_text = _collect_aux_text("scripts", ("*.py", "*.sh"))
    refs_text = _collect_aux_text("references", ("*.md", "*.yaml", "*.toml"))
    tests_text = _collect_aux_text("mcp/tests", ("*.py",))

    unused: list[dict] = []
    for tool in sorted(mcp_tools):
        if tool in skill_text:
            continue
        unused.append(
            {
                "tool": tool,
                "allowlisted": tool in REVERSE_CHECK_ALLOWLIST,
                "legacy": tool in legacy_text,
                "hooks": tool in hooks_text,
                "scripts": tool in scripts_text,
                "references": tool in refs_text,
                "tests": tool in tests_text,
            }
        )

    def _mark(flag: bool) -> str:
        return "✓" if flag else "—"

    lines: list[str] = []
    lines.append("# Unused MCP Tool Audit (W1.4)")
    lines.append("")
    lines.append(
        "> Generated by `python3 scripts/check-skill-wiring.py --report`. "
        "Do not edit by hand — regenerate instead."
    )
    lines.append("")
    lines.append(
        f"Total `@mcp.tool()`: **{len(mcp_tools)}** · cited by active "
        f"SKILL.md/codex: **{len(mcp_tools) - len(unused)}** · uncited: "
        f"**{len(unused)}**"
    )
    lines.append("")
    lines.append(
        "Deletion guidance (W2.1): a tool is *deletable* when every column "
        "except `tests` is `—`. `legacy ✓` = used by the P8 fallback path — "
        "keep or migrate the legacy body first. `hooks/scripts/references ✓` "
        "= infrastructure usage — keep."
    )
    lines.append("")
    lines.append("| tool | allowlisted | legacy | hooks | scripts | references | tests |")
    lines.append("|---|---|---|---|---|---|---|")
    for row in unused:
        lines.append(
            f"| `{row['tool']}` | {_mark(row['allowlisted'])} "
            f"| {_mark(row['legacy'])} | {_mark(row['hooks'])} "
            f"| {_mark(row['scripts'])} | {_mark(row['references'])} "
            f"| {_mark(row['tests'])} |"
        )
    lines.append("")
    deletable = [
        r["tool"]
        for r in unused
        if not (r["legacy"] or r["hooks"] or r["scripts"] or r["references"])
    ]
    lines.append(f"## Deletable candidates ({len(deletable)})")
    lines.append("")
    lines.append(
        "Uncited anywhere except (possibly) tests — safe to delete tool "
        "wrapper + dedicated tests together:"
    )
    lines.append("")
    for t in deletable:
        lines.append(f"- `{t}`")
    lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"report written: {out_path} ({len(unused)} uncited, {len(deletable)} deletable)")


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

    # Boot contract check (W3.1)
    print()
    print("Boot contract: stage skills follow references/skill-boot-template.md ...")
    if not check_boot_contract():
        all_green = False

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
    print("Reference check: MCP-like tool names in references/ resolve ...")
    unresolved_references = find_unresolved_reference_tools()
    if unresolved_references:
        _fail(f"unregistered reference tool(s): {unresolved_references}")
        all_green = False
    else:
        _ok("all MCP-like references resolve to registered tools")

    print()
    print("Summary:", "PASS" if all_green else "FAIL")
    return 0 if all_green else 1


if __name__ == "__main__":
    if "--report" in sys.argv:
        write_report(REPO / "docs" / "unused-tools-report.md")
        sys.exit(0)
    sys.exit(main())
