# Codebase Manifest Schema (v3.3+)

`.samvil/manifest.json` is an auto-generated description of project structure.
It is loaded at stage entry so an AI agent can see a compressed codebase snapshot
without reading the whole repository.

## Top-Level Shape

```json
{
  "schema_version": "1.0",
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

Each direct child directory under `src/` becomes one module:

```json
{
  "name": "auth",
  "path": "src/auth",
  "public_api": ["signIn", "signOut"],
  "depends_on": [],
  "summary": "",
  "files": ["src/auth/index.ts", "src/auth/session.ts"],
  "convention_tags": [],
  "last_updated": "2026-04-25T10:00:00Z"
}
```

## Field Semantics

| Field | Source | Notes |
|---|---|---|
| `schema_version` | constant | fixed at `1.0` during v3.3 Phase 1 |
| `project_name` | caller input | human-readable project name |
| `project_root` | caller input | preserved as provided by the caller |
| `generated_at` | manifest generation time | UTC, second precision |
| `modules` | filesystem walk | one entry per direct child directory under `src/` |
| `conventions` | config-file detection | project-level conventions only in Phase 1 |
| `public_apis` | module `public_api` aggregation | keyed by module name |
| `name` | directory name under `src/` | unique within the project |
| `path` | filesystem walk | relative to `project_root` |
| `public_api` | best-effort regex over `index.ts` / `index.tsx` | manual override and AST parsing are Phase 2 work |
| `depends_on` | planned import analysis | empty in Phase 1 |
| `summary` | planned AI-generated summary | empty in Phase 1 |
| `files` | recursive module walk | `.ts`, `.tsx`, `.js`, `.jsx`, `.py` only |
| `convention_tags` | planned module-level pattern detection | empty in Phase 1 |
| `last_updated` | manifest generation time | UTC, second precision |

## Module Discovery

Phase 1 intentionally uses a narrow and deterministic rule:

- if `src/` does not exist, `modules` is empty
- each direct directory under `src/` is a module
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

## Out Of Scope In Phase 1

- root-level module discovery for projects without `src/`
- namespace re-export resolution
- AST-backed public API extraction
- cross-module dependency graph
- module summaries
- module-level convention tags
- brownfield reverse-ADR generation
