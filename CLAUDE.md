# SAMVIL — AI Vibe-Coding Harness

> "Shape it on the anvil, root it like ginseng."

## What is this?

SAMVIL is a CC Plugin that generates full web applications from a one-line prompt.

```
/samvil "task management SaaS"
  → Interview → Seed → Scaffold → Build → QA → Retro
```

## Architectural Invariants

Every skill in this plugin MUST obey these 4 rules:

1. **INV-1: File is SSOT** — Read seed.json + state.json from disk before any work. Never rely on conversation context.
2. **INV-2: Build logs to files** — `npm run build > .samvil/build.log 2>&1`. Only read on error.
3. **INV-3: Interview to file** — Interview summary saved to `interview-summary.md`. Seed reads this file.
4. **INV-4: Chain pattern** — Each skill invokes the next via Skill tool. State.json enables recovery if chain breaks.

## Key Rules

1. **Seed is SSOT** — Every stage reads project.seed.json before acting
2. **Build must never break** — npm run build must pass after every change
3. **Circuit Breaker** — MAX_RETRIES=2 for build failures, then stop and report
4. **User Checkpoints** — No stage proceeds without user approval
5. **Context Kernel** — seed.json + state.json + blueprint.json + decisions.log

## Target Output

Next.js 14 + Tailwind CSS + shadcn/ui + TypeScript + App Router

## Versioning (필수)

**git push 전에 반드시 버전을 올린다.** `.claude-plugin/plugin.json`의 `version` 필드.

### 판단 기준

| 변경 유형 | 버전 | 예시 |
|----------|------|------|
| **PATCH** (0.0.+1) | 버그 수정, 오타, 프롬프트 미세 조정 | 체인 끊김 수정, Floor Rule 문구 개선 |
| **MINOR** (0.+1.0) | 기능 추가, 에이전트 추가, 프리셋 추가, 스킬 추가 | 새 앱 프리셋, 새 디자인 테마, Phase 2.5 추가 |
| **MAJOR** (+1.0.0) | 호환 안 되는 변경, 아키텍처 변경 | seed 스키마 변경, 파이프라인 구조 변경, INV 규칙 변경 |

### 자동 적용 규칙

push할 때 Claude가:
1. 커밋 내용을 보고 PATCH/MINOR/MAJOR 판단
2. `plugin.json`의 version 자동 증가
3. 커밋에 포함해서 push

### 현재 버전

`0.2.0` — M1~M10 + v2 UX + Health Check + Update
