# PATH Routing Guide (v2.4.0+)

> 인터뷰 질문을 어떻게 누구에게 보낼지 결정하는 규칙. Manifesto v3 P2 (Description vs Prescription) 구현.

---

## 🎯 핵심 원칙

**사실(Description)은 AI가 자동 확인. 결정(Prescription)은 사용자가.**

각 인터뷰 질문마다 MCP `route_question` 호출하여 경로 결정.

---

## 📋 5가지 PATH

| Path | 의미 | 누가 답함 | Answer Prefix |
|------|------|----------|---------------|
| **1a** auto_confirm | 코드/manifest에서 즉시 확정 | AI (자동, 사용자 미개입) | `[from-code][auto-confirmed]` |
| **1b** code_confirm | AI 제안 → 사용자 Y/N | AI + 사용자 간단 확인 | `[from-code]` (user가 No면 `[from-user][correction]`) |
| **2** user | 인간 판단 필요 | 사용자 | `[from-user]` |
| **3** hybrid | 코드 + 판단 혼합 | AI 조사 + 사용자 결정 | `[from-user]` (결정이 사용자이므로) |
| **4** research | 외부 리서치 | AI WebFetch → 사용자 Y/N | `[from-research]` |

추가:
- **forced_user** — Rhythm Guard 발동 시 강제로 PATH 2. Answer prefix: `[from-user]`

---

## 🔀 라우팅 로직 (우선순위)

1. **force_user=True (Rhythm Guard 발동)** → `forced_user`
   - 연속 3회 AI 답변 후 다음 질문 무조건 사용자

2. **Decision Keywords 감지** → `user` (PATH 2)
   - "should we", "prefer", "결정", "선택", "목표", "AC", ...
   - 결정 언어 → 반드시 사용자

3. **Research Keywords 감지** → `research` (PATH 4)
   - "rate limit", "pricing", "최신 버전", "Stripe/AWS API", ...
   - 외부 지식 → 웹 검색

4. **Manifest 매칭** → `auto_confirm` 또는 `code_confirm`
   - Framework, Language, Package Manager 질문 → `auto_confirm` (confidence 높음)
   - Database, Auth 질문 → `code_confirm` (간접 추론이라 user 확인)

5. **Default** → `user`
   - 매칭 안 되면 보수적으로 사용자 판단 요청

---

## 🎨 스킬에서 사용 방법

### 1. 프로젝트 스캔 (한 번)

인터뷰 시작 시:

```
manifest_facts = mcp.scan_manifest(project_path=<CWD>)
# 결과를 state.json에 저장 (향후 재사용)
```

### 2. 각 질문마다 라우팅

```
# 현재 streak 읽기
state = read .samvil/project.state.json
streak = state.get("ai_answer_streak", 0)
force_user = streak >= 3  # Rhythm Guard

# 라우팅
result = mcp.route_question(
    question="What framework is used?",
    manifest_facts=json.dumps(manifest_facts),
    force_user=force_user,
)
```

### 3. Path별 액션

**PATH 1a (auto_confirm)**:
```
사용자에게 표시:
  ℹ️ 자동 감지: Next.js 14.2.0 (package.json)
사용자 입력 없이 바로 기록.
```

**PATH 1b (code_confirm)**:
```
AskUserQuestion:
  "코드에서 찾았음: PostgreSQL (prisma/schema.prisma)
   이게 맞나요?"
  → Yes: 답변 그대로 기록
  → No: 사용자 수정 입력 요청 → [from-user][correction]
```

**PATH 2 (user)**:
```
일반 AskUserQuestion. 답변은 [from-user].
```

**PATH 4 (research)**:
```
1. Tavily 등으로 웹 검색
2. 결과를 사용자에게 제시:
   🔍 리서치 결과: Stripe rate limit 100 req/sec (stripe.com)
   이거 맞나요?
   → Yes: [from-research]
   → No: [from-user][correction]
```

