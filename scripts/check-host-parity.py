#!/usr/bin/env python3
"""SAMVIL structural host parity check (Phase A.2).

Verifies that every CC skill (`skills/<name>/SKILL.md`) has a matching
Codex command (`references/codex-commands/<name>.md`) and that the two
agree on the things a user would notice when switching hosts:

1. **Pair existence**  — every CC skill has a Codex twin and vice versa.
2. **Core MCP tools** — each skill has a curated set of "must-reference"
   MCP tools (the deterministic operations that define what the stage
   does). Both files must reference all of them.
3. **Chain target** — both files agree on the next stage in the pipeline.
4. **Auto-Proceed Policy** — Codex commands for mechanical-only stages
   (evolve, retro) must declare the auto-proceed policy explicitly. CC
   SKILL.md is implicit via the Skill tool.
5. **Gemini QA lifecycle** — the Gemini QA command must finalize and
   materialize synthesis, pass the route-specific gate, and preserve the
   dynamic next skill instead of defaulting every outcome to deploy.

Intentional divergences are listed in `references/host-parity-allowlist.yaml`.

This is a document/wiring check. It does not execute stages natively on Codex
or Gemini, and it reports those surfaces as UNTESTED instead of implying green
runtime parity.

Usage:
    python3 scripts/check-host-parity.py            # report mode
    python3 scripts/check-host-parity.py --strict   # exit 1 on any issue

Failures keep their textual reason so the developer can grep the message.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
CODEX_DIR = REPO_ROOT / "references" / "codex-commands"
GEMINI_DIR = REPO_ROOT / "references" / "gemini-commands"
SERVER_PY = REPO_ROOT / "mcp" / "samvil_mcp" / "server.py"
ALLOWLIST_FILE = REPO_ROOT / "references" / "host-parity-allowlist.yaml"
FORBIDDEN_SSOT_PATHS: dict[str, tuple[str, str]] = {
    ".samvil/project.seed.json": (
        "legacy .samvil/project.seed.json",
        "root project.seed.json",
    ),
    ".samvil/project.config.json": (
        "legacy .samvil/project.config.json",
        "root project.config.json",
    ),
    ".samvil/project.state.json": (
        "legacy .samvil/project.state.json",
        "root project.state.json",
    ),
    ".samvil/interview-summary.md": (
        "legacy .samvil/interview-summary.md",
        "root interview-summary.md",
    ),
}
GEMINI_QA_REQUIRED_MARKERS: tuple[str, ...] = (
    "finalize_qa_verdict",
    "materialize_qa_synthesis",
    "gate_check",
    'next_skill="<finalize.next_skill_decision.suggested>"',
    "do not write a marker",
)

# Host-specific core tools. CC uses aggregator-style helpers
# (e.g., aggregate_build_phase_a) while Codex uses lower-level
# primitives (next_buildable_leaves). Both routes accomplish the
# same job — drift = a stage's defining contract is missing in one host.
CORE_TOOLS_CC: dict[str, set[str]] = {
    "samvil": {"aggregate_orchestrator_state"},
    "samvil-interview": {"score_ambiguity"},
    "samvil-pm-interview": {"validate_pm_seed"},
    "samvil-seed": set(),  # CC delegates to legacy schema validator
    "samvil-council": set(),
    "samvil-design": set(),
    "samvil-scaffold": set(),
    "samvil-build": {"dispatch_build_batch"},  # aggregator
    "samvil-qa": set(),
    "samvil-deploy": {"evaluate_deploy_target"},
    "samvil-evolve": {"compare_seeds"},
    "samvil-retro": set(),  # CC routes through narrate + retro_save
    "samvil-analyze": set(),
    "samvil-doctor": {"get_health_tier_summary"},
    "samvil-update": set(),
}

CORE_TOOLS_CODEX: dict[str, set[str]] = {
    "samvil": {"health_check", "aggregate_orchestrator_state"},
    "samvil-interview": {"score_ambiguity"},
    "samvil-pm-interview": {"validate_pm_seed"},
    "samvil-seed": {"prepare_seed_verify_contracts", "validate_seed"},
    "samvil-council": set(),
    "samvil-design": set(),
    "samvil-scaffold": set(),
    "samvil-build": {
        "collect_stage_evidence",
        "gate_check",
        "next_buildable_leaves",
        "update_leaf_status",
    },
    "samvil-qa": set(),  # validation tools vary by track
    "samvil-deploy": {"evaluate_deploy_target"},
    "samvil-evolve": {"compare_seeds"},
    "samvil-retro": {"aggregate_retro_metrics"},
    "samvil-analyze": set(),
    "samvil-doctor": set(),
    "samvil-update": set(),
}

# Stages where Codex needs an explicit Auto-Proceed Policy because they
# are mechanical (no user-decision pause expected). CC is implicit
# (Skill tool invocation = auto-proceed by definition).
CODEX_AUTO_PROCEED_REQUIRED: set[str] = {"samvil-evolve", "samvil-retro"}

# Stage route contracts that must be visible in both host instruction files.
# Dynamic stages list every allowed explicit target so a wrong hard-coded
# replacement (for example samvil-seed -> samvil-retro) cannot hide behind a
# generic "chain" or "next" section.
CHAIN_TARGETS_REQUIRED: dict[str, set[str]] = {
    "samvil": {"samvil-interview", "samvil-pm-interview", "samvil-analyze"},
    "samvil-interview": {"samvil-seed", "samvil-build"},
    "samvil-pm-interview": {"samvil-design", "samvil-council"},
    "samvil-seed": {"samvil-design", "samvil-council"},
    "samvil-council": {"samvil-design"},
    "samvil-design": {"samvil-scaffold"},
    "samvil-scaffold": {"samvil-build"},
    "samvil-build": {"samvil-qa"},
    "samvil-qa": {"samvil-deploy", "samvil-evolve", "samvil-retro"},
    "samvil-deploy": {"samvil-retro"},
    "samvil-evolve": {"samvil-retro"},
    "samvil-analyze": {"samvil-interview", "samvil-qa", "samvil-design"},
}


def load_server_tools() -> set[str]:
    """All MCP tool names registered in server.py via @mcp.tool()."""
    text = SERVER_PY.read_text(encoding="utf-8")
    # Tolerate both `@mcp.tool()\nasync def` and `@mcp.tool()\ndef` forms.
    return set(re.findall(r"@mcp\.tool\(\)\s*(?:async\s+)?def\s+(\w+)", text))


def load_allowlist() -> dict[str, dict[str, list[str]]]:
    """Parse a tiny YAML-ish allowlist (key: list pairs).

    Avoids a YAML dependency by parsing only the subset we actually use.
    Format:
        samvil-foo:
          missing_in_cc: [tool_a, tool_b]
          missing_in_codex: [tool_c]
    """
    if not ALLOWLIST_FILE.exists():
        return {}
    out: dict[str, dict[str, list[str]]] = {}
    current_key: str | None = None
    current_section: str | None = None
    for raw in ALLOWLIST_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            current_key = line.rstrip(":").strip()
            out.setdefault(current_key, {})
            current_section = None
            continue
        stripped = line.strip()
        if stripped.endswith(":") and current_key is not None:
            current_section = stripped.rstrip(":")
            out[current_key].setdefault(current_section, [])
            continue
        if (
            current_key is not None
            and current_section is not None
            and stripped.startswith("-")
        ):
            value = stripped[1:].strip()
            # Strip inline `# comment` (e.g. `# why: ...`) from list items
            if "#" in value:
                value = value.split("#", 1)[0].rstrip()
            value = value.strip("'\"")
            out[current_key][current_section].append(value)
    return out


def referenced_tools(text: str, all_tools: Iterable[str]) -> set[str]:
    """Tool names from `all_tools` that appear as identifiers in `text`.

    Matches both the standalone form (`<tool>(...)`) and the CC prefixed
    form (`mcp__samvil_mcp__<tool>`). The trailing negative lookahead
    `(?!\\w)` rules out substring hits like `health_check_v2`.
    Note: \\b can't be used at the start because `_` counts as a word
    char, so `mcp__samvil_mcp__<tool>` has no word boundary before <tool>.
    """
    found: set[str] = set()
    for tool in all_tools:
        if re.search(rf"{re.escape(tool)}(?!\w)", text):
            found.add(tool)
    return found


def check_pair(
    name: str,
    cc_text: str,
    codex_text: str,
    all_tools: set[str],
    allowed: dict[str, list[str]],
) -> list[str]:
    """Return human-readable issue strings (empty list = parity)."""
    issues: list[str] = []

    cc_refs = referenced_tools(cc_text, all_tools)
    codex_refs = referenced_tools(codex_text, all_tools)

    # 1a. Each side must reference its host-specific core tool set.
    cc_core = CORE_TOOLS_CC.get(name, set())
    codex_core = CORE_TOOLS_CODEX.get(name, set())
    allow_missing_in_cc = set(allowed.get("missing_in_cc", []))
    allow_missing_in_codex = set(allowed.get("missing_in_codex", []))
    cc_missing_core = (cc_core - cc_refs) - allow_missing_in_cc
    codex_missing_core = (codex_core - codex_refs) - allow_missing_in_codex
    if cc_missing_core:
        issues.append(
            f"{name}: CC SKILL.md missing core tool(s): "
            f"{sorted(cc_missing_core)}"
        )
    if codex_missing_core:
        issues.append(
            f"{name}: Codex command missing core tool(s): "
            f"{sorted(codex_missing_core)}"
        )

    # 1b. Each side must reference SOME MCP tool, otherwise the file is
    # likely a stub that won't drive the stage at all.
    if not cc_refs and cc_core:
        issues.append(f"{name}: CC SKILL.md references no MCP tools at all")
    if not codex_refs and codex_core:
        issues.append(f"{name}: Codex command references no MCP tools at all")

    # 2. Auto-Proceed Policy enforced on Codex side for mechanical stages.
    # Match the section heading specifically (## Auto-Proceed Policy), not
    # any substring — otherwise a stray cross-reference in another section
    # would mask the real deletion of the heading.
    if name in CODEX_AUTO_PROCEED_REQUIRED:
        if not re.search(r"^##\s+Auto-Proceed Policy\s*$", codex_text, re.MULTILINE):
            issues.append(
                f"{name}: Codex command missing '## Auto-Proceed Policy' "
                f"heading (required for mechanical stages — see v4.11.0 retro)"
            )

    # 3. Each non-terminal pair should hint at chain continuation.
    # (Looser check — just verify both files mention `chain` or `next` at all
    #  to catch a totally absent section.)
    if name not in {"samvil-retro", "samvil-doctor", "samvil-update"}:
        if (
            "chain" not in cc_text.lower()
            and "next_skill" not in cc_text
        ):
            issues.append(f"{name}: CC SKILL.md has no chain/next_skill mention")
        if (
            "chain" not in codex_text.lower()
            and "next-skill" not in codex_text.lower()
            and "next_skill" not in codex_text
        ):
            issues.append(
                f"{name}: Codex command has no chain/next-skill mention"
            )
    required_targets = CHAIN_TARGETS_REQUIRED.get(name, set())
    missing_cc_targets = sorted(
        target for target in required_targets if target not in cc_text
    )
    missing_codex_targets = sorted(
        target for target in required_targets if target not in codex_text
    )
    if missing_cc_targets:
        issues.append(
            f"{name}: CC SKILL.md missing chain target(s): {missing_cc_targets}"
        )
    if missing_codex_targets:
        issues.append(
            f"{name}: Codex command missing chain target(s): {missing_codex_targets}"
        )

    return issues


def discover_pairs() -> tuple[list[str], list[str], list[str]]:
    """Return (matched, cc_only, codex_only) skill name lists."""
    cc_names: set[str] = set()
    for d in SKILLS_DIR.iterdir():
        if d.is_dir() and (d / "SKILL.md").exists():
            cc_names.add(d.name)
    codex_names: set[str] = set()
    for f in CODEX_DIR.glob("*.md"):
        codex_names.add(f.stem)
    matched = sorted(cc_names & codex_names)
    cc_only = sorted(cc_names - codex_names)
    codex_only = sorted(codex_names - cc_names)
    return matched, cc_only, codex_only


def untested_core_contracts(matched: Iterable[str]) -> list[str]:
    """Pairs with no curated MCP core-tool assertion on either host."""
    return sorted(
        name
        for name in matched
        if not CORE_TOOLS_CC.get(name, set())
        and not CORE_TOOLS_CODEX.get(name, set())
    )


def ssot_path_contract_issues() -> list[str]:
    """All host-facing command docs must point at canonical root SSOT files."""
    paths = [
        REPO_ROOT / "AGENTS.md",
        *sorted(CODEX_DIR.glob("*.md")),
        *sorted(GEMINI_DIR.glob("*.toml")),
    ]
    issues: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for forbidden, (legacy_label, canonical_label) in FORBIDDEN_SSOT_PATHS.items():
                if forbidden in line:
                    issues.append(
                        f"{path.relative_to(REPO_ROOT)}:{lineno}: "
                        f"uses {legacy_label}; use {canonical_label}"
                    )
    return issues


def gemini_qa_lifecycle_contract_issues() -> list[str]:
    """Gemini QA must preserve the same finalized dynamic route as other hosts."""
    path = GEMINI_DIR / "samvil-qa.toml"
    if not path.exists():
        return ["Gemini QA lifecycle contract: missing samvil-qa.toml"]
    text = path.read_text(encoding="utf-8")
    return [
        "Gemini QA lifecycle contract: "
        f"references/gemini-commands/samvil-qa.toml missing {marker}"
        for marker in GEMINI_QA_REQUIRED_MARKERS
        if marker not in text
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", maxsplit=1)[0])
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 on any reported issue (use in CI)",
    )
    args = parser.parse_args(argv)

    matched, cc_only, codex_only = discover_pairs()
    all_tools = load_server_tools()
    allowlist = load_allowlist()

    issues: list[str] = []
    for name in cc_only:
        issues.append(f"{name}: CC SKILL.md exists but no Codex command")
    for name in codex_only:
        issues.append(f"{name}: Codex command exists but no CC SKILL.md")

    for name in matched:
        cc_text = (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
        codex_text = (CODEX_DIR / f"{name}.md").read_text(encoding="utf-8")
        allowed = allowlist.get(name, {})
        issues.extend(check_pair(name, cc_text, codex_text, all_tools, allowed))
    issues.extend(ssot_path_contract_issues())
    issues.extend(gemini_qa_lifecycle_contract_issues())

    if issues:
        print("✗ host parity check found issues:")
        for issue in issues:
            print(f"  • {issue}")
        print(f"\n  Total: {len(issues)} issue(s) across {len(matched)} skill pair(s)")
        print(
            "  Fix the file or add an entry to "
            f"{ALLOWLIST_FILE.relative_to(REPO_ROOT)} for an intentional gap."
        )
        return 1 if args.strict else 0
    print(
        f"✓ structural host parity: {len(matched)} paired command documents "
        "passed existence/core/chain checks"
    )
    untested = untested_core_contracts(matched)
    print(
        f"UNTESTED: {len(untested)} pair(s) have no curated MCP core-tool "
        f"contract: {', '.join(untested)}"
    )
    print(
        "UNTESTED: Codex native stage execution; this check covers command "
        "documents and model-routing wiring only"
    )
    print(
        "UNTESTED: Gemini native stage execution; SSOT command corpus "
        "contract is checked, but runtime parity is not"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
