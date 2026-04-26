# SAMVIL SSOT Schema (v3.3+)

> Single canonical reference for the `.samvil/` directory and the
> surrounding 4-layer SSOT structure — the harness's file-based source
> of truth. Consolidates the previous `manifest-schema.md`,
> `decision-log-schema.md`, `orchestrator-schema.md`, and
> `host-capability-schema.md` into one document (T2.4 consolidation,
> Tier 2 cleanup).
>
> Old per-layer files are kept as one-line redirects for inbound link
> compatibility but are no longer the source of truth.

## Overview — 4-layer SSOT structure

SAMVIL v3.3+ separates "what is true" from "who decides" into four
layers. Each layer has a distinct surface and a distinct schema:

| Layer | Surface | Role | Schema section |
|---|---|---|---|
| **Layer 1 — Skill** | `skills/<name>/SKILL.md` | Stage entry; ultra-thin, MCP-driven (e.g. `samvil-seed` PoC) | (skill bodies, not covered here) |
| **Layer 2 — Orchestrator** | MCP event store + `.samvil/claims.jsonl` (no new file) | Stage-control: which stage runs next, can it proceed, how to record completion | [Orchestrator State](#layer-2--orchestrator-state) |
| **Layer 3 — Host Adapter** | `mcp/samvil_mcp/host.py` (+ `.samvil/next-skill.json` marker) | Declares runtime capabilities (skill invocation, parallel agents, file-marker handoff) | [Host Capability](#layer-3--host-capability) |
| **Layer 4 — SSOT files** | `.samvil/manifest.json`, `.samvil/decisions/*.md` | Project structure snapshot + human-facing decision history | [Codebase Manifest](#layer-4a--codebase-manifest-samvilmanifestjson) and [Decision Log / ADR](#layer-4b--decision-log--adr-samvildecisionsmd) |

Lower-level append-only ledgers (`.samvil/claims.jsonl`,
`.samvil/events.jsonl`) sit underneath Layer 4 and are documented
separately in `references/contract-layer-protocol.md`. Layer 4 is the
human-readable face on top of those ledgers.

Cross-layer relationships are summarised in
[Cross-layer relationships](#cross-layer-relationships) at the bottom.

---

## Layer 4a — Codebase Manifest (`.samvil/manifest.json`)

`.samvil/manifest.json` is an auto-generated description of project
structure. It is loaded at stage entry so an AI agent can see a
compressed codebase snapshot without reading the whole repository.

### Top-level shape

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

### Module entry

Each direct child directory under `src/` becomes one module. Code files
directly under `src/` become a synthetic `src` module:

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

### Field semantics

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

### Module discovery

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

### Public API extraction

Phase 1 reads `index.ts`, falling back to `index.tsx`, and extracts:

- named re-exports such as `export { signIn } from "./session"`
- type re-exports such as `export type { User } from "./types"`
- direct exports such as `export const x = 1`
- direct `async function`, `interface`, `enum`, and `type` exports
- default exports as the literal name `default`

`export * from "./x"` is intentionally out of scope because it requires
module resolution. A future AST-backed extractor should replace this
regex pass.

### Conventions

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

### Import graph

Schema `1.1` adds conservative internal dependency detection:

- TypeScript/JavaScript: static `import`, `export ... from`, `require()`, and
  dynamic `import()` string specifiers
- Python: `import x` and `from x import y`
- relative imports such as `../ui/button`
- common aliases such as `@/auth/session`, `src/auth/session`, and bare
  module-root imports like `auth/session`

External packages are ignored. The extractor is regex-based and marks
results with `imports:regex`; it is intended for context shaping, not
build enforcement.

### Module summaries

Each module gets a deterministic summary, `summary_generated_by`, and
`summary_generated_at`. The summary is intentionally heuristic so it
can run inside MCP without an LLM call. AI-generated or manual
summaries can be added in later releases using distinct confidence
tags.

### MCP tools

- `build_and_persist_manifest(project_root, project_name)` builds and writes
  `.samvil/manifest.json`
- `read_manifest(project_root)` returns the manifest dict, `missing`, or
  `corrupted`
- `render_manifest_context(project_root, focus?, max_modules?)` returns a
  compressed markdown summary for AI context
- `refresh_manifest(project_root, project_name)` rebuilds, persists, and renders
  context in one call

### Atomicity and safety

Manifest writes use a temp file followed by POSIX rename, so readers
should not see half-written JSON.

MCP wrappers reject empty or nonexistent `project_root` values. This
prevents accidental writes to the MCP server's current working
directory and avoids creating unexpected project trees.

### Out of scope (manifest)

- root-level module discovery for projects without `src/`
- namespace re-export resolution
- AST-backed public API extraction
- module-level convention tags beyond confidence metadata
- brownfield reverse-ADR generation

---

## Layer 4b — Decision Log / ADR (`.samvil/decisions/*.md`)

`.samvil/decisions/*.md` stores durable SAMVIL decisions as markdown
ADRs. The goal is PM-readable auditability: a user should be able to
open the folder, scan the active decisions, and see what was
superseded without reading JSONL.

This layer complements lower-level ledgers:

- `.samvil/claims.jsonl` remains the append-only proof ledger.
- `.samvil/events.jsonl` remains the runtime event stream.
- `.samvil/decisions/*.md` is the human-facing decision history.

### File location

```text
.samvil/
  decisions/
    adr_2026-04-25T10-20-30_use-next-js.md
    adr_council_d001.md
```

The filename is `{id}.md`. IDs must be filesystem-safe and begin with
`adr_`.

### Frontmatter

Frontmatter values are JSON literals, not loose YAML. This keeps
parsing deterministic and avoids depending on optional YAML packages.

```markdown
---
id: "adr_council_d001"
title: "Council: Remove dashboard from P1 features"
status: "accepted"
created_at: "2026-04-04T18:30:00+09:00"
last_reviewed_at: "2026-04-04T18:30:00+09:00"
superseded_by: null
authors: ["samvil-council", "simplifier"]
evidence: ["references/council-protocol.md:156"]
tags: ["council", "gate:A", "binding"]
supersedes: []
---
```

### Statuses

| Status | Meaning |
|---|---|
| `proposed` | Captured but not binding yet |
| `accepted` | Binding decision for later SAMVIL stages |
| `superseded` | Replaced by another ADR via `superseded_by` |
| `rejected` | Explicitly rejected and preserved for history |

### Body sections

Each ADR renders these sections:

```markdown
# Council: Remove dashboard from P1 features

## Context
Gate: A
Round: 2
Agent: simplifier
Reason: P1 scope is too large.
Consensus score: 0.67
Binding: True
Applied: True
Dissenting: False

## Decision
Remove dashboard from P1 features

## Consequences
Subsequent SAMVIL stages should respect this decision.

## Alternatives
Keep dashboard in P1.
```

If an ADR is superseded, a `## Supersession Reason` section is added.

### Council promotion mapping

Legacy council rows from `references/council-protocol.md` map as
follows:

| Legacy field | ADR destination |
|---|---|
| `id` | `adr_council_{id}` |
| `decision` | title suffix and `## Decision` |
| `reason` | `## Context` |
| `agent` | `authors[]` plus `agent:{name}` tag |
| `gate` | `gate:{name}` tag |
| `severity` | `severity:{value}` tag |
| `binding` | `binding` tag when true |
| `applied=false` | `unapplied` tag |
| `dissenting=true` | `dissenting` tag |
| `consensus_score < 0.60` | `weak-consensus` tag |
| `timestamp` | `created_at` and `last_reviewed_at` |

Status is `accepted` only when all of these are true:

- `binding == true`
- `applied == true`
- `dissenting == false`
- `consensus_score` is absent or at least `0.60`

Otherwise the ADR is preserved as `proposed`.

### Supersession

Supersession rewrites the old ADR atomically:

- `status` becomes `superseded`
- `superseded_by` becomes the replacement ADR id
- `last_reviewed_at` is updated
- `## Supersession Reason` records the reason

Chains such as `A -> B -> C` are traversed loop-safely. A malformed
loop stops at the first repeated id rather than recursing forever.

### MCP tools

The v3.3 Decision Log exposes:

- `write_decision_adr(project_root, adr_json)`
- `read_decision_adr(project_root, adr_id)`
- `list_decision_adrs(project_root, status?)`
- `supersede_decision_adr(project_root, old_id, new_id, reason)`
- `find_decision_adrs_referencing(project_root, target)`
- `promote_council_decision(project_root, decision_json)`

All wrappers validate `project_root` before writing. Empty or
nonexistent roots return structured errors instead of creating
surprise directories.

### Out of scope (decision log, Week 2)

- semantic search over decisions
- merging duplicate ADRs
- automatic code-comment rewriting
- conflict resolution beyond explicit supersession
- replacing `.samvil/claims.jsonl` or `.samvil/events.jsonl`

---

## Layer 2 — Orchestrator state

The orchestrator is SAMVIL's stage-control layer. It lets skills ask:

- what stage comes next?
- should this stage be skipped for this tier?
- can this session proceed to a target stage?
- how should a completed stage be recorded?

It is intentionally derived from existing state rather than introducing
a new file:

- `sessions.current_stage` in the MCP event store
- event rows from the MCP event store
- `.samvil/claims.jsonl` for claim output from mutating operations

No new orchestration state file is introduced.

### Stage order

```text
interview
seed
council
design
scaffold
build
qa
deploy
retro
evolve
complete
```

### Tier skip policy

Phase 1 uses a conservative skip policy:

| Stage | minimal | standard | thorough | full |
|---|---:|---:|---:|---:|
| `council` | skip | run | run | run |
| `deploy` | skip | skip | skip | skip |

`deploy` remains skipped until a later host/project capability layer
can prove that deployment is configured and reversible enough to run
automatically.

### Event-derived status

The orchestrator reduces event rows into per-stage status:

| Event examples | Stage status |
|---|---|
| `interview_complete` | `interview=complete` |
| `seed_generated`, `pm_seed_complete` | `seed=complete` |
| `council_complete`, `council_verdict` | `council=complete` |
| `design_complete`, `blueprint_generated` | `design=complete` |
| `scaffold_complete` | `scaffold=complete` |
| `build_pass`, `build_stage_complete` | `build=complete` |
| `build_fail` | `build=failed` |
| `qa_pass` | `qa=complete` |
| `qa_fail`, `qa_blocked`, `qa_unimplemented` | `qa=failed` |
| `deploy_complete` | `deploy=complete` |
| `retro_complete` | `retro=complete` |
| `evolve_converge` | `evolve=complete` |

Later successful events override earlier failed events for the same
stage. This matches repair flows where a failed build is fixed and
then passes.

### Proceed rule

`stage_can_proceed(session_id, target_stage)` returns `can_proceed=true`
only when every prior non-skipped stage is complete.

Blocked examples:

- prior stage has no successful exit event
- prior stage has a latest `failed` status
- target stage itself is skipped by tier
- target stage is unknown

Skipped stages do not block. For example, `minimal` can proceed from
`seed` to `design` without running `council`.

### Complete-stage rule

`complete_stage(session_id, stage, verdict)` is the only mutating
orchestrator tool. It writes:

1. one event row in the MCP event store
2. one `gate_verdict` claim in `.samvil/claims.jsonl` when the project
   path can be resolved

Verdict mapping:

| Verdict | Event | Next stage |
|---|---|---|
| `pass` | stage-specific success event | next non-skipped stage |
| `complete` | stage-specific success event | next non-skipped stage |
| `fail` | stage-specific failure event | none |
| `blocked` | stage-specific blocked event | none |

### MCP tools

- `get_next_stage(current, samvil_tier)`
- `should_skip_stage(stage, samvil_tier)`
- `stage_can_proceed(session_id, target_stage)`
- `complete_stage(session_id, stage, verdict)`
- `get_orchestration_state(session_id)`

The `get_*` tools are read-only. `complete_stage` is the only mutating
tool.

### Failure behavior

If a session cannot be found, wrappers return structured JSON errors
rather than raising through MCP transport. If the project path cannot
be resolved, `complete_stage` still records the event and returns
`claim_id=null`.

---

## Layer 3 — Host capability

`HostCapability` declares runtime differences as data. SAMVIL skills
should ask what the host can do instead of assuming Claude Code
behavior.

### Shape

```json
{
  "name": "codex_cli",
  "skill_invocation": "manual",
  "parallel_agents": false,
  "mcp_tools": true,
  "file_marker_handoff": true,
  "browser_preview": true,
  "native_task_update": false,
  "notes": ["Prefer MCP tools plus explicit file markers."],
  "chain_via": "file_marker"
}
```

### Known hosts

| Host | Chain via | Notes |
|---|---|---|
| `claude_code` | `skill_tool` | Can directly invoke the next SAMVIL skill |
| `codex_cli` | `file_marker` | Uses `.samvil/next-skill.json` for portable continuation |
| `opencode` | `file_marker` | Avoid Claude-specific assumptions |
| `generic` | `file_marker` | Fallback for unknown hosts |

Unknown host names resolve to `generic`.

### Chain strategies

`skill_tool`:

- use when the runtime has a native skill invocation mechanism
- current known host: `claude_code`

`file_marker`:

- write `.samvil/next-skill.json`
- next session or host reads the marker and continues manually
- preferred portable fallback for Codex/OpenCode/generic

Example marker:

```json
{
  "schema_version": "1.0",
  "chain_via": "file_marker",
  "host": "codex_cli",
  "next_skill": "samvil-council",
  "reason": "council required for selected tier",
  "from_stage": "seed",
  "created_by": "samvil-seed"
}
```

See `references/host-continuation.md` for the canonical marker
contract.

### MCP tools

- `resolve_host_capability(host_name?)`
- `host_chain_strategy(host_name?)`

Both tools are read-only and return JSON.

### Seed PoC

`skills/samvil-seed/SKILL.md` is the first ultra-thin PoC of Layer 1
on top of Layers 2/3:

- active skill body is under 90 lines
- full rules are preserved in `skills/samvil-seed/SKILL.legacy.md`
- chaining goes through `host_chain_strategy`
- non-skill-tool hosts use `.samvil/next-skill.json`

This proves the Phase 2 mass-migration shape without deleting the
existing seed knowledge.

---

## Cross-layer relationships

The four layers fit together along the SAMVIL pipeline like this:

1. **Layer 1 (Skill)** is invoked at stage entry. It reads context
   (manifest, prior decisions, prior stage events) and decides what
   work to do this stage.
2. **Layer 4a (Manifest)** gives the skill a compressed view of the
   codebase without forcing it to read the whole repo. It is rebuilt
   on demand via `refresh_manifest`.
3. **Layer 4b (Decision Log / ADR)** records durable decisions made
   during the stage (e.g. council verdicts) in PM-readable form.
   These ADRs are the authoritative human-facing record.
4. **Layer 2 (Orchestrator)** is consulted before transitioning to the
   next stage. `stage_can_proceed` enforces ordering, `complete_stage`
   records both an event and a `gate_verdict` claim in the underlying
   ledgers.
5. **Layer 3 (Host adapter)** decides *how* the next skill is reached
   — directly via `skill_tool` on Claude Code, or by writing
   `.samvil/next-skill.json` on Codex / OpenCode / generic hosts.

A typical stage transition therefore touches all four layers:

```text
[Skill body]
  ↓ reads
[Manifest] + [ADRs]            ← Layer 4 (snapshot + decisions)
  ↓ stage logic produces verdict
[Orchestrator.complete_stage]  ← Layer 2 (event + gate_verdict claim)
  ↓ next-skill resolution
[Host.chain_strategy]          ← Layer 3 (skill_tool or file_marker)
  ↓ continuation
[Next skill]                   ← Layer 1
```

The append-only `.samvil/claims.jsonl` and `.samvil/events.jsonl`
ledgers underpin Layers 2 and 4 — see
`references/contract-layer-protocol.md` for that contract.
