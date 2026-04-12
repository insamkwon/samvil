# Automation Recipes — Python/Node/Shell/CC-skill Patterns

> Reference for `samvil-build` and `samvil-scaffold` when `solution_type: "automation"`.

## 1. Python CLI Pattern (argparse + --dry-run)

```python
#!/usr/bin/env python3
"""<description>"""

import argparse
import json
import sys
from pathlib import Path

from processor import Processor
from config import load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="<description>")
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

### Key Rules
- `--dry-run` flag is **mandatory** for all automation scripts
- dry-run reads from `fixtures/input/` and compares against `fixtures/expected/`
- No real API calls, no network access in dry-run mode
- Exit code 0 on success, non-zero on failure
- Output is structured JSON (machine-readable)

## 2. Fixture Directory Structure Convention

```
fixtures/
  input/
    sample1.json        # Representative input data
    sample2.json        # Edge case input
    ...
  expected/
    sample1.expected.json  # Expected output for sample1.json
    sample2.expected.json  # Expected output for sample2.json
    ...
```

### Rules
- `fixtures/input/` contains realistic input samples (not minimal stubs)
- `fixtures/expected/` contains the exact expected output for each input
- File names must match: `input/<name>.json` -> `expected/<name>.expected.json`
- At least 2 fixture pairs: one happy path, one edge case
- Fixtures must be committed to git (reproducible tests)
- No secrets or real API keys in fixtures

## 3. Error Handling Pattern (Retry with Exponential Backoff)

```python
import time
import logging
from functools import wraps
from typing import Callable, TypeVar, Type

logger = logging.getLogger(__name__)

T = TypeVar("T")

def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: tuple[Type[Exception], ...] = (Exception,),
) -> Callable:
    """Decorator: retry a function with exponential backoff."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        logger.error(
                            "Failed after %d attempts: %s",
                            max_retries + 1, str(e)
                        )
                        raise
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    logger.warning(
                        "Attempt %d/%d failed: %s. Retrying in %.1fs",
                        attempt + 1, max_retries + 1, str(e), delay
                    )
                    time.sleep(delay)
            raise last_exception  # unreachable but satisfies type checker
        return wrapper
    return decorator


# Usage
@retry_with_backoff(max_retries=3, exceptions=(ConnectionError, TimeoutError))
def fetch_data(url: str) -> dict:
    ...
```

### Error Handling Strategies

| Strategy | When to Use | Behavior |
|----------|------------|----------|
| `retry_with_logging` | Transient failures (network, rate limit) | Retry N times with backoff, log each attempt |
| `fail_fast` | Data validation errors | Log error and raise immediately |
| `skip_and_continue` | Non-critical item failures | Log warning, skip item, continue processing |
| `circuit_breaker` | Repeated downstream failures | Stop after N consecutive failures, raise |

## 4. Structured Logging Pattern

```python
import logging
import json
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
        }
        if hasattr(record, "extra_data"):
            log_entry["data"] = record.extra_data
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JSONFormatter())
    logging.root.handlers = [handler]
    logging.root.setLevel(getattr(logging, level.upper()))


# Usage
logger = logging.getLogger(__name__)
logger.info("Processing started", extra={"extra_data": {"items": 42}})
logger.warning("Rate limit approaching", extra={"extra_data": {"remaining": 5}})
logger.error("API call failed", extra={"extra_data": {"url": url, "status": 503}})
```

### Log Level Guidelines

| Level | When | Example |
|-------|------|---------|
| `DEBUG` | Detailed diagnostic info | "Cache miss for key: user_123" |
| `INFO` | Normal operation milestones | "Processing 42 items", "Job completed in 3.2s" |
| `WARNING` | Unexpected but recoverable | "Rate limit at 80%", "Retrying after timeout" |
| `ERROR` | Operation failure | "API returned 500", "Failed to write output" |

## 5. API Client Pattern

```python
import os
import time
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class APIClient:
    """HTTP client with env-based config, timeout, and retry."""

    def __init__(self, base_url: Optional[str] = None, timeout: int = 30):
        self.base_url = base_url or os.environ.get("API_BASE_URL", "")
        self.timeout = timeout
        self.api_key = os.environ.get("API_KEY", "")
        self.session = requests.Session()
        if self.api_key:
            self.session.headers["Authorization"] = f"Bearer {self.api_key}"
        self.session.headers["Content-Type"] = "application/json"

    @retry_with_backoff(max_retries=3, exceptions=(requests.ConnectionError, requests.Timeout))
    def get(self, path: str, params: Optional[dict] = None) -> dict:
        url = f"{self.base_url}{path}"
        logger.info("GET %s", url, extra={"extra_data": {"params": params}})
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    @retry_with_backoff(max_retries=3, exceptions=(requests.ConnectionError, requests.Timeout))
    def post(self, path: str, data: dict) -> dict:
        url = f"{self.base_url}{path}"
        logger.info("POST %s", url, extra={"extra_data": {"data_keys": list(data.keys())}})
        response = self.session.post(url, json=data, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_dry_run(self, fixture_path: str) -> dict:
        """Load fixture data instead of making real API call."""
        import json
        from pathlib import Path
        logger.info("DRY-RUN: loading fixture %s", fixture_path)
        return json.loads(Path(fixture_path).read_text())
```

### Rules
- All config via environment variables (never hardcoded)
- `.env.example` documents all required variables
- Timeout is mandatory (default 30s)
- Retry on transient errors only (5xx, timeout, connection)
- Do NOT retry on 4xx (client errors are not transient)
- In dry-run mode: load from `fixtures/input/` instead of real API

## 6. File I/O Pattern (Read -> Process -> Write)

```python
import json
import csv
import logging
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


def read_input(input_path: str, dry_run: bool = False) -> Iterator[dict]:
    """Read input data from file or fixtures."""
    path = Path("fixtures/input" if dry_run else input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input not found: {path}")

    if path.suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        yield from (data if isinstance(data, list) else [data])
    elif path.suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as f:
            yield from csv.DictReader(f)
    elif path.suffix == ".jsonl":
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)
    else:
        raise ValueError(f"Unsupported format: {path.suffix}")


def write_output(output_path: str, data: list[dict]) -> None:
    """Write processed data to file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.suffix == ".json":
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    elif path.suffix == ".csv":
        if not data:
            path.write_text("", encoding="utf-8")
            return
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
    elif path.suffix == ".jsonl":
        with path.open("w", encoding="utf-8") as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
    else:
        raise ValueError(f"Unsupported output format: {path.suffix}")

    logger.info("Wrote %d items to %s", len(data), path)


