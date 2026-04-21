# Cost-Aware Mode (v3.1.0, v3-018)

> Purpose: 1인 개발자가 **설계는 Claude, 메인 세션은 저렴 모델**(GLM 등)로 비용 절감하는 패턴을 공식 지원. v3-017 모델 호환성과 짝을 이루는 기능.
>
> **Motivation**: 동호님 dogfood 피드백 — "GLM이 토큰이 저렴해서 메인은 GLM, 설계만 Claude로 돌리고 싶다"

---

## 1. 현재 제약

SAMVIL은 메인 세션 모델을 직접 통제할 수 없다 (Claude Code 자체 설정). `model_routing`은 **spawn되는 sub-agent**(Agent tool, Council Round 1/2, Build worker, QA)에만 적용된다.

즉 구조는:

```
Main session (user-configured: Claude Opus / Sonnet / GLM / GPT / ...)
  └─ samvil-interview SKILL
       └─ spawn agent: socratic-interviewer  ← model_routing 적용
  └─ samvil-design SKILL
       └─ spawn agents: ui-designer, ux-researcher, ...  ← model_routing 적용
```

Main session이 GLM이면 Skill instruction을 읽고 해석하는 건 GLM이 담당. Sub-agent spawn은 model_routing에 따라 Sonnet 등으로 가능.

---

## 2. 권장 패턴 — 3단계 조합

### 2a. Full Claude (가장 품질 높음, 비싸다)
- Main: Claude Opus 4.7
- All sub-agents: Claude Sonnet 4.6 or Opus
- 비용: 높음. 품질: 최고.
- 적합: 중요 production 앱, 큰 프로젝트.

### 2b. Cost-aware (추천, 70% 비용 절감)
- Main: **GLM-5.1 1M** (저비용) 또는 Claude Haiku 4.5
- Sub-agents:
  - Council R1: Claude Haiku 4.5
  - Council R2: Claude Sonnet 4.6
  - Design: Claude Sonnet 4.6
  - Build worker: Claude Sonnet 4.6
  - QA: Claude Sonnet 4.6
- 비용: 중. 품질: 거의 full Claude 수준.
- 적합: 대부분 1인 개발자 프로젝트. **v3-016 heartbeat로 GLM stall 복구 자동화되어 안전**.

### 2c. Ultra-cheap (실험용)
- Main: GLM 또는 로컬 Llama
- Sub-agents: 전부 GLM 또는 Haiku
- 비용: 매우 저렴. 품질: 변동 큼.
- 적합: 탐색/실험, 프로덕션 권장 X.

---

## 3. 설정 방법 (project.config.json)

```json
{
  "selected_tier": "standard",
  "max_parallel": 2,
  "model_routing": {
    "default": "sonnet",
    "council_research": "haiku",
    "council_review": "sonnet",
    "design": "sonnet",
    "design_reviewer": "haiku",
    "build_worker": "sonnet",
    "qa": "sonnet",
    "evolve_wonder": "haiku",
    "evolve_reflect": "sonnet",
    "retro": "haiku"
  }
}
```

위 기본값이 **Cost-aware (2b)** 프리셋에 해당. Main session은 사용자 자유 선택.

---

## 4. samvil-doctor에서 감지 + 안내

`samvil-doctor`는 main 세션 모델을 감지(가능한 경우)하고 다음 중 하나를 안내:

| 감지된 main | 안내 |
|---|---|
| Claude Opus/Sonnet/Haiku | "Optimal stack. No action needed." |
| GLM-4/5 | "Cost-aware mode detected. heartbeat + model_routing active. Known: 6x+ slower on design without routing." |
| GPT-4/o1 | "GPT main detected. JSON-strict patterns active. See references/model-specific-prompts.md §2c." |
| Unknown | "Untested main model. Falling back to defensive patterns. Report issues to v3.x.x backlog." |

---

## 5. Stage별 권장 모델 표 (측정 기반)

| Stage | 권장 모델 | 사유 |
|---|---|---|
| Interview (main) | Claude Opus/Sonnet 또는 GLM-5.1 (cost) | 대화 품질 + Rhythm Guard 감지 |
| Seed | Claude Sonnet | JSON 스키마 정확도 |
| Council R1 | **Claude Haiku 4.5** | 속도 + 비용. R1은 research 중심이라 Haiku 충분 |
| Council R2 | Claude Sonnet | 종합 판단 |
| Design | **Claude Sonnet** | GLM 25m+ stall vs Sonnet 4m 18s (v3-020 측정값) |
| Scaffold | Sonnet / GLM | 파일 생성 위주. 간단. |
| Build worker | Claude Sonnet | AC leaf 구현 정확도 |
| QA | Claude Sonnet | Playwright 통합 이해 필요 |
| Evolve cycle 1 | Claude Haiku | Wonder 단순 분석 |
| Evolve cycle 2+ | Claude Sonnet | Reflect 심화 |
| Retro | Claude Haiku | 데이터 집계 |

**측정값 (v3-020)**: Sonnet 전환 후 Design 4m 18s 완료 (GLM 25m+ stall 대비 **6x+ 가속**). vampire-survivors dogfood에서 측정.

---

## 6. 앞으로의 발전 (v3.2.0+)

- **Main session 자동 전환**: Claude Code가 지원 시, Skill 진입 시점에 main을 일시적으로 Claude로 승격하는 패턴. 현재 미구현.
- **Cost tracking**: 각 Stage별 예상/실제 토큰 비용을 `metrics.json`에 기록하고 Retro에서 보고.
- **Budget alerts**: 월 예산 한도 설정 + 도달 시 경고.

---

## 7. 관련 문서

- `references/model-specific-prompts.md` (v3-017) — 모델별 prompt 패턴
- `skills/samvil-doctor/SKILL.md` — 진단 + 권장 모델 안내
- `skills/samvil/SKILL.md` § Model Compatibility — 오케스트레이터 정책

---

_작성: 2026-04-21 · v3.1.0 Sprint 5 (v3-018)_
