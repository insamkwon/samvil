"""Boot-time aggregator for samvil-qa Phase Boot (T4.9 ultra-thin migration).

Single best-effort call that collects everything the now-thin
`samvil-qa` SKILL needs at the **start** of the QA stage:

  1. **stack** — resolves `solution_type` + `framework` from the seed,
     and the per-stack Pass 1 mechanical command (build/typecheck/
     py_compile + dep check) plus Pass 1b smoke recipe pointer.
  2. **paths** — `project_root` + every artifact path the skill body
     reads or writes during QA (seed/state/config/build log/qa results/
     qa evidence dir/qa report/handoff/events/qa-results cache).
  3. **routing** — task routing for `qa-functional` (Judge role) so the
     spawned independent agent picks the right model on entry.
  4. **role separation pre-check** — generator/judge identity check
     payload ready to call `validate_role_separation` (skill body still
     issues the call so the failure halt remains explicit).
  5. **incremental QA hint** — prior `qa-results.json` summary so the
     skill body decides re-verify vs reuse without a separate read.
  6. **resume hint** — `selected_tier`, `qa_max_iterations`,
     `session_id`, `current_model_qa`, `qa_history.length` for Ralph
     loop start state.
  7. **brownfield flag** — whether `project.seed.json` is missing
     (skill body should AskUserQuestion).

What stays in the skill body (CC-bound, P8):
  - Actual Playwright MCP calls (browser_navigate, browser_snapshot,
    browser_click, browser_take_screenshot, etc.).
  - Spawning independent `Agent()` calls for Pass 2/3 in
    standard/thorough/full tiers.
  - Per-leaf semantic_check + validate_evidence calls during Pass 2.5
    (already first-class MCP tools — adapter would be redundant).
  - Ralph Loop iteration counter + BLOCKED detection (control flow).
  - Writing `.samvil/handoff.md`, `.samvil/qa-evidence/*.png`.
  - Chain into `samvil-deploy` / `samvil-evolve` / `samvil-retro`.

All reads are best-effort. Missing files yield empty defaults and a
non-fatal entry in `errors[]`. Never raises. Honors INV-1 (file is
SSOT) and INV-5 (graceful degradation).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

QA_BOOT_SCHEMA_VERSION = "1.0"


# ── Stack catalog: per-solution_type Pass 1 mechanical command ─────────


# Per-`solution_type` Pass 1 (mechanical) verification command. Mirrors
# the legacy SKILL.md "Pass 1: Mechanical Verification" snippets. Skill
# body shells these out; we just hand them over so the per-solution-type
# prose stays in SKILL.legacy.md.
_PASS1_COMMANDS: dict[str, dict[str, str]] = {
    "web-app": {
        "command": "npm run build > .samvil/build.log 2>&1",
        "log_path": ".samvil/build.log",
        "language": "typescript",
        "smoke": "playwright",
    },
    "dashboard": {
        "command": "npm run build > .samvil/build.log 2>&1",
        "log_path": ".samvil/build.log",
        "language": "typescript",
        "smoke": "playwright",
    },
    "game": {
        "command": (
            "npx tsc --noEmit > .samvil/build.log 2>&1 "
            "&& npm run build >> .samvil/build.log 2>&1"
        ),
        "log_path": ".samvil/build.log",
        "language": "typescript",
        "smoke": "playwright-canvas",
    },
    "mobile-app": {
        "command": "npx expo export --platform web > .samvil/build.log 2>&1",
        "log_path": ".samvil/build.log",
        "language": "typescript",
        "smoke": "playwright-mobile",
    },
    "automation-python": {
        "command": (
            "python -m py_compile src/main.py > .samvil/build.log 2>&1 "
            "&& pip check >> .samvil/build.log 2>&1"
        ),
        "log_path": ".samvil/build.log",
        "language": "python",
        "smoke": "dry-run",
    },
    "automation-node": {
        "command": (
            "npx tsc --noEmit > .samvil/build.log 2>&1 "
            "&& npm ls >> .samvil/build.log 2>&1"
        ),
        "log_path": ".samvil/build.log",
        "language": "typescript",
        "smoke": "dry-run",
    },
    "automation-cc-skill": {
        "command": "",  # No compilation step
        "log_path": "",
        "language": "markdown",
        "smoke": "skip",
    },
}


# Per-`solution_type` checklist reference (relative to plugin root).
_QA_CHECKLIST_PATHS: dict[str, str] = {
    "web-app": "references/qa-checklist.md",
    "automation": "references/qa-checklist.md",
    "game": "references/qa-checklist.md",
    "mobile-app": "references/qa-checklist.md",
    "dashboard": "references/qa-checklist.md",
}


# ── Helpers ────────────────────────────────────────────────────────────


def _read_json_safe(path: Path) -> dict[str, Any] | None:
    """Best-effort JSON read. Returns None on missing/invalid file."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _resolve_pass1(
    solution_type: str,
    seed: dict[str, Any],
) -> dict[str, str]:
    """Pick Pass 1 command based on solution_type + (for automation) language."""
    if solution_type == "automation":
        impl = seed.get("implementation") or {}
        runtime = str(impl.get("runtime") or "").lower()
        if runtime in ("python", "py"):
            key = "automation-python"
        elif runtime in ("node", "nodejs", "javascript", "typescript", "ts"):
            key = "automation-node"
        elif runtime in ("cc-skill", "skill"):
            key = "automation-cc-skill"
        else:
            key = "automation-python"
        return dict(_PASS1_COMMANDS[key])

    return dict(_PASS1_COMMANDS.get(solution_type, _PASS1_COMMANDS["web-app"]))


