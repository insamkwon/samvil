# Prompt Patterns for SAMVIL Skills

> Prompt engineering patterns that all SAMVIL skills follow.
> Use this as a reference when writing or editing skill prompts.

## 1. Zero-shot vs Few-shot Selection

### Selection Flowchart

```
START
  │
  ├─ Output is structured (JSON, table, checklist)?
  │   └─ YES → Zero-shot
  │
  ├─ Task is a simple transformation (format, rename, extract)?
  │   └─ YES → Zero-shot
  │
  ├─ Rules are unambiguous and complete?
  │   └─ YES → Zero-shot
  │
  ├─ Task requires creative generation (copy, design, code)?
  │   └─ YES → Few-shot (1-3 examples)
  │
  ├─ Task requires pattern recognition across inputs?
  │   └─ YES → Few-shot (2-3 examples)
  │
  └─ Task requires multi-step reasoning with judgment?
      └─ YES → Few-shot (1 example with reasoning trace)
```

### When to Use Zero-shot

- Structured output generation (JSON schemas, markdown tables)
- Simple transformations (kebab-case conversion, PascalCase extraction)
- Rule-based decisions (tier lookup, dependency resolution)
- Format enforcement (build log parsing, version extraction)

**SAMVIL examples:**
- Seed JSON generation from interview (schema-defined structure)
- Scaffold CLI command construction (deterministic mapping)
- QA verdict matrix application (rule-based classification)

### When to Use Few-shot

- Creative or subjective tasks (UX writing, error messages)
- Pattern recognition (code convention detection, drift detection)
- Complex reasoning (AC testability evaluation, blueprint architecture)

**SAMVIL examples:**
- Interview question generation (requires tone judgment)
- Drift detection output (requires comparing intent vs implementation)
- Retro suggestion generation (requires pattern matching across runs)

## 2. Chain-of-Thought Induction Patterns

### Pattern A: Step-by-Step Reasoning

Use in verification/QA agents where the reasoning trace matters.

```
Before giving your verdict, walk through each check:
1. Read the acceptance criterion
2. Identify what user action would prove it
3. Perform the action
4. Observe the result
5. Compare result with the criterion
6. State your verdict with evidence
```

**Applied in:** samvil-qa Pass 2 (runtime verification), seed self-validation.

### Pattern B: Justification Before Conclusion

Use when the decision needs to be auditable.

```
State your reasoning BEFORE stating the verdict.
Format: "Because <evidence>, I judge <verdict>."
Do NOT state the verdict first and then justify it.
```

**Applied in:** Council agents (APPROVE/CHALLENGE/REJECT with reasoning), QA verdict.

### Pattern C: Self-Critique Loop

Use for quality-sensitive outputs.

```
After generating your output, verify it against these checks:
- [ ] Does it satisfy the original request?
- [ ] Are there vague words that need rewriting?
- [ ] Is the output format correct?
If any check fails, revise before returning.
```

**Applied in:** Seed generation (self-validation step), QA report writing.

## 3. Output Format Enforcement

### Pattern A: Trailing Format Specification

Place the output format as the LAST instruction in the prompt. LLMs attend most to the end of the prompt.

```
## Output Format

Return your result as a JSON object with this exact structure:
```json
{
  "verdict": "PASS|FAIL|PARTIAL|UNIMPLEMENTED",
  "evidence": "<what you tested and observed>",
  "screenshot_path": "<path or null>"
}
```
Do not include any text outside the JSON block.
```

### Pattern B: Delimited Sections

For markdown outputs with multiple sections:

```
## Output Format

Use exactly these markdown sections, in this order:

### Verdict
One of: PASS / REVISE / FAIL

### Evidence
- Bullet list of what was tested

### Issues
Numbered list of problems found (empty if PASS)
```

### Pattern C: Schema-Anchored Output

When output must conform to an existing schema (e.g., seed-schema.json):

```
## Output Format

Output must be valid JSON conforming to the seed schema.
Read `references/seed-schema.md` for the full schema.
Required fields: name, description, tech_stack, core_experience, features, acceptance_criteria, constraints, out_of_scope.
```

## 4. Vague Word Replacement Table

Replace these words with concrete, measurable alternatives in all skill prompts.

| Vague Word | Replace With | Example |
|---|---|---|
| "적절히" (appropriately) | Specific number, format, or pattern | "3-5 items" / "kebab-case" / "HSL color format" |
| "알맞게" (suitably) | Explicit threshold or criteria | ">= 375px width" / "exit code 0" / "ALL ACs covered" |
| "깔끔하게" (neatly) | Component structure + CSS variables | "One component per file + shadcn/ui tokens" |
| "사용자 친화적으로" (user-friendly) | Specific UX pattern | "Toast notification on success, inline error on failure" |
| "잘" (well) | Measurable criterion | "Build exits with code 0" / "All ACs PASS" |
| "자연스럽게" (naturally) | Specific interaction flow | "Tab order follows visual layout, focus ring visible" |
| "간단하게" (simply) | Scope constraint | "Single file, < 50 lines, no external deps" |
| "효율적으로" (efficiently) | Performance target | "First Load JS < 100KB" / "INP < 200ms" |
| "모던하게" (modern) | Specific tech/pattern | "App Router + Server Components + streaming" |
| "직관적으로" (intuitively) | Measurable UX criterion | "Primary action visible within 3 clicks from any page" |
| "적당히" (moderately) | Numeric range | "2-3 levels deep" / "5-7 items visible" |
| "보기 좋게" (prettily) | Design system reference | "shadcn/ui Card component with consistent spacing" |
| "적절한 에러 처리" (proper error handling) | Specific pattern | "try-catch with user-facing Korean message + fallback to default" |

