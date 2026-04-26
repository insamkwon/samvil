---
name: samvil-deploy-legacy
description: "Legacy reference for samvil-deploy. The active skill is the ultra-thin SKILL.md (T3.4). This file preserves the original Korean prose, full per-platform branches (Vercel/Railway/Coolify/EAS/Cron/Serverless/CC-skill/Manual), and historic checklists for forensic lookup."
---

# SAMVIL Deploy — 배포 자동화 (legacy reference)

> **NOT loaded by Claude Code as an active skill.** The active SAMVIL
> deploy entry-point is `SKILL.md`. This file is preserved verbatim from
> v3.34.x for forensic lookup of the original full prose, per-platform
> deploy commands, and the historic post-deploy report templates that
> the thin skill now factors through `evaluate_deploy_target`.

You are adopting the role of **Deployer**. Deploy the QA-verified app to the target platform.

## When to Invoke

QA 통과 후 samvil-retro 전에 자동 호출 (또는 `/samvil-deploy` 수동 호출)

## Boot Sequence (INV-1)

1. Read `project.state.json` → QA status 확인 (반드시 PASS여야 함)
2. Read `project.seed.json` → 배포 타겟 확인 (`tech_stack.deploy`)
3. Read `.env.example` → 필수 환경변수 파악
4. 배포 플랫폼 감지 (seed 설정 또는 프로젝트 설정 파일)
5. **Follow `references/boot-sequence.md`** for metrics start/end and checkpoint rules.
6. **v3.2 Contract Layer — stage entry**: `mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="deploy_started", stage="deploy", data="{}")`. Best-effort, MCP 내부 auto-claim이 `.samvil/claims.jsonl`에 `evidence_posted subject="stage:deploy"` 자동 기록.

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

Read `seed.solution_type` to determine deployment approach.

### web-app

seed에 `tech_stack.deploy`가 있으면 자동 선택, 없으면 사용자에게 선택 제시:

1. **Vercel** — Next.js 기본. `vercel.json` 확인 + `npx vercel --prod`
2. **Railway** — Full-stack. `railway.toml` 확인 + `railway up`
3. **Coolify** — Dockerfile 기반. Dockerfile 생성 + `coolify deploy`
4. **수동** — 빌드 산출물 경로만 안내

### game

Game 프로젝트는 Vite 빌드로 정적 파일을 생성하고 Vercel/GitHub Pages에 배포합니다.

seed에 `tech_stack.deploy`가 있으면 자동 선택, 없으면 사용자에게 선택 제시:

1. **Vercel** (추천) — 정적 호스팅. CDN 배포. 커스텀 도메인.
   ```bash
   cd ~/dev/<seed.name>
   npm run build
   # dist/ 폴더가 생성됨
   npx vercel --prod --yes
   ```

2. **GitHub Pages** — 무료 정적 호스팅. `gh-pages` 브랜치로 배포.
   ```bash
   cd ~/dev/<seed.name>
   npm run build
   npx gh-pages -d dist
   ```

3. **수동** — `dist/` 폴더를 웹 서버에 직접 배포.

**빌드 산출물**:
```bash
cd ~/dev/<seed.name>
npm run build > .samvil/build.log 2>&1
ls dist/
# index.html + assets/ (JS bundle, images, audio)
```

**배포 확인**: 브라우저에서 URL 접속 → Phaser 게임이 로드되는지 확인.

### dashboard

Dashboard 프로젝트는 web-app과 동일한 방식으로 배포합니다. recharts bundle size 최적화에 유의:

seed에 `tech_stack.deploy`가 있으면 자동 선택, 없으면 사용자에게 선택 제시:

1. **Vercel** (추천) — Next.js 기본. `vercel.json` 확인 + `npx vercel --prod`
   - recharts tree-shaking 자동 적용 (Next.js production build)
   - `next.config.mjs`에 `output: 'standalone'` 설정으로 bundle 최적화

2. **Railway** — Full-stack. `railway.toml` 확인 + `railway up`

3. **Coolify** — Dockerfile 기반. Dockerfile 생성 + `coolify deploy`

4. **수동** — 빌드 산출물 경로만 안내

**Bundle size 안내:**
```
recharts 전체 import: ~450KB (gzipped ~130KB)
→ import { LineChart, XAxis, ... } from 'recharts' 로 tree-shaking 권장
→ @next/bundle-analyzer로 번들 크기 확인 가능
```

### mobile-app

seed에 `tech_stack.deploy`가 있으면 자동 선택, 없으면 사용자에게 선택 제시:

1. **EAS Build (APK preview)** — 빠른 테스트 빌드.
   ```bash
   cd ~/dev/<seed.name>
   eas build --platform android --profile preview
   ```
   - APK 파일이 생성되어 직접 설치 가능
   - App Store/Play Store 등록 없이 테스트

2. **EAS Build (production)** — 스토어 제출용 빌드.
   ```bash
   cd ~/dev/<seed.name>
   eas build --platform ios --profile production
   eas build --platform android --profile production
   ```
   - App Store Connect / Google Play Console에 제출
   - 인증서/프로비저닝 필요 (가이드만 제공)

3. **Expo Update (OTA)** — 코드 업데이트를 스토어 심사 없이 배포.
   ```bash
   cd ~/dev/<seed.name>
   eas update --branch production --message "bug fix"
   ```

4. **수동** — 개발 서버 실행 안내만 제공.

