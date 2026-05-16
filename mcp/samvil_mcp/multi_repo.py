"""Multi-repo brownfield registry (v4.29.0 — backs samvil-analyze G5.4).

samvil-analyze SKILL (v4.28) described iterating across N brownfield
repos using ``~/.samvil/brownfield-repos.json``. v4.29 ships the real
implementation: registry parser + path validator + iteration helper.

Registry schema:
    [
        {
            "name": "zep-crm",
            "path": "~/dev/zep-crm",
            "role": "backend",            // optional
            "is_default": true,            // optional
            "notes": "운영 SSOT"           // optional
        },
        ...
    ]

Pure functions: load + validate. The iteration helper is a generator
that yields each registered repo's path for samvil-analyze to process
in turn. No MCP / IO side-effects beyond reading the registry file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

REGISTRY_FILENAME = "brownfield-repos.json"


def _default_registry_path() -> Path:
    return Path.home() / ".samvil" / REGISTRY_FILENAME


def load_repo_registry(config_path: str | Path | None = None) -> dict:
    """Load and parse the brownfield repo registry.

    ``config_path`` defaults to ``~/.samvil/brownfield-repos.json``.

    Returns:
        {
            "ok": bool,
            "exists": bool,
            "repos": [{name, path, role?, is_default?, notes?}, ...],
            "default_count": int,
            "warnings": [str, ...],
            "path": "...",
        }

    Best-effort: malformed JSON or wrong types return ok=False with
    error message rather than raising. Each repo entry is normalized
    (``path`` expanded via expanduser, missing optional fields filled
    with None).
    """
    path = Path(config_path) if config_path else _default_registry_path()
    result: dict = {
        "ok": True,
        "exists": path.exists(),
        "repos": [],
        "default_count": 0,
        "warnings": [],
        "path": str(path),
    }
    if not path.exists():
        return result
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, PermissionError) as exc:
        return {**result, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {**result, "ok": False, "error": f"invalid JSON: {exc}"}
    if not isinstance(entries, list):
        return {**result, "ok": False,
                "error": f"registry must be a JSON array, got {type(entries).__name__}"}

    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            result["warnings"].append(f"entry {i}: not a dict, skipped")
            continue
        name = entry.get("name")
        raw_path = entry.get("path")
        if not name or not isinstance(name, str):
            result["warnings"].append(f"entry {i}: missing or invalid 'name', skipped")
            continue
        if not raw_path or not isinstance(raw_path, str):
            result["warnings"].append(f"entry {i} ({name}): missing or invalid 'path', skipped")
            continue
        normalized = {
            "name": name.strip(),
            "path": str(Path(os.path.expanduser(raw_path)).resolve()),
            "role": entry.get("role"),
            "is_default": bool(entry.get("is_default", False)),
            "notes": entry.get("notes"),
        }
        result["repos"].append(normalized)
        if normalized["is_default"]:
            result["default_count"] += 1
    return result


def validate_repo_paths(repos: list[dict]) -> dict:
    """For each repo, verify the path exists and is a git repo.

    Returns:
        {
            "ok": True (always — this is a report, not a gate),
            "checked": int,
            "passed": [{name, path, has_git, has_manifest}, ...],
            "failed": [{name, path, reason}, ...],
        }

    ``has_manifest`` checks for one of: package.json, pyproject.toml,
    go.mod, Cargo.toml, requirements.txt — the same priority list
    samvil-analyze uses for Brownfield Mode manifest detection.
    """
    if not isinstance(repos, list):
        return {"ok": False, "error": "repos must be a list"}

    manifests = ("package.json", "pyproject.toml", "go.mod", "Cargo.toml", "requirements.txt")
    passed: list[dict] = []
    failed: list[dict] = []

    for repo in repos:
        if not isinstance(repo, dict):
            failed.append({"name": "?", "path": "?", "reason": "not a dict"})
            continue
        name = repo.get("name", "?")
        path_str = repo.get("path", "")
        path = Path(path_str) if path_str else None

        if not path or not path.exists():
            failed.append({"name": name, "path": path_str, "reason": "path does not exist"})
            continue
        if not path.is_dir():
            failed.append({"name": name, "path": path_str, "reason": "path is not a directory"})
            continue

        has_git = (path / ".git").exists()
        has_manifest = any((path / m).exists() for m in manifests)
        passed.append({
            "name": name,
            "path": str(path),
            "has_git": has_git,
            "has_manifest": has_manifest,
        })

    return {
        "ok": True,
        "checked": len(repos),
        "passed": passed,
        "failed": failed,
    }


def iterate_brownfield_repos(
    repos: list[dict],
    only_defaults: bool = False,
) -> list[dict]:
    """Return the repos in stable order, optionally filtering to defaults.

    Order: defaults first (in registry order), then non-defaults (in
    registry order). This makes samvil-analyze process the user's
    primary repos first, which is what you almost always want when
    running a quick brownfield analysis on a microservice cluster.

    samvil-analyze SKILL Step 1 uses this to drive the per-repo loop.
    """
    if not isinstance(repos, list):
        return []
    defaults = [r for r in repos if isinstance(r, dict) and r.get("is_default")]
    non_defaults = [r for r in repos if isinstance(r, dict) and not r.get("is_default")]
    if only_defaults:
        return defaults
    return defaults + non_defaults


def parse_inline_paths(paths_csv: str) -> dict:
    """Parse a comma-separated list of repo paths (samvil-analyze prompt path).

    When the user invokes samvil-analyze in multi-repo mode without
    registering ``~/.samvil/brownfield-repos.json``, they can pass a
    comma-separated path list directly. This helper normalizes that
    input into the same repo-dict shape as the registry.

    Returns:
        {
            "ok": True,
            "repos": [{name, path, is_default}, ...],
        }

    Names are derived from the basename of each path.
    """
    if not isinstance(paths_csv, str):
        return {"ok": False, "error": "paths_csv must be a string"}
    parts = [p.strip() for p in paths_csv.split(",") if p.strip()]
    if not parts:
        return {"ok": True, "repos": []}
    repos: list[dict] = []
    for p in parts:
        expanded = str(Path(os.path.expanduser(p)).resolve())
        name = Path(expanded).name or "repo"
        repos.append({
            "name": name,
            "path": expanded,
            "role": None,
            "is_default": True,  # inline input is treated as default
            "notes": "inline",
        })
    return {"ok": True, "repos": repos}
