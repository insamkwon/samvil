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
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_SCHEMA_VERSION = "1.1"


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
    summary_generated_by: str = ""
    summary_generated_at: str = ""
    files: list[str] = field(default_factory=list)
    convention_tags: list[str] = field(default_factory=list)
    confidence_tags: list[str] = field(default_factory=list)
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
    """Walk src/ and treat direct children as modules.

    Direct subdirectories become named modules. Root-level code files directly
    under ``src/`` become a synthetic ``src`` module so small Vite/React-style
    projects do not produce an empty manifest.

    For projects without src/ this returns []. Caller decides whether to fall
    back to root-level scan (out of scope for v3.3 — we assume src/).

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

    root_files = sorted(
        str(path.relative_to(root))
        for path in src.iterdir()
        if path.is_file() and path.suffix in _CODE_EXTS
    )
    if root_files:
        modules.append(
            ModuleEntry(
                name="src",
                path="src",
                public_api=extract_public_api(src),
                files=root_files,
                last_updated=now,
            )
        )

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
_RE_JS_IMPORT = re.compile(
    r"(?:import|export)\s+(?:[^'\";]*?\s+from\s*)?['\"]([^'\"]+)['\"]"
)
_RE_JS_REQUIRE = re.compile(r"require\(\s*['\"]([^'\"]+)['\"]\s*\)")
_RE_JS_DYNAMIC_IMPORT = re.compile(r"import\(\s*['\"]([^'\"]+)['\"]\s*\)")
_RE_PY_FROM_IMPORT = re.compile(r"^\s*from\s+([.\w]+)\s+import\s+", re.M)
_RE_PY_IMPORT = re.compile(r"^\s*import\s+([\w.]+)", re.M)


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


def infer_module_dependencies(
    project_root: Path | str,
    module: ModuleEntry,
    modules: list[ModuleEntry],
) -> list[str]:
    """Infer internal module dependencies from TS/JS/Python import strings.

    This is intentionally regex-based and conservative. It resolves common
    relative imports plus ``@/`` and ``src/`` aliases into ModuleEntry names.
    External package imports are ignored.
    """
    root = Path(project_root)
    deps: set[str] = set()
    for rel_file in module.files:
        path = root / rel_file
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for spec in _import_specs(text, path.suffix):
            target = _resolve_import_target(root, path, spec)
            if target is None:
                continue
            dep = _module_for_path(target, modules)
            if dep and dep != module.name:
                deps.add(dep)
    return sorted(deps)


def _import_specs(text: str, suffix: str) -> list[str]:
    if suffix in {".ts", ".tsx", ".js", ".jsx"}:
        specs = [m.group(1) for m in _RE_JS_IMPORT.finditer(text)]
        specs.extend(m.group(1) for m in _RE_JS_REQUIRE.finditer(text))
        specs.extend(m.group(1) for m in _RE_JS_DYNAMIC_IMPORT.finditer(text))
        return specs
    if suffix == ".py":
        specs = [m.group(1) for m in _RE_PY_FROM_IMPORT.finditer(text)]
        specs.extend(m.group(1) for m in _RE_PY_IMPORT.finditer(text))
        return specs
    return []


def _resolve_import_target(root: Path, importer: Path, spec: str) -> Path | None:
    if spec.startswith(("./", "../")):
        return (importer.parent / spec).resolve()
    if spec.startswith("."):
        dot_count = len(spec) - len(spec.lstrip("."))
        remainder = spec[dot_count:].replace(".", "/")
        base = importer.parent
        for _ in range(max(dot_count - 1, 0)):
            base = base.parent
        return base / remainder if remainder else base
    if spec.startswith("@/"):
        return root / "src" / spec[2:]
    if spec.startswith("src/"):
        return root / spec

    first = spec.split(".", 1)[0].split("/", 1)[0]
    if first:
        candidate = root / "src" / first
        if candidate.exists():
            remainder = spec[len(first):].lstrip("./")
            return candidate / remainder if remainder else candidate
    return None


def _module_for_path(target: Path, modules: list[ModuleEntry]) -> str | None:
    target_text = str(target)
    ordered = sorted(modules, key=lambda m: len(Path(m.path).parts), reverse=True)
    for module in ordered:
        module_path = str((Path(module.path)).as_posix())
        # target may be absolute, so compare against both absolute suffix and
        # relative path fragments. This avoids resolving the project root here.
        if f"/{module_path}/" in target_text or target_text.endswith(f"/{module_path}"):
            return module.name
    return None


def summarize_module(module: ModuleEntry, *, generated_at: str) -> ModuleEntry:
    """Attach a deterministic heuristic summary and confidence metadata."""
    pieces = [f"Owns {len(module.files)} code file{'s' if len(module.files) != 1 else ''}."]
    if module.public_api:
        pieces.append(f"Exports {', '.join(module.public_api[:5])}.")
    if module.depends_on:
        pieces.append(f"Depends on {', '.join(module.depends_on)}.")
    else:
        pieces.append("No internal module dependencies detected.")
    tags = sorted(set(module.confidence_tags + ["imports:regex", "summary:heuristic"]))
    return replace(
        module,
        summary=" ".join(pieces),
        summary_generated_by="manifest:heuristic-v1",
        summary_generated_at=generated_at,
        confidence_tags=tags,
    )


_CONVENTION_RULES: tuple[tuple[tuple[str, ...], str, str, str], ...] = (
    # (names, key, value, kind) — kind ∈ {"file", "dir"}
    (("tsconfig.json",), "language", "typescript", "file"),
    (("next.config.js", "next.config.mjs", "next.config.ts"), "framework", "next", "file"),
    (("vite.config.js", "vite.config.ts"), "framework", "vite", "file"),
    (("astro.config.mjs", "astro.config.ts"), "framework", "astro", "file"),
    (("tailwind.config.js", "tailwind.config.mjs", "tailwind.config.ts"), "css", "tailwind", "file"),
    ((".eslintrc", ".eslintrc.json", ".eslintrc.js", "eslint.config.js"), "linter", "eslint", "file"),
    (("supabase",), "auth_db", "supabase", "dir"),
    (("prisma",), "orm", "prisma", "dir"),
)


def detect_conventions(project_root: Path | str) -> dict[str, str]:
    """Inspect well-known config files/directories to infer project conventions.

    Best-effort and intentionally narrow. Phase 2's Pattern Registry will
    expand this with content-aware rules. **First matching rule wins** on
    key conflicts (e.g., if both next.config.* and vite.config.* exist,
    `framework` resolves to `next` because the next rule appears first).

    File vs directory distinction is enforced: a *file* named `supabase`
    or `prisma` does NOT trigger the directory-based rules.
    """
    root = Path(project_root)
    out: dict[str, str] = {}
    for patterns, key, value, kind in _CONVENTION_RULES:
        if key in out:
            continue  # first matching rule wins on key conflict
        for pat in patterns:
            candidate = root / pat
            if kind == "dir":
                hit = candidate.is_dir()
            else:
                hit = candidate.is_file()
            if hit:
                out[key] = value
                break
    return out


def build_manifest(project_root: Path | str, *, project_name: str) -> Manifest:
    """End-to-end: walk filesystem, detect conventions, return Manifest.

    Does NOT write to disk. Caller (orchestrator / MCP tool) decides when
    to persist.

    Note: ``project_root`` is recorded as ``str(Path(project_root))`` (no
    ``.resolve()``) so the manifest preserves the exact path the caller
    supplied. macOS in particular resolves ``/var/...`` symlinks to
    ``/private/var/...`` which would surprise callers using temp dirs;
    the caller can ``Path(...).resolve()`` themselves if needed.
    """
    root = Path(project_root)
    generated_at = _now_iso()
    modules = discover_modules(root)
    modules_with_deps = [
        replace(
            module,
            depends_on=infer_module_dependencies(root, module, modules),
            confidence_tags=sorted(set(module.confidence_tags + ["imports:regex"])),
        )
        for module in modules
    ]
    modules = [
        summarize_module(module, generated_at=generated_at)
        for module in modules_with_deps
    ]
    conventions = detect_conventions(root)
    public_apis = {m.name: list(m.public_api) for m in modules if m.public_api}

    return Manifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        project_name=project_name,
        project_root=str(root),
        generated_at=generated_at,
        modules=modules,
        conventions=conventions,
        public_apis=public_apis,
    )


def render_for_context(
    manifest: Manifest,
    *,
    focus: list[str] | None = None,
    max_modules: int = 30,
) -> str:
    """Compress a Manifest into a context-budget-friendly markdown summary.

    Args:
        manifest: the manifest to render.
        focus: if provided, only include modules whose name is in this list.
        max_modules: hard cap. If exceeded, top-N by file count are kept and
            the rest are summarized as "and N more".

    The output is markdown intended for direct injection into an AI session.
    """
    relevant = manifest.modules
    if focus:
        focus_set = set(focus)
        relevant = [m for m in relevant if m.name in focus_set]

    truncated_count = 0
    if len(relevant) > max_modules:
        truncated_count = len(relevant) - max_modules
        relevant = sorted(relevant, key=lambda m: -len(m.files))[:max_modules]

    lines: list[str] = [
        f"# {manifest.project_name}",
        f"_generated: {manifest.generated_at}_",
        "",
    ]

    if manifest.conventions:
        conv_str = ", ".join(f"{k}={v}" for k, v in sorted(manifest.conventions.items()))
        lines.append(f"**Conventions:** {conv_str}")
        lines.append("")

    lines.append(f"## Modules ({len(relevant)} shown)")
    for m in relevant:
        lines.append(f"### {m.name}")
        lines.append(f"- Path: `{m.path}`")
        if m.public_api:
            api_preview = ", ".join(m.public_api[:8])
            if len(m.public_api) > 8:
                api_preview += f", … (+{len(m.public_api) - 8} more)"
            lines.append(f"- Public API: {api_preview}")
        if m.depends_on:
            lines.append(f"- Depends on: {', '.join(m.depends_on)}")
        if m.summary:
            lines.append(f"- Summary: {m.summary}")
        if m.summary_generated_by:
            lines.append(
                f"- Summary source: {m.summary_generated_by} @ {m.summary_generated_at}"
            )
        if m.convention_tags:
            lines.append(f"- Tags: {', '.join(m.convention_tags)}")
        if m.confidence_tags:
            lines.append(f"- Confidence: {', '.join(m.confidence_tags)}")
        if m.files:
            file_preview = ", ".join(f"`{path}`" for path in m.files[:8])
            if len(m.files) > 8:
                file_preview += f", … (+{len(m.files) - 8} more)"
            lines.append(f"- Files: {file_preview}")
        lines.append("")

    if truncated_count:
        # Use singular/plural correctly to avoid "and 1 more modules" awkwardness.
        word = "module" if truncated_count == 1 else "modules"
        lines.append(
            f"_…and {truncated_count} more {word} (call read_manifest for full list)_"
        )

    return "\n".join(lines)
