"""Boot-time aggregator for samvil-build Phase A (T4.8 ultra-thin migration).

Single best-effort call that collects everything the now-thin
`samvil-build` SKILL needs at the **start** of the build stage:

  1. **stack** — resolves `solution_type` + `framework` from the seed,
     plus the per-stack build-verify command and log path (mirrors
     `scaffold_targets` but for the build stage).
  2. **paths** — `project_root` (cwd of this skill invocation) +
     `seed_path` + `state_path` + `config_path` + `blueprint_path` +
     `recipe_path` (the per-`solution_type` recipe markdown).
  3. **routing** — task routing for `build-worker` so the spawned
     agents pick the right model (delegates to existing
     `routing.route_task` via shared core helper).
  4. **patterns** + **domain** — best-effort Pattern Registry +
     Domain Pack context (rendered markdown chunks) so the skill
     never needs to make four separate calls.
  5. **scaffold sanity (Phase A.6)** — file-emptiness scan,
     unsubstituted-template-variable scan, broken-import scan. The
     skill body only needs to *report*; the actual checks live here.
  6. **resume hint** — checkpoint state preview (which features are
     done, which `tree_json` to resume from, last
     `consecutive_fail_batches`) so the skill body decides whether
     to skip-vs-rebuild without a separate `load_checkpoint` call.

What stays in the skill body (CC-bound, P8):
  - Actually running `npm run build`, `tsc --noEmit`, `python -m
    py_compile`, `npx expo export`.
  - Spawning Agent workers (the parallel chunk dispatch lives in CC).
  - Per-feature `Agent()` calls with the worker contract block.
  - Writing `.samvil/build.log`, `.samvil/handoff.md`,
    `.samvil/fix-log.md`, updating `project.state.json`.
  - Chain into `samvil-qa`.
  - The Circuit Breaker counter (`consecutive_fail_batches`) — easier
    to reason about per-iteration in the skill body.

All reads are best-effort. Missing files yield empty defaults and a
non-fatal entry in `errors[]`. Never raises. Honors INV-1 (file is
SSOT) and INV-5 (graceful degradation).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BUILD_PHASE_A_SCHEMA_VERSION = "1.0"


# ── Stack catalog: per-solution_type build-verify line ────────────────


# Per-`solution_type` build verification command. Mirrors the legacy
# SKILL.md "Build verify (INV-2)" snippets. Skill body shells these out;
# we just hand them over so the per-solution-type prose stays in
# SKILL.legacy.md.
_BUILD_VERIFY_COMMANDS: dict[str, dict[str, str]] = {
    "web-app": {
        "command": "npm run build > .samvil/build.log 2>&1",
        "log_path": ".samvil/build.log",
        "language": "typescript",
    },
    "dashboard": {
        "command": "npm run build > .samvil/build.log 2>&1",
        "log_path": ".samvil/build.log",
        "language": "typescript",
    },
    "game": {
        "command": "npx tsc --noEmit > .samvil/build.log 2>&1",
        "log_path": ".samvil/build.log",
        "language": "typescript",
    },
    "mobile-app": {
        "command": "npx expo export --platform web > .samvil/build.log 2>&1",
        "log_path": ".samvil/build.log",
        "language": "typescript",
    },
    "automation-python": {
        "command": (
            "python -m py_compile src/processor.py > .samvil/build.log 2>&1 "
            "&& python -m py_compile src/main.py >> .samvil/build.log 2>&1"
        ),
        "log_path": ".samvil/build.log",
        "language": "python",
    },
    "automation-node": {
        "command": "npx tsc --noEmit > .samvil/build.log 2>&1",
        "log_path": ".samvil/build.log",
        "language": "typescript",
    },
    "automation-cc-skill": {
        "command": "",  # No build step — skill files only
        "log_path": "",
        "language": "markdown",
    },
}


# Per-`solution_type` recipe reference (relative to plugin root).
_RECIPE_PATHS: dict[str, str] = {
    "web-app": "references/web-recipes.md",
    "automation": "references/automation-recipes.md",
    "game": "references/game-recipes.md",
    "mobile-app": "references/mobile-recipes.md",
    "dashboard": "references/dashboard-recipes.md",
}


# ── Helpers ───────────────────────────────────────────────────────────


def _read_json_safe(path: Path) -> dict[str, Any] | None:
    """Best-effort JSON read. Returns None on missing/invalid file."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _resolve_build_verify(
    solution_type: str,
    seed: dict[str, Any],
) -> dict[str, str]:
    """Pick build_verify based on solution_type + (for automation) language."""
    if solution_type == "automation":
        # Automation has 3 sub-modes by `implementation.runtime`.
        impl = seed.get("implementation") or {}
        runtime = str(impl.get("runtime") or "").lower()
        if runtime in ("python", "py"):
            key = "automation-python"
        elif runtime in ("node", "nodejs", "javascript", "typescript", "ts"):
            key = "automation-node"
        elif runtime in ("cc-skill", "skill"):
            key = "automation-cc-skill"
        else:
            # Default to python — most common automation stack.
            key = "automation-python"
        return dict(_BUILD_VERIFY_COMMANDS[key])

    return dict(_BUILD_VERIFY_COMMANDS.get(solution_type, _BUILD_VERIFY_COMMANDS["web-app"]))


