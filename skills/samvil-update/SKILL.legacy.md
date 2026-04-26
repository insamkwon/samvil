---
name: samvil-update-legacy
description: "Legacy SAMVIL update (T3.3 backup)"
---

> **Legacy version (T3.3 backup).** Preserved for rollback. The new ultra-thin
> entry is `SKILL.md`. If migration breaks behavior, this file documents the
> exact behavior to restore.

# SAMVIL Update

SAMVIL 플러그인을 GitHub 최신 버전으로 업데이트.

## 사용법

```
/samvil:update
```

## Process

### Step 1: 현재 버전 확인 (v3.1.0 fallback 강화, v3-006)

```bash
CACHE_DIR=$(ls -td ~/.claude/plugins/cache/samvil/samvil/*/ 2>/dev/null | head -1)

# 1a. plugin.json 존재 확인
PLUGIN_JSON="${CACHE_DIR}.claude-plugin/plugin.json"
if [ -z "$CACHE_DIR" ]; then
  CURRENT="unknown (cache dir not found)"
elif [ ! -f "$PLUGIN_JSON" ]; then
  # fallback 1: 폴더명에서 버전 추정
  CURRENT="unknown (plugin.json missing — folder: $(basename "$CACHE_DIR"))"
else
  # 1b. JSON 파싱 시도. 실패 시 폴더명으로 fallback.
  CURRENT=$(python3 -c "import json; print(json.load(open('${PLUGIN_JSON}'))['version'])" 2>/dev/null)
  if [ -z "$CURRENT" ]; then
    CURRENT="unknown (plugin.json corrupt — folder: $(basename "$CACHE_DIR"))"
  fi
fi
echo "현재 버전: $CURRENT"
```

**v3-006 개선**: plugin.json이 없거나 깨졌을 때 과거처럼 "unknown" 단독으로 표시하는 대신, **이유 + 폴더명 fallback**을 함께 표시. `"v1.0.0 → v3.0.0"` 같은 stale 값이 우연히 찍히는 상황을 방지한다.

### Step 2: 최신 버전 확인

```bash
LATEST=$(gh api repos/insamkwon/samvil/contents/.claude-plugin/plugin.json --jq '.content' 2>/dev/null | base64 -d | python3 -c "import json,sys; print(json.load(sys.stdin)['version'])" 2>/dev/null || echo "unknown")
echo "최신 버전: $LATEST"
```

### Step 3: 비교 및 업데이트

동일하면:
```
[SAMVIL] ✓ 이미 최신 버전입니다 (v{CURRENT})
```

다르면:
```
[SAMVIL] 업데이트 중... v{CURRENT} → v{LATEST}
```

업데이트 실행:
```bash
# 캐시 디렉토리에 최신 코드 다운로드
cd /tmp
rm -rf samvil-update
gh repo clone insamkwon/samvil samvil-update 2>/dev/null

# 기존 캐시 백업 후 교체
CACHE_DIR=$(ls -td ~/.claude/plugins/cache/samvil/samvil/*/ 2>/dev/null | head -1)
rsync -a /tmp/samvil-update/ "$CACHE_DIR" --exclude='.git' --exclude='mcp/.venv' --exclude='node_modules'

# 정리
rm -rf /tmp/samvil-update
```

### Step 4: MCP 서버 업데이트 (있는 경우)

MCP .venv가 존재하면:
```bash
MCP_VENV="${CACHE_DIR}mcp/.venv"
if [ -d "$MCP_VENV" ]; then
  cd "${CACHE_DIR}mcp"
  source .venv/bin/activate
  uv pip install -e . --quiet
  echo "[SAMVIL] ✓ MCP 서버도 업데이트됨"
fi
```

### Step 5: 캐시 폴더 rename (v3.1.0, v3-005) + 구버전 정리

업데이트 성공 시, 현재 폴더명을 최신 버전으로 rename → 구버전 삭제 순서.

#### 5a. 폴더 rename (v3-005 신규)

`rsync`는 파일 내용만 덮어쓰고 폴더 이름은 유지한다. 그래서 v2.7.0 사용자가 v3.0.0으로 업데이트하면 `plugin.json:version`은 `3.0.0`이지만 폴더명은 `2.7.0/`으로 남아 "내 플러그인이 몇 버전?" 혼선이 생긴다. 이를 해결:

