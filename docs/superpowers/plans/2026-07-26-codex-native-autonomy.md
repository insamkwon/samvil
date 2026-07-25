# Codex Native Autonomy Implementation Plan

> **실행 원칙:** 각 Task는 실패하는 테스트를 먼저 작성하고, 구현으로 green을
> 만든 뒤, 명시적 경로만 stage하고 `bash scripts/pre-commit-check.sh` exit 0을
> 확인한 다음 한 개의 커밋으로 닫는다. 실패 테스트만 따로 커밋하거나
> `--no-verify`를 사용하지 않는다.

**Goal:** 개인 Codex skill은 bare name으로 보존하고 SAMVIL 소유 skill만
`samvil:` namespace로 노출하면서, `samvil:run` 한 번으로 같은 Codex task 안에서
stage가 자동 진행되고 중단 후에도 정확히 한 번만 안전하게 재개되는 v4.33.0을
구현한다.

**Architecture:** Codex plugin은 discovery와 public skill surface만 소유한다.
Codex는 internal stage instruction을 실행하고, MCP transition controller는 stage
claim, gate, event/session/claim/marker 전이와 복구를 소유한다. 파일 SSOT는
transition journal과 receipt를 포함해 task·process가 끊겨도 복구 가능한 근거를
남긴다. 기존 Claude Code stage corpus와 domain MCP tool은 복제하지 않고 재사용한다.

**Tech Stack:** Codex CLI 0.144.1 native plugin surface,
`.codex-plugin/plugin.json`, plugin-relative MCP JSON, Python 3.11+, FastMCP,
SQLite/aiosqlite, append-only JSONL, pytest, shell installer wrapper, actual
`codex exec`, Codex Desktop smoke.

**Approved design:**
`docs/superpowers/specs/2026-07-26-codex-native-autonomy-design.md`

---

## 0. Non-negotiable execution rules

1. 항목 1개 = 커밋 1개다. 아래 Task 번호가 기본 커밋 경계다.
2. 모든 Task는 `RED → GREEN → full pre-commit → commit` 순서를 지킨다.
3. 실패 테스트만 별도 커밋하지 않는다. `--no-verify`, 테스트 skip, gate 완화,
   stub/mock stage completion은 금지한다.
4. 새 파일이 pre-commit 스캔에 포함되도록 **명시적 `git add` 후** full
   pre-commit을 실행한다. `git add .`와 `git add -A`는 사용하지 않는다.
5. 저장소의 사용자 소유 untracked literal 경로 `$CODEX_HOME/`은 어떤 Task에서도
   읽기 외 수정·추가·삭제·stage·commit하지 않는다.
6. installer와 E2E fixture는 `tmp_path / "codex-home"` 또는 `mktemp -d`로 만든
   절대 경로를 사용한다. shell에서 확장되지 않은 literal `$CODEX_HOME`을
   working tree 아래에 만들지 않는다.
7. `scripts/setup-codex.sh`의 OpenCode/Gemini 경로는 Codex 변경 때문에 깨뜨리지
   않는다.
8. `resolve_stage_next_skill(..., "samvil-qa") -> None`의 기존 의미를 변경하지
   않는다. missing/corrupt QA 결과는 controller가 QA에 머물게 하며
   contract-stage-end gate를 우회하지 않는다.
9. correctness-critical MCP가 없거나 marker/state/journal 해석이 모호하면
   fail-closed다. read-only status만 파일 fallback을 허용한다.
10. 실제 Codex CLI와 Desktop 증거 전에는 `host.py`의 native capability를 먼저
    올리지 않는다.
11. push, force push, PR 생성은 이 계획의 구현 커밋 범위가 아니다. 최종 검증 후
    사용자가 별도로 결정한다.
12. 각 커밋 메시지는 Conventional Commit prefix와 친절한 한글 한 줄을 사용한다.

### Baseline before Task 1

```bash
git status --short --branch
bash scripts/pre-commit-check.sh
```

Expected:

- branch: `codex/codex-native-autonomy`
- tracked diff 없음
- 사용자 소유 `?? $CODEX_HOME/`만 그대로 남음
- full pre-commit exit 0

---

## 1. Code-first scope corrections

구현 전에 현재 코드를 기준으로 다음 경계를 고정한다.

1. `EventStore.save_event_and_update_stage()`와
   `delete_event_and_restore_stage()`에는 이미 DB event/session stage 원자성과
   보상 토대가 있다. 새 controller가 별도 competing event pipeline을 만들지
   않고 이를 확장한다.
2. 현재 `complete_stage()`는 DB/session + canonical events JSONL을 먼저 처리한 뒤
   claim을 best-effort로 쓴다. Codex 자동 loop에서는 claim/marker까지 포함한
   recoverable transition journal이 필요하다.
3. QA next stage의 실제 owner는 `qa_finalize._decide_next_skill()`과
   `chain_markers.resolve_stage_next_skill()`이다. static `qa → deploy`로
   덮어쓰지 않는다.
4. 현재 `orchestrator.PIPELINE_STAGES`, `host_adapters._SKILL_CHAIN`,
   `resume._STAGE_NEXT_SKILL`이 서로 다른 형태로 stage 정보를 중복한다. 새 catalog가
   canonical source가 되고 기존 public constant는 compatibility view로 남긴다.
5. 실제 Evolve spec-only 재진입은 Scaffold가 아니라 Build다.
   `skills/samvil-evolve/SKILL.md`의 기존 동작을 보존한다.
6. Brownfield Analyze는 terminal stage가 아니다. 사용자 결정에 따라 Interview,
   Seed, Design, QA로 갈 수 있는 checkpointed dynamic stage다.
7. `.claude-plugin/marketplace.json`의 plugin source `./`는 canonical repository
   root가 marketplace로 등록될 때는 정상이다. 현재 문제는 marketplace root가
   repository가 아니라 사용자 home으로 등록된 것이다.
8. `scripts/setup-codex.sh`가 전역 `~/.codex/AGENTS.md`와 absolute MCP block을
   만드는 legacy 동작은 Codex 경로에서만 retire한다.

---

## 2. Target file map