def _scan_sanity(project_path: Path) -> dict[str, Any]:
    """Phase A.6 sanity checks — empty config files, unsubstituted vars,
    broken relative imports.

    Returns a dict with `passed: bool`, `failures: list[str]`,
    `warnings: list[str]`. The skill body decides how to surface the
    result; we just collect.
    """
    failures: list[str] = []
    warnings: list[str] = []

    if not project_path.exists():
        return {"passed": True, "failures": failures, "warnings": warnings, "skipped": True}

    # A.6.1 — Key config files must be non-empty.
    config_files = [
        "package.json",
        "tsconfig.json",
        ".env.example",
        "requirements.txt",
        "pyproject.toml",
        "setup.py",
    ]
    for name in config_files:
        p = project_path / name
        if p.is_file() and p.stat().st_size == 0:
            failures.append(f"empty config file: {name}")

    # A.6.2 — Unsubstituted template variables ({{FOO}} or <FOO>) in source.
    template_re = re.compile(r"\{\{[A-Z_][A-Z0-9_]+\}\}|<[A-Z_]{3,}>")
    src_dirs = ["src", "app", "components", "lib"]
    for sub in src_dirs:
        sub_path = project_path / sub
        if not sub_path.is_dir():
            continue
        for child in sub_path.rglob("*"):
            if not child.is_file():
                continue
            if "node_modules" in child.parts or ".next" in child.parts:
                continue
            if child.suffix not in (".ts", ".tsx", ".js", ".jsx", ".py", ".md", ".json"):
                continue
            try:
                text = child.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if template_re.search(text):
                failures.append(f"unsubstituted template variable in: {child.relative_to(project_path)}")
                if len(failures) > 25:
                    break
        if len(failures) > 25:
            break

    # A.6.3 — Broken relative imports for TS/JS files.
    bad_imports: list[str] = []
    src_root = project_path / "src"
    if src_root.is_dir():
        import_re = re.compile(r"from ['\"](\.[^'\"]+)['\"]")
        for child in src_root.rglob("*"):
            if not child.is_file():
                continue
            if child.suffix not in (".ts", ".tsx", ".js", ".jsx"):
                continue
            try:
                text = child.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for match in import_re.finditer(text):
                rel = match.group(1)
                target = (child.parent / rel).resolve()
                candidates = [
                    target,
                    target.with_suffix(".ts"),
                    target.with_suffix(".tsx"),
                    target.with_suffix(".js"),
                    target.with_suffix(".jsx"),
                    target / "index.ts",
                    target / "index.tsx",
                ]
                if not any(c.exists() for c in candidates):
                    bad_imports.append(
                        f"{child.relative_to(project_path)}: import '{rel}' → not found"
                    )
                    if len(bad_imports) > 10:
                        break
            if len(bad_imports) > 10:
                break
    if bad_imports:
        failures.append("broken imports detected")
        warnings.extend(bad_imports[:10])

    return {
        "passed": not failures,
        "failures": failures,
        "warnings": warnings,
        "skipped": False,
    }


