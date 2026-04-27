# Option D: 3-tier health UI + Enterprise BFF Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** G4(3-tier health UI 가시화) + G5(Enterprise BFF/monorepo/SSO/OpenAPI 구체 패턴 추가)를 완료해 v4.5.1 완전체를 만든다.

**Architecture:**
- G4: `health_tiers.py`에 이미 존재하는 `get_health_tier_summary()` MCP 툴을 `samvil` 오케스트레이터와 `samvil-doctor` 두 스킬 본문에 호출 지시로 추가한다. `samvil-build`(120 LOC 한도 초과)와 `samvil-qa`(118 LOC, 여유 2줄)는 현재 thinness 한도 문제로 skip.
- G5: `domain_packs.py`의 `webapp-enterprise` `build_guidance` 리스트에 BFF 프록시·monorepo·SSO·OpenAPI 4가지 구체 패턴을 추가한다. Python 모듈 변경이므로 테스트 먼저.
- 버전: 사용자가 새 health badge와 새 build guidance를 보게 됨 → **MINOR bump: v4.5.1 → v4.6.0**.

**Tech Stack:** Python (domain_packs), Markdown (skills), pytest

---

## File Map

| 파일 | 변경 종류 | 역할 |
|---|---|---|
| `mcp/samvil_mcp/domain_packs.py` | Modify | webapp-enterprise build_guidance 4개 항목 추가 |
| `mcp/tests/test_domain_packs.py` | Modify | BFF/monorepo/SSO/OpenAPI 회귀 테스트 3개 추가 |
| `mcp/tests/test_health_tiers.py` | Modify | get_health_tier_summary 출력 포맷 테스트 2개 추가 |
| `skills/samvil/SKILL.md` | Modify | Boot Sequence step 1에 get_health_tier_summary 호출 1줄 추가 |
| `skills/samvil-doctor/SKILL.md` | Modify | MCP Gate 섹션에 get_health_tier_summary 호출 지시 추가 |
| `.claude-plugin/plugin.json` | Modify | "4.5.1" → "4.6.0" |
| `mcp/samvil_mcp/__init__.py` | Modify | __version__ "4.5.1" → "4.6.0" |
| `README.md` | Modify | 첫 줄 버전 태그 v4.5.1 → v4.6.0 |
| `CHANGELOG.md` | Modify | v4.6.0 항목 추가 |

**수정하지 않는 파일:**
- `mcp/samvil_mcp/health_tiers.py` — 로직 완성됨, 변경 없음
- `mcp/samvil_mcp/server.py` — MCP 툴 이미 노출됨, 변경 없음
- `skills/samvil-build/SKILL.md` — 120 LOC 한도
- `skills/samvil-qa/SKILL.md` — 118 LOC (여유 2줄뿐, 의미 있는 지시 추가 불가)

---

## Task 1: G5 — Enterprise BFF 테스트 먼저 (TDD)

**Files:**
- Modify: `mcp/tests/test_domain_packs.py`

- [ ] **Step 1.1: 실패할 테스트 3개 작성**

`mcp/tests/test_domain_packs.py` 끝에 추가 (파일 끝 `def test_total_pack_count():` 뒤에):

```python
# ── Option D: Enterprise BFF/monorepo/SSO/OpenAPI ────────────

def test_webapp_enterprise_build_guidance_has_bff_pattern():
    pack = get_domain_pack("webapp-enterprise")
    guidance_text = " ".join(pack.build_guidance)
    assert "BFF" in guidance_text or "proxy" in guidance_text.lower()


def test_webapp_enterprise_build_guidance_has_monorepo_structure():
    pack = get_domain_pack("webapp-enterprise")
    guidance_text = " ".join(pack.build_guidance)
    assert "turborepo" in guidance_text.lower() or "monorepo" in guidance_text.lower()
    assert "packages/" in guidance_text


def test_webapp_enterprise_build_guidance_has_sso_providers():
    pack = get_domain_pack("webapp-enterprise")
    guidance_text = " ".join(pack.build_guidance)
    assert "NextAuth" in guidance_text or "Clerk" in guidance_text
```

