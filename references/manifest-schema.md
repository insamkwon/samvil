# Codebase Manifest Schema (v3.3+)

`.samvil/manifest.json` is an auto-generated description of project structure.
It is loaded at stage entry so an AI agent can see a compressed codebase snapshot
without reading the whole repository.

## Top-Level Shape

```json
{
  "schema_version": "1.1",
  "project_name": "todo-app",
  "project_root": "/Users/me/dev/todo-app",
  "generated_at": "2026-04-25T10:00:00Z",
  "modules": [],
  "conventions": {
    "language": "typescript",
    "css": "tailwind"
  },
  "public_apis": {
    "auth": ["signIn", "signOut"]
  }
}
```

## Module Entry

Each direct child directory under `src/` becomes one module. Code files directly
under `src/` become a synthetic `src` module:

```json
{
  "name": "auth",
  "path": "src/auth",
  "public_api": ["signIn", "signOut"],
  "depends_on": ["ui"],
  "summary": "Owns 2 code files. Exports signIn, signOut. Depends on ui.",
  "summary_generated_by": "manifest:heuristic-v1",
  "summary_generated_at": "2026-04-25T10:00:00Z",
  "files": ["src/auth/index.ts", "src/auth/session.ts"],
  "convention_tags": [],
  "confidence_tags": ["imports:regex", "summary:heuristic"],
  "last_updated": "2026-04-25T10:00:00Z"
}
```

## Field Semantics

| Field | Source | Notes |
|---|---|---|
| `schema_version` | constant | `1.1` includes Manifest v2 intelligence fields |
| `project_name` | caller input | human-readable project name |
| `project_root` | caller input | preserved as provided by the caller |
| `generated_at` | manifest generation time | UTC, second precision |
| `modules` | filesystem walk | one entry per direct child directory under `src/` |
| `conventions` | config-file detection | project-level conventions only in Phase 1 |
| `public_apis` | module `public_api` aggregation | keyed by module name |
| `name` | directory name under `src/` | unique within the project |
| `path` | filesystem walk | relative to `project_root` |
| `public_api` | best-effort regex over `index.ts` / `index.tsx` | manual override and AST parsing are Phase 2 work |
| `depends_on` | regex import analysis | internal module names only |
| `summary` | deterministic heuristic summary | generated from files, public API, and dependencies |
| `summary_generated_by` | summary generator id | currently `manifest:heuristic-v1` |
| `summary_generated_at` | manifest generation time | matches `generated_at` |
| `files` | recursive module walk | `.ts`, `.tsx`, `.js`, `.jsx`, `.py` only |
| `convention_tags` | future module-level pattern detection | currently empty |
| `confidence_tags` | source confidence labels | e.g. `imports:regex`, `summary:heuristic` |
| `last_updated` | manifest generation time | UTC, second precision |

## Module Discovery

Phase 1 intentionally uses a narrow and deterministic rule:

- if `src/` does not exist, `modules` is empty
- each direct directory under `src/` is a module
- direct code files under `src/` are grouped into a synthetic `src` module
- nested directories are included as files inside their parent module
- symlinked directories are not followed
- dot-prefixed and generated directories are ignored

Ignored directories include `node_modules`, `.next`, `.nuxt`, `.svelte-kit`,
`.expo`, `.git`, `.turbo`, `dist`, `build`, `coverage`, `target`, `.samvil`,
`__pycache__`, `.venv`, `venv`, `.idea`, and `.vscode`.

## Public API Extraction

Phase 1 reads `index.ts`, falling back to `index.tsx`, and extracts:

- named re-exports such as `export { signIn } from "./session"`
- type re-exports such as `export type { User } from "./types"`
- direct exports such as `export const x = 1`
- direct `async function`, `interface`, `enum`, and `type` exports
- default exports as the literal name `default`

`export * from "./x"` is intentionally out of scope because it requires module
resolution. A future AST-backed extractor should replace this regex pass.

## Conventions

Inferred from well-known config-file presence:

| Key | Source | Value |
|---|---|---|
| `language` | `tsconfig.json` | `typescript` |
| `framework` | `next.config.*` | `next` |
| `framework` | `vite.config.*` | `vite` |
| `framework` | `astro.config.*` | `astro` |
| `css` | `tailwind.config.*` | `tailwind` |
| `linter` | `.eslintrc*`, `eslint.config.js` | `eslint` |
| `auth_db` | `supabase/` directory | `supabase` |
| `orm` | `prisma/` directory | `prisma` |

If multiple framework config files exist, the first matching rule wins.

## Import Graph

Schema `1.1` adds conservative internal dependency detection:

- TypeScript/JavaScript: static `import`, `export ... from`, `require()`, and
  dynamic `import()` string specifiers
- Python: `import x` and `from x import y`
- relative imports such as `../ui/button`
- common aliases such as `@/auth/session`, `src/auth/session`, and bare
  module-root imports like `auth/session`

External packages are ignored. The extractor is regex-based and marks results
with `imports:regex`; it is intended for context shaping, not build enforcement.

## Module Summaries

Each module gets a deterministic summary, `summary_generated_by`, and
`summary_generated_at`. The summary is intentionally heuristic so it can run
inside MCP without an LLM call. AI-generated or manual summaries can be added in
later releases using distinct confidence tags.

## MCP Tools

- `build_and_persist_manifest(project_root, project_name)` builds and writes
  `.samvil/manifest.json`
- `read_manifest(project_root)` returns the manifest dict, `missing`, or
  `corrupted`
- `render_manifest_context(project_root, focus?, max_modules?)` returns a
  compressed markdown summary for AI context
- `refresh_manifest(project_root, project_name)` rebuilds, persists, and renders
  context in one call

## Atomicity And Safety

Manifest writes use a temp file followed by POSIX rename, so readers should not
see half-written JSON.

MCP wrappers reject empty or nonexistent `project_root` values. This prevents
accidental writes to the MCP server's current working directory and avoids
creating unexpected project trees.

## Out Of Scope

- root-level module discovery for projects without `src/`
- namespace re-export resolution
- AST-backed public API extraction
- module-level convention tags beyond confidence metadata
- brownfield reverse-ADR generation
