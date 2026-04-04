---
name: samvil-build
description: "Build core experience + features from seed. Circuit breaker per feature. Context Kernel sync on every step."
---

# SAMVIL Build — Core Experience + Feature Implementation

You are adopting the role of **Full-Stack Developer**. Implement the seed spec as working code.

## Boot Sequence (INV-1)

1. Read `project.seed.json` → know what to build
2. Read `project.state.json` → know what's already done (resume support)
3. Read `references/web-recipes.md` from this plugin directory → patterns to use
4. Check `completed_features` in state — skip already-built features

## Phase A: Core Experience

The seed's `core_experience` defines what the user does in the first 30 seconds. **Build this first.**

1. Read `seed.core_experience`
2. Create the primary screen component: `components/<primary_screen>.tsx`
3. Create supporting components as needed (keep minimal)
4. Create state management if needed:
   - Zustand (`seed.tech_stack.state` = `"zustand"`): create `lib/store.ts`
   - useState: inline in components
5. Wire into page: update `app/page.tsx` to import and render the primary screen
6. **Build verify (INV-2):**

```bash
cd ~/dev/<seed.name>
npm run build > .samvil/build.log 2>&1
echo "Exit code: $?"
```

**Circuit Breaker (MAX_RETRIES=2):**
- Build fails → `tail -30 .samvil/build.log` → fix → retry
- 2 failures → STOP, report to user

7. Update `project.state.json`: note core experience complete

```
[SAMVIL] Stage 4/5: Core Experience built ✓
  Component: <primary_screen>
  Build: passing
```

## Phase B: Features (Sequential)

Read `seed.features` sorted by priority (1 first, then 2).
Respect dependency order: if feature B `depends_on` feature A, build A first.

**For each feature:**

### 1. Re-read Context Kernel (INV-1)

Re-read `project.seed.json` + `project.state.json` before every feature.
Context may have been compressed — files are the truth.

### 2. Plan the feature

What components? What state changes? What routes?
Keep it minimal — implement exactly what the seed says, nothing more.

### 3. Implement

- Create/modify components in `components/`
- Create/modify lib files in `lib/`
- Create new routes in `app/` if needed
- **Keep existing code working** — don't break what's already built

### 4. Build verify (INV-2)

```bash
cd ~/dev/<seed.name>
npm run build > .samvil/build.log 2>&1
echo "Exit code: $?"
```

**Circuit Breaker (MAX_RETRIES=2):**
- Build fails → `tail -30 .samvil/build.log` → analyze → fix → retry
- 2 failures → mark feature as `failed` in state, **continue to next feature**

### 5. Update state

- Success: add feature name to `completed_features`
- Failure: add feature name to `failed`
- Set `in_progress` to `null`

```
[SAMVIL] Feature: <name> ✓  [N/M features complete]
```

### After All Features

```
[SAMVIL] Stage 4/5: Build complete
  Features: N/M passed
  Failed: [list or "none"]
  Build: passing
```

## Chain to QA (INV-4)

Update `project.state.json`: set `current_stage` to `"qa"`.

```
[SAMVIL] Stage 5/5: Running QA verification...
```

Invoke the Skill tool with skill: `samvil:qa`

## Code Quality Rules

1. **`'use client'`** on every component with hooks, event handlers, or browser APIs
2. **TypeScript strict** — no `any` in business logic. Use proper interfaces.
3. **PascalCase** components, one component per file
4. **State management** — follow `seed.tech_stack.state` pattern
5. **Tailwind only** — utility classes. No inline styles. No CSS modules.
6. **`cn()` utility** — use `cn()` from `lib/utils.ts` (clsx + tailwind-merge) for all className composition. Create it if it doesn't exist:
   ```typescript
   // lib/utils.ts
   import { clsx, type ClassValue } from 'clsx'
   import { twMerge } from 'tailwind-merge'
   export function cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)) }
   ```
7. **Responsive** — use `md:`, `lg:` prefixes for layout changes
8. **`@/` imports** — absolute imports via the alias
9. **Real content** — no "Lorem ipsum" or placeholder text
10. **Empty states** — every list/collection handles zero items
11. **No dead code** — don't generate unreachable code
12. **Hydration-safe** — use the `mounted` pattern from web-recipes.md for any localStorage/browser API usage
13. **localStorage defensive** — always wrap `JSON.parse(localStorage.getItem())` in try-catch with fallback to empty default. Corrupt data must not crash the app.

## What NOT To Do

- Don't add features not in the seed
- Don't change the tech stack
- Don't add testing frameworks
- Don't add linting beyond the template
- Don't create README.md
- Don't add premature optimization (memo, lazy loading)
- Don't dump build logs into conversation — use .samvil/build.log
