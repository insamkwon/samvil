# Codex Native Autonomy — Design Spec

**Date:** 2026-07-26

**Status:** Approved for implementation planning

**Target release:** v4.33.0 candidate

**Primary host:** Codex CLI and Codex Desktop

**Compatibility host:** Claude Code

---

## Implementation status — 2026-07-26

The plugin surface, shared transition controller, idempotent receipt replay,
journal recovery, safe native installer, and Desktop MCP retry have been
implemented. The candidate remains evidence-limited: Codex CLI runtime is
`blocked_auth`, Claude has plugin/MCP smoke only, and the full host scenario
matrices are not implemented. The actual installer supports checked native install
and marketplace-root correction, while legacy `--migrate` remains explicitly
blocked until provenance actions are wired. These gaps block a claim of complete
native parity but do not invalidate the controller and Desktop manual evidence.

---

## 1. Goal

SAMVIL을 Codex의 일급(first-class) 플러그인과 실행 호스트로 만든다.

사용자는 Codex에서 한 번만 SAMVIL을 시작하면 Interview → Seed → Design →
Scaffold → Build → QA 흐름이 같은 task 안에서 자동으로 이어져야 한다. Codex를
종료하거나 task가 compaction된 뒤에도 `.samvil/*` SSOT에서 정확히 재개되어야
한다.

동시에 skill namespace를 소유권 경계로 바로잡는다.

```text
개인 skill                   SAMVIL plugin skill
pre-pr-review               samvil:run
commit                      samvil:resume
data-analyze                samvil:status
```

핵심 사용자 경험은 다음과 같다.

```text
사용자: SAMVIL로 할 일 관리 앱 만들어줘
  → samvil:run
  → Interview
  → Seed
  → Design
  → Scaffold
  → Build
  → QA
  → 사용자 결정, BLOCK, 또는 terminal stage에서만 정지
```

---

## 2. Why now

### 2.1 Codex continuation은 현재 수동 호환 계층이다

현재 `mcp/samvil_mcp/host.py`는 Codex를 다음처럼 선언한다.

- `skill_invocation="manual"`
- `parallel_agents=False`
- `chain_via="file_marker"`

`skills/samvil/SKILL.md`도 Codex 계열 host에서 marker를 쓴 뒤 사용자에게 다음
skill을 수동 호출하도록 요구한다. `.samvil/next-skill.json`은 결정적 복구
정보를 제공하지만 stage를 실제로 실행하는 host driver는 아니다.

### 2.2 구조 parity와 실제 실행 parity가 분리되어 있다

`scripts/check-host-parity.py`는 Claude/Codex instruction 문서의 존재, core MCP
tool, chain target을 검사한다. 그러나 실제 Codex stage 실행은 명시적으로
`UNTESTED`다. green structural check를 native parity의 증거로 사용할 수 없다.

### 2.3 SAMVIL marketplace가 개인 skill 영역을 삼키고 있다

현재 Codex가 고려하는 `samvil` marketplace root는 SAMVIL 저장소가 아니라
사용자 홈이다. marketplace의 plugin source가 `./`이므로 `~/.codex/skills/*`
개인 skill까지 SAMVIL plugin 소유로 해석된다.

그 결과 실제 frontmatter name이 `pre-pr-review`, `commit`, `imagegen`이어도
Codex UI에는 다음처럼 보인다.

```text
samvil:pre-pr-review
samvil:commit
samvil:imagegen
```

### 2.4 Codex는 이미 필요한 native capability를 제공한다

현재 설치된 Codex CLI는 다음 capability를 제공한다.

- stable plugin marketplace/install surface
- `.codex-plugin/plugin.json`
- plugin-owned skills와 MCP servers
- stable multi-agent and hooks capabilities
- saved task resume

따라서 전역 AGENTS 복사와 수동 marker handoff를 계속 확장하기보다 Codex의
native plugin boundary와 agent loop를 사용하는 것이 더 단순하고 정확하다.

---

## 3. Final decisions

| Area | Decision |
|---|---|
| Primary product host | Codex CLI + Codex Desktop |
| Claude Code | 기존 native 경로를 유지하는 compatibility host |
| Personal skills | `~/.codex/skills/*`의 bare name 유지 |
| SAMVIL skills | SAMVIL plugin 소유 skill에만 `samvil:` namespace 적용 |
| Public Codex skills | `samvil:run`, `samvil:resume`, `samvil:status` |
| Stage skills | Codex 사용자 목록에서는 내부화; driver가 instruction을 로드 |
| Same-task continuation | 기본 ON |
| Cross-task continuation | marker/state/event 기반 resume |
| Stage transition owner | MCP transition controller 단독 소유 |
| Critical gate fallback | MCP unavailable이면 fail-closed |
| Read-only fallback | 파일 SSOT로 graceful degradation 허용 |
| Existing marker | recovery SSOT로 유지, execution mechanism 역할은 제거 |
| User approval authority | v4.33에서는 trusted gate override를 발급하지 않음 |
| Multi-agent execution | 이번 release의 실행 목표가 아님; capability foundation만 보존 |
| Target version | 사용자 경로가 바뀌므로 v4.33.0 후보 |