**forced_user**:
```
⚠️ [SAMVIL] 연속 3회 자동 확정. 이번 질문은 직접 답변해주세요.
+ AskUserQuestion
```

### 4. Streak 업데이트 (매 답변 후)

```
source = mcp.extract_answer_source(answer)
result = mcp.update_answer_streak(current_streak=streak, answer_source=source)

state["ai_answer_streak"] = result["new_streak"]
write state.json
```

### 5. Tracks 업데이트 (매 라운드)

인터뷰 초반에 features 파악되면:
```
tracks = mcp.manage_tracks(action="init", features=json.dumps(features))
```

각 라운드에서:
```
# 현재 토픽에 대한 라운드
tracks = mcp.manage_tracks(action="update", tracks_json=..., track_name=<current>)

# Breadth-Keeper 체크
verdict = mcp.manage_tracks(action="check", tracks_json=...)
if verdict["force_breadth"]:
    # 다른 tracks로 전환 질문 삽입
    ask "미해결 tracks: {verdict['unresolved_tracks']}. 이 중 먼저 정할 게 있나요?"
```

토픽 완료 시:
```
tracks = mcp.manage_tracks(action="resolve", tracks_json=..., track_name=<done>)
```

---

## 📝 Answer Prefix 예시

```markdown
# .samvil/interview-summary.md (내부 기록)

Q1: 어떤 프레임워크를 쓸까요?
A1: [from-code][auto-confirmed] Next.js 14.2.0 (package.json)

Q2: 데이터베이스는?
A2: [from-code] PostgreSQL (prisma/schema.prisma)

Q3: Stripe rate limit은?
A3: [from-research] 100 read ops/sec (stripe.com/docs)

Q4: 결제 실패 시 처리?
A4: [from-user] saga 패턴으로 롤백

Q5: 관리자 대시보드?
A5: [from-user][correction] 아니요, Grafana 대신 직접 구현
```

---

## 🎨 사용자 UI (output-format.md 참조)

```
[SAMVIL] 🔵 Phase: Interview (Stage 1/5)
[SAMVIL] 종료 조건: ambiguity ≤ 0.05 (standard tier)

[SAMVIL] 🔍 프로젝트 스캔 중...
[SAMVIL] ℹ️ 자동 감지: Next.js 14.2.0, TypeScript, Prisma+PostgreSQL
         출처: package.json, prisma/schema.prisma

Q: 이 앱의 타겟 사용자는?
→ [사용자] 프리랜서 디자이너

[SAMVIL] 💬 사용자 선택 기록.

Q: 어떤 결제 서비스를 쓰시나요?
→ [사용자] Stripe

⚠️ [SAMVIL] 정보: Stripe 선택됨. Rate limit 정보가 필요합니다.
[SAMVIL] 🔍 PATH 4 리서치 중... 
[SAMVIL] 🔍 리서치 결과: Stripe API rate limit = 100 read / 25 write ops/sec (live mode)
         출처: stripe.com/docs/rate-limits

이게 맞나요?
→ [사용자] Yes
```

---

## 📎 관련 문서

- `references/output-format.md` — 아이콘 + 출력 포맷
- `references/boot-sequence.md` — MCP Tool Loading
- `~/docs/ouroboros-absorb/01-path-routing.md` — 상세 배경
- `~/docs/ouroboros-absorb/02-dialectic-rhythm-guard.md` — Rhythm Guard 상세

---

## ⚙️ 관련 MCP Tools

| Tool | 용도 |
|------|------|
| `scan_manifest` | 프로젝트 manifest 스캔 → facts |
| `route_question` | 질문 → path 결정 |
| `update_answer_streak` | Rhythm Guard 카운터 |
| `manage_tracks` | Breadth-Keeper tracks 관리 |
| `extract_answer_source` | Answer prefix 파싱 |
| `score_ambiguity` | Milestone + Floor + missing_items |