def compare_with_expected(output: list[dict], expected_dir: str) -> bool:
    """Compare output against expected fixtures."""
    expected_path = Path(expected_dir)
    if not expected_path.exists():
        logger.warning("No expected output directory: %s", expected_dir)
        return True  # no expected = pass

    expected_files = sorted(expected_path.glob("*.expected.json"))
    if not expected_files:
        return True

    for ef in expected_files:
        expected = json.loads(ef.read_text(encoding="utf-8"))
        if output != expected:
            logger.error("Mismatch: %s", ef.name)
            return False

    return True
```

## 7. Webhook Receiver Pattern

```python
"""Webhook receiver for automation triggers."""

import hashlib
import hmac
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler

logger = logging.getLogger(__name__)

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        if not self._verify_signature(body):
            self.send_response(401)
            self.end_headers()
            return

        try:
            payload = json.loads(body)
            processor = Processor(load_config())
            result = processor.process_webhook(payload)
            self._send_json(200, {"status": "ok", "result": result})
        except Exception as e:
            logger.error("Webhook processing failed: %s", e)
            self._send_json(500, {"status": "error", "message": str(e)})

    def _verify_signature(self, body: bytes) -> bool:
        if not WEBHOOK_SECRET:
            return True  # no secret configured = skip verification
        signature = self.headers.get("X-Signature-256", "")
        expected = "sha256=" + hmac.new(
            WEBHOOK_SECRET.encode(), body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected)

    def _send_json(self, code: int, data: dict) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())


def run_server(port: int = 8080) -> None:
    server = HTTPServer(("0.0.0.0", port), WebhookHandler)
    logger.info("Webhook server listening on port %d", port)
    server.serve_forever()
```

### Webhook Patterns

| Trigger | Implementation | Signature Verification |
|---------|---------------|----------------------|
| Slack | HTTP POST + JSON body | `X-Slack-Signature` |
| GitHub | HTTP POST + JSON body | `X-Hub-Signature-256` |
| Generic | HTTP POST + JSON body | `X-Signature-256` |
| Stripe | HTTP POST + form body | `Stripe-Signature` |

## 8. Cron Schedule Pattern

```python
"""Cron-compatible entry point. Designed to be called by crontab."""

