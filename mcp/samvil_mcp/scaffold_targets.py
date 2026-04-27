"""SAMVIL scaffold-target evaluator (T4.7).

Centralizes the inputs the `samvil-scaffold` skill needs that are best
produced from inside the MCP process — single source of truth for the
seven `tech_stack.framework` branches that previously lived inline in
the 1653-LOC skill body:

- Stack identification (`seed.tech_stack.framework` → catalog key in
  `references/dependency-matrix.json`).
- CLI command lookup per stack (Next.js, Vite+React, Astro, Phaser,
  Expo, python-script, node-script, cc-skill).
- Pinned-version inventory from the dependency matrix (so the skill
  never installs `@latest`).
- Post-install steps the skill must run (mkdir, shadcn init,
  Playwright, Supabase, etc.).
- Sanity checks for Phase A.6 (which files must exist after scaffold,
  which Tailwind config strings must be present after the shadcn
  v3/v4 overwrite dance).
- Build-verification command + log-path per stack (INV-2).
- Existing-project detection (incremental scaffold path).

What stays in the skill body:

- Actually shelling out to `npx create-next-app`, `npm create vite`,
  `npm create astro`, `npx create-expo-app`, `python3 -m venv`,
  `npm init`, `npx shadcn init`, `npx playwright install`, etc.
  Those are intentionally CC-bound (host-bound, P8 graceful
  degradation): `npm`/`pnpm`/`yarn` versions matter and the MCP
  process can't reliably proxy `node` execution.
- Re-writing `app/layout.tsx`, `tailwind.config.ts`, `app/globals.css`
  to the HSL v3 form after `shadcn init` overwrites them with v4
  oklch syntax. The literal file bodies remain in `SKILL.legacy.md`
  because they're long and rendering them through MCP would just
  pass them through verbatim.
- AskUserQuestion prompts when sanity checks fail.
- Writing `.samvil/build.log`, `.samvil/handoff.md`, and updating
  `project.state.json`.
- Chain into `samvil-build`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── Path resolution ─────────────────────────────────────────────────


def _references_dir() -> Path:
    """Resolve the repo's `references/` directory.

    The MCP module ships inside `mcp/samvil_mcp/`. The matrix lives at
    `<repo_root>/references/dependency-matrix.json`. We avoid hard-coded
    user paths per the v3.2 portability rule (CLAUDE.md §Pre-Commit).
    """
    return Path(__file__).resolve().parents[2] / "references"


def _load_dependency_matrix() -> dict[str, Any]:
    """Best-effort load of `references/dependency-matrix.json`.

    Returns `{}` if the file is missing or malformed — INV-5 / P8: a
    broken matrix must not crash scaffold-target evaluation; the skill
    falls back to its embedded legacy commands.
    """
    matrix_path = _references_dir() / "dependency-matrix.json"
    try:
        return json.loads(matrix_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


# ── Catalog: per-framework scaffold targets ────────────────────────


# Maps `seed.tech_stack.framework` (the user-facing enum) to the catalog
# key in `references/dependency-matrix.json` (the implementation key).
# This indirection exists because the matrix was authored before the
# `solution_type` enum stabilized — `phaser` (framework) vs `phaser-game`
# (matrix) is the canonical mismatch.
_FRAMEWORK_TO_MATRIX_KEY: dict[str, str] = {
    "nextjs": "nextjs14",
    "vite-react": "vite-react",
    "astro": "astro",
    "python-script": "python-script",
    "node-script": "node-script",
    "phaser": "phaser-game",
    "expo": "expo-mobile",
    "cc-skill": "cc-skill",
    # Planned (returned with `status: planned`, skill falls back to nextjs):
    "nuxt": "nuxt_planned",
    "sveltekit": "sveltekit_planned",
}


# Per-framework scaffold catalog. Each entry carries everything the skill
# needs to (a) run the right CLI, (b) verify the install, (c) wire common
# setup. Templates use `<seed.name>` placeholders the skill substitutes
# at render time — same convention as `deploy_targets.DEPLOY_CATALOG`.
SCAFFOLD_CATALOG: dict[str, dict[str, Any]] = {
    "nextjs": {
        "label": "Next.js 14",
        "category": "web",
        "matrix_key": "nextjs14",
        "cli_command_template": (
            "npx create-next-app@14.2.35 <seed.name> --typescript --tailwind "
            "--app --src-dir=false --import-alias=\"@/*\" --eslint --use-npm <<< $'No\\n'"
        ),
        "post_install_steps": [
            "overwrite app/layout.tsx (Inter font, no Geist)",
            "overwrite tailwind.config.ts (HSL v3 colors)",
            "overwrite app/globals.css (HSL v3 vars, no oklch)",
            "npm install -D tailwindcss-animate@1.0.7",
            "shadcn init + add button card input dialog label select textarea",
            "npm install -D @playwright/test && npx playwright install chromium",
            "configure Supabase if seed.tech_stack mentions it",
            "next.config.mjs output:'standalone'",
        ],
        "sanity_checks": [
            {"path": "package.json", "required": True},
            {"path": "app/page.tsx", "required": True},
            {"path": "app/layout.tsx", "required": True},
            {"path": "app/globals.css", "required": True},
            {"path": "tailwind.config.ts", "required": True},
            {"path": "app/globals.css", "must_contain": "@tailwind base"},
            {"path": "tailwind.config.ts", "must_contain": "hsl(var(--"},
        ],
        "build_command": "npm run build > .samvil/build.log 2>&1",
        "build_log_path": ".samvil/build.log",
        "version_check_keys": [
            "next",
            "react",
            "react-dom",
            "tailwindcss",
            "tailwindcss-animate",
            "clsx",
            "tailwind-merge",
        ],
        "env_vars_needed": [
            "NEXT_PUBLIC_SUPABASE_URL",
            "NEXT_PUBLIC_SUPABASE_ANON_KEY",
        ],
        "status": "stable",
    },
    "vite-react": {
        "label": "Vite + React + Tailwind v4",
        "category": "web",
        "matrix_key": "vite-react",
        "cli_command_template": (
            "npm create vite@5.4.21 <seed.name> -- --template react-ts"
        ),
        "post_install_steps": [
            "npm install -D tailwindcss@4.1.4 @tailwindcss/vite@4.2.2",
            "vite.config.ts: add @tailwindcss/vite plugin",
            "src/index.css: add @import \"tailwindcss\"",
            "tsconfig.json: add paths { \"@/*\": [\"./src/*\"] }",
            "vite.config.ts: add resolve.alias @ → ./src",
            "shadcn init + add button card input dialog label select textarea",
            "npm install -D @playwright/test && npx playwright install chromium",
        ],
        "sanity_checks": [
            {"path": "package.json", "required": True},
            {"path": "src/App.tsx", "required": True},
            {"path": "src/index.css", "required": True},
            {"path": "vite.config.ts", "required": True},
            {"path": "vite.config.ts", "must_contain": "@tailwindcss/vite"},
            {"path": "src/index.css", "must_contain": "@import \"tailwindcss\""},
        ],
        "build_command": "npm run build > .samvil/build.log 2>&1",
        "build_log_path": ".samvil/build.log",
        "version_check_keys": [
            "vite",
            "react",
            "react-dom",
            "tailwindcss",
            "@tailwindcss/vite",
        ],
        "env_vars_needed": [
            "VITE_SUPABASE_URL",
            "VITE_SUPABASE_ANON_KEY",
        ],
        "status": "stable",
    },
    "astro": {
        "label": "Astro + React islands",
        "category": "web",
        "matrix_key": "astro",
        "cli_command_template": (
            "npm create astro@6.1.5 <seed.name> -- --template minimal "
            "--install --no-git --typescript strict"
        ),
        "post_install_steps": [
            "npx astro add tailwind -y",
            "npx astro add react -y",
            "manually copy shadcn/ui components from a Next.js setup (not native)",
        ],
        "sanity_checks": [
            {"path": "package.json", "required": True},
            {"path": "astro.config.mjs", "required": True},
            {"path": "src/pages/index.astro", "required": True},
        ],
        "build_command": "npm run build > .samvil/build.log 2>&1",
        "build_log_path": ".samvil/build.log",
        "version_check_keys": ["astro", "@astrojs/tailwind", "@astrojs/react"],
        "env_vars_needed": [],
        "status": "stable",
    },
    "phaser": {
        "label": "Phaser 3 + Vite (game)",
        "category": "game",
        "matrix_key": "phaser-game",
        "cli_command_template": (
            "npm create vite@5.4.21 <seed.name> -- --template vanilla-ts"
        ),
        "post_install_steps": [
            "npm install phaser@3.87.0",
            "mkdir -p public/assets/{sprites,images,audio} src/{scenes,entities,config}",
            "create src/main.ts (Phaser boot)",
            "create src/config/game-config.ts",
            "create src/scenes/{BootScene,MenuScene,GameScene,GameOverScene}.ts",
            "create src/entities/Player.ts",
            "update tsconfig.json + vite.config.ts + package.json scripts",
        ],
        "sanity_checks": [
            {"path": "package.json", "required": True},
            {"path": "src/main.ts", "required": True},
            {"path": "src/scenes/BootScene.ts", "required": True},
            {"path": "src/scenes/GameScene.ts", "required": True},
            {"path": "vite.config.ts", "required": True},
        ],
        "build_command": (
            "npx tsc --noEmit > .samvil/build.log 2>&1 && "
            "npm run build >> .samvil/build.log 2>&1"
        ),
        "build_log_path": ".samvil/build.log",
        "version_check_keys": ["phaser", "vite", "typescript"],
        "env_vars_needed": [],
        "status": "stable",
    },
    "expo": {
        "label": "Expo + React Native (mobile)",
        "category": "mobile",
        "matrix_key": "expo-mobile",
        "cli_command_template": (
            "npx create-expo-app@latest <seed.name> --template tabs"
        ),
        "post_install_steps": [
            "mkdir -p components lib assets",
            "create lib/store.ts (Zustand skeleton)",
            "create lib/utils.ts",
            "update app.json (name, slug, scheme)",
            "update tsconfig.json (paths, strict)",
            "install native modules per blueprint (camera/location/etc.)",
        ],
        "sanity_checks": [
            {"path": "package.json", "required": True},
            {"path": "app/_layout.tsx", "required": True},
            {"path": "app.json", "required": True},
        ],
        "build_command": (
            "npx expo export --platform web > .samvil/build.log 2>&1"
        ),
        "build_log_path": ".samvil/build.log",
        "version_check_keys": ["expo", "react-native", "expo-router"],
        "env_vars_needed": [],
        "status": "stable",
    },
    "python-script": {
        "label": "Python automation (--dry-run)",
        "category": "automation",
        "matrix_key": "python-script",
        "cli_command_template": (
            "mkdir -p <seed.name>/{src,fixtures/input,fixtures/expected,tests,.samvil} && "
            "cd <seed.name> && python3 -m venv .venv"
        ),
        "post_install_steps": [
            "create src/main.py (argparse + --dry-run)",
            "create src/processor.py (Processor with _run_dry/_run_live)",
            "create src/config.py (env loader)",
            "create requirements.txt (pinned)",
            "create tests/test_dry_run.py",
            "create .env.example with externalized model IDs (v3-025)",
        ],
        "sanity_checks": [
            {"path": "src/main.py", "required": True},
            {"path": "src/processor.py", "required": True},
            {"path": "src/config.py", "required": True},
            {"path": "requirements.txt", "required": True},
            {"path": ".venv", "required": True},
        ],
        "build_command": (
            "source .venv/bin/activate && "
            "python -m py_compile src/main.py src/processor.py src/config.py "
            "> .samvil/build.log 2>&1 && "
            "pip install -r requirements.txt > .samvil/deps-install.log 2>&1"
        ),
        "build_log_path": ".samvil/build.log",
        "version_check_keys": [],  # Python uses requirements.txt, not package.json
        "env_vars_needed": ["API_KEY", "API_BASE_URL"],
        "status": "stable",
    },
    "node-script": {
        "label": "Node automation (--dry-run)",
        "category": "automation",
        "matrix_key": "node-script",
        "cli_command_template": (
            "mkdir -p <seed.name>/{src,fixtures/input,fixtures/expected,tests,.samvil} && "
            "cd <seed.name> && npm init -y && "
            "npm install -D typescript @types/node tsx && "
            "npx tsc --init"
        ),
        "post_install_steps": [
            "update tsconfig.json (ES2022, commonjs, strict)",
            "create src/main.ts (parseArgs + --dry-run)",
            "create src/processor.ts + src/config.ts",
            "create tests/test_dry_run.ts",
            "update package.json scripts (start/dry-run/build/test)",
            "create .env.example with externalized model IDs (v3-025)",
        ],
        "sanity_checks": [
            {"path": "package.json", "required": True},
            {"path": "tsconfig.json", "required": True},
            {"path": "src/main.ts", "required": True},
        ],
        "build_command": (
            "npx tsc --noEmit > .samvil/build.log 2>&1 && "
            "npm ls >> .samvil/build.log 2>&1"
        ),
        "build_log_path": ".samvil/build.log",
        "version_check_keys": ["typescript", "tsx"],
        "env_vars_needed": ["API_KEY", "API_BASE_URL"],
        "status": "stable",
    },
    "cc-skill": {
        "label": "Claude Code skill",
        "category": "automation",
        "matrix_key": "cc-skill",
        "cli_command_template": (
            "mkdir -p <seed.name>/.samvil"
        ),
        "post_install_steps": [
            "create SKILL.md (frontmatter + process from seed)",
        ],
        "sanity_checks": [
            {"path": "SKILL.md", "required": True},
        ],
        "build_command": "ls SKILL.md > .samvil/build.log 2>&1",
        "build_log_path": ".samvil/build.log",
        "version_check_keys": [],
        "env_vars_needed": [],
        "status": "stable",
    },
    # Planned-but-not-implemented frameworks. Returned with status="planned"
    # and a fallback recommendation. The skill prints the planned message
    # and falls back to nextjs.
    "nuxt": {
        "label": "Nuxt 3 (planned)",
        "category": "web",
        "matrix_key": "nuxt_planned",
        "cli_command_template": "npx nuxi@latest init <seed.name>",
        "post_install_steps": [],
        "sanity_checks": [],
        "build_command": "npm run build > .samvil/build.log 2>&1",
        "build_log_path": ".samvil/build.log",
        "version_check_keys": [],
        "env_vars_needed": [],
        "status": "planned",
        "fallback_framework": "nextjs",
    },
    "sveltekit": {
        "label": "SvelteKit (planned)",
        "category": "web",
        "matrix_key": "sveltekit_planned",
        "cli_command_template": "npx sv create <seed.name>",
        "post_install_steps": [],
        "sanity_checks": [],
        "build_command": "npm run build > .samvil/build.log 2>&1",
        "build_log_path": ".samvil/build.log",
        "version_check_keys": [],
        "env_vars_needed": [],
        "status": "planned",
        "fallback_framework": "nextjs",
    },
}


# Default framework when seed.tech_stack.framework is missing or empty.
DEFAULT_FRAMEWORK = "nextjs"


# Solution-type → recommended framework when seed itself doesn't pin one.
# Mirrors the "기본값: nextjs" comment in the legacy skill but extends to
# the v2 universal-builder solution_types.
_SOLUTION_TYPE_DEFAULT_FRAMEWORK: dict[str, str] = {
    "web-app": "nextjs",
    "dashboard": "nextjs",
    "game": "phaser",
    "mobile-app": "expo",
    "automation": "python-script",
}


# ── Existing-project detection ─────────────────────────────────────


def detect_existing_project(project_path: str | Path) -> dict[str, Any]:
    """Detect whether a project directory already has a scaffold.

    Looks for `package.json` (web/automation/game) or `requirements.txt`
    (Python automation). The legacy skill has a "기존 프로젝트 감지" Step
    0 that skips the full scaffold and goes straight to incremental
    install.
    """
    root = Path(project_path)
    package_json = root / "package.json"
    requirements_txt = root / "requirements.txt"
    skill_md = root / "SKILL.md"

    if package_json.exists():
        signal = "package.json"
    elif requirements_txt.exists():
        signal = "requirements.txt"
    elif skill_md.exists() and root.name and (root / ".samvil").exists():
        # cc-skill projects are detected by SKILL.md + .samvil dir
        signal = "SKILL.md"
    else:
        signal = None

    return {
        "exists": signal is not None,
        "signal": signal,
        "project_path": str(root),
        "next_action": (
            "skip full scaffold; run incremental dependency install only"
            if signal
            else "run full scaffold from CLI"
        ),
    }


# ── Sanity-check evaluation ────────────────────────────────────────


def evaluate_sanity_checks(
    project_path: str | Path,
    sanity_checks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run the post-scaffold Phase A.6 sanity checks against a directory.

    Each check entry is one of:
      - `{"path": "<rel>", "required": True}` — file/dir must exist
      - `{"path": "<rel>", "must_contain": "<substring>"}` — file must
        exist AND contain the substring (used for the Tailwind v3 vs v4
        overwrite check)

    Returns:
        {
          "all_passed": bool,
          "checks": [{name, passed, reason}],
          "failures": [<check entries that failed>],
        }
    """
    root = Path(project_path)
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for check in sanity_checks:
        path = root / check["path"]
        check_id = check["path"]
        if "must_contain" in check:
            check_id = f"{check['path']} contains {check['must_contain']!r}"
            if not path.exists():
                ok, reason = False, "file missing"
            else:
                try:
                    body = path.read_text(encoding="utf-8")
                except OSError as e:
                    ok, reason = False, f"read failed: {e}"
                else:
                    if check["must_contain"] in body:
                        ok, reason = True, "substring present"
                    else:
                        ok, reason = (
                            False,
                            f"substring {check['must_contain']!r} missing",
                        )
        else:
            ok = path.exists()
            reason = "exists" if ok else "missing"

        entry = {"name": check_id, "passed": ok, "reason": reason}
        results.append(entry)
        if not ok:
            failures.append({**check, **entry})

    return {
        "all_passed": not failures,
        "checks": results,
        "failures": failures,
    }