| Path | Action | Responsibility |
|---|---|---|
| `.codex-plugin/plugin.json` | Create | Codex-native plugin manifest |
| `.codex-mcp.json` | Create | Installed plugin root relative MCP launcher |
| `codex/skills/run/SKILL.md` | Create | Public same-task host driver entry |
| `codex/skills/resume/SKILL.md` | Create | Durable fail-closed resume entry |
| `codex/skills/status/SKILL.md` | Create | Fully read-only status entry |
| `mcp/samvil_mcp/codex_installer.py` | Create | Capability probe, inventory, migration plan and execution |
| `mcp/samvil_mcp/stage_catalog.py` | Create | Canonical stage and instruction policy |
| `mcp/samvil_mcp/transition_controller.py` | Create | Envelope, claim, journal, transition, recovery |
| `mcp/samvil_mcp/chain_markers.py` | Modify | v1.0 compatibility + v1.1 driver marker inspection |
| `mcp/samvil_mcp/event_store.py` | Modify | Durable claim/transition receipt storage |
| `mcp/samvil_mcp/claim_ledger.py` | Modify | Internal transition-id idempotent claim append |
| `mcp/samvil_mcp/server.py` | Modify | Thin MCP wrappers only |
| `mcp/samvil_mcp/host.py` | Modify late | Runtime-proven Codex capability declaration |
| `mcp/samvil_mcp/host_adapters.py` | Modify | `host_driver` strategy and catalog view |
| `mcp/samvil_mcp/orchestrator.py` | Modify | Catalog-backed compatibility view |
| `mcp/samvil_mcp/resume.py` | Modify | Controller recovery classification reuse |
| `scripts/setup-codex.sh` | Modify | Codex native path; preserve other hosts |
| `scripts/check-host-parity.py` | Modify | Runtime receipt-aware honesty |
| `scripts/codex-native-e2e.py` | Create | Actual CLI E2E and receipt generation |
| `hooks/validate-version-sync.sh` | Modify | Claude + Codex manifest version sync |
| `mcp/tests/test_codex_plugin.py` | Create | Manifest/MCP/public inventory contract |
| `mcp/tests/test_setup_codex.py` | Create | Installer planning and isolated mutation tests |
| `mcp/tests/test_stage_catalog.py` | Create | Catalog invariants and compatibility |
| `mcp/tests/test_transition_controller.py` | Create | CAS, atomicity, idempotency, recovery |
| `mcp/tests/test_codex_driver.py` | Create | Driver stop/continue integration contracts |
| `mcp/tests/test_codex_native_e2e.py` | Create | E2E harness/receipt validation |
| `docs/evidence/codex-native-autonomy/` | Create late | CLI/Desktop/runtime receipts |

---

## Wave A — Native packaging and safe ownership

### Task 1: Add the Codex plugin manifest and relative MCP launcher

**Files:**

- Create: `.codex-plugin/plugin.json`
- Create: `.codex-mcp.json`
- Create: `mcp/tests/test_codex_plugin.py`
- Modify: `hooks/validate-version-sync.sh`
- Modify: `scripts/pre-commit-check.sh`

- [ ] **Step 1: Write failing manifest tests**

Add tests asserting:

- Codex manifest exists and has `name == "samvil"`.
- version matches `.claude-plugin/plugin.json` and
  `mcp/samvil_mcp/__init__.py`.
- `skills == "./codex/skills/"` and `mcpServers == "./.codex-mcp.json"`.
- no `hooks` field or Claude-only `${CLAUDE_PLUGIN_ROOT}` reference exists.
- interface uses only fields observed in installed Codex manifest fixtures.
- `.codex-mcp.json` uses `cwd: "."` and a plugin-relative `./mcp` source.
- neither file contains an author-machine absolute path.
- version sync script fails when Codex manifest version is intentionally changed
  in an isolated copied fixture.

Run:

```bash
cd mcp
.venv/bin/python -m pytest tests/test_codex_plugin.py -q
```

Expected RED: Codex manifest and MCP declaration are absent.

- [ ] **Step 2: Implement the minimal verified manifest**

Use the current version `4.32.2`; do not bump the release yet. The MCP launcher
must work both from the repository and an installed plugin cache. Prefer the
locally verified shape:

```json
{
  "mcpServers": {
    "samvil-mcp": {
      "cwd": ".",
      "command": "uvx",
      "args": ["--from", "./mcp", "samvil-mcp"]
    }
  }
}
```

If this exact launcher fails the installed-root smoke, change the launcher based
on observed Codex behavior; never insert an absolute repository path.

- [ ] **Step 3: Extend version synchronization**

`hooks/validate-version-sync.sh` must compare:

1. `.claude-plugin/plugin.json`
2. `.codex-plugin/plugin.json`
3. `mcp/samvil_mcp/__init__.py`
4. README first version occurrence

A mismatch is an error, not a warning. Update the pre-commit section label to
name both host manifests.

- [ ] **Step 4: Run targeted tests and manifest parse smoke**

```bash
cd mcp
.venv/bin/python -m pytest tests/test_codex_plugin.py -q
cd ..
python3 -m json.tool .codex-plugin/plugin.json >/dev/null
python3 -m json.tool .codex-mcp.json >/dev/null
bash hooks/validate-version-sync.sh
```

- [ ] **Step 5: Stage explicitly, run the full gate, and commit**

```bash
git add .codex-plugin/plugin.json .codex-mcp.json \
  mcp/tests/test_codex_plugin.py hooks/validate-version-sync.sh \
  scripts/pre-commit-check.sh
bash scripts/pre-commit-check.sh
git commit -m "feat: Codex 전용 플러그인 매니페스트와 상대 경로 MCP 실행기를 추가한다"
```

Do not stage `$CODEX_HOME/`.

---

### Task 2: Build a read-only marketplace and namespace ownership planner

**Files:**

- Create: `mcp/samvil_mcp/codex_installer.py`
- Create: `mcp/tests/test_setup_codex.py`

- [ ] **Step 1: Write failing pure-function tests**

Cover:

- capability probe parses `codex plugin --help`, marketplace/plugin JSON, and
  feature output without relying on a single version string.