- [ ] **Step 1.2: 테스트 실행 — FAIL 확인**

```bash
cd mcp && .venv/bin/python -m pytest tests/test_domain_packs.py::test_webapp_enterprise_build_guidance_has_bff_pattern tests/test_domain_packs.py::test_webapp_enterprise_build_guidance_has_monorepo_structure tests/test_domain_packs.py::test_webapp_enterprise_build_guidance_has_sso_providers -v
```

Expected: 3개 모두 `FAILED` (현재 build_guidance에 BFF/turborepo/NextAuth 없음)

---

## Task 2: G5 — domain_packs.py webapp-enterprise 확장

**Files:**
- Modify: `mcp/samvil_mcp/domain_packs.py`

현재 `webapp-enterprise`의 `build_guidance` (line 269~):
```python
        build_guidance=[
            "Implement auth with industry-standard libraries (NextAuth, Supabase Auth, etc.).",
            "Use a permission guard pattern: middleware checks role/permission before handler.",
            "Implement tenant context as a request-scoped value, not a global.",
            "Generate API types from OpenAPI schema or shared TypeScript types package.",
            "Use database transactions for operations that span multiple tables.",
            "Add structured logging with correlation IDs for request tracing.",
            "Seed script should create: 1 org, 3 users (admin/member/viewer), sample data.",
        ],
```

- [ ] **Step 2.1: build_guidance 끝에 4개 항목 추가**

위 리스트의 마지막 항목 `"Seed script..."` 뒤에 4개를 추가:

```python
            "BFF pattern: create apps/web/app/api/[...path]/route.ts that proxies to the backend service. Use Next.js rewrites (next.config.ts) or direct fetch with BACKEND_URL from env.",
            "Monorepo structure with turborepo: apps/web (Next.js), apps/api (Express/Hono), packages/ui (shadcn components), packages/types (shared TypeScript), packages/db (Prisma). Root package.json has `turbo` workspaces.",
            "SSO options — NextAuth.js (self-hosted, 50+ providers, free), Clerk (managed, built-in UI, pay-per-MAU), Supabase Auth (PostgreSQL-native, free tier). Choose NextAuth for full control, Clerk for fastest integration.",
            "OpenAPI client gen: run `npx openapi-typescript spec.yaml -o packages/types/src/api.d.ts` after API changes. Use a typed fetch wrapper that accepts the generated paths as generics.",
```

- [ ] **Step 2.2: Task 1 테스트 PASS 확인**

```bash
cd mcp && .venv/bin/python -m pytest tests/test_domain_packs.py::test_webapp_enterprise_build_guidance_has_bff_pattern tests/test_domain_packs.py::test_webapp_enterprise_build_guidance_has_monorepo_structure tests/test_domain_packs.py::test_webapp_enterprise_build_guidance_has_sso_providers -v
```

Expected: 3개 모두 `PASSED`

- [ ] **Step 2.3: 전체 domain_packs 테스트 통과 확인**

```bash
cd mcp && .venv/bin/python -m pytest tests/test_domain_packs.py tests/test_domain_packs_mcp.py -v
```

Expected: 모든 테스트 PASSED (기존 테스트 회귀 없음)

- [ ] **Step 2.4: 커밋**

```bash
git add mcp/samvil_mcp/domain_packs.py mcp/tests/test_domain_packs.py
git commit -m "feat(domain-packs): add BFF/monorepo/SSO/OpenAPI build guidance to webapp-enterprise"
```

---

## Task 3: G4 — health_tiers get_health_tier_summary 테스트 추가

**Files:**
- Modify: `mcp/tests/test_health_tiers.py`

- [ ] **Step 3.1: 2개 테스트 작성**

`mcp/tests/test_health_tiers.py`에 import 추가 및 테스트 클래스 추가:

파일 상단 import 블록에 `get_health_tier_summary` 추가:
```python
from samvil_mcp.health_tiers import (
    TierResult,
    classify_health,
    get_health_tier_summary,
    CRITICAL_TOOLS,
    HEALTHY_THRESHOLD,
    CRITICAL_THRESHOLD,
)
```

파일 끝에 새 클래스 추가:
```python
class TestGetHealthTierSummary:
    def test_summary_contains_tier_badge_healthy(self, tmp_path):
        summary = get_health_tier_summary(project_root=str(tmp_path))
        # No health log = zero-state = healthy
        assert "✅" in summary
        assert "HEALTHY" in summary

    def test_summary_format_has_recommendation(self, tmp_path):
        import json
        health_log = tmp_path / ".samvil" / "mcp-health.jsonl"
        health_log.parent.mkdir(parents=True)
        # Write 30 fail entries to trigger critical
        with health_log.open("w") as f:
            for _ in range(30):
                f.write(json.dumps({"status": "fail", "tool": "save_event"}) + "\n")
        summary = get_health_tier_summary(project_root=str(tmp_path))
        assert "🔴" in summary
        assert "CRITICAL" in summary
        assert "save_event" in summary
```

- [ ] **Step 3.2: 테스트 실행 — PASS 확인**

```bash
cd mcp && .venv/bin/python -m pytest tests/test_health_tiers.py -v
```

Expected: 기존 + 신규 2개 포함 모두 `PASSED`

- [ ] **Step 3.3: 커밋**

```bash
git add mcp/tests/test_health_tiers.py
git commit -m "test(health-tiers): add get_health_tier_summary output format tests"
```

---

## Task 4: G4 — samvil 스킬 Boot Sequence에 health tier badge 추가

**Files:**
- Modify: `skills/samvil/SKILL.md`

현재 Boot Sequence step 1 (line 22):
```
1. `mcp__samvil_mcp__health_check()` — best-effort. Render a one-line summary; degraded MCP is non-fatal (P8).
```

- [ ] **Step 4.1: Boot Sequence step 1 수정**

위 한 줄을 아래로 교체:
```
1. `mcp__samvil_mcp__health_check()` — best-effort. Also call `mcp__samvil_mcp__get_health_tier_summary(project_root="<cwd>")` — best-effort. Render both as one health line: `[health_check one-liner] | Health Tier: ✅/⚠️/🔴 TIER`. Degraded/critical MCP is non-fatal (P8).
```

변경 후 `samvil` LOC: 93 → 95 (2줄: 기존 1줄이 내용 늘어나서 2줄로 wrapping 시, 또는 1줄 유지 시 93 → 93). 120 한도 여유 있음.

- [ ] **Step 4.2: thinness 확인**

```bash
python3 scripts/skill-thinness-report.py --migrated-only --fail-over 120
```

Expected: `samvil` 여전히 `thin` (≤120)

- [ ] **Step 4.3: 커밋**

```bash
git add skills/samvil/SKILL.md
git commit -m "feat(samvil): show 3-tier health badge in Boot Sequence step 1"
```

---

## Task 5: G4 — samvil-doctor 스킬 MCP Gate에 health tier 추가

**Files:**
- Modify: `skills/samvil-doctor/SKILL.md`

현재 MCP Gate 섹션 (`## MCP Gate` 이후):
```
Aggregate MCP-side facts in one call:

```
mcp__samvil_mcp__diagnose_environment()
```

Returns JSON with three sections:
...

## Output

Render one report with three sections (Shell / MCP / Models). ...
- `mcp_health.ok_count` ok, `fail_count` fail, last 1-3
  `recent_failures` (tool + truncated error).
```

- [ ] **Step 5.1: MCP Gate 이후 get_health_tier_summary 호출 추가**

`## MCP Gate` 섹션의 `diagnose_environment()` 호출 다음에 추가 (두 번째 MCP 호출):

