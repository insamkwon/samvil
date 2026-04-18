# Boot Sequence Pattern (INV-1)

모든 SAMVIL 스킬이 시작 시 따라야 하는 공통 부트 시퀀스.

## 0a. Decision Boundary 표시 (v2.3.0+, P3)

스킬 시작 직후 사용자에게 **종료 조건**을 투명하게 표시:

```
[SAMVIL] 🔵 Phase: <Stage Name> (Stage N/5)
[SAMVIL] 종료 조건: <boundary>
```

### Stage별 boundary

| Stage | 종료 조건 |
|-------|----------|
| interview | `ambiguity_score ≤ tier 임계값` (minimal 0.10 / standard 0.05 / thorough 0.02 / full 0.01) |
| seed | seed.json 스키마 검증 통과 + 사용자 검토 |
| council | Round 2 판결 수집 완료 |
| design | blueprint.json 생성 + Gate B (if thorough+) |
| scaffold | Next.js/Vite/Astro 스캐폴드 빌드 통과 |
| build | 모든 features의 leaf AC 구현 + lint/typecheck |
| qa | 3-pass 모두 PASS + evidence 존재 (P1) |
| evolve | similarity ≥ 0.95 + regression 0 + 5 gates 통과 (P5) |
| deploy | 사용자 명시적 승인 (P10 — Irreversible action) |
| retro | feedback.log 기록 완료 |

**원칙**: 사용자는 "언제 끝나는지" 숫자로 알 수 있어야 함 (P3 Decision Boundary).

## 0. MCP Tool Loading (v2.3.0+, P8 Graceful Degradation)

SAMVIL MCP tools는 **deferred tools**로 등록될 수 있어 즉시 사용 불가.
첫 MCP 호출 전에 `ToolSearch`로 로드:

```
ToolSearch query: "+samvil <operation>"

Examples:
- Interview:  "+samvil score"       → score_ambiguity
- Seed:       "+samvil seed"        → save_seed, validate_seed
- Council/Design/Scaffold/Build: "+samvil event" → save_event
- QA:         "+samvil qa"          → save_qa_result
- Evolve:     "+samvil convergence" → compare_seeds, check_convergence
- Retro:      "+samvil retro"       → generate_retro
- Any stage:  "+samvil event"       → save_event (공통)
```

**판단 로직**:
1. ToolSearch 결과 있음 → Path A (MCP 사용)
2. ToolSearch 결과 없음 → **Path B (파일 fallback)** per INV-5
3. MCP 호출 시 에러 → 1회 재시도 → 실패 시 fallback

**IMPORTANT**: 스킬이 MCP 없이 동작 불가하다고 가정하지 말 것. 파일 기반 fallback이 항상 가능해야 함 (INV-5).

## 1. 파일 읽기

```
1. Read project.seed.json → 이번에 뭘 빌드/검증/수정할지 파악
   - interview/seed 스테이지는 아직 seed가 없을 수 있음 → 생략
2. Read project.state.json → current_stage 확인, session_id 획득
3. Read project.config.json → selected_tier, 스테이지별 설정
```

## 2. Metrics 시작 기록 (INV-5)

부트 시퀀스 완료 직후, metrics.json에 스테이지 시작을 기록:

```
metrics = read .samvil/metrics.json
metrics.stages.<stage>.started_at = <ISO timestamp now>
write .samvil/metrics.json
```

스테이지별 메트릭 필드는 `references/metrics-tracking.md` 참조.

## 3. 체크포인트 (INV-6)

스테이지 완료 직후, state.json을 업데이트:

```python
state = read_json("project.state.json")
if stage_name not in state["completed_stages"]:
    state["completed_stages"].append(stage_name)
state["current_stage"] = "<next_stage>"
write_json("project.state.json", state)
```

## 4. Metrics 종료 기록 (INV-5)

다음 스킬 invoke 직전, metrics.json에 스테이지 종료를 기록:

```
metrics = read .samvil/metrics.json
metrics.stages.<stage>.ended_at = <ISO timestamp now>
metrics.stages.<stage>.duration_ms = ended_at - started_at (ms)
# 스테이지별 추가 메트릭 기록
write .samvil/metrics.json
```

## 5. MCP 이벤트 (Dual-Write)

상태 변경 시 `references/graceful-degradation.md`의 Dual-Write 패턴을 따른다.

## 스테이지별 변형

| Stage | seed.json | state.json 확인 | config.json |
|-------|-----------|-----------------|-------------|
| interview | 없음 (생성 전) | `current_stage == "interview"` | `selected_tier` |
| seed | 없음 (이번에 생성) | `current_stage == "seed"` | `selected_tier` |
| council | 있음 | `current_stage == "council"` | `selected_tier` |
| design | 있음 | `current_stage == "design"` | `selected_tier` |
| scaffold | 있음 | `current_stage == "scaffold"` | `selected_tier` |
| build | 있음 | `current_stage == "build"`, resume 지원 | `selected_tier`, `max_total_builds` |
| qa | 있음 | `current_stage == "qa"` | `qa_max_iterations`, `selected_tier` |
| deploy | 있음 | QA PASS 확인 필수 | `selected_tier` |
| evolve | 있음 | qa_history 확인 | `evolve_max_cycles`, `evolve_mode` |
| retro | 있음 | completed_features, qa_history | `selected_tier` |
