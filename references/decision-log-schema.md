# Decision Log / ADR Schema (v3.3+)

`.samvil/decisions/*.md` stores durable SAMVIL decisions as markdown ADRs.
The goal is PM-readable auditability: a user should be able to open the folder,
scan the active decisions, and see what was superseded without reading JSONL.

This layer complements lower-level ledgers:

- `.samvil/claims.jsonl` remains the append-only proof ledger.
- `.samvil/events.jsonl` remains the runtime event stream.
- `.samvil/decisions/*.md` is the human-facing decision history.

## File Location

```text
.samvil/
  decisions/
    adr_2026-04-25T10-20-30_use-next-js.md
    adr_council_d001.md
```

The filename is `{id}.md`. IDs must be filesystem-safe and begin with `adr_`.

## Frontmatter

Frontmatter values are JSON literals, not loose YAML. This keeps parsing
deterministic and avoids depending on optional YAML packages.

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

## Statuses

| Status | Meaning |
|---|---|
| `proposed` | Captured but not binding yet |
| `accepted` | Binding decision for later SAMVIL stages |
| `superseded` | Replaced by another ADR via `superseded_by` |
| `rejected` | Explicitly rejected and preserved for history |

## Body Sections

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

## Council Promotion Mapping

Legacy council rows from `references/council-protocol.md` map as follows:

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

## Supersession

Supersession rewrites the old ADR atomically:

- `status` becomes `superseded`
- `superseded_by` becomes the replacement ADR id
- `last_reviewed_at` is updated
- `## Supersession Reason` records the reason

Chains such as `A -> B -> C` are traversed loop-safely. A malformed loop stops
at the first repeated id rather than recursing forever.

## MCP Tools

The v3.3 Decision Log exposes:

- `write_decision_adr(project_root, adr_json)`
- `read_decision_adr(project_root, adr_id)`
- `list_decision_adrs(project_root, status?)`
- `supersede_decision_adr(project_root, old_id, new_id, reason)`
- `find_decision_adrs_referencing(project_root, target)`
- `promote_council_decision(project_root, decision_json)`

All wrappers validate `project_root` before writing. Empty or nonexistent roots
return structured errors instead of creating surprise directories.

## Out Of Scope In Week 2

- semantic search over decisions
- merging duplicate ADRs
- automatic code-comment rewriting
- conflict resolution beyond explicit supersession
- replacing `.samvil/claims.jsonl` or `.samvil/events.jsonl`
