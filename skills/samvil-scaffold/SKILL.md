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
5. **Read `references/dependency-matrix.json`** → get pinned versions for the target stack
6. **Follow `references/boot-sequence.md`** for metrics start/end and checkpoint rules.

## Process

### Step 0: 기존 프로젝트 감지 및 캐시 확인

#### 기존 프로젝트 감지 (Incremental Scaffold)

```bash
ls ~/dev/<seed.name>/package.json 2>/dev/null
```

**package.json이 존재하면:**

```
[SAMVIL] 기존 프로젝트 감지. scaffold 생략.
  Project: ~/dev/<seed.name>/
```

기존 프로젝트 감지 시 전체 scaffold를 스킵하고 대신:
1. `blueprint.key_libraries`에서 누락된 dependency만 추가 설치
   ```bash
   cd ~/dev/<seed.name>
   # package.json에 없는 패키지만 골라서 설치
   node -e "
   const pkg = require('./package.json');
   const allDeps = { ...pkg.dependencies, ...pkg.devDependencies };
   const needed = process.argv.slice(2).filter(d => !allDeps[d.split('@')[0]]);
   if (needed.length) console.log(needed.join(' '));
   " <missing_packages>
   ```
2. `.samvil/` 디렉토리가 없으면 생성
3. Step 4 (Build Verification)로 바로 이동

**package.json이 없으면:** 아래 Step 0.5 ~ Step 5까지 전체 scaffold 실행.

#### 빌드 캐시 시스템 (.samvil/cache/)

캐시는 동일한 feature의 반복 빌드를 방지:

```bash
mkdir -p ~/dev/<seed.name>/.samvil/cache
```

**캐시 키 생성:**
```bash
# seed.features 배열을 해시하여 캐시 키 생성
node -e "
const crypto = require('crypto');
const seed = require('./project.seed.json');
const hash = crypto.createHash('sha256')
  .update(JSON.stringify(seed.features || []))
  .digest('hex').slice(0, 12);
console.log(hash);
" > ~/dev/<seed.name>/.samvil/cache/seed-hash.txt
```

**캐시 적중 판정:**
1. `.samvil/cache/seed-hash.txt` 읽기
2. 현재 seed.features 해시와 비교
3. 일치 → 변경 없는 feature의 scaffold 스킵
4. 불일치 → 전체 캐시 무효화 후 전체 scaffold 실행

**캐시 무효화 조건:**
- seed 버전(`seed.version`)이 변경된 경우 → `.samvil/cache/` 전체 삭제 후 재생성
- features 배열이 변경된 경우 → 변경된 feature만 재빌드

**캐시 파일 포맷** (`.samvil/cache/<feature-name>.json`):
```json
{
  "feature_name": "<feature.name>",
  "seed_hash": "abc123def456",
  "scaffolded_at": "2025-01-01T00:00:00Z",
  "dependencies_installed": ["pkg1@1.0.0", "pkg2@2.0.0"],
  "files_created": ["components/Feature.tsx", "lib/feature.ts"]
}
```

### Step 0.5: Load Pinned Versions (Determinism)

Read `references/dependency-matrix.json` to get exact version pins. This ensures **same input → same output, every time**.

Never use `@latest` or unversioned installs. Always use versions from the matrix.

### Step 1: Determine Stack

Read `seed.tech_stack.framework` to determine which CLI to use:

| `tech_stack.framework` | Matrix Key | CLI Command (pinned) | 비고 |
|---|---|---|---|
| `nextjs` | `nextjs14` | `npx create-next-app@14.2.35` | SSR, API routes, SEO |
| `vite-react` | `vite-react` | `npm create vite@5.4.21 -- --template react-ts` | 가벼움, SPA |
| `astro` | `astro` | `npm create astro@6.1.5 -- --template minimal` | 정적, 빠른 로딩 |
| `python-script` | `python-script` | `python3 -m venv .venv` | 자동화 스크립트 |
| `node-script` | `node-script` | `npm init -y && npx tsc --init` | Node.js 자동화 |
| `cc-skill` | `cc-skill` | (파일 직접 생성) | CC 스킬 전용 |

기본값: `nextjs` (seed에 명시 없으면)

#### Stack Comparison (인터뷰에서 프레임워크 질문 시 참고)

**지원 스택 (Stable)**

