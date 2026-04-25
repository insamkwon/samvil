"""Codebase Manifest — Layer 4 SSOT for SAMVIL v3.3+.

`.samvil/manifest.json` is an auto-generated description of project structure:
modules, public APIs, dependencies, conventions. Loaded at every stage entry
to give AI a 5K-token snapshot of the codebase regardless of total LOC.

This module is responsible for:
  - The schema (Manifest + ModuleEntry dataclasses)
  - Filesystem walking + module discovery
  - Convention detection (lint config, tsconfig, etc.)
  - Atomic file I/O
  - Rendering compressed context strings for AI sessions

It is NOT responsible for:
  - Deciding when to regenerate (orchestrator does that)
  - Mutating modules (manifest is read-mostly; regenerate to update)
  - Cross-module verification (gates / claim_ledger do that)
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_SCHEMA_VERSION = "1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class ModuleEntry:
    """A single module in the codebase."""

    name: str
    path: str  # relative to project_root
    public_api: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    summary: str = ""
    files: list[str] = field(default_factory=list)
    convention_tags: list[str] = field(default_factory=list)
    last_updated: str = ""


@dataclass(frozen=True)
class Manifest:
    """Top-level manifest. Materialized to .samvil/manifest.json."""

    schema_version: str
    project_name: str
    project_root: str
    generated_at: str
    modules: list[ModuleEntry] = field(default_factory=list)
    conventions: dict[str, str] = field(default_factory=dict)
    public_apis: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "project_name": self.project_name,
            "project_root": self.project_root,
            "generated_at": self.generated_at,
            "modules": [asdict(m) for m in self.modules],
            "conventions": dict(self.conventions),
            "public_apis": {k: list(v) for k, v in self.public_apis.items()},
        }

    @staticmethod
    def from_dict(d: dict) -> Manifest:
        return Manifest(
            schema_version=d["schema_version"],
            project_name=d["project_name"],
            project_root=d["project_root"],
            generated_at=d["generated_at"],
            modules=[ModuleEntry(**m) for m in d.get("modules", [])],
            conventions=dict(d.get("conventions", {})),
            public_apis={k: list(v) for k, v in d.get("public_apis", {}).items()},
        )


def manifest_path(project_root: Path | str) -> Path:
    """Return the canonical .samvil/manifest.json path for a project."""
    root = Path(project_root)
    return root / ".samvil" / "manifest.json"


def write_manifest(manifest: Manifest, project_root: Path | str) -> Path:
    """Atomic write to .samvil/manifest.json.

    Strategy: write to .tmp file, then POSIX rename. The rename is atomic on
    the same filesystem, so readers never see a half-written file.
    """
    target = manifest_path(project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    payload = json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False)
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, target)
    return target


def read_manifest(project_root: Path | str) -> Manifest | None:
    """Read .samvil/manifest.json. Returns None if missing or unreadable."""
    target = manifest_path(project_root)
    if not target.exists():
        return None
    try:
        d = json.loads(target.read_text(encoding="utf-8"))
        return Manifest.from_dict(d)
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


_IGNORE_DIRS = frozenset({
    "node_modules", ".next", ".nuxt", ".svelte-kit", ".expo",
    ".git", ".turbo", "dist", "build", "coverage", "target",
    ".samvil", "__pycache__", ".venv", "venv",
    ".idea", ".vscode",
})

_CODE_EXTS = frozenset({".ts", ".tsx", ".js", ".jsx", ".py"})


def discover_modules(project_root: Path | str) -> list[ModuleEntry]:
    """Walk src/ and treat each direct subdirectory as a module.

    For projects without src/ this returns []. Caller decides whether to
    fall back to root-level scan (out of scope for v3.3 — we assume src/).

    Symlinked directories are not followed (os.walk default).
    Broken symlinks are silently skipped (their is_file() check fails).
    Dot-prefixed directories are skipped (treated like ignore-dirs).
    """
    root = Path(project_root)
    src = root / "src"
    if not src.is_dir():
        return []

    modules: list[ModuleEntry] = []
    now = _now_iso()

    for child in sorted(src.iterdir()):
        if not child.is_dir():
            continue
        if child.name in _IGNORE_DIRS or child.name.startswith("."):
            continue

        files: list[str] = []
        for dirpath, dirnames, filenames in os.walk(child):
            # Prune in-place so we never descend into ignore-dirs at all.
            dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
            for fn in filenames:
                ext = os.path.splitext(fn)[1]
                if ext not in _CODE_EXTS:
                    continue
                full = os.path.join(dirpath, fn)
                files.append(os.path.relpath(full, root))
        files.sort()

        api = extract_public_api(child)
        modules.append(
            ModuleEntry(
                name=child.name,
                path=str(child.relative_to(root)),
                public_api=api,
                files=files,
                last_updated=now,
            )
        )

    return modules


_RE_NAMED_REEXPORT = re.compile(
    r"export\s+(?:type\s+)?\{([^}]+)\}\s*from\s*['\"][^'\"]+['\"]\s*;?"
)
_RE_DIRECT_NAMED_EXPORT = re.compile(
    r"export\s+(?:async\s+)?(?:const|function|class|let|var|interface|enum|type)\s+(\w+)"
)
_RE_DEFAULT_EXPORT = re.compile(r"export\s+default\b")


def extract_public_api(module_dir: Path) -> list[str]:
    """Parse module's index.ts (or index.tsx fallback) to extract exported names.

    Best-effort regex. Catches:
      - export { a, b as c } from './x';
      - export type { Foo } from './types';
      - export const|function|class|let|var|interface|enum|type X
      - export async function fn() {}
      - export default <anything>  → 'default'

    Note: ``export * from './x'`` is intentionally not parsed in Phase 1
    (whole-namespace re-exports require an AST resolver — Phase 2 work).
    Comments are stripped as a best-effort pre-pass; pathological cases
    (comments inside strings, nested block comments) may still leak.
    """
    index = module_dir / "index.ts"
    if not index.exists():
        index = module_dir / "index.tsx"
    if not index.exists():
        return []

    text = index.read_text(encoding="utf-8")

    # Strip line and block comments to avoid phantom names from commented-out code.
    # Best-effort: not a JS lexer, so /* nested */ or comments inside strings may slip.
    # Phase 2 AST parser will replace this entirely.
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)

    names: list[str] = []

    for match in _RE_NAMED_REEXPORT.finditer(text):
        body = match.group(1)
        for piece in body.split(","):
            piece = piece.strip()
            if not piece:
                continue
            # Handle "a as b" → take the alias (the externally visible name)
            if " as " in piece:
                _, alias = piece.split(" as ", 1)
                names.append(alias.strip())
            else:
                names.append(piece)

    for match in _RE_DIRECT_NAMED_EXPORT.finditer(text):
        names.append(match.group(1))

    if _RE_DEFAULT_EXPORT.search(text):
        names.append("default")

    # De-dup while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


_CONVENTION_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    # (file_globs, key, value)
    (("tsconfig.json",), "language", "typescript"),
    (("next.config.js", "next.config.mjs", "next.config.ts"), "framework", "next"),
    (("vite.config.js", "vite.config.ts"), "framework", "vite"),
    (("astro.config.mjs", "astro.config.ts"), "framework", "astro"),
    (("tailwind.config.js", "tailwind.config.mjs", "tailwind.config.ts"), "css", "tailwind"),
    ((".eslintrc", ".eslintrc.json", ".eslintrc.js", "eslint.config.js"), "linter", "eslint"),
    (("supabase",), "auth_db", "supabase"),  # directory match
    (("prisma",), "orm", "prisma"),  # directory match
)


def detect_conventions(project_root: Path | str) -> dict[str, str]:
    """Inspect well-known config files to infer project conventions.

    This is best-effort and intentionally narrow. Phase 2's Pattern Registry
    will expand this with content-aware rules.
    """
    root = Path(project_root)
    out: dict[str, str] = {}
    for patterns, key, value in _CONVENTION_RULES:
        for pat in patterns:
            candidate = root / pat
            if candidate.exists():
                out[key] = value
                break
    return out