---

## 4. Non-goals

이번 설계에서 하지 않는 것:

1. Ouroboros식 TaskGraph/AgentPool 병렬 실행을 함께 구현하지 않는다.
2. `safe / parallel / autonomous` 전체 실행 모드를 이번 release에 넣지 않는다.
3. Claude Code의 기존 stage skill 체인을 제거하거나 재설계하지 않는다.
4. Gemini/OpenCode native parity까지 범위를 확장하지 않는다.
5. 모든 host instruction 문서를 한 번에 통합 리팩터링하지 않는다.
6. 개인 skill의 이름, 내용, 디렉터리를 SAMVIL installer가 임의로 수정하지 않는다.
7. Codex plugin namespace 자체를 제거하지 않는다.
8. green CI만으로 Codex native support 완료를 선언하지 않는다.
9. stub, mock stage executor, hardcoded completion으로 E2E를 통과시키지 않는다.

---

## 5. Architectural principle

> **Plugin owns discovery. MCP owns transition. Files own recovery. Codex owns execution.**

- **Plugin**은 SAMVIL skill과 MCP를 Codex에 정확한 namespace로 노출한다.
- **MCP**는 stage 시작, gate 검증, 완료, 다음 marker 기록의 원자적 경계를 소유한다.
- **Files**는 host와 task가 바뀌어도 복구할 수 있는 durable SSOT다.
- **Codex**는 현재 stage instruction을 수행하고 같은 task에서 다음 stage로 이어간다.

Codex prompt나 driver skill은 stage 완료를 추측하지 않는다. MCP가 반환한
transition verdict만 신뢰한다.

---

## 6. Target architecture

```text
Codex plugin registry
  └─ samvil@samvil
      ├─ samvil:run
      ├─ samvil:resume
      ├─ samvil:status
      └─ samvil-mcp
              │
              ▼
      Codex Host Driver
              │
      get_stage_envelope
              │
              ▼
      Internal Codex stage instruction
              │
      existing deterministic MCP tools
              │
              ▼
      commit_stage_transition
              │
      DB session + event + claim + project.state + marker + receipt
              │
              ├─ next stage → loop
              ├─ user checkpoint → wait
              ├─ blocked → stop and report
              └─ terminal → complete
```

---

## 7. Host-specific plugin packaging

### 7.1 Keep separate host manifests

```text
.claude-plugin/plugin.json  # Claude Code manifest
.codex-plugin/plugin.json   # Codex manifest
```

`.claude-plugin/plugin.json`은 기존 Claude Code skill/hook surface를 유지한다.

새 `.codex-plugin/plugin.json`은 Codex에서 검증된 field만 사용한다.

```json
{
  "name": "samvil",
  "version": "4.33.0",
  "description": "Codex-first trustworthy app-building harness.",
  "skills": "./codex/skills/",
  "mcpServers": "./.codex-mcp.json",
  "interface": {
    "displayName": "SAMVIL",
    "shortDescription": "Interview, build, verify, and resume apps in Codex",
    "developerName": "insam",
    "category": "Developer Tools",
    "capabilities": ["Interactive", "Read", "Write"]
  }
}
```

Exact interface metadata는 implementation 시 Codex manifest fixture와 schema test로
검증한다. 지원이 확인되지 않은 Claude-only field를 Codex manifest에 복사하지
않는다.

### 7.2 Codex MCP launcher

현재 `.mcp.json`의 `${CLAUDE_PLUGIN_ROOT}`는 Codex-native manifest에서 사용하지
않는다. Codex용 `.codex-mcp.json`은 plugin root 상대 경로와 `cwd="."`를
사용한다.

MCP launcher 요구사항:

1. author machine absolute path 금지
2. 설치된 plugin root 기준으로 Python 환경 해석
3. repository-local development install과 cached plugin install 모두 지원
4. 같은 interpreter로 parent runner와 child release check 실행
5. dependency bootstrap 실패 시 정확한 repair command 출력

### 7.3 Plugin hooks limitation

Codex의 host hooks capability와 plugin manifest hook 설치는 동일하지 않다.
correctness-critical gate를 plugin hook에 두지 않는다.