| 항목 | Next.js 14 | Vite + React | Astro | Python Script | Node Script | CC Skill |
|---|---|---|---|---|---|---|
| **장점** | SSR/SSG, API routes, SEO | 빠른 개발, 가벼운 번들 | 콘텐츠 중심, 빠른 로딩 | API/데이터 처리 강점 | JS 생태계 | AI 판단, CC 통합 |
| **단점** | 빌드 느림, 복잡 | SSR 미지원 | 동적 인터랙션 제한 | 웹 UI 없음 | 웹 UI 없음 | CC 의존 |
| **배포** | Vercel, Railway | Vercel, Netlify | Vercel, Netlify | cron, serverless | cron, serverless | CronCreate |

**계획 중인 스택 (Planned — 아직 scaffold 미구현)**

| 항목 | Nuxt 3 | SvelteKit |
|---|---|---|
| **장점** | 파일 기반 라우팅, auto-imports, Nitro 서버 | 작은 번들, 컴파일 타임 최적화, 간결한 문법 |
| **단점** | Vue 에코시스템 규모, Nuxt 모듈 의존 | 에코시스템 작음, 레퍼런스 부족 |
| **UI** | Nuxt UI | shadcn-svelte |
| **상태관리** | Pinia | Svelte stores (내장) |
| **scaffold CLI** | `npx nuxi@latest init` | `npx sv create` |
| **상태** | **🚧 Planned** | **🚧 Planned** |

> **Nuxt/SvelteKit 지원은 계획 중입니다.** 선택 시: "Nuxt support coming soon" 또는 "SvelteKit support coming soon" 메시지 출력 후 `nextjs`로 폴백 안내.

### Step 2: Generate Project

#### Next.js

```bash
cd ~/dev
npx create-next-app@14.2.35 <seed.name> --typescript --tailwind --app --src-dir=false --import-alias="@/*" --eslint --use-npm <<< $'No\n'
cd ~/dev/<seed.name>
# create-next-app@14.2.35이 npm install까지 완료함. 추가 패키지만 별도 설치.
```

**Version pin verification (idempotency check):**
```bash
# Verify installed next version matches matrix
node -e "console.log(require('./package.json').dependencies.next)"
# Must show 14.2.35. If not, run: npm install next@14.2.35 react@18.3.1 react-dom@18.3.1
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

**4) 의존성 설치 (pinned versions from matrix):**
```bash
npm install tailwindcss-animate@1.0.7 --save-dev
```

**이 4단계를 shadcn init 전에 실행한다.** shadcn init이 globals.css를 덮어쓰면 다시 위 CSS로 교체.

#### Vite + React

```bash
cd ~/dev
npm create vite@5.4.21 <seed.name> -- --template react-ts
cd ~/dev/<seed.name>
npm install
npm install -D tailwindcss@4.1.4 @tailwindcss/vite@4.2.2
```

**Vite + Tailwind v4 설정**:
- `vite.config.ts`에 `@tailwindcss/vite` 플러그인 추가
- `src/index.css`에 `@import "tailwindcss"` 추가
- `tsconfig.json`에 `"paths": { "@/*": ["./src/*"] }` 추가
- `vite.config.ts`에 `resolve.alias` 추가: `"@": path.resolve(__dirname, "./src")`

shadcn/ui는 Vite에서 v4 네이티브 지원:
```bash
npx shadcn@2.6.3 init -y -d
npx shadcn@2.6.3 add button card input dialog label select textarea -y
```

#### Astro

```bash
cd ~/dev
npm create astro@6.1.5 <seed.name> -- --template minimal --install --no-git --typescript strict
cd ~/dev/<seed.name>
npx astro add tailwind -y
npx astro add react -y
```

#### Python Script (automation)

No CLI scaffolding tool. Create project structure manually.

```bash
cd ~/dev
mkdir -p <seed.name>/src <seed.name>/fixtures/input <seed.name>/fixtures/expected <seed.name>/tests <seed.name>/.samvil
cd ~/dev/<seed.name>
python3 -m venv .venv
source .venv/bin/activate
```

Create files:

**`src/main.py`** — Entry point with `--dry-run` support:
```python
#!/usr/bin/env python3
"""<seed.description>"""

import argparse
import json
import sys
from pathlib import Path