```
Also call `mcp__samvil_mcp__get_health_tier_summary(project_root="<cwd>")` — best-effort. Returns markdown with tier badge (✅/⚠️/🔴).
```

그리고 `## Output` 섹션의 MCP 데이터 렌더 지시 맨 앞에 추가:
```
- Tier badge from `get_health_tier_summary` — render as the **first line** of the MCP section.
```

변경 후 예상 LOC: 87 → 90. 120 한도 여유 있음.

- [ ] **Step 5.2: thinness 확인**

```bash
python3 scripts/skill-thinness-report.py --migrated-only --fail-over 120
```

Expected: `samvil-doctor` 여전히 `thin` (≤120)

- [ ] **Step 5.3: 커밋**

```bash
git add skills/samvil-doctor/SKILL.md
git commit -m "feat(samvil-doctor): render 3-tier health badge at top of MCP section"
```

---

## Task 6: 버전 bump v4.5.1 → v4.6.0

**Files:**
- Modify: `.claude-plugin/plugin.json`, `mcp/samvil_mcp/__init__.py`, `README.md`, `CHANGELOG.md`

- [ ] **Step 6.1: 세 파일 버전 동기화**

`.claude-plugin/plugin.json`:
```json
"version": "4.6.0"
```

`mcp/samvil_mcp/__init__.py`:
```python
__version__ = "4.6.0"
```

`README.md` 첫 줄 (현재: `` `v4.5.1` ``):
```
`v4.6.0`
```

- [ ] **Step 6.2: CHANGELOG.md 항목 추가**

CHANGELOG.md 상단(기존 `## v4.5.1` 위)에 삽입:
```markdown
## v4.6.0 — Option D: 3-tier health UI + Enterprise BFF (2026-04-27)

### New
- **G4 (3-tier health UI)**: `samvil` Boot Sequence와 `samvil-doctor` 출력에 `✅/⚠️/🔴` health tier badge 추가. `get_health_tier_summary` MCP 툴 호출.
- **G5 (Enterprise BFF)**: `webapp-enterprise` domain pack `build_guidance`에 BFF 프록시 패턴, turborepo monorepo 구조, SSO 옵션 비교(NextAuth/Clerk/Supabase Auth), OpenAPI client gen 4개 항목 추가.

### Tests
- `test_domain_packs.py`: BFF/monorepo/SSO provider 회귀 테스트 3개.
- `test_health_tiers.py`: `get_health_tier_summary` 포맷(healthy/critical badge) 테스트 2개.

### Version bump reason: MINOR
사용자가 새 health badge(samvil 첫 화면, samvil-doctor 출력)와 새 build guidance를 보게 됨.
```

- [ ] **Step 6.3: validate-version-sync.sh 실행**

```bash
bash hooks/validate-version-sync.sh
```

Expected: `✓ version sync: 4.6.0`

- [ ] **Step 6.4: 커밋**

```bash
git add .claude-plugin/plugin.json mcp/samvil_mcp/__init__.py README.md CHANGELOG.md
git commit -m "chore: bump to v4.6.0 (Option D: 3-tier health UI + Enterprise BFF)"
```

---

## Task 7: 최종 pre-commit 검증 + 캐시 동기화

- [ ] **Step 7.1: pre-commit check 실행**

```bash
bash scripts/pre-commit-check.sh
```

Expected 출력:
```
✓ no hard-coded home paths
✓ version sync: 4.6.0
✓ glossary: no banned terms
✓ pytest: 1463+ passed   ← 기존 1458 + 신규 5
✓ skill wiring smoke: PASS
✓ migrated skills under 120 active lines
✓ phase2 cross-host replay: PASS
✓ server imports clean (167 tools)
✓ all markdown references resolve

═══ pre-commit check: PASS ═══
```

9/9 PASS 확인 필수. 실패 시 원인 수정 후 재실행.

- [ ] **Step 7.2: 캐시 동기화**

