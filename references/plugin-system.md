# SAMVIL Plugin System (INV-8)

> **Status: Planned.** Hook 포인트는 정의되었으나, 아직 scaffold/build/qa 스킬에 연결되지 않음.
> 연결 시 각 스킬의 SKILL.md에 `run_plugin_hook` 호출 지점을 추가해야 함.

## 개요

사용자가 파이프라인의 특정 스테이지에 커스텀 로직을 끼워 넣을 수 있는 플러그인 시스템.

**핵심 원칙: Plugin is best-effort.** 플러그인 실패는 하네스 실행에 영향 없음. 경고만 출력하고 계속 진행.

## Hook Points

파이프라인의 6개 스테이지 전후에 hook 포인트가 존재한다:

```
before_scaffold → [Scaffold] → after_scaffold
before_build    → [Build]    → after_build
before_qa       → [QA]       → after_qa
```

| Hook | Timing | 입력 (stdin JSON) | 기대 출력 |
|------|--------|-------------------|-----------|
| `before_scaffold` | scaffold 실행 직전 | `seed.json` 경로 | 없음 (종료 코드만 확인) |
| `after_scaffold` | scaffold 완료 직후 | `seed.json` 경로, 생성된 파일 목록 | 없음 |
| `before_build` | build 실행 직전 | `seed.json` 경로, features 배열 | 없음 |
| `after_build` | build 완료 직후 | 빌드 결과 (pass/fail, features 요약) | `pass` / `fail` |
| `before_qa` | QA 실행 직전 | `seed.json` 경로, features 배열 | 없음 |
| `after_qa` | QA 완료 직후 | QA 결과 (verdict, pass_rate) | `pass` / `fail` |

## 플러그인 로딩 프로세스

각 스테이지 시작/종료 시 오케스트레이터가 수행하는 절차:

```bash
# 1. 플러그인 디렉토리 확인
PLUGIN_DIR=~/.samvil/plugins
if [ ! -d "$PLUGIN_DIR" ]; then
  # 플러그인 없음 → 바로 다음 스테이지 진행
  return
fi

# 2. 각 플러그인의 plugin.json 읽기
for plugin_manifest in "$PLUGIN_DIR"/*/plugin.json; do
  [ -f "$plugin_manifest" ] || continue
  plugin_name=$(basename $(dirname "$plugin_manifest"))
  
  # 3. 해당 hook에 등록된 명령어 확인
  command=$(python3 -c "
import json, sys
m = json.load(open('$plugin_manifest'))
hooks = m.get('hooks', {})
hook_config = hooks.get('$HOOK_NAME', {})
print(hook_config.get('command', ''))
" 2>/dev/null)
  
  # 4. command가 없으면 스킵
  [ -z "$command" ] && continue
  
  # 5. 명령어 실행 (stdin으로 JSON 입력 전달)
  echo "$INPUT_JSON" | eval "$command" > ".samvil/plugin-output/${plugin_name}-${HOOK_NAME}.log" 2>".samvil/plugin-output/${plugin_name}-${HOOK_NAME}.err"
  exit_code=$?
  
  # 6. 결과 기록
  if [ $exit_code -ne 0 ]; then
    echo "[SAMVIL] Plugin '$plugin_name' ($HOOK_NAME) failed (exit $exit_code). Continuing..."
  else
    echo "[SAMVIL] Plugin '$plugin_name' ($HOOK_NAME) completed."
  fi
done
```

**의사코드 (스킬 내부 동작):**

```
function run_plugin_hook(hook_name, input_data):
    plugin_dir = expand("~/.samvil/plugins")
    if not exists(plugin_dir):
        return  # 플러그인 없음 → 스킵
    
    output_dir = ".samvil/plugin-output"
    mkdir -p(output_dir)
    
    for each plugin_manifest in glob("$plugin_dir/*/plugin.json"):
        plugin_name = basename(dirname(plugin_manifest))
        manifest = read_json(plugin_manifest)
        hook_config = manifest.get("hooks", {}).get(hook_name)
        
        if not hook_config or not hook_config.get("command"):
            continue  # 이 hook에 등록 안 됨
        
        command = hook_config["command"]
        
        try:
            result = bash(f'echo \'{to_json(input_data)}\' | {command}')
            write(f'{output_dir}/{plugin_name}-{hook_name}.log', result.stdout)
            
            # state.json에 플러그인 결과 기록
            state = read_json("project.state.json")
            state.setdefault("plugin_results", {})
            state["plugin_results"][f"{plugin_name}:{hook_name}"] = {
                "exit_code": 0,
                "timestamp": iso_now()
            }
            write_json("project.state.json", state)
            
            print(f"[SAMVIL] Plugin '{plugin_name}' ({hook_name}) completed.")
        except:
            print(f"[SAMVIL] Plugin '{plugin_name}' ({hook_name}) failed. Continuing...")
            write(f'{output_dir}/{plugin_name}-{hook_name}.err', error_message)
```

## 체인 내 호출 시점

오케스트레이터는 각 스테이지 스킬을 invoke 하기 직전과 직후에 plugin hook을 실행한다:

```
[Scaffold 스테이지]
  run_plugin_hook("before_scaffold", {"seed_path": "..."})
  → Invoke samvil-scaffold
  run_plugin_hook("after_scaffold", {"seed_path": "...", "files": [...]})

[Build 스테이지]
  run_plugin_hook("before_build", {"seed_path": "...", "features": [...]})
  → Invoke samvil-build
  run_plugin_hook("after_build", {"result": "pass", "features_passed": N, ...})

[QA 스테이지]
  run_plugin_hook("before_qa", {"seed_path": "...", "features": [...]})
  → Invoke samvil-qa
  run_plugin_hook("after_qa", {"verdict": "PASS", "pass_rate": 0.95})
```

**참고:** 현재(M2)는 오케스트레이터가 체인을 시작(samvil-interview invoke)한 후 각 스킬이 자체적으로 다음 스킬을 invoke하므로, plugin hook 호출은 **각 스킬(scaffold, build, qa) 내부**에서도 수행되어야 한다:

- **scaffold 스킬**: Boot Sequence 시작 전 `before_scaffold`, Chain 종료 후 `after_scaffold`
- **build 스킬**: Boot Sequence 시작 전 `before_build`, Chain 종료 후 `after_build`
- **qa 스킬**: Boot Sequence 시작 전 `before_qa`, Chain 종료 후 `after_qa`

각 스킬의 SKILL.md에도 plugin hook 호출 지점을 추가해야 한다 (별도 작업).

## state.json 플러그인 결과 기록

```json
{
  "plugin_results": {
    "my-plugin:after_scaffold": {
      "exit_code": 0,
      "timestamp": "2024-01-01T00:05:00Z"
    },
    "my-plugin:after_build": {
      "exit_code": 1,
      "error": "command not found",
      "timestamp": "2024-01-01T00:10:00Z"
    }
  }
}
```

## 플러그인 검색 우선순위

1. `~/.samvil/plugins/<plugin-name>/plugin.json` (사용자 글로벌 플러그인)
2. `.samvil/plugins/<plugin-name>/plugin.json` (프로젝트 로컬 플러그인)

프로젝트 로컬이 글로벌보다 우선. 같은 이름의 플러그인이 양쪽에 있으면 로컬만 실행.
