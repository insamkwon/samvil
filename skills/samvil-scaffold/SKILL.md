---
name: samvil-scaffold
description: "CLI-based project scaffold. Supports Next.js, Vite+React, Astro. No template folder dependency."
---

# SAMVIL Scaffold — CLI-Based Project Generation

You are adopting the role of **Scaffolder**. Create a project directory with a verified, buildable skeleton using CLI tools (no template folder).

## Boot Sequence (INV-1)

0. **TaskUpdate**: "Scaffold" task를 `in_progress`로 설정
1. Read `project.seed.json` from the project directory
2. Read `project.state.json` → confirm `current_stage` is `"scaffold"`, get `session_id`
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

**Next.js 14 + shadcn 호환 설정** — shadcn@latest가 Tailwind v4 문법을 생성하므로 반드시 아래로 덮어써야 함:

**1) `app/layout.tsx`** — Geist 로컬 폰트 제거, Inter 사용:
```tsx
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: "<seed.name title-cased>",
  description: "<seed.description>",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={cn("font-sans antialiased", inter.variable)}>{children}</body>
    </html>
  );
}
```

**2) `tailwind.config.ts`** — 전체 교체:
```ts
import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
        secondary: { DEFAULT: "hsl(var(--secondary))", foreground: "hsl(var(--secondary-foreground))" },
        destructive: { DEFAULT: "hsl(var(--destructive))", foreground: "hsl(var(--destructive-foreground))" },
        muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
        accent: { DEFAULT: "hsl(var(--accent))", foreground: "hsl(var(--accent-foreground))" },
        card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },
        popover: { DEFAULT: "hsl(var(--popover))", foreground: "hsl(var(--popover-foreground))" },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
export default config;
```

**3) `app/globals.css`** — 전체 교체 (shadcn이 생성한 oklch 제거):
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 0 0% 3.9%;
    --card: 0 0% 100%;
    --card-foreground: 0 0% 3.9%;
    --popover: 0 0% 100%;
    --popover-foreground: 0 0% 3.9%;
    --primary: 0 0% 9%;
    --primary-foreground: 0 0% 98%;
    --secondary: 0 0% 96.1%;
    --secondary-foreground: 0 0% 9%;
    --muted: 0 0% 96.1%;
    --muted-foreground: 0 0% 45.1%;
    --accent: 0 0% 96.1%;
    --accent-foreground: 0 0% 9%;
    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 0 0% 98%;
    --border: 0 0% 89.8%;
    --input: 0 0% 89.8%;
    --ring: 0 0% 3.9%;
    --radius: 0.5rem;
  }
  .dark {
    --background: 0 0% 3.9%;
    --foreground: 0 0% 98%;
    --card: 0 0% 3.9%;
    --card-foreground: 0 0% 98%;
    --popover: 0 0% 3.9%;
    --popover-foreground: 0 0% 98%;
    --primary: 0 0% 98%;
    --primary-foreground: 0 0% 9%;
    --secondary: 0 0% 14.9%;
    --secondary-foreground: 0 0% 98%;
    --muted: 0 0% 14.9%;
    --muted-foreground: 0 0% 63.9%;
    --accent: 0 0% 14.9%;
    --accent-foreground: 0 0% 98%;
    --destructive: 0 62.8% 30.6%;
    --destructive-foreground: 0 0% 98%;
    --border: 0 0% 14.9%;
    --input: 0 0% 14.9%;
    --ring: 0 0% 83.1%;
  }
  * { @apply border-border; }
  body { @apply bg-background text-foreground; }
}
```

**4) 의존성 설치:**
```bash
npm install tailwindcss-animate --save-dev
```

**이 4단계를 shadcn init 전에 실행한다.** shadcn init이 globals.css를 덮어쓰면 다시 위 CSS로 교체.

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
   **⚠️ Next.js 14 전용**: shadcn init이 globals.css와 tailwind.config를 Tailwind v4 문법(oklch)으로 덮어쓴다. **반드시 위 Step 2의 HSL 버전으로 다시 교체해야 한다.** 교체 안 하면 색상이 전부 빠져서 밋밋한 흰/검 디자인이 됨.
   ```