```bash
CACHE=$(ls -td ~/.claude/plugins/cache/samvil/samvil/*/ 2>/dev/null | head -1)
cp skills/samvil/SKILL.md "$CACHE/skills/samvil/SKILL.md"
cp skills/samvil-doctor/SKILL.md "$CACHE/skills/samvil-doctor/SKILL.md"
cp mcp/samvil_mcp/domain_packs.py "$CACHE/mcp/samvil_mcp/domain_packs.py"
cp .claude-plugin/plugin.json "$CACHE/.claude-plugin/plugin.json"
cp README.md "$CACHE/README.md"
echo "Cache sync done: $CACHE"
```

- [ ] **Step 7.3: git log 확인**

```bash
git log --oneline -5
```

Expected: 최신 5개 커밋이 이 세션 작업 반영

---

## Task 8: PR 생성 + Retro 작성

- [ ] **Step 8.1: feature branch push + PR**

브랜치명: `option/d-3tier-ui-enterprise-bff`

```bash
git checkout -b option/d-3tier-ui-enterprise-bff
git push -u origin option/d-3tier-ui-enterprise-bff
```

그 다음 PR 생성 (`/pr` 스킬 또는 gh):
```bash
gh pr create \
  --title "Option D: 3-tier health UI + Enterprise BFF (v4.6.0)" \
  --body "$(cat <<'EOF'
## Summary
- G4: samvil/samvil-doctor 스킬에 get_health_tier_summary 호출 추가 (✅/⚠️/🔴 badge)
- G5: webapp-enterprise domain pack에 BFF/monorepo/SSO/OpenAPI 구체 패턴 4개 추가
- Tests: +5 (domain_packs 3, health_tiers 2)
- Version: v4.5.1 → v4.6.0 MINOR

## Test plan
- [ ] bash scripts/pre-commit-check.sh → 9/9 PASS, 1463+ tests
- [ ] python3 -m pytest mcp/tests/test_domain_packs.py mcp/tests/test_health_tiers.py -v
- [ ] python3 scripts/skill-thinness-report.py --migrated-only --fail-over 120 (모두 thin)
- [ ] bash hooks/validate-version-sync.sh → 4.6.0

🤖 Generated with Claude Code
EOF
)"
```

- [ ] **Step 8.2: Retro 작성**

완료 후 `~/docs/samvil-option-d-retro.md` 작성 (무엇이 잘 됐나, 어떤 예상치 못한 점이 있었나, 다음 Option A를 위한 메모).

---

## Self-Review Checklist

**스펙 커버리지:**
- [x] G4: samvil Boot Sequence에 tier badge → Task 4
- [x] G4: samvil-doctor에 tier badge → Task 5
- [x] G4 optional (samvil-build/qa): LOC 한도로 skip — 명시적으로 documented
- [x] G5: BFF 패턴 → Task 2 step 2.1 (첫 번째 항목)
- [x] G5: monorepo (turborepo) → Task 2 step 2.1 (두 번째 항목)
- [x] G5: SSO 비교 → Task 2 step 2.1 (세 번째 항목)
- [x] G5: OpenAPI client gen → Task 2 step 2.1 (네 번째 항목)
- [x] Tests 5+ → Task 1 (3), Task 3 (2) = 5개 total
- [x] 버전 bump MINOR → Task 6
- [x] pre-commit check → Task 7.1
- [x] 캐시 동기화 → Task 7.2
- [x] PR → Task 8.1
- [x] Retro → Task 8.2

**타입/이름 일관성:**
- Task 2에서 추가하는 4개 문자열은 단순 list append — 기존 타입 변경 없음
- Task 3/1의 함수명 `get_health_tier_summary`는 `health_tiers.py:get_health_tier_summary()` 와 일치
- Task 4/5의 MCP 툴명 `mcp__samvil_mcp__get_health_tier_summary` 는 server.py:4645에서 확인된 실제 툴명

**Placeholder 없음:** 모든 코드 블록에 실제 내용 포함 확인.
