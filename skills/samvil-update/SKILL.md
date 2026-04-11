---
name: samvil-update
description: "SAMVIL을 최신 버전으로 업데이트합니다."
---

# SAMVIL Update

SAMVIL 플러그인을 GitHub 최신 버전으로 업데이트.

## 사용법

```
/samvil:update
```

## Process

### Step 1: 현재 버전 확인

```bash
CACHE_DIR=$(ls -td ~/.claude/plugins/cache/samvil/samvil/*/ 2>/dev/null | head -1)
CURRENT=$(python3 -c "import json; print(json.load(open('${CACHE_DIR}.claude-plugin/plugin.json'))['version'])" 2>/dev/null || echo "unknown")
echo "현재 버전: $CURRENT"
```

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

### Step 5: 완료

```
[SAMVIL] ✓ 업데이트 완료! v{CURRENT} → v{LATEST}
  새 세션을 열면 업데이트된 SAMVIL이 로드됩니다.
```

### 실패 시

```
[SAMVIL] ✗ 업데이트 실패
  원인: {에러 메시지}
  수동 업데이트: gh repo clone insamkwon/samvil /tmp/samvil && cp -r /tmp/samvil/* {CACHE_DIR}
```

## Output Format

Console output only (no files written):
- Success: `[SAMVIL] ✓ 업데이트 완료! v{CURRENT} → v{LATEST}`
- Already latest: `[SAMVIL] ✓ 이미 최신 버전입니다 (v{CURRENT})`
- Failure: `[SAMVIL] ✗ 업데이트 실패` with error message and manual instructions

## Anti-Patterns

1. Do NOT overwrite the MCP `.venv` directory — only update source files
2. Do NOT modify user project files — this updates the plugin only
3. Do NOT proceed if `gh` CLI is not installed