def _incremental_hint(qa_results_path: Path, seed: dict[str, Any]) -> dict[str, Any]:
    """Read prior qa-results.json (if any) for incremental-QA decisions.

    Returns a dict with `present`, `prior_features` (count), `prior_pass`
    (count), `prior_fail` (count), `prior_iterations`. Skill body decides
    whether to re-verify all features or just changed ones.
    """
    data = _read_json_safe(qa_results_path)
    if not data:
        return {
            "present": False,
            "prior_features": 0,
            "prior_pass": 0,
            "prior_fail": 0,
            "prior_iterations": 0,
        }

    meta = data.get("_meta") or {}
    features = data.get("features") or {}
    if isinstance(features, dict):
        feat_iter = features.values()
    elif isinstance(features, list):
        feat_iter = features
    else:
        feat_iter = []

    prior_pass = 0
    prior_fail = 0
    for f in feat_iter:
        if not isinstance(f, dict):
            continue
        status = str(f.get("status", "")).upper()
        if status == "PASS":
            prior_pass += 1
        elif status in ("FAIL", "REVISE"):
            prior_fail += 1

    return {
        "present": True,
        "prior_features": len(list(features) if isinstance(features, list) else features),
        "prior_pass": prior_pass,
        "prior_fail": prior_fail,
        "prior_iterations": int(meta.get("total_iterations") or 0),
    }