from processor import Processor
from config import load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="<seed.description>")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run with fixtures/ data instead of real API calls")
    parser.add_argument("--config", default=".env",
                        help="Path to config file (default: .env)")
    parser.add_argument("--output", default=None,
                        help="Output file path (default: stdout)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)

    if args.dry_run:
        config["dry_run"] = True
        config["input_dir"] = "fixtures/input"
        config["expected_dir"] = "fixtures/expected"

    processor = Processor(config)
    result = processor.run()

    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**`src/processor.py`** — Core logic skeleton:
```python
"""Core processing logic."""


class Processor:
    def __init__(self, config: dict):
        self.config = config
        self.dry_run = config.get("dry_run", False)

    def run(self) -> dict:
        if self.dry_run:
            return self._run_dry()
        return self._run_live()

    def _run_dry(self) -> dict:
        # TODO: Implement dry-run logic using fixtures/input/
        return {"status": "ok", "mode": "dry-run"}

    def _run_live(self) -> dict:
        # TODO: Implement real processing logic
        return {"status": "ok", "mode": "live"}
```

**`src/config.py`** — Environment-based configuration:
```python
"""Configuration loader from environment / .env file."""

import os
from pathlib import Path


def load_config(config_path: str = ".env") -> dict:
    """Load config from .env file or environment variables."""
    config = {}
    env_path = Path(config_path)
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                config[key.strip()] = value.strip()
    # Environment variables take precedence
    for key in config:
        if key in os.environ:
            config[key] = os.environ[key]
    return config
```

**`requirements.txt`** — Pinned versions from dependency-matrix.json:
```
# Core
requests==2.32.3
python-dotenv==1.1.0
# Add project-specific dependencies from blueprint.dependencies
```

**`tests/test_dry_run.py`** — Dry-run verification:
```python
"""Test that --dry-run works with fixtures."""

import subprocess
import json
import sys


def test_dry_run_exit_code():
    """--dry-run should exit with code 0."""
    result = subprocess.run(
        [sys.executable, "src/main.py", "--dry-run"],
        capture_output=True, text=True
    )
    assert result.returncode == 0, f"Exit code {result.returncode}: {result.stderr}"


def test_dry_run_valid_json():
    """--dry-run output should be valid JSON."""
    result = subprocess.run(
        [sys.executable, "src/main.py", "--dry-run"],
        capture_output=True, text=True
    )
    data = json.loads(result.stdout)
    assert isinstance(data, dict)


def test_dry_run_no_api_calls():
    """--dry-run should not make real API calls (check logs)."""
    result = subprocess.run(
        [sys.executable, "src/main.py", "--dry-run"],
        capture_output=True, text=True
    )
    # stderr should not contain real API URLs
    assert "api.openweathermap.org" not in result.stderr
    assert "api.slack.com" not in result.stderr
```

**`.env.example`**:
```
# API Keys
API_KEY=your-api-key-here
API_BASE_URL=https://api.example.com

# Output
OUTPUT_DIR=./output
```

#### Node Script (automation)

```bash
cd ~/dev
mkdir -p <seed.name>/src <seed.name>/fixtures/input <seed.name>/fixtures/expected <seed.name>/tests <seed.name>/.samvil
cd ~/dev/<seed.name>
npm init -y
npm install -D typescript @types/node tsx
npx tsc --init
```

**`tsconfig.json`** updates:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "commonjs",
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true,
    "resolveJsonModule": true
  }
}
```

**`src/main.ts`** — Entry point with `--dry-run`:
```typescript
import { config } from "./config";
import { Processor } from "./processor";

interface Args {
  dryRun: boolean;
  config: string;
  output?: string;
}

function parseArgs(): Args {
  const args = process.argv.slice(2);
  return {
    dryRun: args.includes("--dry-run"),
    config: args.includes("--config")
      ? args[args.indexOf("--config") + 1]
      : ".env",
    output: args.includes("--output")
      ? args[args.indexOf("--output") + 1]
      : undefined,
  };
}

async function main(): Promise<number> {
  const args = parseArgs();
  const cfg = config.load(args.config);

  if (args.dryRun) {
    cfg.dryRun = true;
  }

  const processor = new Processor(cfg);
  const result = await processor.run();

  const output = JSON.stringify(result, null, 2);
  if (args.output) {
    require("fs").writeFileSync(args.output, output);
  } else {
    console.log(output);
  }

  return 0;
}