4. **Tailwind 설정 검증** (shadcn init 후 필수):

   shadcn init이 globals.css와 tailwind.config를 Tailwind v4 문법으로 덮어쓸 수 있다. 반드시 확인:

   **Next.js 14:**
   ```bash
   # globals.css 첫 줄이 @tailwind base여야 함 (oklch/@import tailwindcss가 아님)
   head -1 app/globals.css
   # tailwind.config.ts에 hsl(var(--...)) 패턴이 있어야 함
   grep -c "hsl(var(--" tailwind.config.ts
   # postcss.config.mjs에 tailwindcss 플러그인이 있어야 함
   grep -c "tailwindcss" postcss.config.mjs
   ```

   **Vite:**
   ```bash
   # index.css 첫 줄이 @import "tailwindcss"여야 함
   head -1 src/index.css
   # vite.config.ts에 @tailwindcss/vite 플러그인이 있어야 함
   grep -c "@tailwindcss/vite" vite.config.ts
   ```

   검증 실패 시: Step 2의 올바른 내용으로 덮어쓰고 다시 검증. 이 단계를 건너뛰면 빌드 재시도 루프의 원인이 됨.

5. **추가 의존성** (blueprint.key_libraries 기반):
   ```bash
   npm install <library1> <library2> ...
   ```

6. **디자인 프리셋 적용**: `interview-summary.md`에서 디자인 프리셋 읽고, `references/design-presets.md`의 CSS 변수로 교체.

7. **package.json 업데이트**: name, description을 seed 기반으로 변경.

8. **app/page.tsx** (또는 `src/App.tsx`): 보일러플레이트를 간단한 Welcome 페이지로 교체.

9. **.gitignore에 `.samvil/` 추가** (없으면).

10. **Playwright 설치** (QA Smoke Run용):
    ```bash
    npm install -D @playwright/test
    npx playwright install chromium
    ```
    Playwright는 QA Pass 1b에서 dev server의 콘솔 에러와 빈 화면을 검출하는 데 사용.

11. **Supabase 설정** (interview에서 Supabase 선택 시만):
    ```bash
    npm install @supabase/supabase-js @supabase/ssr
    ```
    `lib/supabase/client.ts`:
    ```typescript
    import { createBrowserClient } from '@supabase/ssr'

    export function createClient() {
      return createBrowserClient(
        process.env.NEXT_PUBLIC_SUPABASE_URL!,
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
      )
    }
    ```
    `lib/supabase/server.ts` (Next.js only):
    ```typescript
    import { createServerClient } from '@supabase/ssr'
    import { cookies } from 'next/headers'

    export async function createClient() {
      const cookieStore = await cookies()
      return createServerClient(
        process.env.NEXT_PUBLIC_SUPABASE_URL!,
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
        { cookies: { getAll() { return cookieStore.getAll() }, setAll(cookiesToSet) { cookiesToSet.forEach(({ name, value, options }) => cookieStore.set(name, value, options)) } } }
      )
    }
    ```

12. **.env.example 생성** (필요한 환경변수 명시):
    ```
    # Supabase (if selected)
    NEXT_PUBLIC_SUPABASE_URL=your-project-url
    NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key

    # External APIs (if applicable)
    NEXT_PUBLIC_API_KEY=your-api-key
    ```
    Copy `.env.example` to `.env.local` as template.

13. **next.config.mjs에 standalone output 추가** (배포 준비):
    ```javascript
    /** @type {import('next').NextConfig} */
    const nextConfig = {
      output: 'standalone',
    }
    export default nextConfig
    ```

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

**MCP (best-effort):** Save scaffold completion:
```
mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="scaffold_complete", stage="build", data='{"framework":"<framework>","shadcn_components":["button","card","input","dialog"]}')
```

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

**TaskUpdate**: "Scaffold" task를 `completed`로 설정
## Chain (Runtime-specific)

### Claude Code
Invoke the Skill tool with skill: `samvil-build`

### Codex CLI (future)
Read `skills/samvil-build/SKILL.md` and follow its instructions.
