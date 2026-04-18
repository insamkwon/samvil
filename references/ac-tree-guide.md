# AC Tree Guide (v2.5.0+, Ouroboros #06 흡수)

> Acceptance Criteria를 recursive tree로 관리. Flat AC array 하위호환 유지.

---

## 🎯 목적

기존: `acceptance_criteria: ["User can sign up", ...]` flat 배열.
문제: 대형 AC ("User can sign up") = 실제로는 5~10개 sub-task.

**해결**: Tree 구조로 재귀 분해.

```
AC-1 User can sign up
├── AC-1.1 Email format validation
├── AC-1.2 Password hashing (bcrypt)
├── AC-1.3 User table insert with UNIQUE constraint
│   ├── AC-1.3.1 Duplicate email rejection
│   └── AC-1.3.2 Transaction handling
├── AC-1.4 Confirmation email send
└── AC-1.5 Success page redirect
```

---

## 📝 Schema (backward-compatible)

### Flat (v2.4.x 이하, 지속 지원)

```json
"acceptance_criteria": [
  "User can sign up",
  "User can log in"
]
```

### Tree (v2.5.0+ 옵션)

```json
"acceptance_criteria": [
  {
    "id": "AC-1",
    "description": "User can sign up",
    "children": [
      {
        "id": "AC-1.1",
        "description": "Email format validation",
        "children": []
      },
      ...
    ]
  }
]
```

### 혼합 허용

```json
"acceptance_criteria": [
  "Simple AC as string",                           // ← 자동 leaf 노드
  {"id": "AC-2", "description": "complex", "children": [...]}  // ← tree
]
```

Loader (`ac_tree.load_ac_from_schema`)가 자동으로 ACNode로 변환.

---

## 🌳 제약

- **MAX_DEPTH = 3** — 과도한 재귀 분해 방지
- Leaf 노드만 실제 빌드 태스크
- Branch 노드는 자식 상태 aggregate

---

## 🎨 Status Aggregation

```
Branch status = aggregate of children:
  all pass       → pass
  any fail       → fail
  any in_progress → in_progress
  any blocked    → blocked
  otherwise       → pending
```

---

## 🔧 MCP Tools

| Tool | 용도 |
|------|------|
| `parse_ac_tree` | string or dict → ACNode |
| `render_ac_tree_hud` | ASCII HUD 렌더 |
| `suggest_ac_decomposition` | Heuristic 분해 제안 (LLM 없이) |

---

## 📋 사용 시나리오

### 시나리오 A: Greenfield 프로젝트 — Flat 유지

v2.4.x와 동일한 UX. 사용자는 tree 신경 쓸 필요 없음.

### 시나리오 B: 대형 앱 — Manual tree

사용자가 seed.json에 직접 tree 구조 정의:

```json
{
  "features": [
    {
      "name": "user-management",
      "acceptance_criteria": [
        {
          "id": "AC-1",
          "description": "User sign up with email + password",
          "children": [
            {"id": "AC-1.1", "description": "Email validation"},
            {"id": "AC-1.2", "description": "Password hashing"},
            {"id": "AC-1.3", "description": "DB insert"}
          ]
        }
      ]
    }
  ]
}
```

### 시나리오 C: AI-assisted decomposition (v2.5.0 기초, LLM은 future)

`suggest_ac_decomposition`이 heuristic하게 제안:
- "Email validation and password hashing" → ["Email validation", "password hashing"]
- "Create, edit, delete" → ["Create", "edit", "delete"]

복잡한 decomposition은 LLM 필요 (v2.6+에서).

---

## 🎯 Build/QA 순회

### samvil-build (v2.6+, 현재는 flat 기본)

```python
# Pseudocode
tree = load_ac_tree(seed["acceptance_criteria"])
for leaf in leaves(tree):
    assign_to_worker_agent(leaf)
    # Branch는 자동 aggregate
```

### samvil-qa (v2.5.0+, 선택적)

Tree 구조 있으면 leaf 단위 verdict, branch는 aggregate.
Flat만 있으면 기존처럼 per-feature verdict.

---

## 🏗️ AC Tree HUD 예시

```
AC Tree HUD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AC-1 사용자 회원가입            [⟳ in_progress]
├── ✓ AC-1.1 이메일 검증
├── ✓ AC-1.2 비번 해싱
├── ⟳ AC-1.3 DB 저장
│   ├── ✓ AC-1.3.1 중복 거부
│   └── ⟳ AC-1.3.2 트랜잭션
├── ⏸ AC-1.4 이메일 발송
└── ⏸ AC-1.5 리디렉션

AC-2 결제                       [⏸ blocked]
└── (blocked by AC-1)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 🚧 v2.5.0에서의 범위

- ✅ Schema 확장 (flat + tree 지원)
- ✅ Loader (`load_ac_from_schema`)
- ✅ Status aggregation
- ✅ ASCII HUD 렌더러
- ✅ Heuristic decomposition suggestion
- ❌ LLM-based decomposition (future)
- ❌ Build 스킬 tree 순회 (future, 현재는 flat으로 동작)
- ❌ QA 스킬 tree aggregate (future)

**즉, v2.5.0은 infrastructure만**. 실제 tree 기반 실행은 v2.6.0+.

---

## 📎 관련

- `mcp/samvil_mcp/ac_tree.py` — 구현
- `mcp/tests/test_ac_tree.py` — 테스트
- Ouroboros 흡수 문서: `~/docs/ouroboros-absorb/06-recursive-ac-decomposition.md`