import sys
import logging
from datetime import datetime

from main import parse_args, load_config
from processor import Processor

logger = logging.getLogger(__name__)


def run_cron() -> int:
    """Entry point for cron execution. Logs start/end timestamps."""
    start = datetime.now()
    logger.info("Cron job started at %s", start.isoformat())

    try:
        config = load_config(".env")
        processor = Processor(config)
        result = processor.run()
        elapsed = (datetime.now() - start).total_seconds()
        logger.info(
            "Cron job completed in %.1fs",
            elapsed,
            extra={"extra_data": {"result_summary": str(result)[:200]}}
        )
        return 0
    except Exception as e:
        elapsed = (datetime.now() - start).total_seconds()
        logger.error(
            "Cron job failed after %.1fs: %s",
            elapsed, str(e),
            exc_info=True
        )
        return 1


if __name__ == "__main__":
    sys.exit(run_cron())
```

### Crontab Entry Template

```bash
# .samvil/crontab-template
# Edit and install with: crontab .samvil/crontab-template

# Run every day at 9 AM
0 9 * * * cd /path/to/project && /usr/bin/python3 src/main.py --config .env >> .samvil/cron.log 2>&1

# Run every Monday at 8 AM
0 8 * * 1 cd /path/to/project && /usr/bin/python3 src/main.py --config .env >> .samvil/cron.log 2>&1

# Run every 6 hours
0 */6 * * * cd /path/to/project && /usr/bin/python3 src/main.py --config .env >> .samvil/cron.log 2>&1
```

## 9. CC Skill Template Pattern

When `execution.type` is `"cc-skill"`, generate a SKILL.md file:

```markdown
---
name: <skill-name>
description: "<one-line description>"
---

# <Skill Name>

## What it does
<description of the automation>

## When to use
<trigger conditions>

## Usage
```
/<skill-name> [args]
```

## Process

### Step 1: Read Config
Read environment variables for API keys and settings.

### Step 2: Fetch Data
<describe data source>

### Step 3: Process
<describe transformation>

### Step 4: Output
<describe output format>

## Output Format
<describe expected output>

## Error Handling
- API failure: retry 3 times with backoff
- Invalid data: log warning, skip item
- Config missing: fail with clear message

## Requirements
- Environment variables: `API_KEY`, `OUTPUT_PATH`
- Python packages: `requests`, `python-dotenv`
```

### CC Skill Integration with CronCreate

When deployed as a CC skill with scheduled execution:

```
CronCreate(
  cron: "<schedule>",
  prompt: "Run /<skill-name>",
  recurring: true,
  durable: true
)
```

## 10. Node.js Automation Pattern

For `tech_stack.framework: "node-script"`:

```typescript
// src/main.ts
import { config } from "./config";
import { Processor } from "./processor";
import { Logger } from "./logger";
import { readFixtures, compareOutput } from "./fixtures";

const logger = new Logger();

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
    const input = readFixtures("fixtures/input");
    const expected = readFixtures("fixtures/expected");
    const processor = new Processor(cfg);
    const result = processor.run(input);

    if (!compareOutput(result, expected)) {
      logger.error("Dry-run output does not match expected");
      return 1;
    }
    logger.info("Dry-run passed");
    return 0;
  }

  const processor = new Processor(cfg);
  const result = await processor.run();
  logger.info("Processing complete", { itemCount: result.length });

  if (args.output) {
    require("fs").writeFileSync(args.output, JSON.stringify(result, null, 2));
  } else {
    console.log(JSON.stringify(result, null, 2));
  }

  return 0;
}

main().then(process.exit).catch((e) => {
  logger.error("Fatal error", { error: e.message });
  process.exit(1);
});
```

### Node.js project structure

```
<project>/
  src/
    main.ts       # Entry point with argparse + --dry-run
    processor.ts  # Core logic
    config.ts     # Env-based config
    logger.ts     # Structured logging
    fixtures.ts   # Fixture loading + comparison
  fixtures/
    input/
    expected/
  tests/
    test_dry_run.ts
  .env.example
  package.json
  tsconfig.json
  README.md
```