- stage gate와 transition: MCP 필수
- event/claim consistency: MCP 필수
- destructive action jurisdiction: MCP + Codex permission boundary
- optional telemetry/log convenience: host hook 사용 가능

Codex hook이 설치되지 않아도 stage correctness가 달라지면 안 된다.

---

## 8. Namespace ownership

### 8.1 Desired inventory

```text
~/.codex/skills/pre-pr-review/SKILL.md  → pre-pr-review
~/.codex/skills/commit/SKILL.md         → commit
~/.codex/skills/data-analyze/SKILL.md   → data-analyze

<samvil-plugin>/codex/skills/run        → samvil:run
<samvil-plugin>/codex/skills/resume     → samvil:resume
<samvil-plugin>/codex/skills/status     → samvil:status
```

### 8.2 Invariants

1. SAMVIL install/update/uninstall 전후 개인 skill inventory가 동일해야 한다.
2. 개인 skill에 `samvil:` prefix가 붙으면 설치 실패다.
3. SAMVIL public skill에 plugin namespace가 없으면 설치 실패다.
4. plugin marketplace root는 resolved SAMVIL repository/plugin root여야 한다.
5. marketplace root가 `$HOME` 또는 `.codex/skills`의 ancestor면 설치를 차단한다.
6. namespace 문제를 alias skill 복제로 숨기지 않는다.
7. user-owned modified skill은 자동 이동·삭제하지 않는다.

### 8.3 Legacy duplicate handling

`~/.codex/skills/samvil*`에 기존 stage copy가 남아 있을 수 있다.

- repo canonical copy와 byte-for-byte/hash 일치: SAMVIL-generated legacy candidate
- 내용이 다름: user-modified candidate

기본 설치는 어느 쪽도 삭제하지 않는다. exact legacy candidate는 reversible
`--migrate` 경로에서만 timestamped backup으로 이동한다. user-modified candidate가
plugin skill과 충돌하면 path와 hash를 보고하고 설치를 차단한다.

---

## 9. Installer and migration

### 9.1 Current behavior to retire

현재 `scripts/setup-codex.sh`는 다음 legacy 동작을 한다.

- `AGENTS.md`를 `~/.codex/AGENTS.md`로 전역 복사
- `~/.codex/config.toml`에 absolute Python path MCP block append
- Codex native plugin install 없이 integration을 구성

### 9.2 New installer flow

```text
capability probe
  → personal skill inventory snapshot
  → current marketplace root inspect
  → legacy registration diagnosis
  → reversible backup
  → public skills/controller readiness verify
  → correct repository marketplace add
  → samvil@samvil install/enable
  → MCP import/stdio smoke
  → namespace inventory compare
  → Codex plugin/skill/status smoke
```

설치 구현은 두 시점으로 분리한다. 초반에는 read-only planner와 격리된 fake Codex
환경의 reversible executor까지만 만든다. 실제 `scripts/setup-codex.sh codex` 활성화와
사용자 profile 설치는 transition MCP와 public `run/resume/status`가 모두 구현된 뒤에만
허용한다. manifest가 가리키는 `codex/skills/` root는 첫 커밋부터 tracked 상태여야 하지만,
미완성 stub skill을 임시로 공개하지 않는다.

### 9.3 Capability-based detection

버전 문자열 하나만으로 native support를 판단하지 않는다. 다음 명령과 feature를
probe한다.

- `codex plugin --help`
- `codex plugin marketplace list --json`
- `codex plugin list --json`
- Codex plugin feature stable 여부
- MCP plugin dependency load 여부

필수 capability가 없으면 legacy mode로 자동 위장하지 않는다. `DEGRADED`로
보고하고 지원 Codex upgrade command를 제시한다.

### 9.4 Marketplace correction

Codex registry의 `samvil` marketplace root가 canonical root와 다르면:

1. 현재 marketplace/plugin inventory를 JSON receipt로 backup
2. `codex plugin marketplace remove samvil`
3. canonical repository root를 `codex plugin marketplace add`로 등록
4. `codex plugin add samvil@samvil`
5. resolved plugin path와 version 검증

원본 `~/.claude-plugin/marketplace.json` 파일 자체는 Codex migration이 삭제하거나
수정하지 않는다. Codex registry reference만 교정한다.

### 9.5 Global AGENTS migration

새 installer는 `~/.codex/AGENTS.md`를 생성하지 않는다.

기존 파일은 다음 조건을 모두 만족할 때만 SAMVIL-generated로 판단한다.

- known SAMVIL header
- canonical generated content checksum 일치
- 사용자 추가 section 없음