main().then(process.exit).catch((e) => {
  console.error("Fatal error:", e.message);
  process.exit(1);
});
```

**`package.json`** scripts:
```json
{
  "scripts": {
    "start": "tsx src/main.ts",
    "dry-run": "tsx src/main.ts --dry-run",
    "build": "tsc",
    "test": "tsx tests/test_dry_run.ts"
  }
}
```

#### CC Skill (automation)

No project scaffolding needed. Create only a `SKILL.md` file:

```bash
cd ~/dev
mkdir -p <seed.name> <seed.name>/.samvil
```

**`SKILL.md`** — Generated based on seed spec:
```markdown
---
name: <seed.name>
description: "<seed.description>"
---

# <seed.name>

## What it does
<seed.description>

## When to use
<seed.core_flow.trigger>

## Usage
```
/<seed.name> [--dry-run]
```

## Process

### Step 1: Read Config
Read environment variables from `.env`.

### Step 2: <Fetch / Read / Receive>
<seed.core_flow.input>

### Step 3: Process
<seed.features P1 items>

### Step 4: Output
<seed.core_flow.output>

## Output Format
<JSON or text format>

## Error Handling
<seed.constraints error handling>

## Requirements
- Environment variables: <list from .env.example>
```

#### Nuxt 3 (🚧 Planned — 아직 구현되지 않음)

> **Nuxt support coming soon.** 아래는 설계만 포함하며, 실제 scaffold 로직은 후속 버전에서 구현 예정.

**설계:**
```bash
cd ~/dev
npx nuxi@latest init <seed.name>
cd ~/dev/<seed.name>
# 예정된 설정:
# - @nuxt/ui 설치 및 설정
# - Tailwind CSS 통합 (Nuxt UI에 포함)
# - Pinia 상태관리 설정
# - Supabase 모듈 연동 (@nuxtjs/supabase)
# - TypeScript strict 모드
```

**seed.tech_stack.framework이 `nuxt`인 경우:**
```
[SAMVIL] Nuxt 3 scaffold is planned but not yet implemented.
  Falling back to Next.js 14 (default stack).
  Nuxt support will be available in a future version.
```

#### SvelteKit (🚧 Planned — 아직 구현되지 않음)

> **SvelteKit support coming soon.** 아래는 설계만 포함하며, 실제 scaffold 로직은 후속 버전에서 구현 예정.

**설계:**
```bash
cd ~/dev
npx sv create <seed.name>
cd ~/dev/<seed.name>
# 예정된 설정:
# - shadcn-svelte 설치 및 컴포넌트 추가
# - Tailwind CSS 설정
# - Svelte stores 기반 상태관리
# - Supabase 클라이언트 설정 (@supabase/ssr)
# - TypeScript 설정
```

**seed.tech_stack.framework이 `sveltekit`인 경우:**
```
[SAMVIL] SvelteKit scaffold is planned but not yet implemented.
  Falling back to Next.js 14 (default stack).
  SvelteKit support will be available in a future version.
```

### Step 3: Common Setup

#### web-app 공통 설정

1. **디렉토리 생성**:
   ```bash
   mkdir -p ~/dev/<seed.name>/components ~/dev/<seed.name>/lib ~/dev/<seed.name>/.samvil
   ```
   (Vite는 `src/components`, `src/lib`)

2. **cn() utility** (shadcn 없으면 직접 생성, pinned versions):
   ```bash
   npm install clsx@2.1.1 tailwind-merge@3.5.0
   ```
   `lib/utils.ts` (또는 `src/lib/utils.ts`):
   ```typescript
   import { type ClassValue, clsx } from "clsx";
   import { twMerge } from "tailwind-merge";
   export function cn(...inputs: ClassValue[]) {
     return twMerge(clsx(inputs));
   }
   ```

3. **shadcn/ui 초기화** (Next.js, Vite) — **반드시 매트릭스 버전 사용**:
   ```bash
   npx shadcn@2.6.3 init -y -d > .samvil/shadcn-init.log 2>&1
   npx shadcn@2.6.3 add button card input dialog label select textarea -y >> .samvil/shadcn-init.log 2>&1
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

#### web-app

```bash
cd ~/dev/<seed.name>
npm run build > .samvil/build.log 2>&1
echo "Exit code: $?"
```

