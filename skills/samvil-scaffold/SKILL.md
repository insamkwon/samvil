---
name: samvil-scaffold
description: "CLI-based project scaffold. Supports Next.js, Vite+React, Astro. No template folder dependency."
---

# SAMVIL Scaffold — CLI-Based Project Generation

You are adopting the role of **Scaffolder**. Create a project directory with a verified, buildable skeleton using CLI tools (no template folder).

## Boot Sequence (INV-1)

1. Read `project.seed.json` from the project directory
2. Read `project.state.json` → confirm `current_stage` is `"scaffold"`
3. Read `project.config.json` → `selected_tier`
4. Read `project.blueprint.json` → architecture decisions (if exists)
   - Use `key_libraries` to know which npm packages to install
   - Use `component_structure` to create feature directories

## Process

### Step 1: Determine Stack

Read `seed.tech_stack.framework` to determine which CLI to use:

| `tech_stack.framework` | CLI Command | 비고 |
|---|---|---|
| `nextjs` | `npx create-next-app@14` | SSR, API routes, SEO |
| `vite-react` | `npm create vite@latest -- --template react-ts` | 가벼움, SPA |
| `astro` | `npm create astro@latest` | 정적, 빠른 로딩 |

기본값: `nextjs` (seed에 명시 없으면)

### Step 2: Generate Project

#### Next.js

```bash
cd ~/dev
npx create-next-app@14 <seed.name> --typescript --tailwind --app --src-dir=false --import-alias="@/*" --eslint --use-npm <<< $'No\n'
cd ~/dev/<seed.name>
# create-next-app이 npm install까지 완료함. 추가 패키지만 별도 설치.
```

**Next.js 14 + shadcn 호환 설정** (fix-log 패턴):
- `app/layout.tsx`: Geist 로컬 폰트 → `Inter` from `next/font/google`로 교체
- `tailwind.config.ts`: shadcn 호환 HSL 컬러 시스템으로 교체 (border, input, ring, primary 등)
- `app/globals.css`: HSL 기반 CSS variables로 교체 (`--background: 0 0% 100%` 형식)
- `tailwindcss-animate` 플러그인 설치: `npm install tailwindcss-animate --save-dev`

#### Vite + React

```bash
cd ~/dev
npm create vite@latest <seed.name> -- --template react-ts
cd ~/dev/<seed.name>
npm install
npm install -D tailwindcss @tailwindcss/vite
```

**Vite + Tailwind v4 설정**:
- `vite.config.ts`에 `@tailwindcss/vite` 플러그인 추가
- `src/index.css`에 `@import "tailwindcss"` 추가
- `tsconfig.json`에 `"paths": { "@/*": ["./src/*"] }` 추가
- `vite.config.ts`에 `resolve.alias` 추가: `"@": path.resolve(__dirname, "./src")`

shadcn/ui는 Vite에서 v4 네이티브 지원:
```bash
npx shadcn@latest init -y -d
npx shadcn@latest add button input -y
```

#### Astro

```bash
cd ~/dev
npm create astro@latest <seed.name> -- --template minimal --install --no-git --typescript strict
cd ~/dev/<seed.name>
npx astro add tailwind -y
npx astro add react -y
```

### Step 3: Common Setup

모든 스택 공통:

1. **디렉토리 생성**:
   ```bash
   mkdir -p ~/dev/<seed.name>/components ~/dev/<seed.name>/lib ~/dev/<seed.name>/.samvil
   ```
   (Vite는 `src/components`, `src/lib`)

2. **cn() utility** (shadcn 없으면 직접 생성):
   ```bash
   npm install clsx tailwind-merge
   ```
   `lib/utils.ts` (또는 `src/lib/utils.ts`):
   ```typescript
   import { type ClassValue, clsx } from "clsx";
   import { twMerge } from "tailwind-merge";
   export function cn(...inputs: ClassValue[]) {
     return twMerge(clsx(inputs));
   }
   ```

3. **shadcn/ui 초기화** (Next.js, Vite):
   ```bash
   npx shadcn@latest init -y -d > .samvil/shadcn-init.log 2>&1
   npx shadcn@latest add button card input dialog -y >> .samvil/shadcn-init.log 2>&1
   ```

4. **추가 의존성** (blueprint.key_libraries 기반):
   ```bash
   npm install <library1> <library2> ...
   ```

5. **디자인 프리셋 적용**: `interview-summary.md`에서 디자인 프리셋 읽고, `references/design-presets.md`의 CSS 변수로 교체.

6. **package.json 업데이트**: name, description을 seed 기반으로 변경.

7. **app/page.tsx** (또는 `src/App.tsx`): 보일러플레이트를 간단한 Welcome 페이지로 교체.

8. **.gitignore에 `.samvil/` 추가** (없으면).

### Step 4: Build Verification — Circuit Breaker (INV-2)

```bash
cd ~/dev/<seed.name>
npm run build > .samvil/build.log 2>&1
echo "Exit code: $?"
```

**If build succeeds (exit 0):**

```
[SAMVIL] Stage 3/5: Scaffold ✓
  Project: ~/dev/<seed.name>/
  Stack: <framework>
  Dependencies: installed
  Build: passing
```

**If build fails — Circuit Breaker (MAX_RETRIES=2):**

1. Read error: `tail -30 .samvil/build.log`
2. Diagnose and fix
3. Log fix to `.samvil/fix-log.md`
4. Retry build
5. Still fails after 2 retries? → **STOP** and report to user

### Step 5: Update State and Chain (INV-4)

Update `project.state.json`: set `current_stage` to `"build"`.

```
[SAMVIL] Stage 3/5: Scaffold ✓
[SAMVIL] Stage 4/5: Building core experience...
```

Invoke the Skill tool with skill: `samvil-build`

## Rules

1. **No template folder dependency.** CLI tools generate everything.
2. **npm install MUST succeed.** Fix package.json and retry if it fails.
3. **npm run build MUST pass.** Non-negotiable.
4. **No business logic in scaffold.** Components dir is empty. Just the skeleton.
5. **All build output goes to .samvil/ files.** Never dump npm output into conversation.
6. **Respect seed.tech_stack.framework.** Don't override user's stack choice.

## Chain (Runtime-specific)

### Claude Code
Invoke the Skill tool with skill: `samvil-build`

### Codex CLI (future)
Read `skills/samvil-build/SKILL.md` and follow its instructions.