# ── Aggregator ─────────────────────────────────────────────────────


@dataclass
class ScaffoldTargetReport:
    """Aggregated scaffold-readiness view the thin skill renders from."""

    schema_version: str = "1.0"
    project_path: str = ""
    framework: str = ""  # resolved framework name (key in SCAFFOLD_CATALOG)
    framework_source: str = ""  # "seed" | "solution_type_default" | "default"
    label: str = ""
    category: str = ""
    status: str = ""  # "stable" | "planned"
    fallback_framework: str | None = None
    cli_command: str = ""  # template with <seed.name> substituted
    post_install_steps: list[str] = field(default_factory=list)
    sanity_checks: list[dict[str, Any]] = field(default_factory=list)
    build_command: str = ""
    build_log_path: str = ""
    version_pins: dict[str, str] = field(default_factory=dict)
    env_vars_needed: list[str] = field(default_factory=list)
    existing_project: dict[str, Any] = field(default_factory=dict)
    sanity_result: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_path": self.project_path,
            "framework": self.framework,
            "framework_source": self.framework_source,
            "label": self.label,
            "category": self.category,
            "status": self.status,
            "fallback_framework": self.fallback_framework,
            "cli_command": self.cli_command,
            "post_install_steps": self.post_install_steps,
            "sanity_checks": self.sanity_checks,
            "build_command": self.build_command,
            "build_log_path": self.build_log_path,
            "version_pins": self.version_pins,
            "env_vars_needed": self.env_vars_needed,
            "existing_project": self.existing_project,
            "sanity_result": self.sanity_result,
            "notes": self.notes,
            "blockers": self.blockers,
        }


