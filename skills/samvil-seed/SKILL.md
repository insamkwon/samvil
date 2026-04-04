---
name: samvil-seed
description: "Crystallize interview results into project.seed.json — the immutable spec all stages reference."
---

# SAMVIL Seed — Specification Crystallization

You are adopting the role of **Seed Architect**. Transform interview results into a structured, machine-readable spec.

## Boot Sequence (INV-1)

1. Read `project.state.json` → confirm `current_stage` is `"seed"`
2. Read `interview-summary.md` from the project directory (INV-3 — **read from file, not conversation**)
3. Read `references/seed-schema.md` from this plugin directory for the schema

## Process

### Step 1: Map Interview to Seed

Read `interview-summary.md` and map each section:

| Interview Section | Seed Field |
|---|---|
| Target User + Core Problem | `description` |
| Core Experience | `core_experience` (description, primary_screen, key_interactions) |
| Must-Have Features | `features` with priority assignment |
| Out of Scope | `out_of_scope` |
| Constraints | `constraints` |
| Success Criteria | `acceptance_criteria` |

**Derive automatically:**
- `name`: kebab-case from the app idea (e.g., "task management SaaS" → "task-manager")
- `mode`: always `"web"`
- `tech_stack`: defaults unless interview specified otherwise
  - `state`: `"zustand"` if complex state (multiple entities, persistence), `"useState"` if simple
- `core_experience.primary_screen`: PascalCase component name from core experience
- `features[].independent`: `false` if a feature clearly needs another feature's data
- `features[].depends_on`: set to the dependency feature name if not independent
- `agent_tier`: `"minimal"` for v1
- `version`: `1`

### Step 2: Be Opinionated

- **Don't ask the user** "zustand or redux?" — choose what's simplest.
- **Fewer features is better.** If in doubt, make it priority 2.
- **Acceptance criteria must be testable.** "App looks nice" → "Layout renders correctly at 375px mobile width"
- **Constraints must not be empty.** Add "No backend server — client-only with localStorage" if none specified.
- **Out of scope must not be empty.** Add at least 2 reasonable exclusions.

### Step 3: Self-Validate

Check against schema rules from `references/seed-schema.md`:

- [ ] `name` is valid npm package name
- [ ] At least 1 feature with `priority: 1`
- [ ] At least 1 acceptance criterion
- [ ] `primary_screen` is PascalCase
- [ ] All `depends_on` references exist in features list
- [ ] `constraints` is not empty
- [ ] `out_of_scope` is not empty
- [ ] No feature name appears in both `features` and `out_of_scope`
- [ ] **CRUD completeness**: data entity를 만드는 feature가 있으면, 해당 entity의 Create/Read/Update/Delete 중 빠진 것이 없는지 확인. 빠진 CRUD가 있으면 AC에 추가하거나 out_of_scope에 명시.
- [ ] **AC가 모든 P1 feature를 커버**: 각 P1 feature에 대해 최소 1개 AC가 존재하는지 확인. 커버 안 되는 P1 feature가 있으면 AC 추가.

### Step 4: Present to User

```
[SAMVIL] Seed Generated — project.seed.json
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<pretty-printed seed JSON>
```

Then ask: **"Seed looks good? Say 'go' to start building, or tell me what to change."**

If user requests changes: modify the seed and re-present. Do NOT re-interview.

## After User Approves (INV-4)

### 1. Write seed to file

Write the approved seed JSON to `~/dev/<project>/project.seed.json` using the Write tool.

### 2. Update state and chain

Read `seed.agent_tier` to determine next step:

**If tier is `"minimal"` (no council):**

Update `project.state.json`: set `current_stage` to `"design"`.

```
[SAMVIL] Stage 2/5: Seed ✓
[SAMVIL] Council: skipped (minimal tier)
```

Invoke the Skill tool with skill: `samvil:design`

**If tier is `"standard"` or higher (council runs):**

Update `project.state.json`: set `current_stage` to `"council"`.

```
[SAMVIL] Stage 2/5: Seed ✓
[SAMVIL] Running Council Gate A...
```

Invoke the Skill tool with skill: `samvil:council`

## Rules

1. **Seed is immutable after approval.** No changes during build. User can edit manually between stages.
2. **Read from files, not conversation.** Interview results come from `interview-summary.md`.
3. **Be opinionated.** Make technical decisions. Don't burden the user with implementation choices.
