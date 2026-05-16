# SAMVIL Tutorial (Codex CLI)

5-min hands-on tour through a sample SAMVIL pipeline. Builds a simple
todo app while explaining each stage's purpose. Korean.

## Prerequisites

Optional: `read_chain_marker(project_root="${PWD}")` to detect existing
SAMVIL state. If found, ask user whether to start tutorial in a new
directory (recommended) or in current state.

## Steps

### 0. Confirm start + environment

Ask: "튜토리얼 시작할까요?" with options:
- 네, 시작 → Step 1
- 먼저 환경 진단부터 → invoke `/samvil-doctor` then return
- 취소 → stop

### 1. Directory setup

Direct user to: `mkdir -p ~/dev/samvil-tutorial-app && cd ~/dev/samvil-tutorial-app`.
Tutorial uses isolated directory — non-destructive.

### 2. Interview stage explanation

Explain (5 min total budget):
- 인터뷰 = 1개씩 결정. 5-10 min.
- Per answer: ✅ Confirmed [Phase] + 잠정 AC + ℹ️ 자동확인 (Brownfield)
- Gates: Step 0.5 Epic Claim / Step 1 Refine Gate / Step 4.5 Restate Gate

Direct user: `/samvil "간단한 할 일 앱 만들어줘"`. Interview itself is the lesson.

### 3. Seed → council → design stages

Explain:
- samvil-seed = 답변 + 잠정 AC → seed.json
- v4.21+ Refine Gate data → no LLM guessing
- v4.23+ evaluation_principles + exit_conditions auto-derived
- samvil-council (standard tier+) = multi-agent debate → blueprint.json

### 4. Scaffold + Build stages

Explain:
- samvil-scaffold = project skeleton (Next.js / Vite / Phaser / Expo)
- samvil-build = AC leaf-level code generation (parallel)
- Circuit Breaker (max 2 retries)

### 5. QA + completion

Explain:
- samvil-qa = 3-pass (build / AC evidence / quality)
- v4.23+ weighted score via seed.evaluation_principles
- v4.25+ `--target=seed` for seed faithfulness check
- PASS → optional samvil-deploy
- samvil-retro for next-run improvement

End: "튜토리얼 완료. 본인 프로젝트로 시작 OK. 디렉토리 정리: `rm -rf ~/dev/samvil-tutorial-app`."

## Anti-Patterns

1. NEVER overload — 5 stages, one screen each, don't expand all.
2. NEVER skip pauses between stages.
3. NEVER hide failure paths — explain Circuit Breaker.

## Chain

Terminal skill — **do not call** `write_chain_marker`. User invokes
`/samvil` for real project separately.
