---
name: samvil-scaffold
description: "Generate project skeleton from seed. Copy Next.js 14 template, install deps, verify build passes."
---

# SAMVIL Scaffold — Project Skeleton Generation

You are adopting the role of **Scaffolder**. Create a project directory with a verified, buildable skeleton.

## Boot Sequence (INV-1)

1. Read `project.seed.json` from the project directory
2. Read `project.state.json` → confirm `current_stage` is `"scaffold"`

## Process

### Step 1: Locate and Copy the Template

The template is in this plugin's cache. Try these paths in order:

```bash
# Try to find the template
TEMPLATE=""
for dir in \
  ~/.claude/plugins/cache/samvil/samvil/*/templates/nextjs-14 \
  ~/dev/samvil/templates/nextjs-14; do
  if [ -d "$dir" ]; then
    TEMPLATE="$dir"
    break
  fi
done
echo "Template: $TEMPLATE"
```

**If template found:** Copy it to the project directory:

```bash
cp -r $TEMPLATE/* ~/dev/<seed.name>/
mkdir -p ~/dev/<seed.name>/components ~/dev/<seed.name>/lib ~/dev/<seed.name>/.samvil
```

**If template NOT found (fallback):** Generate the project using `create-next-app`:

```bash
cd ~/dev
npx create-next-app@14 <seed.name> --typescript --tailwind --app --src-dir=false --import-alias="@/*" --eslint --use-npm <<< $'No\n'
mkdir -p ~/dev/<seed.name>/components ~/dev/<seed.name>/lib ~/dev/<seed.name>/.samvil
```

Then simplify `app/layout.tsx` (replace local fonts with Google Inter) and `app/page.tsx` (replace boilerplate with simple welcome page) as described in Step 3 below.

### Step 3: Customize

1. **Update `package.json`**:
   - Set `"name"` to `seed.name`
   - Set `"description"` to `seed.description`
   - Add dependencies based on `seed.tech_stack`:
     - If `state` = `"zustand"`: add `"zustand": "^4.5.0"` to dependencies
     - If any feature involves drag-and-drop: add `"@hello-pangea/dnd": "^16.6.0"`

2. **Update `app/layout.tsx`**:
   - Set `metadata.title` to seed.name (title-cased, spaces for hyphens)
   - Set `metadata.description` to seed.description

3. **Update `app/page.tsx`**:
   - Simple welcome page with the app name:
   ```tsx
   export default function Home() {
     return (
       <main className="flex min-h-screen items-center justify-center">
         <h1 className="text-4xl font-bold">Welcome to <AppName></h1>
       </main>
     );
   }
   ```

4. **Create `.gitignore` in project** (if not already there):
   ```
   node_modules/
   .next/
   .samvil/
   ```

### Step 4: Install Dependencies (INV-2)

```bash
cd ~/dev/<seed.name>
npm install > .samvil/install.log 2>&1
echo "Exit code: $?"
```

If install fails: read `tail -20 .samvil/install.log`, fix package.json, retry.

### Step 5: Build Verification — Circuit Breaker (INV-2)

```bash
cd ~/dev/<seed.name>
npm run build > .samvil/build.log 2>&1
echo "Exit code: $?"
```

**If build succeeds (exit 0):**

```
[SAMVIL] Stage 3/5: Scaffold ✓
  Project: ~/dev/<seed.name>/
  Dependencies: installed
  Build: passing
```

**If build fails — Circuit Breaker (MAX_RETRIES=2):**

1. Read error: `tail -30 .samvil/build.log`
2. Diagnose: missing dependency? Config error? TypeScript error?
3. Fix the specific issue
4. Retry: `npm run build > .samvil/build.log 2>&1`
5. Still fails after 2 retries? → **STOP** and report to user:
   ```
   [SAMVIL] ✗ Scaffold build failed after 2 retries
   Error: <last error message>
   Project is at ~/dev/<seed.name>/ — please check manually.
   ```

### Step 6: Update State and Chain (INV-4)

Update `project.state.json`: set `current_stage` to `"build"`.

```
[SAMVIL] Stage 3/5: Scaffold ✓
[SAMVIL] Stage 4/5: Building core experience...
```

Invoke the Skill tool with skill: `samvil:build`

## Rules

1. **Template files are the source of truth.** Don't generate config files from memory — copy from template.
2. **npm install MUST succeed.** Fix package.json and retry if it fails.
3. **npm run build MUST pass.** Non-negotiable.
4. **No business logic in scaffold.** Components dir is empty. Lib dir is empty. Just the skeleton.
5. **All build output goes to .samvil/ files.** Never dump npm output into conversation.