```bash
CACHE_ROOT=~/.claude/plugins/cache/samvil/samvil
CURRENT_FOLDER=$(basename "$CACHE_DIR")

# $LATEST가 명확하고 현재 폴더와 다르면 rename
if [ -n "$LATEST" ] && [ "$CURRENT_FOLDER" != "$LATEST" ]; then
  NEW_PATH="${CACHE_ROOT}/${LATEST}"
  if [ -d "$NEW_PATH" ] && [ "$NEW_PATH" != "$CACHE_DIR" ]; then
    # 대상 이미 존재 (거의 없지만 안전 가드)
    echo "[SAMVIL] ⚠️ 대상 폴더 이미 존재: $NEW_PATH — rename 건너뜀"
  else
    mv "$CACHE_DIR" "$NEW_PATH"
    CACHE_DIR="$NEW_PATH/"
    echo "[SAMVIL] 폴더 rename: ${CURRENT_FOLDER} → ${LATEST}"
  fi
fi
```

#### 5b. 구버전 디렉토리 정리

```bash
LATEST_DIR="${CACHE_ROOT}/${LATEST}"

# 안전 검증: 최신 버전 디렉토리가 존재하는지 + $LATEST가 비어있지 않은지 확인
if [ -z "$LATEST" ] || [ ! -d "$LATEST_DIR" ]; then
  echo "[SAMVIL] ⚠️ 최신 버전 디렉토리가 없어 캐시 정리를 건너뜁니다"
  echo "[SAMVIL] LATEST=${LATEST:-'(empty)'}"
else
  # 삭제 전 용량 측정
  BEFORE_SIZE=$(du -sh "$CACHE_ROOT" 2>/dev/null | cut -f1)

  # 구버전 삭제 (최신 버전 제외)
  for dir in "$CACHE_ROOT"/*/; do
    dirname=$(basename "$dir")
    if [ "$dirname" != "$LATEST" ]; then
      echo "[SAMVIL] 구버전 삭제: v${dirname}"
      rm -rf "$dir"
    fi
  done

  # 삭제 후 용량 측정
  AFTER_SIZE=$(du -sh "$CACHE_ROOT" 2>/dev/null | cut -f1)
  echo "[SAMVIL] 캐시 정리: ${BEFORE_SIZE} → ${AFTER_SIZE}"
fi
```

**주의**: `$LATEST`가 비어있으면 `$CACHE_ROOT/*/`에서 전체 삭제 위험이 있으므로, `-z "$LATEST"` 체크가 반드시 먼저 실행되어야 함. `rm -rf`는 이중 가드(empty check + explicit match)로 보호. rename도 `-n "$LATEST"` 가드 필수.

### Step 6: 완료

```
[SAMVIL] ✓ 업데이트 완료! v{CURRENT} → v{LATEST}
  캐시 정리: {BEFORE_SIZE} → {AFTER_SIZE}
  새 세션을 열면 업데이트된 SAMVIL이 로드됩니다.
```

### Step 6.5: v3.2 → v3.2.x upgrade note (end-user)

이 skill은 **end-user가 SAMVIL을 사용해 앱을 만드는 경우**를 위한 플러그인
업데이트 경로다. end-user는 repo를 clone하거나 git hooks를 설치할 필요가
**없다**. 필요한 것은 전부 다음과 같이 자동 처리된다:

- `.mcp.json`의 `${CLAUDE_PLUGIN_ROOT}` expansion으로 MCP 서버 자동 spawn.
- SessionStart hook이 `.samvil/claims.jsonl` 등 baseline 자동 생성.
- `save_event` 호출이 자동으로 claim ledger에 기록.
- Retro chain이 명령형으로 보장되어 Deploy 스킵 후에도 회고 실행.

기존 프로젝트에 v3.2 claim ledger를 소급 적용하려면 Step 7의
`--migrate v3.2` 경로를 사용한다. 새 프로젝트는 아무 액션 없이 바로
v3.2.x 기능을 사용 가능.

**SAMVIL 플러그인 자체를 수정**하려는 경우 (contributor)는 repo를 clone하고
`bash scripts/install-git-hooks.sh`를 1회 실행해야 pre-commit/pre-push
훅이 활성화된다. 자세한 내용은 README의 "SAMVIL 자체를 개선하려면
(Contributors)" 섹션 참조.

### Step 7: 프로젝트 Seed Migration 체크 (v3.0.0+)

업데이트 후, 현재 CWD에 `project.seed.json`이 있고 schema가 v3 미만이면 migration을 제안한다.

```bash
CWD_SEED="$(pwd)/project.seed.json"
if [ -f "$CWD_SEED" ]; then
  CURRENT_SCHEMA=$(python3 -c "import json; print(json.load(open('$CWD_SEED')).get('schema_version', 'unknown'))" 2>/dev/null)
  echo "[SAMVIL] 현재 seed 스키마: $CURRENT_SCHEMA"
fi
```