일치하면 `--migrate`에서 timestamped backup 후 전역 적용을 해제한다. 하나라도
불확실하면 파일을 건드리지 않고 exact blocker를 출력한다.

### 9.6 Legacy direct MCP config

plugin-owned MCP와 기존 `[mcp_servers.samvil-mcp]`가 동시에 등록되지 않게 한다.
기존 block이 installer가 생성한 known shape와 일치할 때만 reversible migration
대상으로 삼는다. 사용자 수정 block은 자동 편집하지 않는다.

---

## 10. Public Codex skill surface

### 10.1 `samvil:run`

책임:

- fresh/brownfield/resume mode 결정
- initial orchestrator 실행
- current stage envelope 획득
- internal stage instruction 실행
- transition result에 따라 같은 task에서 loop
- user checkpoint, BLOCK, terminal 처리

사용자가 `samvil:interview`, `samvil:seed` 등을 직접 호출할 필요가 없어야 한다.

### 10.2 `samvil:resume`

책임:

- marker/state/event/claim의 재개 가능성 검증
- in-progress stage와 last committed transition 구분
- 안전한 동일 stage 재실행 또는 다음 stage 진행
- ambiguous recovery는 fail-closed

### 10.3 `samvil:status`

완전 read-only다.

출력:

- current stage
- completed stages
- next stage
- stage status
- last committed marker revision
- retry count
- gate verdict
- waiting user / blocked reason
- recovery recommendation

### 10.4 Internal stage instructions

이번 release에서는 기존 `references/codex-commands/*.md`를 Codex internal stage
instruction corpus로 재사용한다. public plugin skills path에는 등록하지 않는다.

장기적으로 Claude/Codex stage contract를 단일 source로 생성할 수 있지만 이번
release의 non-goal이다.

---

## 11. Stage catalog

stage order, valid transitions, instruction path, execution policy를 deterministic
catalog 한 곳에서 관리한다.

예시 schema:

```python
StageSpec(
    name="samvil-build",
    instruction="references/codex-commands/samvil-build.md",
    auto_proceed=True,
    requires_user_checkpoint=False,
    terminal=False,
    dynamic_next=False,
    valid_next=("samvil-qa",),
)
```

Catalog owns:

- canonical stage names
- valid previous/next transitions
- internal instruction path allowlist
- auto-proceed policy
- user checkpoint policy
- dynamic route owner
- terminal behavior

Dynamic routing examples:

- Seed → Design or Council
- QA → QA stay / Deploy / Evolve / Retro
- Evolve rebuild → Build

> **스코프 보정 (2026-07-26):** 현재 구현은
> `materialize_evolve_rebuild_handoff` 후 `project.state.json.current_stage`를
> `build`로 설정하고 `samvil-build`로 재진입한다
> (`skills/samvil-evolve/SKILL.md`). 이번 release는 이 검증된 경로를 보존하며,
> Scaffold 재진입은 별도 설계 변경 없이는 도입하지 않는다.

Driver, marker validation, host parity check, command generator가 같은 catalog를
사용해야 한다.

---

## 12. Codex Host Driver loop

### 12.1 Main loop

```text
1. read current durable state
2. get_stage_envelope
3. if waiting_user/blocked/terminal → stop
4. validate instruction path against stage catalog
5. begin stage with expected marker revision
6. execute internal stage instruction
7. commit stage transition through MCP
8. read committed next envelope
9. unchanged same-cause transition twice → circuit break
10. otherwise continue in same Codex task
```

### 12.2 Driver does not own stage logic

Driver는 다음을 직접 구현하지 않는다.

- Interview 질문 생성
- Seed validation
- Design generation
- Build implementation
- QA verdict synthesis
- Deploy target choice

각 stage instruction과 existing MCP domain tool이 계속 소유한다. Driver는 실행
순서와 stop/continue만 소유한다.

### 12.3 Stop conditions

Driver는 다음 경우 반드시 정지한다.

1. explicit user checkpoint
2. Restate Gate
3. irreversible action confirmation
4. gate `BLOCK`
5. corrupt or ambiguous SSOT
6. correctness-critical MCP unavailable
7. same root cause twice
8. terminal pipeline state

### 12.4 Natural-language trigger

사용자는 namespace를 외울 필요가 없다. `samvil:run` description은 다음 의도를
trigger해야 한다.

- "SAMVIL로 앱 만들어줘"
- "한 줄 아이디어로 프로젝트 시작"
- "SAMVIL 이어서 진행"

명시적 skill 선택 시에는 `samvil:run`이 canonical entry다.

---

## 13. MCP transition controller

### 13.1 Why a stronger boundary is required

