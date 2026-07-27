"""Resolve SAMVIL runtime roots and reject path escapes before mutation."""

from __future__ import annotations

import os
from pathlib import Path


class RuntimeLayoutError(ValueError):
    """Raised when a runtime path cannot be proven to stay in its owner root."""


def discover_repository_root(
    required_relative_path: str | Path,
    *,
    package_file: str | Path,
    working_directory: str | Path | None = None,
) -> Path:
    """Find the installed plugin root by proving a required repository file exists."""
    required = Path(required_relative_path)
    candidates: list[Path] = []
    configured = os.environ.get("SAMVIL_PLUGIN_ROOT", "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())
    cwd = Path(working_directory or Path.cwd()).expanduser()
    candidates.extend((cwd, *cwd.parents))
    package = Path(package_file).expanduser().resolve(strict=False)
    candidates.extend(package.parents)

    seen: set[Path] = set()
    for candidate in candidates:
        root = candidate.resolve(strict=False)
        if root in seen:
            continue
        seen.add(root)
        target = (root / required).resolve(strict=False)
        try:
            target.relative_to(root)
        except ValueError:
            continue
        if target.is_file() and (root / ".codex-plugin" / "plugin.json").is_file():
            return root
    raise RuntimeLayoutError(f"SAMVIL repository root is unavailable for {required}")


def safe_child_directory(root: str | Path, relative: str | Path, *, label: str) -> Path:
    """Return a lexical child path only when every existing segment is non-symlinked."""
    owner = Path(root).expanduser().resolve(strict=False)
    if owner == Path(owner.anchor):
        raise RuntimeLayoutError(f"unsafe {label} owner root: {owner}")
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise RuntimeLayoutError(f"unsafe {label} path: {relative_path}")
    candidate = owner / relative_path
    cursor = owner
    for part in relative_path.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise RuntimeLayoutError(f"unsafe {label} path: {cursor}")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(owner)
    except ValueError as exc:
        raise RuntimeLayoutError(f"unsafe {label} path: {candidate}") from exc
    return candidate


__all__ = [
    "RuntimeLayoutError",
    "discover_repository_root",
    "safe_child_directory",
]