`CURRENT_SCHEMA`가 `3.*`로 시작하지 **않으면** 사용자에게 물어본다 (AskUserQuestion):

```
질문: "SAMVIL v3.0.0은 AC Tree 기반입니다. 현재 프로젝트의 seed (v{CURRENT_SCHEMA})를 v3로 마이그레이션할까요?

- Yes: 백업(project.v2.backup.json) 후 AC tree 구조로 변환
- No:  v2.x 유지 (v3의 tree build/QA 기능은 사용 불가)
- Later: 다음에 `/samvil:update --migrate`로 실행"

옵션: [Yes, No, Later]
```

**Yes 선택 시** — MCP tool로 migration 실행:
```
mcp__samvil_mcp__migrate_seed_file(seed_path="$CWD_SEED")
```
결과:
```
[SAMVIL] ✓ Migration 완료
  Backup:         project.v2.backup.json
  Schema:         v{CURRENT_SCHEMA} → v3.0
  AC tree leaves: <tree_progress.total_leaves>
```

**No/Later 선택 시** — 안내만:
```
[SAMVIL] Migration 건너뜀. 언제든 `/samvil:update --migrate` 또는
         직접 `mcp__samvil_mcp__migrate_seed_file(seed_path=...)` 실행 가능.
```

### `/samvil:update --migrate` — 명시적 migration 모드

`--migrate` 플래그가 주어지면 Step 1~6을 건너뛰고 Step 7만 실행한다 (이미 최신 버전인 프로젝트에서 seed만 변환하고 싶을 때).

```
/samvil:update --migrate
```

동작:
1. CWD에 `project.seed.json`이 없으면 에러 출력 후 종료.
2. 이미 `3.*` 스키마라면 `[SAMVIL] ✓ 이미 v3 스키마입니다` 출력 후 종료.
3. 그 외는 Step 7의 Yes 분기를 강제 실행 (backup + migrate).

### `/samvil:update --migrate v3.2` — v3.1 → v3.2 (Sprint 6, ⑫)

`--migrate v3.2`는 v3.1 프로젝트를 v3.2로 전환한다. 주요 변경:
legacy v3.1 tier 필드 → `samvil_tier` rename, 12개 AI-inferred AC
필드 backfill, `.samvil/claims.jsonl` 초기화, `model_profiles.yaml`
시드, `.samvil/rollback/v3_2_0/manifest.json` snapshot 생성. 상세는
`references/migration-v3.1-to-v3.2.md` 참조.

```
/samvil:update --migrate v3.2 [--dry-run]
```

동작:

1. CWD에 `project.seed.json`이 없으면 에러.
2. dry-run 먼저:
   ```
   mcp__samvil_mcp__migrate_plan(project_root=".")
   ```
   → `plan.seed_changes` + `files_created` + `backups` 출력. 사용자 승인 대기.
3. 승인 후:
   ```
   mcp__samvil_mcp__migrate_apply(project_root=".", dry_run=false)
   ```
   → 실패 시 `project.v3-1.backup.json`에서 수동 복구 안내.
4. 완료 출력:
   ```
   [SAMVIL] ✓ v3.1 → v3.2 Migration 완료
     Schema:    3.1 → 3.2
     Backup:    project.v3-1.backup.json
     Rollback:  .samvil/rollback/v3_2_0/manifest.json
     Council:   .samvil/council/*.md → retro observations (read-only)
   ```

**롤백**: `.samvil/rollback/v3_2_0/` 스냅샷을 보고 수동 복원. 아직
automated rollback CLI는 제공되지 않는다 (v3.3에서 제공 예정).

### 실패 시

```
[SAMVIL] ✗ 업데이트 실패
  원인: {에러 메시지}
  수동 업데이트: gh repo clone insamkwon/samvil /tmp/samvil && cp -r /tmp/samvil/* {CACHE_DIR}
```

## Output Format

Console output only (no files written):
- Success: `[SAMVIL] ✓ 업데이트 완료! v{CURRENT} → v{LATEST}` + cache cleanup summary
- Already latest: `[SAMVIL] ✓ 이미 최신 버전입니다 (v{CURRENT})`
- Failure: `[SAMVIL] ✗ 업데이트 실패` with error message and manual instructions

## Anti-Patterns

1. Do NOT overwrite the MCP `.venv` directory — only update source files
2. Do NOT modify user project files — this updates the plugin only
3. Do NOT proceed if `gh` CLI is not installed