def _resume_hint(project_path: Path) -> dict[str, Any]:
    """Read `project.state.json` + checkpoint file (if any) for resume."""
    state = _read_json_safe(project_path / "project.state.json") or {}
    completed_features: list[str] = list(state.get("completed_features") or [])
    return {
        "completed_features": completed_features,
        "current_stage": str(state.get("current_stage") or ""),
        "session_id": str(state.get("session_id") or ""),
        "current_model_build": state.get("current_model_build") or {},
    }


# ── Aggregator ────────────────────────────────────────────────────────


@dataclass
class BuildPhaseAReport:
    schema_version: str = BUILD_PHASE_A_SCHEMA_VERSION
    project_path: str = ""
    solution_type: str = ""
    framework: str = ""
    seed_loaded: bool = False
    state_loaded: bool = False
    blueprint_loaded: bool = False
    build_verify: dict[str, str] = field(default_factory=dict)
    recipe_path: str = ""
    paths: dict[str, str] = field(default_factory=dict)
    sanity: dict[str, Any] = field(default_factory=dict)
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
            "blueprint_loaded": self.blueprint_loaded,
            "build_verify": self.build_verify,
            "recipe_path": self.recipe_path,
            "paths": self.paths,
            "sanity": self.sanity,
            "resume_hint": self.resume_hint,
            "notes": self.notes,
            "errors": self.errors,
        }


def aggregate_build_phase_a(
    project_path: str | Path,
    *,
    run_sanity_checks: bool = True,
) -> dict[str, Any]:
    """Aggregate every fact the samvil-build skill needs at Phase A.

    Args:
        project_path: Project root containing `project.seed.json`,
            `project.state.json`, optional `project.config.json`,
            optional `project.blueprint.json`.
        run_sanity_checks: When True (default), runs the Phase A.6
            scaffold sanity scan.

    Returns:
        JSON-serializable dict — see BuildPhaseAReport fields. Keys
        always present; missing files set the corresponding `_loaded`
        flag to False and append an entry to `errors`.
    """
    report = BuildPhaseAReport()
    root = Path(str(project_path)).expanduser()
    report.project_path = str(root)

    # Seed.
    seed = _read_json_safe(root / "project.seed.json")
    if seed is None:
        report.errors.append("project.seed.json not found or invalid")
        seed = {}
    else:
        report.seed_loaded = True

    # State.
    state = _read_json_safe(root / "project.state.json")
    if state is None:
        state = {}
    else:
        report.state_loaded = True

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

    # Build-verify command.
    report.build_verify = _resolve_build_verify(solution_type, seed)

    # Recipe path.
    report.recipe_path = _RECIPE_PATHS.get(solution_type, "")

    # Paths.
    report.paths = {
        "seed": str(root / "project.seed.json"),
        "state": str(root / "project.state.json"),
        "config": str(root / "project.config.json"),
        "blueprint": str(root / "project.blueprint.json"),
        "decisions_log": str(root / "decisions.log"),
        "build_log": str(root / ".samvil" / "build.log"),
        "fix_log": str(root / ".samvil" / "fix-log.md"),
        "handoff": str(root / ".samvil" / "handoff.md"),
        "events": str(root / ".samvil" / "events.jsonl"),
        "rate_budget": str(root / ".samvil" / "rate-budget.jsonl"),
        "sanity_log": str(root / ".samvil" / "sanity.log"),
    }

    # Sanity scan.
    if run_sanity_checks:
        report.sanity = _scan_sanity(root)
    else:
        report.sanity = {"passed": True, "failures": [], "warnings": [], "skipped": True}

    # Resume hint.
    report.resume_hint = _resume_hint(root)

    # Notes.
    if not report.seed_loaded:
        report.notes.append("seed missing — skill should AskUserQuestion or chain back to samvil-seed")
    if solution_type not in _BUILD_VERIFY_COMMANDS and solution_type != "automation":
        report.notes.append(
            f"unknown solution_type '{solution_type}' — defaulting to web-app build verify"
        )
    if not framework:
        report.notes.append("framework missing in seed.tech_stack — skill should default by solution_type")

    return report.to_dict()