**Pre-build Version Check (idempotency guard):**
```bash
# Verify key dependencies match the matrix before building
node -e "
const pkg = require('./package.json');
const checks = {
  'next': '14.2.35',
  'react': '18.3.1',
  'react-dom': '18.3.1',
  'tailwindcss': '3.4.19',
  'tailwindcss-animate': '1.0.7',
  'clsx': '2.1.1',
  'tailwind-merge': '3.5.0'
};
let ok = true;
for (const [dep, expected] of Object.entries(checks)) {
  const actual = pkg.dependencies[dep] || pkg.devDependencies[dep] || 'MISSING';
  // Strip leading ^ or ~
  const clean = actual.replace(/^[\^~]/, '');
  if (clean !== expected) {
    console.error('MISMATCH: ' + dep + ' expected=' + expected + ' actual=' + actual);
    ok = false;
  }
}
if (ok) console.log('All versions match dependency-matrix.json');
process.exit(ok ? 0 : 1);
"
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

#### automation

**Python:**
```bash
cd ~/dev/<seed.name>
source .venv/bin/activate
python -m py_compile src/main.py > .samvil/build.log 2>&1
python -m py_compile src/processor.py >> .samvil/build.log 2>&1
python -m py_compile src/config.py >> .samvil/build.log 2>&1
echo "Exit code: $?"
pip install -r requirements.txt > .samvil/deps-install.log 2>&1
python -c "import src.main" >> .samvil/build.log 2>&1
echo "Import check exit code: $?"
```

**Node:**
```bash
cd ~/dev/<seed.name>
npx tsc --noEmit > .samvil/build.log 2>&1
echo "Exit code: $?"
npm ls >> .samvil/build.log 2>&1
```

**CC skill:**
```bash
# No build step needed. Just verify SKILL.md exists.
ls ~/dev/<seed.name>/SKILL.md
```

**If automation build succeeds:**
```
[SAMVIL] Stage 3/5: Scaffold ✓
  Project: ~/dev/<seed.name>/
  Type: automation
  Stack: <python-script|node-script|cc-skill>
  Build: passing
```

**If automation build fails — Circuit Breaker (MAX_RETRIES=2):**
Same as web-app: read error, diagnose, fix, retry, MAX_RETRIES=2.

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

## Output Format

### web-app

Files created in `~/dev/<seed.name>/`:
- Scaffolded project via CLI (Next.js / Vite / Astro — based on `seed.tech_stack.framework`)
- `lib/utils.ts` (or `src/lib/utils.ts`): `cn()` utility using clsx + tailwind-merge
- `components/ui/`: shadcn/ui components (button, card, input, dialog, label, select, textarea)
- `app/page.tsx` (or `src/App.tsx`): minimal Welcome page — no business logic
- `.env.example`: environment variable templates
- `.samvil/`: build logs, shadcn init log
- `app/globals.css`: HSL CSS variables (NOT oklch — shadcn overwrite prevention)
- `tailwind.config.ts` (Next.js only): HSL `hsl(var(--...))` color tokens

### automation

**Python:**
Files created in `~/dev/<seed.name>/`:
- `src/main.py`: Entry point with argparse + `--dry-run` flag
- `src/processor.py`: Core logic skeleton with `_run_dry()` and `_run_live()`
- `src/config.py`: Env-based configuration loader
- `fixtures/input/`: Directory for test input fixtures
- `fixtures/expected/`: Directory for expected output fixtures
- `tests/test_dry_run.py`: Dry-run verification tests
- `.env.example`: Environment variable templates
- `requirements.txt`: Pinned dependencies from dependency-matrix.json
- `.samvil/`: Build logs

**Node:**
Files created in `~/dev/<seed.name>/`:
- `src/main.ts`: Entry point with `--dry-run` flag
- `src/processor.ts`: Core logic skeleton
- `src/config.ts`: Env-based configuration
- `src/fixtures.ts`: Fixture loading + comparison utilities
- `fixtures/input/`, `fixtures/expected/`: Test fixtures
- `tests/test_dry_run.ts`: Dry-run verification
- `.env.example`: Environment variable templates
- `package.json`, `tsconfig.json`: Project config with pinned deps
- `.samvil/`: Build logs

**CC skill:**
Files created in `~/dev/<seed.name>/`:
- `SKILL.md`: Skill definition with process, output format, error handling
- `.env.example`: Environment variable templates
- `.samvil/`: State directory

Verification output:
- `npm run build` exit code 0
- `[SAMVIL] Stage 3/5: Scaffold ✓` with project path, stack, dependency, build status

## Anti-Patterns

1. Do NOT include any business logic in scaffold — components dir has only shadcn/ui defaults
2. Do NOT use `@latest` for any package — use pinned versions from `references/dependency-matrix.json`
3. Do NOT skip the Tailwind verification step after shadcn init

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