수동 handoff에서는 stage state와 marker가 잠시 어긋나도 사용자가 다음 호출 전에
복구할 여지가 있다. 자동 loop는 stale marker를 즉시 소비하므로 transition
원자성이 더 중요하다.

### 13.2 Internal module

새 `transition_controller.py`가 다음 공통 로직을 소유한다.

- stage envelope construction
- marker revision validation
- stage claim/lease
- gate verification
- DB session/event/claim, canonical JSONL, `project.state.json`, marker, receipt commit boundary
- idempotent retry result
- recovery classification

Claude existing paths와 Codex tools가 가능한 한 같은 internal controller를
사용한다. Codex 전용 로직으로 contract를 복제하지 않는다.

### 13.3 MCP tool surface

최종 이름은 implementation plan에서 repository naming과 충돌을 검증한 뒤
확정하지만 책임은 다음처럼 고정한다.

#### `get_stage_envelope(project_root, host_name)`

Read-only. 반환:

```json
{
  "run_id": "run-...",
  "host_name": "codex_cli",
  "stage": "samvil-build",
  "status": "ready",
  "marker_revision": 7,
  "instruction_path": "references/codex-commands/samvil-build.md",
  "execution_policy": "auto",
  "stop_reason": ""
}
```

#### `begin_stage(project_root, run_id, stage, expected_revision)`

- expected revision compare-and-swap
- existing in-progress claim idempotent reuse
- conflicting claim reject
- stage start event/claim coordination

#### `commit_stage_transition(...)`

- stage evidence and gate verify
- session/project stage update
- canonical event commit
- next marker commit
- revision increment
- duplicate completion returns previous committed result

`requested_next_skill`은 catalog-valid한 비파괴 route 선택만 표현한다. 이 입력과 caller
prose는 trusted approval이나 gate override 증거가 아니다. Restate Gate, irreversible
action, gate override가 필요한 경우 controller는 `waiting_user` 또는 `blocked`를 반환하고
같은 호출에서 transition을 commit하지 않는다. Codex native permission boundary 밖의
승인을 MCP가 발급했다고 주장하지 않는다.

사용자 응답 뒤의 새 호출은 두 경우를 분리한다. 일반 route 선택은 untrusted
`user_choice` context로 기록할 수 있고, Restate 같은 정상 gate 충족은 새로 materialize된
stage artifact를 deterministic하게 재검증해 진행할 수 있다. 반면 기존 gate 판정을
무시하는 override와 irreversible action 승인에는 이 경로를 사용할 수 없다.

현재 `ClaimLedger.record_host_user_approval()`과 `record_gate_override()`는 신뢰할 수 있는
non-model-callable host adapter가 없어 의도적으로 fail-closed다. v4.33은 이 경계를
유지한다. native host attestation은 후속 release의 별도 설계 대상이다.

### 13.4 Atomic transition protocol

`project.state.json`은 marker의 보조 파일이 아니라 현재 pipeline stage SSOT다. 하나의
transition은 다음 materialization 전부를 같은 `transition_id`로 묶는다.

1. SQLite event, session stage, stage claim, pending receipt
2. `.samvil/events.jsonl` canonical event
3. `.samvil/claims.jsonl` transition claim
4. `project.state.json`의 `current_stage`, `completed_stages`, transition revision/id
5. `.samvil/next-skill.json` marker
6. acknowledged transition receipt

고정 lock/materialization 순서는 다음과 같다.

```text
transition lock → journal → DB → events → claims → project.state → marker → receipt/ack
```

PREPARED journal은 기존/new project-state hash, 보존해야 할 non-stage fields, intended
stage patch를 포함한다. `project.state.json`은 임시 파일 작성·검증·atomic replace로
materialize한다. PREPARED 뒤 DB commit 여부가 확인되지 않는데 SQLite가 unavailable이면
아무 file도 더 진행하거나 journal을 지우지 않는다. DB_COMMITTED 뒤 실패하면 광범위
rollback하지 않고 journal로 남은 file SSOT를 idempotently 완성한다. SQLite 파일이
소실된 경우에도 journal과 file SSOT가 단일 transition을 증명할 때만 schema를 다시 만들고
그 session/transition row를 복원한다. unrelated DB history까지 복구했다고 주장하지 않는다.
단일 해석이 증명되지 않으면 fail-closed다. recovery는 최신 transition을 이전 retry가
되돌리지 못하게 한다.

shared controller가 이 경계를 소유한 뒤에는 Claude/Codex stage instruction이
`current_stage`, completed stages, marker를 별도로 갱신하지 않는다.

### 13.5 Marker schema v1.1