- canonical marketplace root is `Path.resolve()` of the SAMVIL repository.
- `$HOME`, filesystem root, and any ancestor of `~/.codex/skills` are rejected.
- symlinked unsafe roots are rejected after resolution.
- personal skill inventory records directory, frontmatter name, and content hash.
- bare personal names remain bare in the before/after inventory.
- exact canonical legacy SAMVIL copies are classified `generated_legacy`.
- byte-different legacy copies are classified `user_modified` and block mutation.
- known generated global AGENTS/direct MCP shapes are distinguished from ambiguous
  user-modified files.
- the planner produces actions and blockers without changing the filesystem.

Run:

```bash
cd mcp
.venv/bin/python -m pytest tests/test_setup_codex.py -q
```

Expected RED: `codex_installer` does not exist.

- [ ] **Step 2: Implement immutable inventory and migration-plan models**

Use dataclasses or typed dictionaries for:

- `CodexCapabilityProbe`
- `SkillInventoryEntry`
- `LegacyOwnership`
- `MigrationAction`
- `CodexInstallPlan`

The planner must be deterministic and serialize to JSON for receipts. It must not
accept user-facing labels as ownership proof; provenance requires known shape and
hash/content checks.

- [ ] **Step 3: Run targeted tests**

```bash
cd mcp
.venv/bin/python -m pytest tests/test_setup_codex.py -q
```

- [ ] **Step 4: Stage, full gate, commit**

```bash
git add mcp/samvil_mcp/codex_installer.py mcp/tests/test_setup_codex.py
bash scripts/pre-commit-check.sh
git commit -m "feat: Codex 마켓플레이스 소유권과 개인 스킬 보존 규칙을 검증한다"
```

---

### Task 3: Execute clean install and reversible legacy migration safely

**Files:**

- Modify: `mcp/samvil_mcp/codex_installer.py`
- Modify: `mcp/tests/test_setup_codex.py`
- Modify: `scripts/setup-codex.sh`
- Modify: `README.md`

- [ ] **Step 1: Add failing isolated integration tests**

Create a fake `codex` executable in `tmp_path/bin`, set an explicit temporary
`CODEX_HOME`, and record commands. Cover:

1. clean install
2. repeated install idempotency
3. update of an already-correct install
4. current home-root marketplace correction with JSON backup receipt
5. marketplace remove failure leaves the original registration recoverable
6. plugin add failure restores or reports the exact prior registration
7. exact generated global AGENTS migration only with `--migrate`
8. ambiguous global AGENTS blocks and remains byte-identical
9. exact generated direct MCP block migration only with `--migrate`
10. ambiguous direct MCP block blocks and remains byte-identical
11. exact legacy SAMVIL skill copies move to timestamped backup only with
    `--migrate`
12. user-modified `samvil*` copies block and remain byte-identical
13. unrelated personal skill inventory is unchanged after install/update/uninstall
14. uninstall removes only `samvil@samvil` registration/cache ownership
15. OpenCode and Gemini branches retain their current behavior

Tests must never point `CODEX_HOME` at the real user home or at the working tree.

- [ ] **Step 2: Implement the mutation executor**

Add CLI modes to `python -m samvil_mcp.codex_installer`:

```text
--check       read-only capability/inventory report
--install     clean install and safe registry correction
--migrate     include only proven legacy generated artifacts
--uninstall   remove plugin registration without personal skill deletion
--json        machine-readable receipt
```

Use atomic receipt writes and timestamped backups. On any ambiguous ownership,
stop before mutation and print exact path/hash/blocker. Never edit
`.claude-plugin/marketplace.json` in the user home; correct only the Codex registry
reference.

- [ ] **Step 3: Make the shell wrapper delegate only the Codex branch**

`scripts/setup-codex.sh codex` should:

1. verify/install uv
2. prepare the MCP environment
3. invoke the Python installer
4. run plugin/MCP/namespace smoke

It must stop copying global AGENTS or appending an absolute Codex MCP block.
OpenCode/Gemini branches remain isolated and covered by regression tests.

- [ ] **Step 4: Run targeted tests and shell syntax**

```bash
cd mcp
.venv/bin/python -m pytest tests/test_setup_codex.py -q
cd ..
bash -n scripts/setup-codex.sh
```

- [ ] **Step 5: Stage, full gate, commit**

```bash
git add mcp/samvil_mcp/codex_installer.py mcp/tests/test_setup_codex.py \
  scripts/setup-codex.sh README.md
bash scripts/pre-commit-check.sh
git commit -m "feat: 개인 설정을 보존하며 Codex 플러그인을 안전하게 설치하고 이전한다"
```

---

## Wave B — Canonical stages and trustworthy transitions

### Task 4: Introduce the canonical stage catalog without behavior changes

**Files:**

- Create: `mcp/samvil_mcp/stage_catalog.py`
- Create: `mcp/tests/test_stage_catalog.py`
- Modify: `mcp/samvil_mcp/host_adapters.py`
- Modify: `mcp/samvil_mcp/orchestrator.py`
- Modify: `mcp/samvil_mcp/resume.py`
- Modify: existing host/orchestrator/resume tests as compatibility assertions only

- [ ] **Step 1: Write characterization tests before moving data**

Pin the current behavior for:

- canonical stage names and state-stage mapping
- internal instruction path existence and repository containment
- static transitions Interview→Seed→Design→Scaffold→Build→QA
- Council opt-in and minimal-tier skip
- QA dynamic targets `{samvil-qa, samvil-deploy, samvil-evolve, samvil-retro}`
- Analyze checkpointed targets `{samvil-interview, samvil-seed, samvil-design,
  samvil-qa}`
- Evolve targets `{samvil-build, samvil-retro}`
- Deploy→Retro and Retro terminal behavior
- auxiliary Doctor/Update terminal behavior
- old `_SKILL_CHAIN`, `PIPELINE_STAGES`, and resume mapping views remain equivalent

Add traversal tests for `../`, symlink escape, absolute paths, unknown stages, and
invalid dynamic targets.

- [ ] **Step 2: Implement `StageSpec` and catalog APIs**

Required APIs:

```python
get_stage_spec(skill_name)
iter_stage_specs()
instruction_path_for(skill_name, repository_root)
validate_stage_transition(from_skill, to_skill)
state_stage_for(skill_name)
skill_for_state_stage(state_stage)
```

Dynamic route policy belongs in the catalog metadata, but QA decision logic remains
in `qa_finalize`; do not duplicate thresholds or verdict semantics.

- [ ] **Step 3: Replace duplicate data with compatibility views**

