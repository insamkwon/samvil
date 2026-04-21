# Model-Specific Prompts (v3.1.0, v3-017)

> Purpose: SAMVIL은 **Universal Builder** 비전이지만 현재 Skill chain이 Claude instruction-following 특성에 암묵적으로 의존한다. 이 문서는 Claude/GLM/GPT 등 다른 모델에서도 SAMVIL이 작동하도록 하는 호환성 가이드.
>
> **Triggered by**: `v3-017` dogfood — mobile game with glm-5.1[1m] in main session stalled samvil-design 25분+, Sonnet 전환 후 4m 18s 완료. 모델 거부가 아니라 호환성 보강이 옳다.

---

## 1. 권장 모델 (측정 기반)

| 단계 | 권장 모델 | 측정값 |
|---|---|---|
| Interview | Claude Sonnet 4.6 / Opus 4.7 | GLM도 가능하나 Rhythm Guard 감지 품질 차이 |
| Seed | Claude Sonnet 4.6 | JSON 스키마 준수율 Claude > GLM |
| Council (Round 1 research) | **Claude Haiku 4.5** | 속도 최적화, 비용 80% 절약 |
| Council (Round 2 review) | Claude Sonnet 4.6 | 종합 판단 품질 |
| Design | **Claude Sonnet 4.6** | **GLM 25m+ stall vs Sonnet 4m 18s** — 6x+ gap |
| Scaffold | Claude Sonnet 4.6 / GLM (짧은 프롬프트) | 파일 생성 위주 단순 작업 |
| Build (worker) | Claude Sonnet 4.6 | AC leaf 단위 구현 |
| QA | Claude Sonnet 4.6 | Playwright 통합 이해 필요 |
| Evolve (cycle 1) | Claude Haiku 4.5 | Wonder 단순 분석 |
| Evolve (cycle 2+) | Claude Sonnet 4.6 | Reflect 심화 |
| Retro | Claude Haiku 4.5 | 데이터 집계 위주 |

**Main session (대화 모델)**: Claude Opus 4.7 권장. GLM-5.1도 지원되지만 설계/빌드 단계 진입 시 Claude로 전환 권장 (v3-018 cost-aware mode).

---

## 2. 모델별 알려진 차이점

### 2a. Claude (Opus / Sonnet / Haiku)

- **강점**: instruction-following, JSON 스키마 준수, multi-step reasoning, tool use (best-in-class)
- **제약**: 비용 (특히 Opus)
- **Skill 진입 patterns**: 현재 기본값. 변경 없이 작동.

### 2b. GLM (5.x)

- **강점**: 토큰 비용 매우 저렴 (Claude 대비 1/5~1/10), 1M context 지원
- **제약**: 긴 implicit reasoning 체인에서 step drop. Agent spawn 직후 result aggregate 단계에서 hang 보고됨.
- **Skill 진입 patterns 수정 권장**:
  - Bullet list 명시: "Step 1: Do X. Step 2: Do Y." 형식
  - 각 step 끝에 결과 검증 라인 ("→ Result: <expected>")
  - Tool 호출 후 30초 heartbeat 의무 (v3-016 stall_detector 활용)

### 2c. GPT-4 / GPT-4o / o1

- **강점**: 일반 지식 breadth, 수학/논리
- **제약**: tool use 재시도 시 luckbox, JSON 형식 일관성 Claude 대비 약간 낮음
- **Skill 진입 patterns 수정 권장**:
  - JSON output 요구 시 "Output MUST be valid JSON. Do not include markdown code fences." 명시
  - Temperature 0 설정 권장
  - Tool use 실패 시 재시도 + fallback 명시

### 2d. 기타 (Gemini, Mistral, Llama 등)

- **현재 미검증**. README에 "Best tested with Claude, other models supported with known limitations" 명시.
- 시도 시 GPT patterns을 starting point로 사용.

---

## 3. Skill 공통 진입점 패턴 (모델 독립)

모든 SAMVIL Skill의 첫 섹션에 다음 패턴이 적용되어야 한다 (v3-017 fix 1):

### 3a. Boot Sequence 명시적 Step

❌ 나쁜 예:
> "Read the seed, understand the plan, then proceed."

✅ 좋은 예:
> "Step 1: Read `project.seed.json`. Step 2: Read `project.state.json` to confirm current_stage. Step 3: Call `mcp__samvil_mcp__heartbeat_state`. Step 4: Read tier and proceed to Phase A."

### 3b. Tool use 앞에 '왜'와 '무엇'

❌ 나쁜 예:
> "Call the MCP tool."

✅ 좋은 예:
> "Call `mcp__samvil_mcp__update_leaf_status(leaf_id='<X>', status='in_progress')` to mark this leaf as being worked on. The main session reads this to track progress; skip causes status=unknown in QA."

### 3c. Progress announcement + heartbeat 루프

긴 loop (Agent spawn batches, AC leaf iteration)에서는:

```
For each batch:
  1. Print: "[SAMVIL] Processing batch K/N of size M"
  2. Call heartbeat_state
  3. Dispatch batch (Agent spawn, leaf build, etc.)
  4. Collect results
  5. Print: "[SAMVIL]   <k>/<N> complete: <summary>"
  6. Call heartbeat_state again
  7. Check is_state_stalled between batches — inject reawake if stalled
```

### 3d. Error case explicit

❌ 나쁜 예:
> "If something fails, handle it."

✅ 좋은 예:
> "If Agent returns a non-JSON response: (a) log `contract_violation` event, (b) retry once with explicit 'Output must be JSON' reminder, (c) if still failing, mark leaf as `failed` and continue to next — do not block the batch."

---

## 4. 모델별 Skill 진입점 분기 (future, v3.2.0+)

현재(v3.1.0)는 공통 패턴만 적용. v3.2.0부터 모델 감지 후 분기 고려.

```
# Pseudo-code for future model-aware entry
main_model = detect_main_model()  # from state.json or CC API
if main_model.startswith("claude"):
    use_standard_patterns()
elif main_model.startswith("glm"):
    use_explicit_step_patterns()  # bullet + result verification
elif main_model.startswith("gpt"):
    use_json_strict_patterns()    # "Output MUST be JSON" prefix
else:
    use_fallback_patterns()  # most defensive
    warn_user_untested()
```

---

## 5. 강제 거부 금지

**SAMVIL은 모델을 강제로 거부하지 않는다.** 사용자가 어떤 모델을 main에 써도:

- 작동할 수 있는 최선의 patterns으로 진행
- 알려진 제약은 README + samvil-doctor에서 투명하게 공개
- Stall/hang이 발생하면 v3-016 heartbeat/reawake로 자동 복구 시도
- MAX_REAWAKES 초과 시에만 사용자 개입 요청

---

## 6. 관련 문서

- `references/cost-aware-mode.md` (v3-018) — GLM main + Claude sub 패턴
- `references/boot-sequence.md` — Skill 부팅 공통 프로토콜
- `skills/samvil-doctor/SKILL.md` — 환경 진단 + 모델 감지
- `README.md` — "Best tested with Claude" badge + 권장 모델 표

---

_작성: 2026-04-21 · v3.1.0 Sprint 2 (v3-017 Model Compatibility)_
