"""SAMVIL brownfield analyzer (T4.4).

Centralizes the inputs the `samvil-analyze` skill needs that are best produced
from inside the MCP process — single source of truth for the four phases of
reverse-engineering an existing codebase into a v3.x seed:

1. **Framework + tech-stack detection** — package.json deps, lockfiles, config
   files (next/vite/astro/expo/phaser/python-script). Reuses `manifest.detect_conventions`.
2. **Module + feature inventory** — walks `src/` (and `app/` for Next.js
   App Router) to identify cohesive feature subdirectories. Reuses
   `manifest.discover_modules` + `extract_public_api`.
3. **Reverse-seed assembly** — produces a v3.0 seed dict with every detected
   feature represented as `status: "existing"` + an AC-tree leaf carrying
   file:line evidence (P1).
4. **Confidence tagging + ADR seeding** — every inferred field gets a
   confidence score (`high` / `medium` / `low`) and one ADR-EXISTING-NNN
   per heuristic decision (framework choice, state-management choice,
   data-source choice).

What stays in the skill body:

- Git safety net (`git status` shell call, AskUserQuestion to commit).
- Path AskUserQuestion (current dir vs. typed-in path).
- The user-review checkpoint after the analysis is rendered.
- Writing `project.seed.json`, `project.state.json`, `interview-summary.md`,
  `decisions.log`, and the ADR files (host-bound file IO with explicit
  user approval, INV-1).
- Routing the user's gap-analysis answer to `samvil-build` /
  `samvil-design` / `samvil-qa`.

Schema notes:

- The returned dict's top level is `BrownfieldReport.to_dict()` — see the
  dataclass below for the contract.
- `report["seed"]` is a v3.0-shaped dict that the skill writes verbatim to
  `project.seed.json` once the user approves. It validates against
  `references/seed-schema.json` for `schema_version: "3.0"`.
- `report["adrs"]` is a list of ADR-EXISTING-NNN entries the skill appends
  to `decisions.log` (one row each) — they explain *why* a heuristic
  inference was made (e.g., "framework=next inferred from next.config.mjs").
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import manifest as _manifest


# ── Catalog: framework-detection rules ─────────────────────────────────


# Each rule:
#   (key, value, kind, hits)
# `kind` ∈ {"dep", "config_file", "config_dir", "lockfile"}.
# The first matching rule for each *category* wins. Categories:
#   framework / language / runtime / package_manager
_FRAMEWORK_RULES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    # Frontend frameworks
    # NOTE: Phaser/Expo/React-Native deps win over vite/astro config files
    # because they signal solution_type uniquely. Bundler choice is captured
    # separately as a signal, but the *framework* (and downstream
    # solution_type) is the runtime, not the bundler.
    ("framework", "phaser", "dep", ("phaser",)),
    ("framework", "expo", "dep", ("expo",)),
    ("framework", "next", "config_file", (
        "next.config.js", "next.config.mjs", "next.config.ts",
    )),
    ("framework", "next", "dep", ("next",)),
    ("framework", "vite-react", "config_file", (
        "vite.config.js", "vite.config.ts",
    )),
    ("framework", "astro", "config_file", (
        "astro.config.mjs", "astro.config.ts", "astro.config.js",
    )),
    ("framework", "expo", "config_file", ("app.json", "app.config.js")),
    ("framework", "react-native", "dep", ("react-native",)),
    ("framework", "vue", "dep", ("vue",)),
    ("framework", "svelte", "dep", ("svelte",)),
    ("framework", "express", "dep", ("express",)),
    ("framework", "fastify", "dep", ("fastify",)),
    # Languages
    ("language", "typescript", "config_file", ("tsconfig.json",)),
    ("language", "python", "config_file", (
        "pyproject.toml", "setup.py", "requirements.txt",
    )),
    # Runtimes
    ("runtime", "node", "config_file", ("package.json",)),
    ("runtime", "python", "config_file", (
        "pyproject.toml", "setup.py",
    )),
    ("runtime", "deno", "config_file", ("deno.json", "deno.jsonc")),
    ("runtime", "bun", "config_file", ("bun.lockb",)),
    # Package managers
    ("package_manager", "pnpm", "lockfile", ("pnpm-lock.yaml",)),
    ("package_manager", "yarn", "lockfile", ("yarn.lock",)),
    ("package_manager", "npm", "lockfile", ("package-lock.json",)),
    ("package_manager", "bun", "lockfile", ("bun.lockb",)),
    ("package_manager", "pip", "lockfile", ("requirements.txt",)),
    ("package_manager", "poetry", "lockfile", ("poetry.lock",)),
    ("package_manager", "uv", "lockfile", ("uv.lock",)),
)


# UI library detection — walks deps + folders.
_UI_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # (key, kind, signals) where kind ∈ {"dep", "dir", "config_file"}
    ("shadcn", "dir", ("components/ui",)),
    ("shadcn", "config_file", ("components.json",)),
    ("mui", "dep", ("@mui/material", "@material-ui/core")),
    ("chakra", "dep", ("@chakra-ui/react",)),
    ("antd", "dep", ("antd",)),
    ("tailwind", "config_file", (
        "tailwind.config.js", "tailwind.config.mjs", "tailwind.config.ts",
    )),
    ("tailwind", "dep", ("tailwindcss",)),
    ("styled-components", "dep", ("styled-components",)),
    ("emotion", "dep", ("@emotion/react",)),
)


# State-management detection.
_STATE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # (key, deps)
    ("zustand", ("zustand",)),
    ("redux", ("@reduxjs/toolkit", "redux", "react-redux")),
    ("recoil", ("recoil",)),
    ("jotai", ("jotai",)),
    ("mobx", ("mobx", "mobx-react")),
    ("react-query", ("@tanstack/react-query", "react-query")),
    ("swr", ("swr",)),
)


# Data-source detection — deps + folders.
_DATA_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # (key, kind, signals) where kind ∈ {"dep", "dir"}
    ("supabase", "dep", ("@supabase/supabase-js", "@supabase/auth-helpers-nextjs")),
    ("prisma", "dep", ("@prisma/client",)),
    ("prisma", "dir", ("prisma",)),
    ("drizzle", "dep", ("drizzle-orm",)),
    ("firebase", "dep", ("firebase",)),
    ("mongodb", "dep", ("mongodb", "mongoose")),
    ("postgres", "dep", ("pg", "postgres")),
    ("api-routes", "dir", ("app/api", "pages/api")),
)


# solution_type detection — chooses based on framework + signals.
def _infer_solution_type(framework: str, conventions: dict[str, str]) -> tuple[str, str]:
    """Return (solution_type, confidence) where confidence ∈ {high, medium, low}."""
    if framework in ("next", "vite-react", "astro", "vue", "svelte"):
        return ("web-app", "high")
    if framework in ("expo", "react-native"):
        return ("mobile-app", "high")
    if framework == "phaser":
        return ("game", "high")
    if framework in ("express", "fastify"):
        return ("automation", "medium")  # API server is closest to automation
    if conventions.get("language") == "python":
        return ("automation", "medium")  # python script most likely
    return ("web-app", "low")  # fallback


# ── Helpers ────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _file_exists(root: Path, names: tuple[str, ...]) -> str | None:
    for n in names:
        if (root / n).is_file():
            return n
    return None


def _dir_exists(root: Path, names: tuple[str, ...]) -> str | None:
    for n in names:
        if (root / n).is_dir():
            return n
    return None


def _has_dep(pkg: dict[str, Any], names: tuple[str, ...]) -> str | None:
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
    for n in names:
        if n in deps:
            return n
    return None


# ── Detection passes ───────────────────────────────────────────────────


def detect_framework(root: Path, pkg: dict[str, Any]) -> dict[str, Any]:
    """Return a dict with framework/language/runtime/package_manager + signals."""
    out: dict[str, Any] = {
        "framework": "unknown",
        "framework_signal": "",
        "language": "unknown",
        "runtime": "unknown",
        "package_manager": "unknown",
    }
    seen: set[str] = set()
    for key, value, kind, hits in _FRAMEWORK_RULES:
        if key in seen:
            continue
        signal: str | None = None
        if kind == "dep":
            signal = _has_dep(pkg, hits)
            if signal:
                signal = f"dep:{signal}"
        elif kind == "config_file":
            f = _file_exists(root, hits)
            if f:
                signal = f"file:{f}"
        elif kind == "config_dir":
            d = _dir_exists(root, hits)
            if d:
                signal = f"dir:{d}"
        elif kind == "lockfile":
            f = _file_exists(root, hits)
            if f:
                signal = f"lockfile:{f}"
        if signal:
            out[key] = value
            if key == "framework":
                out["framework_signal"] = signal
            seen.add(key)
    return out


def detect_ui_library(root: Path, pkg: dict[str, Any]) -> dict[str, Any]:
    """Return UI library name + signal."""
    for key, kind, hits in _UI_RULES:
        signal: str | None = None
        if kind == "dep":
            signal = _has_dep(pkg, hits)
            if signal:
                return {"ui": key, "ui_signal": f"dep:{signal}"}
        elif kind == "config_file":
            f = _file_exists(root, hits)
            if f:
                return {"ui": key, "ui_signal": f"file:{f}"}
        elif kind == "dir":
            d = _dir_exists(root, hits)
            if d:
                return {"ui": key, "ui_signal": f"dir:{d}"}
    return {"ui": "unknown", "ui_signal": ""}


def detect_state_management(pkg: dict[str, Any]) -> dict[str, Any]:
    """Return state-management library + signal (or 'react-state' if none)."""
    for key, hits in _STATE_RULES:
        signal = _has_dep(pkg, hits)
        if signal:
            return {"state": key, "state_signal": f"dep:{signal}"}
    return {"state": "react-state", "state_signal": "default"}


def detect_data_source(root: Path, pkg: dict[str, Any]) -> dict[str, Any]:
    """Return data source detection (db / api / storage)."""
    sources: list[str] = []
    signals: list[str] = []
    for key, kind, hits in _DATA_RULES:
        if kind == "dep":
            signal = _has_dep(pkg, hits)
            if signal:
                sources.append(key)
                signals.append(f"{key}=dep:{signal}")
        elif kind == "dir":
            d = _dir_exists(root, hits)
            if d:
                sources.append(key)
                signals.append(f"{key}=dir:{d}")
    if not sources:
        return {"data_sources": [], "data_signals": []}
    return {"data_sources": sources, "data_signals": signals}


# ── Feature inference (from modules) ───────────────────────────────────


# Heuristic blocklist — these module names rarely correspond to product features.
_NON_FEATURE_MODULES = frozenset({
    "lib", "utils", "util", "types", "config", "constants", "hooks",
    "styles", "assets", "public", "test", "tests", "__tests__",
    "components",  # too generic — child folders are features
    "ui",          # shadcn/ui components dir
    "store",
    "src",         # synthetic root module from manifest
    "api",         # routes, not features per se
    "app",         # Next.js App Router root
    "pages",       # Next.js Pages Router root
})


def infer_features(
    project_root: Path,
    modules: list[_manifest.ModuleEntry],
) -> list[dict[str, Any]]:
    """Convert ModuleEntry list into v3 seed feature dicts.

    Heuristic: each module that isn't in the blocklist becomes a feature with
    one AC-tree leaf carrying file:line evidence pointing at the first code
    file in the module.
    """
    features: list[dict[str, Any]] = []
    for m in modules:
        if m.name in _NON_FEATURE_MODULES:
            continue
        if not m.files:
            continue
        # First file is the evidence anchor — line 1 is a placeholder; the
        # user can sharpen this in the review checkpoint.
        anchor = m.files[0]
        ac_id = f"AC-{_slug(m.name)}-1"
        feature_name = _slug(m.name)
        leaf = {
            "id": ac_id,
            "description": (
                f"기존 모듈 `{m.name}` (`{m.path}`)이 존재한다."
                + (
                    f" 공개 API: {', '.join(m.public_api[:3])}"
                    if m.public_api
                    else ""
                )
            ),
            "children": [],
            "status": "pass",
            "evidence": [f"{anchor}:1"],
        }
        features.append({
            "name": feature_name,
            "priority": 1,
            "independent": True,
            "status": "existing",
            "acceptance_criteria": [leaf],
        })
    return features


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(name: str) -> str:
    s = _SLUG_RE.sub("-", name.lower()).strip("-")
    return s or "feature"


# ── Reverse-seed assembly ──────────────────────────────────────────────


@dataclass
class BrownfieldReport:
    """Aggregated brownfield-analysis view the thin skill renders from."""

    schema_version: str = "1.0"
    project_root: str = ""
    project_name: str = ""
    framework: dict[str, Any] = field(default_factory=dict)
    ui_library: dict[str, Any] = field(default_factory=dict)
    state_management: dict[str, Any] = field(default_factory=dict)
    data_sources: dict[str, Any] = field(default_factory=dict)
    solution_type: str = "web-app"
    solution_type_confidence: str = "low"
    module_count: int = 0
    feature_count: int = 0
    seed: dict[str, Any] = field(default_factory=dict)
    confidence_tags: dict[str, str] = field(default_factory=dict)
    adrs: list[dict[str, Any]] = field(default_factory=list)
    summary_lines: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_root": self.project_root,
            "project_name": self.project_name,
            "framework": self.framework,
            "ui_library": self.ui_library,
            "state_management": self.state_management,
            "data_sources": self.data_sources,
            "solution_type": self.solution_type,
            "solution_type_confidence": self.solution_type_confidence,
            "module_count": self.module_count,
            "feature_count": self.feature_count,
            "seed": self.seed,
            "confidence_tags": self.confidence_tags,
            "adrs": self.adrs,
            "summary_lines": self.summary_lines,
            "warnings": self.warnings,
        }


def _build_adr(
    nnn: int,
    *,
    title: str,
    decision: str,
    signal: str,
    confidence: str,
) -> dict[str, Any]:
    return {
        "id": f"ADR-EXISTING-{nnn:03d}",
        "title": title,
        "status": "accepted",
        "decision": decision,
        "rationale": f"Inferred from existing codebase. Signal: {signal}.",
        "confidence": confidence,
        "source": "samvil-analyze (brownfield reverse-engineering)",
        "created_at": _now_iso(),
    }


def _confidence_for_signal(signal: str) -> str:
    """`high` if config-file or lockfile, `medium` if dep, `low` otherwise."""
    if not signal:
        return "low"
    if signal.startswith("file:") or signal.startswith("lockfile:"):
        return "high"
    if signal.startswith("dep:") or signal.startswith("dir:"):
        return "medium"
    return "low"


def _build_summary_lines(report: BrownfieldReport, modules: list[_manifest.ModuleEntry]) -> list[str]:
    lines: list[str] = []
    fw = report.framework
    lines.append(
        f"프레임워크: {fw.get('framework', 'unknown')}"
        + (
            f" (signal: {fw.get('framework_signal')})"
            if fw.get("framework_signal")
            else ""
        )
    )
    lines.append(f"언어: {fw.get('language', 'unknown')} · 런타임: {fw.get('runtime', 'unknown')}")
    lines.append(f"패키지 매니저: {fw.get('package_manager', 'unknown')}")
    lines.append(f"UI: {report.ui_library.get('ui', 'unknown')}")
    lines.append(f"상태관리: {report.state_management.get('state', 'react-state')}")
    if report.data_sources.get("data_sources"):
        lines.append(
            "데이터: " + ", ".join(report.data_sources["data_sources"])
        )
    else:
        lines.append("데이터: (탐지 안 됨)")
    lines.append(
        f"solution_type: {report.solution_type} (confidence: {report.solution_type_confidence})"
    )
    lines.append(f"모듈: {report.module_count}개 · 추론된 기능: {report.feature_count}개")
    if modules:
        names = [m.name for m in modules[:8]]
        more = "" if len(modules) <= 8 else f", … (+{len(modules) - 8} more)"
        lines.append(f"모듈 목록: {', '.join(names)}{more}")
    return lines


def analyze_brownfield_project(
    project_root: str | Path,
    *,
    project_name: str | None = None,
) -> dict[str, Any]:
    """Aggregate every fact the samvil-analyze skill needs in one call.

    Args:
        project_root: Directory to analyze. Should contain at minimum a
            `package.json` (JS/TS) or `pyproject.toml` (Python). Tolerant
            of either.
        project_name: Override for the project's display name. Defaults to
            `package.json:name` then to the directory's basename.

    Returns:
        A dict shaped per `BrownfieldReport.to_dict()`. Errors are surfaced
        as a top-level `error` key (INV-5 / P8): the skill must not crash
        on a missing or partially-readable codebase.
    """
    root = Path(project_root)
    if not root.is_dir():
        return {
            "schema_version": "1.0",
            "error": f"project_root is not a directory: {project_root!r}",
            "project_root": str(root),
        }

    pkg = _read_json(root / "package.json") or {}
    inferred_name = (
        project_name
        or pkg.get("name")
        or root.name
        or "brownfield-project"
    )

    framework = detect_framework(root, pkg)
    ui = detect_ui_library(root, pkg)
    state_mgmt = detect_state_management(pkg)
    data = detect_data_source(root, pkg)
    solution_type, solution_conf = _infer_solution_type(
        framework["framework"], framework
    )

    # Module discovery + features
    modules = _manifest.discover_modules(root)
    features = infer_features(root, modules)

    # Confidence tags per inferred top-level field
    fw_conf = _confidence_for_signal(framework.get("framework_signal", ""))
    ui_conf = _confidence_for_signal(ui.get("ui_signal", ""))
    state_conf = _confidence_for_signal(state_mgmt.get("state_signal", ""))
    confidence_tags: dict[str, str] = {
        "framework": fw_conf,
        "ui": ui_conf,
        "state": state_conf,
        "solution_type": solution_conf,
        "features": "medium" if features else "low",
    }

    # ADR seeding — one per heuristic decision worth recording
    adrs: list[dict[str, Any]] = []
    if framework.get("framework_signal"):
        adrs.append(_build_adr(
            len(adrs) + 1,
            title=f"Framework: {framework['framework']}",
            decision=f"This project uses {framework['framework']}.",
            signal=framework["framework_signal"],
            confidence=fw_conf,
        ))
    if ui.get("ui_signal"):
        adrs.append(_build_adr(
            len(adrs) + 1,
            title=f"UI library: {ui['ui']}",
            decision=f"UI is rendered with {ui['ui']}.",
            signal=ui["ui_signal"],
            confidence=ui_conf,
        ))
    if state_mgmt.get("state_signal") and state_mgmt["state"] != "react-state":
        adrs.append(_build_adr(
            len(adrs) + 1,
            title=f"State management: {state_mgmt['state']}",
            decision=f"State is managed via {state_mgmt['state']}.",
            signal=state_mgmt["state_signal"],
            confidence=state_conf,
        ))
    if data.get("data_sources"):
        adrs.append(_build_adr(
            len(adrs) + 1,
            title=f"Data sources: {', '.join(data['data_sources'])}",
            decision=f"Project persists data via {', '.join(data['data_sources'])}.",
            signal="; ".join(data.get("data_signals", [])),
            confidence="medium",
        ))

    # Compose the v3.0 reverse-seed
    description = (
        pkg.get("description")
        or f"Brownfield project reverse-engineered by samvil-analyze. "
           f"Detected framework: {framework['framework']}."
    )
    seed: dict[str, Any] = {
        "schema_version": "3.0",
        "name": inferred_name,
        "description": description,
        "solution_type": solution_type,
        "tech_stack": {
            "framework": framework["framework"],
            "language": framework.get("language", "unknown"),
            "runtime": framework.get("runtime", "unknown"),
            "package_manager": framework.get("package_manager", "unknown"),
            "ui": ui.get("ui", "unknown"),
            "state": state_mgmt.get("state", "react-state"),
            "data_sources": data.get("data_sources", []),
        },
        "core_experience": {
            "description": (
                f"Reverse-engineered from existing {framework['framework']} codebase. "
                "Refine via interview before evolve."
            ),
            "primary_screen": (modules[0].name if modules else "unknown"),
            "key_interactions": [],
        },
        "features": features,
        "constraints": [],
        "out_of_scope": [],
        "version": 1,
        "_analysis": {
            "source": "brownfield",
            "analyzed_at": _now_iso(),
            "module_count": len(modules),
            "feature_count": len(features),
            "framework_detected": framework["framework"],
            "framework_signal": framework.get("framework_signal", ""),
            "confidence_tags": confidence_tags,
        },
    }

    # Warnings — fields the skill should re-confirm with the user
    warnings: list[str] = []
    if framework["framework"] == "unknown":
        warnings.append(
            "framework=unknown — neither package.json deps nor a known config "
            "file matched. Ask the user to identify the framework."
        )
    if not features:
        warnings.append(
            "No feature modules detected (src/ may be missing or only contain "
            "non-feature folders like lib/utils/types). Reverse-seed has empty "
            "features[]; user must add at least one feature manually before build."
        )
    if solution_conf == "low":
        warnings.append(
            "solution_type confidence=low. Re-confirm with user before chaining "
            "downstream stages."
        )

    report = BrownfieldReport(
        project_root=str(root),
        project_name=inferred_name,
        framework=framework,
        ui_library=ui,
        state_management=state_mgmt,
        data_sources=data,
        solution_type=solution_type,
        solution_type_confidence=solution_conf,
        module_count=len(modules),
        feature_count=len(features),
        seed=seed,
        confidence_tags=confidence_tags,
        adrs=adrs,
        warnings=warnings,
    )
    report.summary_lines = _build_summary_lines(report, modules)
    return report.to_dict()