`host_adapters`, `orchestrator`, and `resume` import/derive from the catalog. Keep
legacy constants exported if current tests/callers import them.

- [ ] **Step 4: Run targeted suites**

```bash
cd mcp
.venv/bin/python -m pytest \
  tests/test_stage_catalog.py \
  tests/test_host_adapters.py \
  tests/test_orchestrator.py \
  tests/test_resume.py -q
```

- [ ] **Step 5: Stage, full gate, commit**

```bash
git add mcp/samvil_mcp/stage_catalog.py mcp/tests/test_stage_catalog.py \
  mcp/samvil_mcp/host_adapters.py mcp/samvil_mcp/orchestrator.py \
  mcp/samvil_mcp/resume.py mcp/tests/test_host_adapters.py \
  mcp/tests/test_orchestrator.py mcp/tests/test_resume.py
bash scripts/pre-commit-check.sh
git commit -m "refactor: 모든 호스트가 같은 단계 카탈로그와 전이 규칙을 사용하게 한다"
```

---

### Task 5: Add marker schema v1.1 while preserving v1.0 callers

**Files:**

- Modify: `mcp/samvil_mcp/chain_markers.py`
- Modify: `mcp/tests/test_chain_markers.py`
- Modify: `mcp/tests/test_chain_marker_e2e.py`
- Modify: `scripts/host-continuation-smoke.py`
- Modify: `references/host-continuation.md`

- [ ] **Step 1: Write failing schema/inspection tests**

Cover:

- v1.0 reads remain compatible.
- v1.1 requires `run_id`, non-negative integer `revision`, valid `status`,
  `chain_via="host_driver"`, host, stage, reason, and timestamp.
- booleans do not pass integer revision validation.
- unknown schema is `unsupported`, not silently treated as missing.
- malformed JSON is `corrupt`; absent file is `missing`.
- path and stage values are catalog-validated.
- atomic writer never writes the final path directly.
- existing `read_chain_marker()` still returns `None` for corrupt legacy callers.
- a new inspection API preserves the exact recovery classification.
- `resolve_stage_next_skill()` retains its existing `None` behavior.

- [ ] **Step 2: Implement explicit compatibility APIs**

Keep the existing writer default at v1.0 for non-driver callers. Add an internal
v1.1 builder/writer used only by the transition controller. Suggested API:

```python
inspect_chain_marker(project_root) -> MarkerInspection
build_driver_marker(...)
write_driver_marker(...)
```

Do not infer a trusted QA route from `None`.

- [ ] **Step 3: Update smoke documentation and validator**

The smoke script accepts both schemas, reports their execution semantics, and fails
on unknown schema or invalid revision/status.

- [ ] **Step 4: Run targeted tests**

```bash
cd mcp
.venv/bin/python -m pytest \
  tests/test_chain_markers.py tests/test_chain_marker_e2e.py \
  tests/test_ssot_hardening.py -q
```

- [ ] **Step 5: Stage, full gate, commit**

```bash
git add mcp/samvil_mcp/chain_markers.py mcp/tests/test_chain_markers.py \
  mcp/tests/test_chain_marker_e2e.py scripts/host-continuation-smoke.py \
  references/host-continuation.md
bash scripts/pre-commit-check.sh
git commit -m "feat: 기존 마커 호환성을 유지하며 재시도 가능한 v1.1 전이 마커를 추가한다"
```

---

### Task 6: Add read-only stage envelopes and idempotent stage claims

**Files:**

- Create: `mcp/samvil_mcp/transition_controller.py`
- Create: `mcp/tests/test_transition_controller.py`
- Modify: `mcp/samvil_mcp/event_store.py`
- Modify: `mcp/tests/test_event_store.py`

- [ ] **Step 1: Write failing envelope and begin-stage tests**

Cover:

- `run_id` reuses the durable session id; no parallel run registry is invented.
- envelope is read-only and reports `fresh`, `ready`, `in_progress`,
  `waiting_user`, `blocked`, `terminal`, or `recovering`.
- instruction path comes only from the stage catalog.
- `begin_stage` uses expected marker revision CAS.
- duplicate begin for the same run/stage/revision returns the same claim id.
- a conflicting run/stage claim is rejected without mutation.
- stale revision is rejected without mutation.
- begin writes v1.1 `in_progress` state only after a durable claim exists.
- marker write failure compensates the newly created claim.
- missing/corrupt/unsupported ambiguous state blocks.
- a user checkpoint envelope never auto-begins.

- [ ] **Step 2: Add durable stage claim storage**

Extend the EventStore schema with a narrowly scoped `stage_claims` table keyed by
`(session_id, stage, marker_revision)`. Store claim id, status, timestamps, and
completed transition id. Migration must be idempotent.

- [ ] **Step 3: Implement envelope and begin APIs**

Controller dependencies should be injectable in tests. Do not import FastMCP into
the controller. Hold the existing per-session process/file transition locks around
claim + marker coordination.

- [ ] **Step 4: Run targeted tests**

```bash
cd mcp
.venv/bin/python -m pytest \
  tests/test_transition_controller.py tests/test_event_store.py -q
```

- [ ] **Step 5: Stage, full gate, commit**

```bash
git add mcp/samvil_mcp/transition_controller.py \
  mcp/tests/test_transition_controller.py mcp/samvil_mcp/event_store.py \
  mcp/tests/test_event_store.py
bash scripts/pre-commit-check.sh
git commit -m "feat: 단계 실행 봉투와 중복 없는 실행 claim을 원자적으로 관리한다"
```

---

### Task 7: Commit stage transitions exactly once with crash recovery

**Files:**

- Modify: `mcp/samvil_mcp/transition_controller.py`
- Modify: `mcp/samvil_mcp/event_store.py`
- Modify: `mcp/samvil_mcp/claim_ledger.py`
- Modify: `mcp/tests/test_transition_controller.py`
- Modify: event-store and claim-ledger tests where needed

- [ ] **Step 1: Write failure-injection tests first**

For one trusted completion, inject failure at each boundary:

1. transition journal prepared, before DB transaction
2. DB event/session/claim receipt committed, before canonical event append
3. canonical event appended, before transition claim append
4. claim appended, before marker replace
5. marker replaced, before DB/journal acknowledgement

