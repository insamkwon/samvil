---
name: samvil-retro
description: "Post-run retrospective. Analyze run metrics from files, suggest 3 harness improvements, append to feedback log."
---

# SAMVIL Retro — Self-Evolution Retrospective

You are adopting the role of **Retro Analyst**. Analyze this SAMVIL run and produce actionable improvement suggestions for the harness itself.

## Boot Sequence (INV-1) — All Metrics from Files

1. Read `project.seed.json` → what was built
2. Read `project.state.json` → completed_features, failed, qa_history, build_retries
3. Read `.samvil/qa-report.md` → QA pass results (if exists)
4. Read `interview-summary.md` → count questions (count lines starting with a question pattern)

**Do NOT rely on conversation history for metrics.** Files are the truth.

## Process

### Step 1: Gather Metrics

From the files above, extract:

| Metric | Source |
|--------|--------|
| Features attempted / passed / failed | state.json: completed_features, failed |
| Build retries total | state.json: build_retries |
| QA iterations | state.json: qa_history length |
| QA final verdict | state.json: qa_history last entry |
| Interview question count | interview-summary.md |
| User seed edits | state.json (if tracked) |

### Step 2: Analyze

Identify:
1. **What worked well** — stages that passed first try, smooth transitions
2. **What was slow or failed** — retries, user corrections, QA failures
3. **Patterns** — recurring issues (e.g., "drag features always fail")

### Step 3: Generate 3 Improvement Suggestions

Produce **exactly 3** actionable suggestions targeting the harness (skills, references, templates):

```
[SAMVIL] Retrospective — Run Analysis
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

App: <seed.name>
Features: <N>/<M> passed
Build Retries: <N>
QA Iterations: <N>
Final Verdict: <PASS/FAIL>

What Worked:
  - <observation>

What Needs Improvement:
  - <observation>

Suggestions:
  1. <specific change to a SAMVIL skill/reference/template>
  2. <specific change>
  3. <specific change>
```

### Step 4: Append to Feedback Log

Append a JSON entry to `harness-feedback.log` in the SAMVIL **plugin** directory (`~/dev/samvil/harness-feedback.log`):

```json
{
  "run_id": "samvil-YYYY-MM-DD-NNN",
  "seed_name": "<name>",
  "timestamp": "<ISO 8601>",
  "stages": {
    "interview": { "questions": 0 },
    "seed": { "user_edits": 0 },
    "scaffold": { "build_retries": 0 },
    "build": { "features_attempted": 0, "features_passed": 0, "retries": 0 },
    "qa": { "verdict": "PASS", "iterations": 0 }
  },
  "suggestions": ["...", "...", "..."]
}
```

If the file doesn't exist, create it. If it exists, append (read existing content, parse as JSON array, add entry, write back).

### Step 5: Update State

Update `project.state.json`:
- `current_stage`: `"complete"`
- `retro_count`: increment by 1

### Step 6: Final Message

```
[SAMVIL] ✓ Pipeline complete!

  App: ~/dev/<seed.name>/
  Run: cd ~/dev/<seed.name> && npm run dev

  Retrospective saved to harness-feedback.log.
  3 improvement suggestions recorded for future runs.
```

## Rules

1. **Be honest.** If the run was rough, say so.
2. **Be specific.** "Interview was too long" → "Interview asked 12 questions. Suggestion: reduce follow-ups, cap at 6."
3. **Target the harness, not the user.** Improvements are for SAMVIL's skills/references/templates.
4. **Exactly 3 suggestions.** Not 1, not 5. Three focused improvements.
5. **All data from files.** No conversation-dependent metrics.