```json
{
  "schema_version": "1.1",
  "run_id": "run-...",
  "revision": 8,
  "status": "ready",
  "chain_via": "host_driver",
  "host_name": "codex_cli",
  "next_skill": "samvil-qa",
  "from_stage": "samvil-build",
  "reason": "build gate passed",
  "written_at": "<ISO 8601>"
}
```

Compatibility:

- v1.0 marker read 지원
- first trusted transition에서 v1.1로 upgrade
- unknown schema는 자동 진행 금지
- missing/corrupt marker는 state에서 단일 해석이 가능할 때만 복구

### 13.6 QA fail-closed preservation

QA 결과가 missing/corrupt/invalid면:

- marker가 `samvil-qa`에 머문다
- Deploy/Evolve/Retro로 advance하지 않는다
- `resolve_stage_next_skill()`의 기존 `None` 의미를 변경하지 않는다
- contract-stage-end gate를 우회하는 fallback을 만들지 않는다

---

## 14. Recovery and error handling

| Condition | Behavior |
|---|---|
| No marker + no project state | Fresh start |
| Valid marker + matching state | Resume current target |
| Marker in-progress + same run | Idempotent same-stage resume |
| Marker revision stale | Reject stale completion |
| Marker missing + state unambiguous | Write recovery receipt, reconstruct marker |
| Marker corrupt + state ambiguous | BLOCK |
| Marker/state stage mismatch | BLOCK unless deterministic last commit proves one side |
| MCP unavailable during status | File fallback, DEGRADED |
| MCP unavailable during transition | Fail-closed |
| Gate fail | Remain current stage |
| Same root cause twice | Circuit breaker + exact blocker |
| User checkpoint | Return `waiting_user`, commit no stage transition, and yield |
| Terminal stage | Persist completion, clear active continuation marker safely |

Recovery assertions require file/line or artifact evidence. Conversation memory is never
accepted as the only recovery source.

---

## 15. Host capability update

Codex native support를 실제 E2E가 통과하기 전에는 capability declaration을 먼저
올리지 않는다.

검증 후 target declaration:

```text
host_name=codex_cli
skill_invocation=plugin_driver
chain_via=host_driver
file_marker_handoff=true   # recovery fallback
mcp_tools=true
native_task_update=true    # only after runtime proof
parallel_agents=<unchanged until separate multi-agent release>
```

`parallel_agents`는 Codex product capability가 존재한다는 이유만으로 이번 release에
SAMVIL 지원 완료로 표시하지 않는다. 실제 SAMVIL parallel execution contract가
생긴 뒤 별도 변경한다.

---

## 16. Testing strategy

### 16.1 Unit tests

1. stage catalog valid transition coverage
2. instruction path allowlist and traversal rejection
3. marker v1.0 → v1.1 compatibility
4. stale revision rejection
5. duplicate begin/commit idempotency
6. user checkpoint stop behavior
7. QA missing/corrupt fail-closed
8. terminal marker cleanup
9. marketplace root safety validation
10. personal skill inventory comparison
11. legacy global AGENTS provenance detection
12. direct MCP config provenance detection
13. EventStore schema migration preserves existing sessions/events and rolls back cleanly
14. transition failure before/after `project.state.json` atomic replace
15. prepared-journal recovery with SQLite unavailable or lost
16. forged approval/gate-override input remains fail-closed

### 16.2 Installer integration tests

Isolated Codex configuration fixtures에서 검증한다.

1. clean install
2. repeated install idempotency
3. update existing correct install
4. home-root marketplace migration
5. user-modified marketplace conflict
6. exact legacy SAMVIL skill duplicate
7. user-modified `samvil*` skill conflict
8. existing personal skills preserved
9. plugin MCP starts from installed root
10. uninstall does not remove personal skills
11. real activation is rejected until controller and all three public skills are ready
12. actual migration requires explicit `--check` then `--migrate`

### 16.3 Driver integration tests

1. fresh orchestrator → Interview
2. Interview → Seed automatic continuation
3. Seed → Design default route
4. Seed → Council explicit route
5. Design → Scaffold → Build
6. Build → QA
7. QA fail remains QA
8. QA pass follows trusted dynamic route
9. user checkpoint yields without advancing
10. restart resumes same stage without duplicate transition
11. route choice cannot mint trusted approval or bypass an irreversible-action boundary

### 16.4 Real Codex CLI E2E

실제 `codex exec`를 사용하며 stage completion을 stub/mock하지 않는다.

필수 scenarios:

1. greenfield web minimal
2. greenfield mobile-app standard
3. brownfield analyze → build
4. Interview interruption/resume
5. Build interruption/resume
6. QA missing/corrupt recovery
7. marker stale/corrupt recovery
8. MCP process failure/restart
9. duplicate completion replay
10. three repeated end-to-end runs