After each failure, rerun recovery/commit and assert:

- exactly one DB event
- exactly one canonical `.samvil/events.jsonl` row by transition/event id
- exactly one transition claim identity in `.samvil/claims.jsonl`
- one session-stage advancement
- marker revision increments exactly once
- duplicate completion returns the original committed receipt
- no later transition is rolled back by an older retry

Also cover concurrent commits, stale revision, wrong claim id, wrong stage,
unsupported marker schema, terminal marker cleanup, and two identical root-cause
failures triggering the circuit breaker.

- [ ] **Step 2: Define the durable transition protocol**

Use one active atomic file journal at `.samvil/transition-journal.json` plus a
durable transition receipt. The journal must contain `transition_id`, run/session,
claim, expected revision, from/to stage, event payload hash, claim payload hash,
marker payload, and phase.

Protocol:

```text
lock
  → validate claim/revision/gate/evidence
  → atomically write PREPARED journal
  → one SQLite transaction: event + session stage + claim status + pending receipt
  → idempotently materialize events JSONL by event_id
  → idempotently materialize claim by transition_id
  → atomically replace v1.1 marker
  → acknowledge DB receipt and close journal
unlock
```

Before the SQLite commit, failure removes the prepared journal and leaves no durable
transition. After SQLite commit, failure leaves a recoverable journal; it must not
perform an unsafe broad rollback. The next envelope/retry reconciles it before any
new stage begins.

- [ ] **Step 3: Add internal idempotent claim append**

Add an internal ClaimLedger API keyed by `meta.transition_id`. Do not weaken the
public claim type, evidence, Generator/Judge, or host-only checks.

- [ ] **Step 4: Keep QA routing fail-closed**

`commit_stage_transition` computes QA next stage from trusted materialized QA state.
Missing/corrupt/invalid QA evidence keeps the marker and session at QA and returns a
blocked receipt. It must not reinterpret `resolve_stage_next_skill() is None` as
Deploy.

- [ ] **Step 5: Run targeted and adversarial tests**

```bash
cd mcp
.venv/bin/python -m pytest \
  tests/test_transition_controller.py \
  tests/test_event_store.py \
  tests/test_claim_ledger.py \
  tests/test_claim_ledger_lock.py \
  tests/test_chain_markers.py -q
```

- [ ] **Step 6: Stage, full gate, commit**

```bash
git add mcp/samvil_mcp/transition_controller.py \
  mcp/samvil_mcp/event_store.py mcp/samvil_mcp/claim_ledger.py \
  mcp/tests/test_transition_controller.py mcp/tests/test_event_store.py \
  mcp/tests/test_claim_ledger.py mcp/tests/test_claim_ledger_lock.py \
  mcp/tests/test_chain_markers.py
bash scripts/pre-commit-check.sh
git commit -m "feat: 단계 전이를 장애 후에도 정확히 한 번만 완료하도록 보장한다"
```

---

### Task 8: Classify resume, ambiguous recovery, and read-only status

**Files:**

- Modify: `mcp/samvil_mcp/transition_controller.py`
- Modify: `mcp/samvil_mcp/resume.py`
- Modify: `mcp/tests/test_transition_controller.py`
- Modify: `mcp/tests/test_resume.py`

- [ ] **Step 1: Write the recovery matrix as failing table tests**

Cover every approved condition:

| Condition | Expected |
|---|---|
| no marker + no state | fresh |
| valid marker + matching state | ready |
| in-progress marker + same claim | resume same stage |
| stale marker revision | blocked |
| missing marker + one trusted receipt interpretation | reconstruct + receipt |
| corrupt marker + ambiguous state | blocked |
| marker/state mismatch + matching open journal | recover journal |
| marker/state mismatch without proof | blocked |
| MCP unavailable during status | file fallback `DEGRADED` |
| MCP unavailable during transition | blocked |
| terminal receipt | complete and no active marker |

Ensure status reads never create directories, markers, journals, events, or claims.

- [ ] **Step 2: Implement recovery as evidence-based classification**

Conversation memory and caller prose are never recovery evidence. Use marker,
project state, latest trusted event/transition receipt, and journal only. Marker
reconstruction writes a separate recovery receipt before replacing the marker.

- [ ] **Step 3: Make legacy `resume_session()` delegate classification**

Preserve its current return fields for compatibility and add structured status,
revision, stop reason, and recovery recommendation.

- [ ] **Step 4: Run targeted tests**

```bash
cd mcp
.venv/bin/python -m pytest \
  tests/test_transition_controller.py tests/test_resume.py -q
```

- [ ] **Step 5: Stage, full gate, commit**

```bash
git add mcp/samvil_mcp/transition_controller.py \
  mcp/samvil_mcp/resume.py mcp/tests/test_transition_controller.py \
  mcp/tests/test_resume.py
bash scripts/pre-commit-check.sh
git commit -m "feat: 중단 위치와 모호한 상태를 증거 기반으로 안전하게 복구한다"
```

---

### Task 9: Expose thin MCP tools for the Codex driver

**Files:**

- Modify: `mcp/samvil_mcp/server.py`
- Modify: `mcp/tests/test_orchestrator_mcp.py`
- Modify: `mcp/tests/test_server_tools_smoke.py`
- Modify: `mcp/tests/test_server_domain_split.py`
- Modify: async offload tests if filesystem work is exposed

- [ ] **Step 1: Write failing tool-surface tests**

Register and test exact wrappers:

```text
get_stage_envelope(project_root, host_name)
begin_stage(project_root, run_id, stage, expected_revision)
commit_stage_transition(project_root, run_id, stage,
                        expected_revision, claim_id, verdict,
                        evidence_json, requested_next_skill="")
```

Assertions:

- wrappers parse inputs and return controller JSON without stage logic.
- filesystem/SQLite work is offloaded appropriately.
- invalid JSON or booleans-as-revisions fail closed.
- requested dynamic next stage is catalog-valid and, where applicable,
  backed by trusted user approval or deterministic QA policy.
- all tools appear in the MCP import/tool registry.

- [ ] **Step 2: Implement thin wrappers**

Do not move transition logic into `server.py`. Reuse existing store singleton and
health logging. Exact tool errors must remain machine-readable.

- [ ] **Step 3: Run targeted tests and import smoke**