**배포 전 체크리스트 안내:**
```
[SAMVIL] 모바일 배포 준비
  1. EAS 계정 설정: eas login
  2. 프로젝트 연결: eas build:configure
  3. 앱 서명 (iOS): Apple Developer 계정 필요
  4. 앱 서명 (Android): keystore 생성 필요
  5. 스토어 등록: App Store Connect / Google Play Console

  빠른 테스트:
    eas build --platform android --profile preview
    → APK 다운로드 링크 제공

  프로덕션:
    eas build --platform ios --profile production
    eas build --platform android --profile production
    → 스토어 제출 가이드
```

### automation (execution type)

Read `seed.core_flow.trigger` or `blueprint.execution.type` to determine deployment:

1. **CC skill** — `execution.type: "cc-skill"`
   - Use CronCreate tool to register the skill as a scheduled task
   - Print execution command: `/<seed.name> [args]`

2. **Cron** — `execution.type: "cron"`
   - Generate crontab entry template
   - Save to `.samvil/crontab-template`
   - Print install command: `crontab .samvil/crontab-template`

3. **Serverless** — `execution.type: "webhook"` or manual serverless
   - Generate `serverless.yml` (AWS Lambda) template if Python
   - Generate `vercel.json` with rewrites if Node
   - Print deploy command

4. **Manual** — `execution.type: "cli"`
   - Print run command: `python src/main.py --config .env` (Python)
   - Print run command: `npx tsx src/main.ts --config .env` (Node)
   - Remind about `.env` setup

## Step 3: Deploy

### web-app

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

### automation

#### CC skill 배포

Use CronCreate tool to register:

```
CronCreate(
  cron: "<schedule from seed.core_flow.trigger>",
  prompt: "Run /<seed.name>",
  recurring: true,
  durable: true
)
```

Output:
```
[SAMVIL] CC Skill 등록 완료
  스킬: /<seed.name>
  스케줄: <cron expression>
  실행: /<seed.name> [args]
```

#### Cron 배포

Generate `.samvil/crontab-template`:
```bash
# <seed.name> — <seed.description>
# Install: crontab .samvil/crontab-template
# Logs: .samvil/cron.log

# <schedule from seed.core_flow.trigger>
<schedule> cd <project_path> && source .venv/bin/activate && python src/main.py --config .env >> .samvil/cron.log 2>&1
```

Output:
```
[SAMVIL] Cron 배포 준비 완료
  템플릿: .samvil/crontab-template
  설치: crontab .samvil/crontab-template
  로그: .samvil/cron.log
```

#### Serverless 배포

**Python (AWS Lambda):** Generate `serverless.yml`:
```yaml
service: <seed.name>
frameworkVersion: '3'
provider:
  name: aws
  runtime: python3.12
  environment:
    API_KEY: ${env:API_KEY}
functions:
  main:
    handler: src/main.handler
    events:
      - schedule:
          rate: cron(0 9 * * ? *)
          enabled: true
      - http:
          path: run
          method: post
```

**Node (Vercel):** Generate `vercel.json`:
```json
{
  "functions": {
    "api/run.ts": { "runtime": "nodejs20.x" }
  },
  "crons": [
    { "path": "/api/run", "schedule": "0 9 * * *" }
  ]
}
```

Output:
```
[SAMVIL] Serverless 배포 준비 완료
  설정: serverless.yml (또는 vercel.json)
  배포: serverless deploy (또는 vercel --prod)
```

#### Manual 배포

Output:
```
[SAMVIL] 수동 실행 안내
  실행: cd ~/dev/<seed.name> && python src/main.py --config .env
  Dry-run: python src/main.py --dry-run
  설정: .env 파일에 API 키 등 필수 값 입력
```

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

### web-app

```
[SAMVIL] Deploy complete
  Platform: Vercel
  URL: https://my-app.vercel.app
  Environment: production
  Deploy time: 30s
```

### mobile-app

```
[SAMVIL] Deploy complete (mobile)
  Type: EAS Build
  Platform: <ios / android / both>
  Profile: <preview / production>
  Build: <EAS build URL or "pending">
  OTA: eas update --branch production
  Config: app.json에 권한/버전 확인
```

### dashboard

```
[SAMVIL] Deploy complete (dashboard)
  Platform: <Vercel / Railway / Coolify>
  URL: https://my-dashboard.vercel.app
  Environment: production
  Deploy time: 30s
  Bundle note: recharts tree-shaking 적용됨
```

### automation

```
[SAMVIL] Deploy complete (automation)
  Type: <cron|serverless|cc-skill|manual>
  Stack: <python-script|node-script|cc-skill>
  Command: <execution command or schedule>
  Config: .env에 필수값 입력 필요
```

## Chain Continuation

배포 완료(또는 사용자가 스킵) 후 → **반드시** `samvil-retro` 호출.

**필수 동작** (v3.2 L1.5 — 스킵 경로 체인 끊김 regression 방지):

1. 배포 완료 또는 사용자가 "나중에" 선택 → `.samvil/handoff.md`에 Deploy 섹션 append
2. `mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="deploy_complete", stage="deploy", data='{"status":"<deployed|skipped>"}')` 호출
3. **즉시** `Invoke the Skill tool with skill: samvil-retro` — 사용자 승인 대기하지 말고 자동 진행. Retro는 회고일 뿐이고 파일 변경이 없어서 P10 Irreversibility 대상 아님.
4. Retro가 끝나면 완료 메시지 + samvil-status 출력.

이 체인을 빠뜨리면 파이프라인이 Deploy에서 멈추고 Retro가 실행되지 않아 harness-feedback.log가 갱신되지 않음. v3.2 dogfood (weekly-exercise-tracker run)에서 이 regression이 확인됐고 수정됨.

## Anti-Patterns

1. QA 미통과 앱 배포 금지
2. .env에 secrets 하드코딩 금지
3. 배포 실패 시 재시도 없이 사용자에게 보고
4. seed/state 없이 배포 진행 금지
