# SAMVIL Publish (Codex CLI)

Convert `project.seed.json` into GitHub Issues (Epic + Tasks). Team
workflow or personal kanban. Pattern adapted from Ouroboros publish.

## Prerequisites (optional)

This skill is invoked manually outside the standard pipeline flow.
Run `read_chain_marker(project_root="${PWD}")` first to check if a
SAMVIL pipeline is mid-run; if so, defer publish until completion.

Verify: `gh` installed (`command -v gh`), authenticated
(`gh auth status`), and `project.seed.json` exists. Any fails → stop.

## Steps

### 1. Resolve target repository

```bash
gh repo view --json nameWithOwner -q '.nameWithOwner' 2>/dev/null
```

Ask user via standard prompt to confirm or specify alternate
`owner/repo`. Store as `$REPO`. Every subsequent `gh` command MUST
include `-R $REPO`.

### 2. Duplicate check

```bash
gh issue list -R $REPO --label "samvil" --state all \
  --search "$(jq -r .name project.seed.json)" --limit 5 \
  --json number,title,state
```

If matches found: ask user whether to proceed; if cancelled, stop.

### 3. Plan + 4. Labels + 5. Epic + 6. Tasks + 7. Update Epic

Plan `[Epic]` + one `[Task]` per `seed.features[i]`. Create idempotent
labels: `samvil`, `epic`, `task`. Create Epic with `--body` containing
Goal/Tech/Constraints/Out-of-Scope (and `evaluation_principles` +
`exit_conditions` if v4.23+ present). Capture `EPIC_NUM`. Create one
Task per feature with `Parent: #$EPIC_NUM` + AC checklist. Comment
back to Epic listing all task links.

### 8. Summary

Print tree view + View URL.

## Anti-Patterns

1. NEVER skip Step 2 duplicate check — multiple identical Epics ruin
   a tracker.
2. NEVER write secrets (`external_api_config.api_keys`) into issue
   bodies.
3. NEVER reuse `-R` flag value from a stale variable — re-derive from
   `$REPO` every time.

## Chain

Terminal skill — **do not call** `write_chain_marker`. This skill
lives outside the standard pipeline flow (no `next_skill` exists).