```bash
cd mcp
.venv/bin/python -m pytest \
  tests/test_orchestrator_mcp.py \
  tests/test_server_tools_smoke.py \
  tests/test_server_domain_split.py \
  tests/test_async_file_offload.py -q
.venv/bin/python -c "from samvil_mcp import server; print(len(server.mcp._tool_manager._tools))"
```

- [ ] **Step 4: Stage, full gate, commit**

```bash
git add mcp/samvil_mcp/server.py mcp/tests/test_orchestrator_mcp.py \
  mcp/tests/test_server_tools_smoke.py mcp/tests/test_server_domain_split.py \
  mcp/tests/test_async_file_offload.py
bash scripts/pre-commit-check.sh
git commit -m "feat: Codex 드라이버가 사용할 신뢰 가능한 단계 전이 MCP 도구를 공개한다"
```

---

## Wave C — Codex public UX and same-task driver

### Task 10: Add only the three public Codex skills

**Files:**

- Create: `codex/skills/run/SKILL.md`
- Create: `codex/skills/resume/SKILL.md`
- Create: `codex/skills/status/SKILL.md`
- Modify: `mcp/tests/test_codex_plugin.py`
- Modify: skill wiring/forward-integrity scripts only if they do not yet scan
  plugin-owned Codex skills

- [ ] **Step 1: Write failing public-surface tests**

Assert:

- the plugin public directory contains exactly `run`, `resume`, `status`.
- frontmatter names are bare `run`, `resume`, `status`; the plugin owns the
  `samvil:` prefix.
- no internal `samvil-interview`, `samvil-build`, etc. directory is exposed.
- run/resume cite all three transition MCP tools by exact registered names.
- status cites only read-only tools and contains no write/begin/commit command.
- all three point internal instructions through catalog-returned paths, never
  caller-provided paths.
- run description covers Korean/English natural-language SAMVIL start/resume
  intent without hijacking unrelated build requests.

- [ ] **Step 2: Write `samvil:run` driver instructions**

The loop must be explicit:

```text
read envelope
  → stop if waiting/blocked/terminal
  → begin with expected revision
  → read exact catalog instruction completely
  → execute that stage
  → commit through MCP
  → continue from returned committed envelope
```

It must never infer completion from its own prose or edit marker/state directly.

- [ ] **Step 3: Write resume and status instructions**

Resume first reconciles/reclassifies durable state and reruns the same stage when
completion is not proven. Status is read-only and clearly separates confirmed,
recoverable, degraded, blocked, and unverified information.

- [ ] **Step 4: Run targeted wiring tests**

```bash
cd mcp
.venv/bin/python -m pytest tests/test_codex_plugin.py -q
cd ..
python3 scripts/check-skill-wiring.py
python3 scripts/check-skill-forward-integrity.py
```

- [ ] **Step 5: Stage, full gate, commit**

```bash
git add codex/skills/run/SKILL.md codex/skills/resume/SKILL.md \
  codex/skills/status/SKILL.md mcp/tests/test_codex_plugin.py \
  scripts/check-skill-wiring.py scripts/check-skill-forward-integrity.py
bash scripts/pre-commit-check.sh
git commit -m "feat: Codex 사용자에게 실행 재개 상태 확인 세 가지 스킬만 제공한다"
```

Only add checker files to `git add` if they actually changed.

---

### Task 11: Verify the same-task driver state machine and circuit breaker

**Files:**

- Create: `mcp/tests/test_codex_driver.py`
- Modify: `mcp/samvil_mcp/transition_controller.py` only for missing deterministic
  driver decisions
- Modify: `codex/skills/run/SKILL.md`
- Modify: `codex/skills/resume/SKILL.md`

- [ ] **Step 1: Write integration tests with real controller state**

Use temporary projects, real EventStore/controller, and a test executor that only
records which real instruction path would be handed to Codex. It may not return
hardcoded completion without creating the required real stage evidence.

Cover:

1. fresh orchestrator → Interview
2. Interview → Seed automatic continue
3. Seed → Design default
4. Seed → Council opt-in
5. Design → Scaffold → Build
6. Build → QA
7. QA revise remains QA
8. QA pass follows trusted dynamic route
9. Restate/irreversible checkpoint yields without advancing
10. process stop before begin, during stage, during commit, and after commit
11. resume produces no duplicate transition
12. same root-cause envelope twice trips the circuit breaker
13. compaction/re-entry uses the durable envelope rather than conversation history

- [ ] **Step 2: Tighten driver instructions from test findings**

The driver keeps only bounded per-loop information in conversation: run id, stage,
claim id, expected revision, and exact stop reason. All other continuation data is
reread from MCP/files after compaction.

- [ ] **Step 3: Run targeted tests**

```bash
cd mcp
.venv/bin/python -m pytest \
  tests/test_codex_driver.py tests/test_transition_controller.py -q
```

- [ ] **Step 4: Stage, full gate, commit**

```bash
git add mcp/tests/test_codex_driver.py \
  mcp/samvil_mcp/transition_controller.py codex/skills/run/SKILL.md \
  codex/skills/resume/SKILL.md
bash scripts/pre-commit-check.sh
git commit -m "test: Codex가 중단과 컨텍스트 압축 뒤에도 같은 작업에서 안전하게 이어지는지 검증한다"
```

---

### Task 12: Migrate the legacy `complete_stage` path to the shared controller

**Files:**

- Modify: `mcp/samvil_mcp/server.py`
- Modify: relevant Claude stage skills and Codex command references
- Modify: contract hook tests, orchestrator MCP tests, host parity tests

- [ ] **Step 1: Write compatibility tests before changing the wrapper**

Pin that:

- `complete_stage` retains its existing external signature and response fields.
- it delegates trusted persistence to the controller.
- Claude Skill-tool chaining still receives the correct next stage.
- its recovery marker is a fallback, not a manual Codex executor.
- QA dynamic next stage no longer allows DB session stage and marker to disagree.
- claim failure cannot be silently reported as a completed trusted transition.
- existing contract-stage-start/end gates remain mandatory.

- [ ] **Step 2: Thin the compatibility wrapper**

Map existing stage/verdict calls into the shared controller. Update stage instructions
so they do not perform a second competing marker transition. Claude may immediately
invoke the returned next Skill after a committed transition; the marker remains only
as recovery evidence.

