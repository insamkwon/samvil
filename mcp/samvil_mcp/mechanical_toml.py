"""mechanical.toml contract (v4.26.0 — G4.2).

Captures the deterministic, machine-runnable commands SAMVIL invokes for
a project: build / test / lint / typecheck / dev-server / deploy. Before
v4.26, these commands were embedded as prose inside SKILL.md (e.g. "run
``npm run build``"). That made external tools (CI, other AI coding
agents, scripts) blind — they couldn't discover SAMVIL's contract for
the project.

Format: TOML at ``<project_root>/.samvil/mechanical.toml``. Lives next
to events.jsonl / state.json. Optional — when absent, samvil-build/qa
fall back to their solution_type defaults (web-app → npm run build,
automation → python -m py_compile, etc.).

Pattern adapted from Ouroboros's `.ouroboros/mechanical.toml` — Stage 1
of their evaluation pipeline reads the toml verbatim with no hardcoded
language presets. We add SAMVIL-specific fields (solution_type,
dev_server) but keep the same "single source of truth for build
commands" discipline.

Aligns with INV-1 (file SSOT) + INV-5 (Graceful Degradation).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Python 3.11+ has tomllib; fall back to tomli for 3.10
if sys.version_info >= (3, 11):
    import tomllib as _toml_reader  # type: ignore[import-not-found]
else:  # pragma: no cover
    try:
        import tomli as _toml_reader  # type: ignore[import-not-found]
    except ImportError:
        _toml_reader = None  # type: ignore[assignment]

MECHANICAL_FILENAME = "mechanical.toml"
SAMVIL_DIR = ".samvil"

# Fields the writer / validator knows about. Extra fields are preserved
# on round-trip but not validated.
KNOWN_FIELDS = frozenset({
    "build",
    "test",
    "lint",
    "typecheck",
    "dev_server",
    "deploy",
    "format",
    "coverage",
    "solution_type",
    "framework",
})


def _toml_path(project_root: str | Path) -> Path:
    return Path(project_root) / SAMVIL_DIR / MECHANICAL_FILENAME


def read_mechanical_toml(project_root: str | Path) -> dict:
    """Parse the mechanical.toml file if it exists.

    Returns:
        {
            "ok": bool,
            "exists": bool,
            "commands": {field: str, ...},  # only KNOWN_FIELDS that are present
            "extra": {field: any},  # anything outside KNOWN_FIELDS
            "warnings": [str, ...],  # unknown fields, empty commands, etc.
            "path": "...",
        }

    Best-effort: parse errors return ok=False with the error message
    rather than raising. The caller decides whether to fall back to
    the solution_type defaults.
    """
    path = _toml_path(project_root)
    result: dict = {
        "ok": True,
        "exists": path.exists(),
        "commands": {},
        "extra": {},
        "warnings": [],
        "path": str(path),
    }
    if not path.exists():
        return result
    if _toml_reader is None:  # pragma: no cover
        return {**result, "ok": False, "error": "tomllib/tomli not available"}
    try:
        data = _toml_reader.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {**result, "ok": False, "error": f"{type(exc).__name__}: {exc}"}

    if not isinstance(data, dict):
        return {**result, "ok": False, "error": "toml root is not a table"}

    for key, value in data.items():
        if key in KNOWN_FIELDS:
            if isinstance(value, str):
                stripped = value.strip()
                if stripped:
                    result["commands"][key] = stripped
                else:
                    result["warnings"].append(f"{key}: empty string")
            else:
                result["warnings"].append(
                    f"{key}: expected string, got {type(value).__name__}"
                )
        else:
            result["extra"][key] = value
            result["warnings"].append(f"unknown field: {key}")
    return result


def render_default_toml(
    solution_type: str,
    framework: str = "",
) -> str:
    """Render a starting-point mechanical.toml string for a solution type.

    The output is meant to be written verbatim into a fresh project's
    `.samvil/mechanical.toml`. Users / samvil-scaffold can then edit
    individual lines without losing the contract.

    Supported solution_types match references/seed-schema.json enum:
        web-app / automation / game / mobile-app / dashboard.
    """
    common_header = (
        "# SAMVIL mechanical contract — auto-generated, edit freely.\n"
        "# Each entry is a single shell command that SAMVIL runs for this\n"
        "# project. samvil-build / samvil-qa read these verbatim. Missing\n"
        "# entries fall back to the solution_type defaults.\n"
        f'solution_type = "{solution_type}"\n'
    )
    if framework:
        common_header += f'framework = "{framework}"\n'
    common_header += "\n"

    presets = {
        "web-app": (
            'build = "npm run build"\n'
            'test = ""  # add when test framework is installed\n'
            'lint = "npx eslint . --quiet"\n'
            'typecheck = "npx tsc --noEmit"\n'
            'dev_server = "npm run dev"\n'
            'format = "npx prettier --write ."\n'
            'deploy = ""  # set after first deploy run\n'
        ),
        "automation": (
            'build = ""  # python is no-build\n'
            'test = "python -m pytest"\n'
            'lint = "python -m ruff check ."\n'
            'typecheck = "python -m mypy ."\n'
            'dev_server = ""  # automations are scripts, no server\n'
            'format = "python -m ruff format ."\n'
            'deploy = ""  # set after first deploy run\n'
        ),
        "game": (
            'build = "npm run build"\n'
            'test = ""  # phaser games typically lack a test suite\n'
            'lint = "npx eslint . --quiet"\n'
            'typecheck = "npx tsc --noEmit"\n'
            'dev_server = "npm run dev"\n'
            'format = "npx prettier --write ."\n'
            'deploy = ""  # set after first deploy run\n'
        ),
        "mobile-app": (
            'build = "npx expo export --platform web"\n'
            'test = ""  # add when test framework is installed\n'
            'lint = "npx eslint . --quiet"\n'
            'typecheck = "npx tsc --noEmit"\n'
            'dev_server = "npx expo start"\n'
            'format = "npx prettier --write ."\n'
            'deploy = ""  # eas submit — set after first deploy\n'
        ),
        "dashboard": (
            'build = "npm run build"\n'
            'test = ""\n'
            'lint = "npx eslint . --quiet"\n'
            'typecheck = "npx tsc --noEmit"\n'
            'dev_server = "npm run dev"\n'
            'format = "npx prettier --write ."\n'
            'deploy = ""\n'
        ),
    }
    body = presets.get(solution_type)
    if body is None:
        body = (
            f'# Unknown solution_type: {solution_type}\n'
            f'# Fill these in manually:\n'
            f'build = ""\n'
            f'test = ""\n'
            f'lint = ""\n'
            f'typecheck = ""\n'
            f'dev_server = ""\n'
            f'format = ""\n'
            f'deploy = ""\n'
        )
    return common_header + body


def write_default_toml(
    project_root: str | Path,
    solution_type: str,
    framework: str = "",
    overwrite: bool = False,
) -> dict:
    """Write a fresh default mechanical.toml. Returns ``{ok, path, wrote}``.

    By default, refuses to overwrite an existing file (returns
    wrote=False and ok=True). Pass ``overwrite=True`` to force.
    """
    path = _toml_path(project_root)
    if path.exists() and not overwrite:
        return {"ok": True, "wrote": False, "path": str(path),
                "note": "file exists; not overwritten (overwrite=False)"}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = render_default_toml(solution_type=solution_type, framework=framework)
        path.write_text(content, encoding="utf-8")
        return {"ok": True, "wrote": True, "path": str(path)}
    except (OSError, PermissionError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "path": str(path)}


def resolve_command(
    project_root: str | Path,
    field: str,
    fallback: str = "",
) -> dict:
    """Look up a single command in mechanical.toml with fallback.

    Returns ``{ok, command, source, path}`` where source is
    ``"toml"`` (read from file), ``"fallback"`` (file missing or field
    empty), or ``"none"`` (no command at all — caller must handle).

    Used by samvil-build / samvil-qa: pass field="build" and
    fallback="npm run build", get the right command for this project.
    """
    if field not in KNOWN_FIELDS:
        return {"ok": False, "error": f"unknown field: {field}", "source": "none"}

    toml = read_mechanical_toml(project_root)
    if not toml["ok"]:
        # Parse error — fall back conservatively
        if fallback:
            return {"ok": True, "command": fallback, "source": "fallback",
                    "note": f"toml unreadable: {toml.get('error', 'unknown')}"}
        return {"ok": False, "error": toml.get("error", "toml unreadable"),
                "source": "none"}

    if not toml["exists"]:
        if fallback:
            return {"ok": True, "command": fallback, "source": "fallback"}
        return {"ok": True, "command": "", "source": "none",
                "note": "no mechanical.toml and no fallback"}

    cmd = toml["commands"].get(field, "")
    if cmd:
        return {"ok": True, "command": cmd, "source": "toml", "path": toml["path"]}
    if fallback:
        return {"ok": True, "command": fallback, "source": "fallback",
                "note": f"field '{field}' empty in toml; using fallback"}
    return {"ok": True, "command": "", "source": "none",
            "note": f"field '{field}' empty in toml and no fallback"}
