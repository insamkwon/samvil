# Skill Boot Contract (W3.1)

> 모든 stage skill의 Boot Sequence가 따라야 하는 공통 계약. 각 SKILL.md는
> stage 특화 파라미터(aggregator 도구, 파일 목록)만 다르고, 아래 골격은
> 동일해야 한다. 드리프트는 `scripts/check-skill-wiring.py`의
> Boot Contract 체크가 잡는다.

## 골격 (순서 고정)

1. **TaskUpdate** — 해당 stage task를 `in_progress`로.
2. **Stage entry event** — `mcp__samvil_mcp__save_event(session_id="<sid>",
   event_type="<stage>_started", stage="<stage>", data="{}")`.
   Best-effort (INV-5). server.py가 `evidence_posted subject="stage:<stage>"`
   claim을 자동 게시한다 (hook 경로 실패 시의 결정론적 백업).
3. **SSOT reads** — 대화 기억 금지 (INV-1). stage별 aggregator 도구
   (`aggregate_*_context` / `aggregate_orchestrator_state`)를 우선 호출하고,
   반환 `errors[]` 또는 MCP 불통 시 파일 직접 읽기로 강등.
4. **P8 fallback** — MCP 실패 시 `SKILL.legacy.md`의 해당 섹션으로 폴백.
   파이프라인은 절대 hook/MCP 장애로 멈추지 않는다.
5. **Contract layer entry** (해당 stage가 role 분리 대상일 때) —
   `route_task` → `validate_role_separation` → `claim_post` 순.
   상세: `references/contract-layer-protocol.md`.

## 계약 토큰 (기계 검증 대상)

| 토큰 | 의미 | 검증 |
|---|---|---|
| `save_event` | stage entry event 발행 | 필수 |
| `SKILL.legacy.md` 또는 `P8` | MCP 장애 폴백 경로 명시 | 필수 |

새 stage skill 추가 시: 이 골격대로 Boot를 쓰고,
`scripts/check-skill-wiring.py`의 `BOOT_CONTRACT_SKILLS`에 등록한다.
`event_type` 신설 시 server.py `_STAGE_ENTRY_EVENTS` /
`_EVENT_TYPE_TO_STAGE` 갱신 (CLAUDE.md 체크리스트).

## 명시적 비목표

- 부트 본문을 include/치환 매크로로 추출하지 않는다 — CC Skill 로더는
  전처리를 지원하지 않고, 호출 라인 자체는 stage 특화라 추출 이득이 없다.
- 이 문서는 규범(normative)이고, 각 SKILL.md의 부트가 구현이다.
