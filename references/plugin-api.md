# SAMVIL Plugin API

> 사용자가 파이프라인 특정 스테이지에 커스텀 로직을 끼워 넣을 수 있는 플러그인 시스템.

## Plugin Manifest (plugin.json)

각 플러그인은 `plugin.json` 매니페스트 파일로 정의된다.

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "Scaffold 후 자동 테스트 실행",
  "hooks": {
    "after_scaffold": {
      "command": "npm run test"
    },
    "after_build": {
      "command": "npm run lint && npm run test"
    },
    "after_qa": {
      "command": "echo 'QA done' > qa-done.flag"
    }
  }
}
```

### 필드 정의

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `name` | string | O | 플러그인 이름. 영문, 숫자, 하이픈만 사용 |
| `version` | string | O | 시맨틱 버전 (semver) |
| `description` | string | - | 플러그인 설명 |
| `hooks` | object | O | hook 포인트별 설정. 최소 1개 이상의 hook 필요 |

### Hook 설정

```json
{
  "<hook_name>": {
    "command": "<실행할 쉘 명령어>"
  }
}
```

- `command`는 독립 쉘 프로세스에서 실행된다
- stdin으로 JSON 입력이 전달된다
- 종료 코드 0 = 성공, 0 외 = 실패

## Hook Points

| Hook | Timing | stdin JSON 입력 | Expected Output |
|------|--------|----------------|-----------------|
| `before_scaffold` | scaffold 실행 직전 | `{"seed_path": "<path>"}` | 종료 코드 0 |
| `after_scaffold` | scaffold 완료 직후 | `{"seed_path": "<path>", "files": ["package.json", "app/page.tsx", ...]}` | 종료 코드 0 |
| `before_build` | build 실행 직전 | `{"seed_path": "<path>", "features": ["auth", "dashboard", ...]}` | 종료 코드 0 |
| `after_build` | build 완료 직후 | `{"result": "pass", "features_passed": 5, "features_failed": 0, "features_total": 5}` | 종료 코드 0 |
| `before_qa` | QA 실행 직전 | `{"seed_path": "<path>", "features": ["auth", "dashboard", ...]}` | 종료 코드 0 |
| `after_qa` | QA 완료 직후 | `{"verdict": "PASS", "pass_rate": 0.95, "iterations": 1}` | 종료 코드 0 |

### Hook 입력 상세

**before_scaffold / after_scaffold**
```json
{
  "seed_path": "/Users/user/dev/my-app/seed.json"
}
```
after_scaffold 추가 필드:
```json
{
  "seed_path": "/Users/user/dev/my-app/seed.json",
  "files": ["package.json", "app/page.tsx", "components/ui/button.tsx", ...]
}
```

**before_build / after_build**
```json
{
  "seed_path": "/Users/user/dev/my-app/seed.json",
  "features": ["auth", "dashboard", "settings"]
}
```
after_build 추가 필드:
```json
{
  "result": "pass",
  "features_passed": 5,
  "features_failed": 0,
  "features_total": 5
}
```

**before_qa / after_qa**
```json
{
  "seed_path": "/Users/user/dev/my-app/seed.json",
  "features": ["auth", "dashboard", "settings"]
}
```
after_qa 추가 필드:
```json
{
  "verdict": "PASS",
  "pass_rate": 0.95,
  "iterations": 1
}
```

## Plugin Directory Structure

### 사용자 글로벌 플러그인

```
~/.samvil/plugins/
├── my-plugin/
│   ├── plugin.json      ← 매니페스트
│   ├── run-tests.sh     ← 플러그인 스크립트
│   └── (기타 파일)
└── another-plugin/
    ├── plugin.json
    └── ...
```

### 프로젝트 로컬 플러그인

```
<project-dir>/.samvil/plugins/
├── local-plugin/
│   ├── plugin.json
│   └── ...
└── ...
```

**우선순위**: 프로젝트 로컬 > 글로벌. 같은 이름이면 로컬만 실행.

## 실행 규칙

1. **독립 프로세스** — 플러그인은 쉘 명령으로 실행. 하네스와 프로세스 분리.
2. **Best-effort** — 플러그인 실패(exit code != 0)는 하네스 실행에 영향 없음. 경고만 출력.
3. **stdout 저장** — `.samvil/plugin-output/<plugin-name>-<hook>.log`에 저장.
4. **stderr는 경고** — stderr 출력은 `[SAMVIL] Plugin '<name>' (<hook>) failed. Continuing...` 형태로 출력.
5. **시간 제한** — 플러그인 명령은 60초 내 완료해야 함 (권장). 초과 시 경고.
6. **환경 변수** — `SAMVIL_PROJECT_DIR`, `SAMVIL_SEED_PATH`, `SAMVIL_HOOK` 환경 변수가 설정됨.

### 환경 변수

| 변수 | 예시 값 | 설명 |
|------|---------|------|
| `SAMVIL_PROJECT_DIR` | `/Users/user/dev/my-app` | 프로젝트 루트 경로 |
| `SAMVIL_SEED_PATH` | `/Users/user/dev/my-app/seed.json` | seed.json 경로 |
| `SAMVIL_HOOK` | `after_build` | 현재 실행 중인 hook 이름 |
| `SAMVIL_PLUGIN_NAME` | `my-plugin` | 현재 실행 중인 플러그인 이름 |

## 플러그인 결과 기록

플러그인 실행 결과는 `project.state.json`의 `plugin_results` 필드에 기록된다:

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

## 플러그인 예시

### 예시 1: Scaffold 후 자동 테스트

```json
{
  "name": "auto-test",
  "version": "1.0.0",
  "description": "Scaffold 완료 후 자동으로 테스트를 실행합니다",
  "hooks": {
    "after_scaffold": {
      "command": "cd $SAMVIL_PROJECT_DIR && npm test 2>&1 || true"
    }
  }
}
```

### 예시 2: Build 후 슬랙 알림

```json
{
  "name": "slack-notify",
  "version": "1.0.0",
  "description": "Build 결과를 슬랙으로 알림",
  "hooks": {
    "after_build": {
      "command": "curl -s -X POST $SLACK_WEBHOOK_URL -H 'Content-type: application/json' --data '{\"text\":\"SAMVIL Build: '$(cat /dev/stdin)'\"}'"
    }
  }
}
```

### 예시 3: QA 전 커버리지 체크

```json
{
  "name": "coverage-check",
  "version": "1.0.0",
  "description": "QA 실행 전 코드 커버리지를 체크합니다",
  "hooks": {
    "before_qa": {
      "command": "cd $SAMVIL_PROJECT_DIR && npx c8 --reporter=text npm test > .samvil/coverage-report.txt 2>&1 || true"
    }
  }
}
```

## Anti-Patterns

1. 플러그인에서 프로젝트 파일을 삭제하지 마세요 (하네스가 관리하는 파일과 충돌 가능)
2. 플러그인이 오래 실행되면 파이프라인이 지연됩니다 (60초 이내 권장)
3. 플러그인 간 실행 순서는 보장되지 않습니다 (독립적으로 실행)
4. `seed.json`을 수정하지 마세요 (다음 스테이지에 영향을 줄 수 있음)