def _resume_hint(state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Build resume hint for Ralph loop start state."""
    qa_history = state.get("qa_history") or []
    return {
        "session_id": str(state.get("session_id") or ""),
        "selected_tier": str(
            state.get("selected_tier")
            or state.get("samvil_tier")
            or config.get("selected_tier")
            or config.get("samvil_tier")
            or "standard"
        ),
        "qa_max_iterations": int(config.get("qa_max_iterations") or 3),
        "current_model_qa": state.get("current_model_qa") or {},
        "qa_history_length": len(qa_history),
        "stage_claims": state.get("stage_claims") or {},
    }


# ── Aggregator ─────────────────────────────────────────────────────────


@dataclass
class QABootReport:
    schema_version: str = QA_BOOT_SCHEMA_VERSION
    project_path: str = ""
    solution_type: str = ""
    framework: str = ""
    seed_loaded: bool = False
    state_loaded: bool = False
    config_loaded: bool = False
    blueprint_loaded: bool = False
    brownfield: bool = False
    pass1: dict[str, str] = field(default_factory=dict)
    qa_checklist_path: str = ""
    paths: dict[str, str] = field(default_factory=dict)
    role_separation_check: dict[str, str] = field(default_factory=dict)
    incremental_hint: dict[str, Any] = field(default_factory=dict)
    resume_hint: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_path": self.project_path,
            "solution_type": self.solution_type,
            "framework": self.framework,
            "seed_loaded": self.seed_loaded,
            "state_loaded": self.state_loaded,
            "config_loaded": self.config_loaded,
            "blueprint_loaded": self.blueprint_loaded,
            "brownfield": self.brownfield,
            "pass1": self.pass1,
            "qa_checklist_path": self.qa_checklist_path,
            "paths": self.paths,
            "role_separation_check": self.role_separation_check,
            "incremental_hint": self.incremental_hint,
            "resume_hint": self.resume_hint,
            "notes": self.notes,
            "errors": self.errors,
        }


def aggregate_qa_boot_context(
    project_path: str | Path,
) -> dict[str, Any]:
    """Aggregate every fact the samvil-qa skill needs at boot.

    Args:
        project_path: Project root containing `project.seed.json`,
            `project.state.json`, optional `project.config.json`,
            optional `project.blueprint.json`, optional
            `.samvil/qa-results.json`.

    Returns:
        JSON-serializable dict — see QABootReport fields. Keys always
        present; missing files set the corresponding `_loaded` flag to
        False and (where critical) append an entry to `errors`.
    """
    report = QABootReport()
    root = Path(str(project_path)).expanduser()
    report.project_path = str(root)

    # Seed.
    seed = _read_json_safe(root / "project.seed.json")
    if seed is None:
        report.errors.append("project.seed.json not found or invalid")
        report.brownfield = True
        seed = {}
    else:
        report.seed_loaded = True

    # State.
    state = _read_json_safe(root / "project.state.json")
    if state is None:
        state = {}
    else:
        report.state_loaded = True

    # Config.
    config = _read_json_safe(root / "project.config.json")
    if config is None:
        config = {}
    else:
        report.config_loaded = True

    # Blueprint (optional).
    blueprint = _read_json_safe(root / "project.blueprint.json")
    if blueprint is not None:
        report.blueprint_loaded = True

    # Resolve solution_type + framework.
    solution_type = str(seed.get("solution_type") or "web-app")
    tech_stack = seed.get("tech_stack") or {}
    framework = str(tech_stack.get("framework") or "")
    report.solution_type = solution_type
    report.framework = framework

    # Pass 1 command.
    report.pass1 = _resolve_pass1(solution_type, seed)

    # QA checklist path.
    report.qa_checklist_path = _QA_CHECKLIST_PATHS.get(solution_type, "references/qa-checklist.md")

    # Paths.
    samvil_dir = root / ".samvil"
    report.paths = {
        "seed": str(root / "project.seed.json"),
        "state": str(root / "project.state.json"),
        "config": str(root / "project.config.json"),
        "blueprint": str(root / "project.blueprint.json"),
        "build_log": str(samvil_dir / "build.log"),
        "qa_results": str(samvil_dir / "qa-results.json"),
        "qa_report": str(samvil_dir / "qa-report.md"),
        "qa_evidence_dir": str(samvil_dir / "qa-evidence"),
        "handoff": str(samvil_dir / "handoff.md"),
        "events": str(samvil_dir / "events.jsonl"),
        "fix_log": str(samvil_dir / "fix-log.md"),
        "next_skill_marker": str(samvil_dir / "next-skill.json"),
        "qa_routing": str(samvil_dir / "qa-routing.json"),
        "launch_checklist": str(samvil_dir / "launch-checklist.md"),
        "mcp_health": str(samvil_dir / "mcp-health.jsonl"),
    }

    # Role separation pre-check payload (skill body issues the call).
    # Generator: build-worker. Judge: qa-functional. They MUST differ.
    report.role_separation_check = {
        "claimed_by": "agent:build-worker",
        "verified_by": "agent:qa-functional",
    }

    # Incremental QA hint.
    report.incremental_hint = _incremental_hint(samvil_dir / "qa-results.json", seed)

    # Resume hint.
    report.resume_hint = _resume_hint(state, config)

    # Notes.
    if report.brownfield:
        report.notes.append(
            "brownfield mode — skill should AskUserQuestion (samvil-analyze first vs general QA only)"
        )
    if solution_type not in _PASS1_COMMANDS and solution_type != "automation":
        report.notes.append(
            f"unknown solution_type '{solution_type}' — defaulting to web-app pass1"
        )
    if not framework and not report.brownfield:
        report.notes.append("framework missing in seed.tech_stack — skill should default by solution_type")
    qa_history_len = report.resume_hint["qa_history_length"]
    max_iter = report.resume_hint["qa_max_iterations"]
    if qa_history_len >= max_iter:
        report.notes.append(
            f"qa_history.length={qa_history_len} ≥ qa_max_iterations={max_iter} — Ralph loop exhausted on prior run"
        )

    return report.to_dict()