`--check`는 실제 web/mobile scenario 전에 ephemeral `127.0.0.1` port를 bind하고
해제할 수 있는지 검증한다. 동일 localhost blocker가 두 번 반복되면 harness는 회로를
차단한다.

### 16.5 Codex Desktop smoke

1. plugin appears as installed/enabled
2. personal skills show bare names
3. only SAMVIL skills use `samvil:` namespace
4. `samvil:run`, `resume`, `status` are discoverable
5. natural-language trigger selects `samvil:run`
6. task close/reopen resumes from durable state

### 16.6 Actual Claude Code runtime E2E

1. existing `.claude-plugin/plugin.json` remains valid
2. actual `claude` binary가 plugin을 load한다
3. actual Skill tool로 최소 Interview → Seed 또는 Build → QA chain을 완료한다
4. marker fallback resume와 user checkpoint stop을 실제 runtime에서 검증한다
5. sanitized `claude-runtime.json` receipt를 남긴다
6. Codex manifest does not alter Claude plugin discovery
7. shared MCP transition controller preserves existing contract hooks
8. host-specific test expectations remain explicit

### 16.7 Runtime evidence provenance

실행 harness 코드와 증거를 같은 커밋에서 만들지 않는다. 먼저 harness를 commit하고,
clean `HEAD`에서 실제 runtime을 실행한 뒤 receipt-only evidence commit을 만든다.
receipt는 테스트한 exact commit과 git tree hash, CLI/app/plugin/runtime version, command,
exit code, artifact hash를 기록한다. evidence commit은 직전 tested commit만 가리키며,
verifier는 evidence 외 delta가 없음을 확인한다.

Codex Desktop 증거는 `verification_level=manual_desktop`으로 분류한다. screenshot이나
수동 관찰을 cryptographic/trusted host attestation으로 승격하지 않으며, Desktop
receipt만으로 gate override나 irreversible action 권한을 열지 않는다.

---

## 17. Acceptance criteria

### AC-1 — Namespace isolation

Given personal skills and SAMVIL plugin are installed, Codex inventory shows personal
skills with bare names and only SAMVIL-owned skills with the `samvil:` prefix.

### AC-2 — Native plugin install

Given a clean supported Codex installation, one setup command installs/enables
`samvil@samvil`, starts its MCP server, and leaves no direct absolute-path MCP duplicate.

### AC-3 — Same-task automatic continuation

Given a trusted completed stage, Codex loads and starts the next stage without requiring
the user to invoke another skill manually.

### AC-4 — User checkpoint preservation

Given a Restate Gate or irreversible decision, Codex stops and waits for explicit user
input without writing a next-stage commit.

### AC-5 — Idempotent resume

Given Codex stops before, during, or after a stage transition, resume produces one
canonical stage transition and no duplicate DB event, JSONL event, claim,
`project.state.json`, session stage, marker, or receipt advancement.

### AC-6 — Fail-closed transition

Given missing/corrupt QA evidence, stale marker revision, ambiguous state, or unavailable
critical MCP, the driver does not advance.

### AC-7 — Real host runtime proof

Actual Codex CLI and actual Claude Code runs plus a separately classified Codex Desktop
manual smoke, not structural document checks, provide persisted artifacts demonstrating
stage execution and resume.

### AC-8 — Structural parity honesty

The host parity report no longer presents native execution as green unless real runtime
proof exists. Remaining unsupported surfaces are enumerated exactly.

### AC-9 — Claude compatibility

The actual Claude Code plugin and Skill-tool chain pass a runtime smoke in addition to
their existing structural and test gates.

### AC-10 — User-owned path preservation

Installer and tests do not modify, delete, or claim ownership of unrelated personal
skills or ambiguous user-modified configuration.

---

## 18. File-level change map