- [ ] **Step 3: Run Claude/Codex shared-path regression tests**

```bash
cd mcp
.venv/bin/python -m pytest \
  tests/test_orchestrator_mcp.py \
  tests/test_contract_hooks.py \
  tests/test_skill_wiring.py \
  tests/test_host_parity.py \
  tests/test_codex_driver.py -q
```

- [ ] **Step 4: Stage, full gate, commit**

Stage only the files actually changed, then:

```bash
bash scripts/pre-commit-check.sh
git commit -m "refactor: Claude와 Codex가 같은 신뢰 전이 컨트롤러를 사용하게 한다"
```

---

## Wave D — Actual runtime proof

### Task 13: Build and run the real Codex CLI E2E harness

**Files:**

- Create: `scripts/codex-native-e2e.py`
- Create: `mcp/tests/test_codex_native_e2e.py`
- Create: `docs/evidence/codex-native-autonomy/cli-runtime.json`
- Create: `docs/evidence/codex-native-autonomy/cli-runtime.md`

- [ ] **Step 1: Write harness contract tests**

Validate that the harness:

- calls the real `codex` binary and records `codex --version`.
- uses Python `subprocess.run(..., timeout=...)`, not GNU `timeout`.
- creates projects under `mktemp`/temporary directories.
- redacts auth/config secrets from JSONL output.
- captures command, exit code, task/session id, starting/ending marker revision,
  event ids, transition ids, and artifact hashes.
- rejects mock/stub completion and hardcoded PASS receipts.
- validates receipt schema and current git commit.
- never targets the repository literal `$CODEX_HOME/` path.

- [ ] **Step 2: Implement dry-run and real modes**

```text
--check          environment/plugin/MCP readiness only
--scenario NAME  run one scenario
--all            run required matrix
--repeat N       repeat full green scenarios
--receipt PATH   write sanitized machine-readable evidence
```

- [ ] **Step 3: Safely install/update the plugin on the actual Codex profile**

Before mutation, save installer plan and personal skill inventory receipt. Run the
installer only if there are no ambiguous blockers. Compare personal inventory after
installation and stop immediately on any drift.

- [ ] **Step 4: Run required actual scenarios**

1. greenfield web minimal
2. greenfield mobile-app standard with Expo web/Playwright evidence
3. brownfield analyze → selected build path
4. Interview interruption + `codex exec resume`
5. Build interruption + resume
6. QA missing/corrupt fail-closed
7. marker stale/corrupt recovery
8. MCP process failure/restart
9. duplicate completion replay
10. three repeated greenfield end-to-end runs

External deployment is not performed automatically. The run stops at its explicit
deployment/user checkpoint after QA evidence is committed.

- [ ] **Step 5: Validate receipts and targeted tests**

```bash
python3 scripts/codex-native-e2e.py --check
cd mcp
.venv/bin/python -m pytest tests/test_codex_native_e2e.py -q
```

Then run the real matrix with a bounded timeout and preserve sanitized output.

- [ ] **Step 6: Stage, full gate, commit**

```bash
git add scripts/codex-native-e2e.py mcp/tests/test_codex_native_e2e.py \
  docs/evidence/codex-native-autonomy/cli-runtime.json \
  docs/evidence/codex-native-autonomy/cli-runtime.md
bash scripts/pre-commit-check.sh
git commit -m "test: 실제 Codex CLI에서 자동 진행 중단 복구 중복 방지를 끝까지 검증한다"
```

If the same runtime failure repeats twice, stop and report the exact blocker instead
of weakening the harness.

---

### Task 14: Capture Codex Desktop proof and enable runtime-proven capability

**Files:**

- Create: `docs/evidence/codex-native-autonomy/desktop-smoke.md`
- Add screenshot/receipt files under the same evidence directory if used
- Modify: `mcp/samvil_mcp/host.py`
- Modify: `mcp/samvil_mcp/host_adapters.py`
- Modify: `scripts/check-host-parity.py`
- Modify: `mcp/tests/test_host.py`
- Modify: `mcp/tests/test_host_adapters.py`
- Modify: `mcp/tests/test_host_parity.py`

- [ ] **Step 1: Write receipt-aware capability tests**

Before valid current receipts, parity output must continue to say `UNTESTED` and
tests must reject a premature capability declaration. A valid CLI + Desktop receipt
allows the target declaration:

```text
skill_invocation=plugin_driver
chain_via=host_driver
file_marker_handoff=true
native_task_update=true
parallel_agents=false
```

- [ ] **Step 2: Run the actual Desktop smoke**

In a fresh/restarted Codex Desktop task verify:

1. `samvil@samvil` installed and enabled
2. personal skills display bare names
3. only SAMVIL plugin skills use `samvil:`
4. only `samvil:run`, `samvil:resume`, `samvil:status` are public
5. natural-language SAMVIL request selects the run entry
6. task close/reopen resumes from durable state
7. status is read-only
8. user checkpoint does not auto-advance

Record app version, plugin version, repository commit, task id, observed result, and
screenshots where useful. Separate confirmed observations from manual inference.

- [ ] **Step 3: Update host capability and parity honesty**

`check-host-parity.py` validates receipt schema/version/commit and enumerates any
remaining untested host surface. Do not convert Gemini/OpenCode native execution to
green.

- [ ] **Step 4: Run targeted tests**

```bash
cd mcp
.venv/bin/python -m pytest \
  tests/test_host.py tests/test_host_adapters.py tests/test_host_parity.py -q
cd ..
python3 scripts/check-host-parity.py --strict
```

- [ ] **Step 5: Stage, full gate, commit**

Stage exact evidence and changed code files, then:

```bash
bash scripts/pre-commit-check.sh
git commit -m "feat: 실제 Codex CLI와 Desktop 증거를 바탕으로 네이티브 실행을 활성화한다"
```

---

## Wave E — Release synchronization and final review

### Task 15: Synchronize v4.33.0 docs, evidence, and release gates

**Files:**

