---
name: samvil-deploy
description: "Deploy built app to Vercel/Railway/Coolify. Post-QA, pre-retro chain step."
---

# SAMVIL Deploy — 배포 자동화

You are adopting the role of **Deployer**. Deploy the QA-verified app to the target platform.

## When to Invoke

QA 통과 후 samvil-retro 전에 자동 호출 (또는 `/samvil-deploy` 수동 호출)

## Boot Sequence (INV-1)

1. Read `project.state.json` → QA status 확인 (반드시 PASS여야 함)
2. Read `project.seed.json` → 배포 타겟 확인 (`tech_stack.deploy`)
3. Read `.env.example` → 필수 환경변수 파악
4. 배포 플랫폼 감지 (seed 설정 또는 프로젝트 설정 파일)

## Step 1: Pre-Deploy Check

### QA Gate
- `project.state.json`에서 QA verdict 확인
- QA status가 `PASS`가 아니면 **배포 중단** + 사용자에게 보고

### Environment
- `.env.example` 읽기 → `.env` 또는 `.env.production` 변환
- 필수값이 비어있으면 사용자에게 입력 요청 (AskUserQuestion)
- secrets 하드코딩 절대 금지

### Build Artifacts
- `.next/` (Next.js) 또는 `dist/` (Vite/Astro) 존재 확인
- 산출물이 없으면 `npm run build` 실행 (INV-2: `> .samvil/build.log 2>&1`)

## Step 2: Platform Selection

seed에 `tech_stack.deploy`가 있으면 자동 선택, 없으면 사용자에게 선택 제시:

1. **Vercel** — Next.js 기본. `vercel.json` 확인 + `npx vercel --prod`
2. **Railway** — Full-stack. `railway.toml` 확인 + `railway up`
3. **Coolify** — Dockerfile 기반. Dockerfile 생성 + `coolify deploy`
4. **수동** — 빌드 산출물 경로만 안내

## Step 3: Deploy

선택된 플랫폼에 맞는 배포 명령 실행:

### Vercel
```bash
# vercel.json 존재 확인
# npx vercel --prod --yes
```

### Railway
```bash
# railway.toml 또는 nixpacks.toml 확인
# railway up
```

### Coolify
```bash
# Dockerfile 없으면 생성 (Node.js 기본 템플릿)
# coolify deploy
```

### 공통
- 배포 실패 시 재시도 없이 사용자에게 에러 보고
- 배포 URL 발급 후 저장

## Step 4: Post-Deploy

1. 배포 URL 출력
2. `.samvil/deploy-info.json` 저장:
```json
{
  "platform": "vercel",
  "url": "https://my-app.vercel.app",
  "environment": "production",
  "deployed_at": "<ISO timestamp>",
  "deploy_time_seconds": 30
}
```
3. `project.state.json` 업데이트: `deploy_status: "deployed"` + URL

## Output Format

```
[SAMVIL] Deploy complete
  Platform: Vercel
  URL: https://my-app.vercel.app
  Environment: production
  Deploy time: 30s
```

## Chain Continuation

배포 완료(또는 사용자가 스킵) 후 → `samvil-retro` 호출

## Anti-Patterns

1. QA 미통과 앱 배포 금지
2. .env에 secrets 하드코딩 금지
3. 배포 실패 시 재시도 없이 사용자에게 보고
4. seed/state 없이 배포 진행 금지