| Path | Responsibility |
|---|---|
| `.codex-plugin/plugin.json` | Codex-native plugin manifest |
| `.codex-mcp.json` | Codex-relative MCP server declaration |
| `codex/skills/README.md` | Tracked skill root without a temporary stub skill |
| `codex/skills/run/SKILL.md` | Public Codex driver entry |
| `codex/skills/resume/SKILL.md` | Durable resume entry |
| `codex/skills/status/SKILL.md` | Read-only status entry |
| `mcp/samvil_mcp/stage_catalog.py` | Canonical stage metadata and transitions |
| `mcp/samvil_mcp/transition_controller.py` | Envelope, revision, atomic transition, recovery |
| `mcp/samvil_mcp/chain_markers.py` | v1.1 marker compatibility and validation |
| `mcp/samvil_mcp/host.py` | Codex verified capability declaration |
| `mcp/samvil_mcp/host_adapters.py` | `host_driver` continuation strategy |
| `mcp/samvil_mcp/server.py` | Thin MCP wrappers for driver tools |
| `scripts/setup-codex.sh` | Native plugin install and safe migration |
| `scripts/check-host-parity.py` | Runtime evidence-aware parity reporting |
| `scripts/codex-native-e2e.py` | Real Codex CLI E2E orchestration |
| `scripts/claude-native-e2e.py` | Real Claude Code runtime compatibility proof |
| `docs/evidence/codex-native-autonomy/*.json` | Clean-commit machine/manual receipts |
| `mcp/tests/test_stage_catalog.py` | Stage catalog contracts |
| `mcp/tests/test_transition_controller.py` | Atomicity/idempotency/recovery tests |
| `mcp/tests/test_codex_plugin.py` | Manifest and namespace tests |
| `mcp/tests/test_setup_codex.py` | Installer migration tests |
| `mcp/tests/test_codex_driver.py` | Driver decision-loop tests |
| `README.md` | Codex-first install and user flow |
| `references/host-continuation.md` | marker recovery vs host execution distinction |

File names may be narrowed during implementation planning, but responsibility boundaries
must not be collapsed back into `server.py` or prompt-only logic.

---

## 19. Implementation sequence and commit boundaries

Each item starts with a failing test and ends with full pre-commit success.

1. **Codex manifest contract and tracked non-stub skill root**
2. **Marketplace ownership and namespace isolation planner**
3. **Reversible installer executor in isolated/fake Codex only**
4. **Canonical stage catalog**
5. **Marker v1.1 revision and compatibility**
6. **Read-only envelopes and durable stage claims**
7. **Full transition atomicity including `project.state.json`**
8. **Resume and ambiguous recovery behavior**
9. **Thin transition MCP wrappers with no trusted approval minting**
10. **Public `run/resume/status` skill surface**
11. **Codex Host Driver automatic continuation**
12. **Shared Claude/Codex `complete_stage` controller path**
13. **Actual Codex installer activation and explicit legacy migration**
14. **Codex and Claude runtime harness code**
15. **Clean-commit Codex CLI and Claude Code machine receipts**
16. **Codex Desktop manual receipt**
17. **Receipt-backed capability and parity declaration**
18. **SSOT evidence, docs, changelog, and v4.33.0 release sync**

One concern should remain one commit. A later issue discovered by review receives its own
TDD commit rather than being folded into an unrelated item.

---

## 20. Release gates

Before merge:

1. every item-level targeted test green
2. `bash scripts/pre-commit-check.sh` exit 0 before every commit
3. full suite green on final branch
4. real Codex CLI E2E machine receipt persisted against a clean commit/tree
5. real Claude Code runtime machine receipt persisted against the same clean commit/tree
6. Codex Desktop smoke persisted and labeled `manual_desktop`
7. namespace inventory before/after receipt persisted
8. adversarial review of retry, duplicate, checkpoint, and gate bypass
9. `samvil:pre-pr-review` R3 read-only review
10. actual P1/P2 findings fixed with separate TDD commits and re-review
11. normal push only; no force push or verification bypass

The release is not complete merely because plugin discovery, structural parity, or unit
tests are green.

---

## 21. User-visible result

### Before

```text
Personal skills may appear as samvil:<personal-skill>.
Codex writes a next-skill marker and may require manual stage invocation.
Native stage parity is not proven.
Global AGENTS and direct MCP config leak SAMVIL concerns into unrelated projects.
```

### After

```text
Personal skills keep their original names.
Only SAMVIL-owned skills use the samvil: namespace.
samvil:run continues stages automatically in one Codex task.
samvil:resume restores durable state after restart.
samvil:status explains the current state without mutation.
Critical transitions remain fail-closed and idempotent.
Codex support is backed by real CLI evidence and separately classified Desktop evidence.
Claude compatibility is backed by an actual Claude Code runtime receipt.
```

---

## 22. Implementation readiness

No product decision remains open for implementation planning.

The implementation plan must preserve these fixed boundaries:

1. Codex is the primary host for this release.
2. personal skills remain bare and user-owned.
3. only SAMVIL plugin skills receive `samvil:` namespace.
4. public Codex surface is `run`, `resume`, `status`.
5. stage execution continues automatically within the current task.
6. files remain recovery SSOT, but MCP owns trusted transitions.
7. user checkpoints and fail-closed gates cannot be bypassed.
8. native support is claimed only after clean-commit Codex and Claude runtime evidence.
9. v4.33 does not mint trusted user approval or gate-override claims.