- Modify: `.claude-plugin/plugin.json`
- Modify: `.codex-plugin/plugin.json`
- Modify: `mcp/samvil_mcp/__init__.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `AGENTS.md`
- Modify: `references/host-continuation.md`
- Modify: `references/troubleshooting-codex.md`
- Modify: approved design/plan checkboxes or completion evidence
- Create/modify final evidence summary under `docs/evidence/codex-native-autonomy/`

- [ ] **Step 1: Write failing release-sync assertions**

Extend tests/checks to require:

- both manifests, MCP package, README badge, and changelog release are `4.33.0`.
- Codex setup docs use native plugin install and do not copy global AGENTS.
- docs do not claim all personal skills are SAMVIL-owned.
- public Codex skill docs mention only run/resume/status.
- host continuation clearly distinguishes execution from recovery.
- real runtime receipt remains current for the release candidate commit or records
  the exact pre-release commit plus final code-only delta justification.

- [ ] **Step 2: Update user-facing documentation**

Explain:

- what changed from manual marker chaining
- why only SAMVIL skills retain the prefix
- clean install, safe migration, status, resume, uninstall
- fail-closed and user-checkpoint behavior
- Claude Code compatibility and remaining OpenCode/Gemini limitations
- multi-agent autonomy remains a later release

- [ ] **Step 3: Record exact completion evidence**

For every Task commit, add:

- commit hash
- exact `file:line` evidence
- targeted test result
- full pre-commit result
- runtime receipt reference where applicable

- [ ] **Step 4: Run final adversarial verification**

```bash
bash scripts/pre-commit-check.sh
cd mcp
.venv/bin/python -m pytest tests/ -q
cd ..
python3 scripts/codex-native-e2e.py --check
python3 scripts/check-host-parity.py --strict
python3 scripts/check-skill-wiring.py
python3 scripts/check-skill-forward-integrity.py
git diff main...HEAD --check
git status --short
```

Review specifically:

- personal skill namespace drift
- home-root marketplace recurrence
- symlink/ancestor path bypass
- marker revision ABA/stale completion
- journal crash boundaries
- duplicate event/claim/marker records
- user checkpoint bypass
- QA missing/corrupt fallback
- `resolve_stage_next_skill(None)` semantic regression
- Claude hook gate bypass
- actual vs structural host parity claims
- accidental `$CODEX_HOME/` staging

- [ ] **Step 5: Run `samvil:pre-pr-review` R3 read-only**

Read the full skill file first. Any real P1/P2 receives a new independent TDD commit,
full pre-commit, and re-review. The review itself does not edit, commit, push, or post
GitHub comments.

- [ ] **Step 6: Stage, full gate, and release-doc commit**

```bash
git add .claude-plugin/plugin.json .codex-plugin/plugin.json \
  mcp/samvil_mcp/__init__.py README.md CHANGELOG.md AGENTS.md \
  references/host-continuation.md references/troubleshooting-codex.md \
  docs/superpowers/specs/2026-07-26-codex-native-autonomy-design.md \
  docs/superpowers/plans/2026-07-26-codex-native-autonomy.md \
  docs/evidence/codex-native-autonomy
bash scripts/pre-commit-check.sh
git commit -m "docs: Codex 네이티브 실행 v4.33.0의 사용법과 검증 증거를 동기화한다"
```

Do not stage `$CODEX_HOME/`. Do not push in this Task.

---

## 3. Definition of done

Implementation is complete only when all statements below have persisted evidence.

- [ ] Personal skill inventory is byte/hash-equivalent before and after install.
- [ ] Only SAMVIL plugin skills appear with the `samvil:` prefix.
- [ ] Public Codex surface is exactly run/resume/status.
- [ ] A trusted completed stage continues in the same Codex task automatically.
- [ ] User checkpoint, BLOCK, corrupt state, or critical MCP failure stops the loop.
- [ ] Restart/resume creates no duplicate event, claim, session advancement, or marker
      revision.
- [ ] Failure injection passes at every transition journal boundary.
- [ ] QA missing/corrupt evidence remains in QA without changing
      `resolve_stage_next_skill()` semantics.
- [ ] Clean install, repeat install, update, migration, and uninstall preserve
      unrelated user-owned paths.
- [ ] Actual Codex CLI scenario matrix passes, including three repeated runs.
- [ ] Actual Codex Desktop smoke passes after restart/reopen.
- [ ] Claude Code plugin and stage chain regressions pass.
- [ ] Host parity reports structural proof and runtime proof separately.
- [ ] Full pre-commit exits 0 before every commit.
- [ ] R3 review has no unresolved P1/P2.
- [ ] Final working tree contains no accidental tracked `$CODEX_HOME/` content.

---

## 4. Expected commit sequence

1. `feat: Codex 전용 플러그인 매니페스트와 상대 경로 MCP 실행기를 추가한다`
2. `feat: Codex 마켓플레이스 소유권과 개인 스킬 보존 규칙을 검증한다`
3. `feat: 개인 설정을 보존하며 Codex 플러그인을 안전하게 설치하고 이전한다`
4. `refactor: 모든 호스트가 같은 단계 카탈로그와 전이 규칙을 사용하게 한다`
5. `feat: 기존 마커 호환성을 유지하며 재시도 가능한 v1.1 전이 마커를 추가한다`
6. `feat: 단계 실행 봉투와 중복 없는 실행 claim을 원자적으로 관리한다`
7. `feat: 단계 전이를 장애 후에도 정확히 한 번만 완료하도록 보장한다`
8. `feat: 중단 위치와 모호한 상태를 증거 기반으로 안전하게 복구한다`
9. `feat: Codex 드라이버가 사용할 신뢰 가능한 단계 전이 MCP 도구를 공개한다`
10. `feat: Codex 사용자에게 실행 재개 상태 확인 세 가지 스킬만 제공한다`
11. `test: Codex가 중단과 컨텍스트 압축 뒤에도 같은 작업에서 안전하게 이어지는지 검증한다`
12. `refactor: Claude와 Codex가 같은 신뢰 전이 컨트롤러를 사용하게 한다`
13. `test: 실제 Codex CLI에서 자동 진행 중단 복구 중복 방지를 끝까지 검증한다`
14. `feat: 실제 Codex CLI와 Desktop 증거를 바탕으로 네이티브 실행을 활성화한다`
15. `docs: Codex 네이티브 실행 v4.33.0의 사용법과 검증 증거를 동기화한다`

Review findings, if any, are appended as separate commits after Task 15 rather than
folded into unrelated history.