### Vague Word Detection (for AC validation)

These words trigger automatic rewrite suggestions:

```
Korean: 좋은, 빠른, 깔끔한, 직관적인, 부드러운, 전문적인, 모던한, 사용자 친화적인,
        잘, 자연스럽게, 간단하게, 효율적으로, 적절히, 알맞게, 적당히, 보기 좋게
English: good, nice, fast, clean, intuitive, smooth, professional, modern,
         user-friendly, well, simply, efficiently, properly, appropriate, suitable
```

## 5. SAMVIL Skill Prompt Structure Template

Every SAMVIL skill follows this structure. Maintain the order and completeness.

```markdown
## Role (1-2 lines)
Who you are and what you do. Adopt a named persona.
Example: "You are adopting the role of **Seed Architect**. Transform interview results into a structured, machine-readable spec."

## Input (what you read)
List every file the skill reads, with purpose.
Example:
- Read `project.seed.json` -> the spec being reviewed
- Read `project.state.json` -> current stage, session_id
- Read `references/qa-checklist.md` -> QA criteria

## Process (step-by-step instructions)
Numbered steps with:
- What to do
- How to verify it worked
- What to do on failure
Each step is atomic and verifiable.

## Output Format (exact format of the result)
Define the exact structure of what the skill produces.
Specify: file path, format (JSON/markdown), required fields.
Example:
Write to `~/dev/<project>/project.seed.json` with this schema:
{field definitions}

## Anti-Patterns (3 forbidden actions)
List exactly 3 things the skill must NOT do.
Example:
1. Do NOT ask the user implementation choices (be opinionated)
2. Do NOT modify files outside the project directory
3. Do NOT proceed if build fails (circuit breaker)
```

### Why This Order?

1. **Role first** — sets the persona before any instructions
2. **Input before Process** — ensures all context is loaded before acting
3. **Process before Output** — actions define what gets produced
4. **Output before Anti-Patterns** — format is positive, then boundaries
5. **Anti-Patterns last** — recency bias makes the final "do not" stick

### Chain Section (separate from prompt structure)

Every skill ends with a Chain section specifying the next skill to invoke. This is not part of the prompt pattern — it is an execution directive.

```
## Chain
Invoke the Skill tool with skill: `<next-skill-name>`
```

## 6. Interview Adaptive Patterns

Patterns for the samvil-interview skill's adaptive follow-up system.

### Pattern A: Answer-Length Branching

After each user answer, measure response length and branch strategy.

```
IF answer_length >= 100 chars OR answer contains multiple topics:
  → Structure question: pick one focus, ask "화면/동작/순서 중 무엇을 먼저?"
ELSE IF answer_length < 30 chars OR answer is 1-2 words:
  → Expand question: ask "why" + "what problem" + "example situation"
ELSE IF answer contains vague_words OR "알아서"/"적당히"/"대충":
  → Choice question: provide 2 concrete alternatives, ask "which is closer?"
ELSE:
  → Proceed to next planned question (no follow-up needed)
```

**Applied in:** samvil-interview Phase 1-2, after every user response.

### Pattern B: Preset-Driven Question Generation

When a preset matches, reduce question count and enrich option quality.

```
Given: matched_preset from references/app-presets.md

FOR each interview_phase:
  preset_fields = extract_relevant_fields(preset, phase)
  IF preset_fields.has_defaults:
    options = preset_fields.defaults  (preset values as options)
    question_count = max(1, phase.min_questions - 1)  // reduce by 1
  ELSE:
    options = generate_contextual_options(app_idea, phase)
    question_count = phase.min_questions

  AskUserQuestion with options + "Other" fallback
```

**Applied in:** samvil-interview Step 1 (preset matching), all Phase questions.

### Pattern C: Ambiguity Convergence Loop

Iterative loop that measures and reduces ambiguity until tier threshold is met.

```
REPEAT (max 2 iterations):
  score = mcp__samvil_mcp__score_ambiguity(interview_state, tier)

  IF score <= tier_threshold AND all_gates_passed:
    BREAK → proceed to Phase 4 (summary)

  IF score > tier_threshold:
    vague_items = identify_vague_acs_or_features(interview_state)
    FOR each vague_item:
      AskUserQuestion with rewrite suggestion + Other

  IF gates_failed:
    missing_gate = first_failed_gate(gates)
    AskUserQuestion targeting missing_gate

  update interview_state with new answers

FORCE_PROCEED after 2 iterations (avoid infinite loop)
```

**Applied in:** samvil-interview Phase 3 (Convergence Check).

### Pattern D: Auto-Detection for Phase 2.5

Automatically activate deep-probing based on answer quality, regardless of tier.

```
Phase 2.5 activation:
  standard_activation = tier IN ["thorough", "full"]

  auto_detect_signals:
    - preset_matched == false
    - short_answer_ratio = count(answers < 30 chars) / total_answers
    - short_answer_ratio > 0.5

  IF standard_activation:
    run Phase 2.5 with both Pre-mortem + Inversion questions
  ELSE IF auto_detect_signals:
    run Phase 2.5 with only Pre-mortem (1 question, abbreviated)
  ELSE:
    skip Phase 2.5
```

**Applied in:** samvil-interview Phase 2.5 activation decision.
