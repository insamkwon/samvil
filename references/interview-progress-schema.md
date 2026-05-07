# Interview Progress Schema (v4.19.0)

Single source of truth for `<project_root>/.samvil/interview-progress.json`,
the JSONL file that captures interview state during a samvil-interview run.

This file replaces v4.18.0's bash-`echo`-append pattern with structural
persistence guaranteed by MCP tools (`persist_interview_answer`,
`mark_interview_phase_complete`, `load_interview_progress`,
`clear_interview_progress`).

The interview never *blocks* on persistence failures — `INV-5 Graceful
Degradation` guarantees the loop continues even if the file is
unreachable. The only requirement is that whenever persistence *does*
succeed, the file remains valid JSONL.

---

## File location

`<project_root>/.samvil/interview-progress.json`

JSONL — one JSON object per line. Empty lines and malformed lines are
skipped at replay time. Order is append-only and preserved.

A sibling lock file at `interview-progress.json.lock` is used by
`fcntl.flock` on POSIX. Windows fallback is a no-op (single-threaded
SAMVIL main session is the practical case).

---

## Entry types

Three entry types share the same file. Each is identified by `type`.

### 1. `qa` — a question/answer pair

```json
{
  "type": "qa",
  "phase": "core",
  "q": "이 앱을 주로 누가 사용하나요?",
  "a": "1인 솔로 개발자",
  "source": "from-user",
  "ts": "2026-05-07T03:14:15.926535+00:00"
}
```

| Field | Required | Meaning |
|---|---|---|
| `type` | yes | Always `"qa"`. |
| `phase` | yes | Phase id (`core`, `scope`, `unknown`, `nonfunc`, `inversion`, `stakeholder`, `lifecycle`, `research`, `domain_deep`). |
| `q` | yes | The question text shown to the user. Korean. |
| `a` | yes | The user (or routed) answer. May contain `[from-code]`, `[from-user]`, `[from-research]` prefixes per the routing protocol. |
| `source` | no | One of `from-user`, `from-code`, `from-code-confirmed`, `from-research`. Default `from-user`. |
| `ts` | yes | ISO-8601 timestamp (UTC). |

### 2. `ac_candidate` — a leaf-level AC inferred from the answer

```json
{
  "type": "ac_candidate",
  "phase": "scope",
  "ac_text": "사용자는 할일을 추가/삭제/완료 표시할 수 있다",
  "ts": "2026-05-07T03:14:18.000000+00:00"
}
```

| Field | Required | Meaning |
|---|---|---|
| `type` | yes | Always `"ac_candidate"`. |
| `phase` | yes | Phase id under which this AC was derived. |
| `ac_text` | yes | Single-sentence Korean AC. Implementation-level when possible. |
| `ts` | yes | ISO-8601 timestamp. |

`ac_candidate` entries are produced **inline during the interview**
(samvil-interview Step 5 Progressive Output). They are *jamjeong*
(잠정) — they are confirmed at samvil-seed consolidation time and may
be reworded, deduplicated, or grouped at that point. Users see them
during the interview with the label "잠정 AC (seed 단계에서 확정)".

### 3. `phase_complete` — a marker that this phase is closed

```json
{
  "type": "phase_complete",
  "phase": "core",
  "ts": "2026-05-07T03:14:30.000000+00:00"
}
```

Written at the end of each Phase loop. Used at resume time to know
which Phases were already finished, so an interrupted interview
doesn't re-ask completed phases.

Duplicates are tolerated — replay deduplicates `completed_phases`.

---

## Replay (resume) semantics

`load_interview_progress(project_root)` returns:

```json
{
  "ok": true,
  "exists": true,
  "qa_entries": [...],
  "ac_candidates": [...],
  "completed_phases": ["core", "scope"],
  "ac_by_phase": {"core": ["AC1", "AC2"], "scope": ["AC3"]},
  "answers_by_phase": {"core": [{"q": "...", "a": "...", "source": "...", "ts": "..."}]},
  "path": "/path/to/interview-progress.json"
}
```

samvil-interview Boot Sequence reads this when the file exists and
restores `completed_phases`, `ac_by_phase`, and `answers_by_phase` into
the live interview state. Phases listed in `completed_phases` are
skipped in Step 2.

samvil-seed reads this to consolidate AC candidates into confirmed ACs
in seed.json. If the file is absent, samvil-seed falls back to
`interview-summary.md` (v4.18 and earlier behavior).

---

## Lifecycle

```
1. samvil-interview Step 0  →  test if file exists
                              │
                              ├─ yes → load_interview_progress + skip completed phases
                              │
                              └─ no  → start fresh
                              ↓
2. Step 2 Phase loop           → persist_interview_answer per Q&A
                                  (with optional ac_candidates_json)
                              → mark_interview_phase_complete at phase end
                              ↓
3. Step 5.1 summary write       → write interview-summary.md
                              → clear_interview_progress (file is no longer needed)
                              ↓
4. samvil-seed                  → load_interview_progress (fallback to summary)
                              → consolidate ac_by_phase into seed.features[*].acceptance_criteria
```

---

## Compatibility

- **v4.18 → v4.19 forward**: existing `.samvil/interview-progress.json`
  files written by the v4.18 bash-`echo` pattern remain valid as long
  as they used the same JSONL shape. Any `{"phase": ..., "q": ..., "a": ...}`
  line missing a `type` field is skipped at replay time, so an
  in-flight v4.18 interview that upgrades mid-session simply restarts
  cleanly.
- **v4.19 → v4.18 backward**: not supported (bash echo can't read AC
  candidate entries). Downgrade requires deleting the file.

---

## Why JSONL (not a single JSON document)

Append-only crash safety. A truncated last line is skipped; valid
prefix is preserved. Compare to a JSON document where mid-write
corruption invalidates the whole file.

## Why MCP tools (not skill-side bash)

v4.18 used `echo '{...}' >> file`. This is a behavioral guarantee — the
LLM has to remember to append after each answer. Model drift, context
compaction, or a tool-permission decline silently breaks persistence.
v4.19 lifts this to a structural guarantee: the MCP wrapper always
writes (or returns ok=False; the caller can react).

---

## See also

- `mcp/samvil_mcp/interview_state.py` — implementation
- `mcp/tests/test_interview_state.py` — test suite (16 tests)
- `skills/samvil-interview/SKILL.md` — usage in Boot Sequence + Step 2 + Step 5
- `skills/samvil-seed/SKILL.md` — consume side (consolidation)