def _resolve_framework(
    framework_arg: str | None,
    seed: dict[str, Any],
) -> tuple[str, str]:
    """Pick the framework to scaffold + tag where it came from.

    Precedence:
      1. Caller-provided `framework` argument.
      2. `seed.tech_stack.framework`.
      3. Solution-type default (`solution_type` → mapping above).
      4. Hard default `nextjs`.

    Returns (framework_name, source_tag).
    """
    if framework_arg:
        return framework_arg, "argument"

    tech_stack = seed.get("tech_stack") or {}
    if isinstance(tech_stack, dict):
        seed_framework = tech_stack.get("framework")
        if seed_framework:
            return str(seed_framework), "seed"

    solution_type = str(seed.get("solution_type") or "")
    if solution_type in _SOLUTION_TYPE_DEFAULT_FRAMEWORK:
        return _SOLUTION_TYPE_DEFAULT_FRAMEWORK[solution_type], "solution_type_default"

    return DEFAULT_FRAMEWORK, "default"


def _substitute_seed_name(template: str, seed_name: str) -> str:
    """Substitute `<seed.name>` placeholders. No-op if name is empty."""
    if not seed_name:
        return template
    return template.replace("<seed.name>", seed_name)


def _extract_version_pins(
    matrix_entry: dict[str, Any],
    version_check_keys: list[str],
) -> dict[str, Any]:
    """Pull the pinned versions the skill must verify post-install.

    The matrix uses underscore keys (`react_dom`, `tailwindcss_animate`)
    while npm uses dashed names (`react-dom`, `tailwindcss-animate`).
    `version_check_keys` is the npm-form list; we translate.
    """
    if not matrix_entry:
        return {}

    # Build a value-indexed lookup so we can find e.g. "next@14.2.35" stored
    # under the `framework` field instead of a `next` key. The matrix uses
    # mixed conventions: some entries name the package directly (`react`,
    # `react_dom`, `tailwindcss`) while others stash the headline framework
    # version under `framework` (`next@14.2.35`, `vite@5.4.21`).
    by_pkg_name: dict[str, str] = {}
    for value in matrix_entry.values():
        if not isinstance(value, str) or "@" not in value:
            continue
        # "next@14.2.35" → pkg "next"; "@tailwindcss/vite@4.2.2" → "@tailwindcss/vite"
        pkg, _, _ver = value.rpartition("@")
        if pkg:
            by_pkg_name[pkg] = value

    pins: dict[str, Any] = {}
    for npm_name in version_check_keys:
        # 1) Direct value lookup ("next" → "next@14.2.35" via reverse index).
        if npm_name in by_pkg_name:
            pins[npm_name] = by_pkg_name[npm_name]
            continue
        # 2) Underscore-key lookup ("react-dom" → matrix key "react_dom").
        matrix_key = npm_name.replace("-", "_").replace("@", "").replace("/", "_")
        # Special case: scoped `@tailwindcss/vite` is matrix key `tailwindcss_vite`.
        if matrix_key.startswith("tailwindcss_") and "@" in npm_name:
            matrix_key = "tailwindcss_vite"
        value = matrix_entry.get(matrix_key) or matrix_entry.get(npm_name)
        if value:
            pins[npm_name] = value
    return pins


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def evaluate_scaffold_target(
    project_path: str | Path,
    *,
    framework: str | None = None,
    seed: dict[str, Any] | None = None,
    run_sanity_checks: bool = False,
) -> dict[str, Any]:
    """Aggregate every fact the samvil-scaffold skill needs in one call.

    Args:
        project_path: Directory the project will be (or has been)
            scaffolded into. The directory does not need to exist yet
            for the catalog lookup; only the existing-project /
            sanity-check branches read from it.
        framework: Override the seed's framework choice (e.g. for
            re-scaffolding with a different stack). When omitted, the
            seed at `<project_path>/project.seed.json` wins, then the
            `solution_type` default, then `nextjs`.
        seed: Optional pre-loaded seed dict. Falls back to reading
            `<project_path>/project.seed.json`.
        run_sanity_checks: When True, also evaluate the per-framework
            sanity checks against the existing project tree. Skill
            calls this from Phase A.6.

    Returns:
        Dict shaped per `ScaffoldTargetReport.to_dict()`.

    INV-5 / P8: never raises; missing seed / missing matrix / unknown
    framework all surface as `notes` / `blockers`.
    """
    root = Path(project_path)

    if seed is None:
        seed = _read_json(root / "project.seed.json") or {}

    framework_used, source = _resolve_framework(framework, seed)

    notes: list[str] = []
    blockers: list[str] = []

    if framework_used not in SCAFFOLD_CATALOG:
        # Unknown framework — fall through to the default catalog so the
        # skill can still render *something* and surface the mismatch.
        notes.append(
            f"unknown framework {framework_used!r}; falling back to {DEFAULT_FRAMEWORK!r}"
        )
        framework_used = DEFAULT_FRAMEWORK
        source = "default"

    catalog_entry = SCAFFOLD_CATALOG[framework_used]
    matrix = _load_dependency_matrix()
    matrix_entry = matrix.get(catalog_entry["matrix_key"]) or {}
    if not matrix_entry:
        notes.append(
            f"dependency-matrix.json missing entry {catalog_entry['matrix_key']!r}; "
            "version pins unavailable"
        )

    if catalog_entry.get("status") == "planned":
        fallback = catalog_entry.get("fallback_framework", DEFAULT_FRAMEWORK)
        blockers.append(
            f"{framework_used} scaffold is planned but not yet implemented; "
            f"skill should fall back to {fallback}"
        )

    seed_name = str(seed.get("name") or "")
    cli_command = _substitute_seed_name(
        catalog_entry["cli_command_template"], seed_name
    )
    if not seed_name:
        notes.append("seed.name missing; cli_command still has <seed.name> placeholder")

    version_pins = _extract_version_pins(
        matrix_entry, catalog_entry.get("version_check_keys", [])
    )

    existing = detect_existing_project(root) if root.exists() else {
        "exists": False,
        "signal": None,
        "project_path": str(root),
        "next_action": "run full scaffold from CLI",
    }

    sanity_result: dict[str, Any] | None = None
    if run_sanity_checks and root.exists():
        sanity_result = evaluate_sanity_checks(
            root, catalog_entry.get("sanity_checks", [])
        )
        if not sanity_result["all_passed"]:
            blockers.append(
                f"sanity-check failures: "
                + ", ".join(f["name"] for f in sanity_result["failures"])
            )

    report = ScaffoldTargetReport(
        project_path=str(root),
        framework=framework_used,
        framework_source=source,
        label=catalog_entry["label"],
        category=catalog_entry["category"],
        status=catalog_entry.get("status", "stable"),
        fallback_framework=catalog_entry.get("fallback_framework"),
        cli_command=cli_command,
        post_install_steps=list(catalog_entry.get("post_install_steps", [])),
        sanity_checks=list(catalog_entry.get("sanity_checks", [])),
        build_command=catalog_entry.get("build_command", ""),
        build_log_path=catalog_entry.get("build_log_path", ""),
        version_pins=version_pins,
        env_vars_needed=list(catalog_entry.get("env_vars_needed", [])),
        existing_project=existing,
        sanity_result=sanity_result,
        notes=notes,
        blockers=blockers,
    )
    return report.to_dict()
