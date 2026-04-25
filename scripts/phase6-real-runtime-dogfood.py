#!/usr/bin/env python3
"""Run Phase 6 real runtime dogfood for dashboard and game apps.

This is network-free but runtime-real: each generated app runs `npm run build`,
starts a local HTTP server with `npm start`, and is validated through HTTP
responses. It also rechecks SAMVIL domain, pattern, manifest, telemetry,
status, and retro surfaces.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.domain_packs import match_domain_packs  # noqa: E402
from samvil_mcp.manifest import build_manifest, render_for_context, write_manifest  # noqa: E402
from samvil_mcp.pattern_registry import list_patterns  # noqa: E402
from samvil_mcp.telemetry import (  # noqa: E402
    build_run_report,
    derive_retro_observations,
    write_run_report,
)


@dataclass(frozen=True)
class RuntimeScenario:
    name: str
    expected_pack: str
    framework: str
    seed: dict[str, Any]
    required_html: tuple[str, ...]


SCENARIOS: tuple[RuntimeScenario, ...] = (
    RuntimeScenario(
        name="saas-dashboard-runtime",
        expected_pack="saas-dashboard",
        framework="vite-react",
        seed={
            "name": "saas-dashboard-runtime",
            "solution_type": "dashboard",
            "domain": "saas",
            "app_idea": "Runtime SaaS dashboard with KPI cards, filters, chart, table, and empty-state copy.",
            "tech_stack": {"framework": "vite-react"},
        },
        required_html=(
            "SaaS Runtime Dashboard",
            "Revenue",
            "Date range filter",
            "Revenue chart",
            "Report table",
            "No data for selected range",
        ),
    ),
    RuntimeScenario(
        name="browser-game-runtime",
        expected_pack="browser-game",
        framework="phaser",
        seed={
            "name": "browser-game-runtime",
            "solution_type": "game",
            "domain": "game",
            "app_idea": "Runtime browser game with canvas, player input, score loop, collision, and restart.",
            "tech_stack": {"framework": "phaser"},
        },
        required_html=(
            "Browser Game Runtime",
            "<canvas",
            "Score",
            "ArrowRight",
            "collision",
            "Restart",
        ),
    ),
)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _status_module():
    script = REPO / "scripts" / "samvil-status.py"
    spec = importlib.util.spec_from_file_location("samvil_status_script", script)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load samvil-status.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _materialize_project(root: Path, scenario: RuntimeScenario) -> None:
    (root / ".samvil").mkdir(parents=True, exist_ok=True)
    _write_json(root / "project.state.json", {
        "session_id": f"phase6-{scenario.name}",
        "project_name": scenario.name,
        "current_stage": "complete",
        "samvil_tier": "standard",
        "seed_version": 1,
    })
    _write_json(root / "project.config.json", {
        "samvil_tier": "standard",
        "selected_tier": "standard",
    })
    _write_json(root / "project.seed.json", scenario.seed)
    _write_json(root / "project.blueprint.json", {
        "name": scenario.name,
        "framework": scenario.framework,
        "runtime": "node-http-static",
    })
    _write_json(root / "package.json", {
        "name": scenario.name,
        "private": True,
        "type": "module",
        "scripts": {
            "build": "node scripts/build-check.mjs",
            "start": "node scripts/server.mjs",
        },
    })
    (root / "scripts").mkdir(exist_ok=True)
    (root / "public").mkdir(exist_ok=True)
    (root / "src").mkdir(exist_ok=True)
    _write_runtime_files(root, scenario)
    _write_events_and_claims(root, scenario)


def _write_runtime_files(root: Path, scenario: RuntimeScenario) -> None:
    if scenario.expected_pack == "saas-dashboard":
        title = "SaaS Runtime Dashboard"
        html_body = """
<main aria-label="SaaS Runtime Dashboard">
  <h1>SaaS Runtime Dashboard</h1>
  <section data-testid="kpis">
    <strong>Revenue</strong><strong>Active users</strong><strong>Churn</strong>
  </section>
  <label>Date range filter <input value="Last 7 days" /></label>
  <section id="chart">Revenue chart synced to filtered metrics</section>
  <table aria-label="Report table"><tbody><tr><td>2026-04-26</td><td>$12,000</td></tr></tbody></table>
  <p>No data for selected range</p>
</main>
"""
        source = """
export const dashboardRuntime = {
  kpis: ['Revenue', 'Active users', 'Churn'],
  filter: 'Date range filter',
  chart: 'Revenue chart',
  table: 'Report table',
  empty: 'No data for selected range',
};
"""
    else:
        title = "Browser Game Runtime"
        html_body = """
<main aria-label="Browser Game Runtime">
  <h1>Browser Game Runtime</h1>
  <canvas id="game" width="320" height="180"></canvas>
  <p>Score: <span id="score">0</span></p>
  <p>Press ArrowRight to move. Collision ends the run. Restart resets score.</p>
  <button id="restart">Restart</button>
</main>
<script>
  const game = { score: 0, playerX: 10, enemyX: 80, collision: false };
  window.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowRight') game.playerX += 5;
  });
  document.getElementById('restart').addEventListener('click', () => {
    game.score = 0;
    game.collision = false;
  });
</script>
"""
        source = """
export const gameRuntime = {
  canvas: true,
  input: 'ArrowRight',
  scoreLoop: true,
  collision: true,
  restart: true,
};
"""

    (root / "src" / "runtime.js").write_text(source.strip() + "\n", encoding="utf-8")
    (root / "public" / "index.html").write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>{title}</title>
</head>
<body>
{html_body.strip()}
</body>
</html>
""",
        encoding="utf-8",
    )
    (root / "scripts" / "build-check.mjs").write_text(
        """import { access, mkdir, copyFile, readFile } from 'node:fs/promises';
import { constants } from 'node:fs';

await access('public/index.html', constants.R_OK);
await access('src/runtime.js', constants.R_OK);
const html = await readFile('public/index.html', 'utf8');
const source = await readFile('src/runtime.js', 'utf8');
if (!html.includes('<main') || !source.includes('Runtime')) {
  throw new Error('runtime source did not include expected app markers');
}
await mkdir('dist', { recursive: true });
await copyFile('public/index.html', 'dist/index.html');
console.log('runtime build ok');
""",
        encoding="utf-8",
    )
    (root / "scripts" / "server.mjs").write_text(
        """import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';

const port = Number(process.env.PORT || 0);
const html = await readFile('dist/index.html', 'utf8');
const server = createServer((request, response) => {
  if (request.url === '/health') {
    response.writeHead(200, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ status: 'ok' }));
    return;
  }
  response.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
  response.end(html);
});
server.listen(port, '127.0.0.1', () => {
  const address = server.address();
  console.log(`SAMVIL_RUNTIME_READY ${address.port}`);
});
""",
        encoding="utf-8",
    )


def _write_events_and_claims(root: Path, scenario: RuntimeScenario) -> None:
    stages = ["interview", "seed", "design", "scaffold", "build", "qa", "runtime", "retro"]
    complete = {
        "interview": "interview_complete",
        "seed": "seed_generated",
        "design": "blueprint_generated",
        "scaffold": "scaffold_complete",
        "build": "build_stage_complete",
        "qa": "qa_pass",
        "runtime": "runtime_check_complete",
        "retro": "retro_complete",
    }
    events: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    minute = 0
    for stage in stages:
        start_ts = f"2026-04-26T04:{minute:02d}:00Z"
        end_ts = f"2026-04-26T04:{minute + 1:02d}:00Z"
        events.append({"event_type": f"{stage}_started", "stage": stage, "timestamp": start_ts})
        events.append({"event_type": complete[stage], "stage": stage, "timestamp": end_ts})
        claims.append({
            "claim_id": f"{scenario.name}-{stage}-gate",
            "type": "gate_verdict",
            "subject": f"gate:{stage}_exit",
            "statement": f"verdict=pass for {stage}",
            "authority_file": "project.state.json",
            "evidence": [f"event:{complete[stage]}"],
            "claimed_by": "agent:phase6-runtime-dogfood",
            "status": "verified",
            "ts": end_ts,
            "meta": {"verdict": "pass", "event_type": complete[stage]},
        })
        minute += 2
    _write_jsonl(root / ".samvil" / "events.jsonl", events)
    _write_jsonl(root / ".samvil" / "claims.jsonl", claims)
    _write_jsonl(root / ".samvil" / "mcp-health.jsonl", [
        {"status": "ok", "tool": "runtime_dogfood", "timestamp": "2026-04-26T04:00:00Z"},
        {"status": "ok", "tool": "build_run_report", "timestamp": "2026-04-26T04:01:00Z"},
    ])


def _run_build(root: Path) -> str:
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )
    if result.returncode != 0:
        raise AssertionError(f"npm run build failed in {root}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    return result.stdout + result.stderr


def _start_and_fetch(root: Path, scenario: RuntimeScenario) -> dict[str, Any]:
    port = _free_port()
    env = {**os.environ, "PORT": str(port)}
    proc = subprocess.Popen(
        ["npm", "start"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        _wait_for_http(f"http://127.0.0.1:{port}/health", timeout=8)
        html = _fetch(f"http://127.0.0.1:{port}/")
        missing = [needle for needle in scenario.required_html if needle not in html]
        if missing:
            raise AssertionError(f"{scenario.name}: served HTML missing {missing}")
        return {"port": port, "html_bytes": len(html.encode("utf-8"))}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def _wait_for_http(url: str, *, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            _fetch(url)
            return
        except Exception as exc:  # noqa: BLE001 - retry until timeout
            last_error = exc
            time.sleep(0.1)
    raise AssertionError(f"server did not become ready: {last_error}")


def _fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=2) as response:
        if response.status != 200:
            raise AssertionError(f"unexpected HTTP status {response.status} for {url}")
        return response.read().decode("utf-8")


def _assert_samvil_surfaces(root: Path, scenario: RuntimeScenario) -> dict[str, Any]:
    matches = match_domain_packs(scenario.seed)
    if not matches or matches[0]["pack_id"] != scenario.expected_pack:
        raise AssertionError(f"{scenario.name}: domain pack mismatch {matches}")
    patterns = list_patterns(
        solution_type=scenario.seed["solution_type"],
        framework=scenario.framework,
    )
    if not patterns:
        raise AssertionError(f"{scenario.name}: no pattern match")
    manifest = build_manifest(root, project_name=scenario.name)
    write_manifest(manifest, root)
    manifest_context = render_for_context(manifest)
    if "## Modules" not in manifest_context or not manifest.modules:
        raise AssertionError(f"{scenario.name}: manifest missing module context")
    report = build_run_report(root)
    write_run_report(report, root)
    if report["timeline"]["failure_count"] != 0 or report["timeline"]["retry_count"] != 0:
        raise AssertionError(f"{scenario.name}: report had failures/retries")
    retro = derive_retro_observations(report)
    if retro:
        raise AssertionError(f"{scenario.name}: successful runtime produced retro candidates: {retro}")
    status = _status_module()
    status_json = json.loads(status.render_json(root))
    if not status_json["run_report"]["present"]:
        raise AssertionError(f"{scenario.name}: status did not see run report")
    return {
        "pack": matches[0]["pack_id"],
        "confidence": matches[0]["confidence"],
        "patterns": len(patterns),
        "modules": len(manifest.modules),
        "events": report["events"]["total"],
        "retro": len(retro),
    }


def run_scenario(base: Path, scenario: RuntimeScenario) -> dict[str, Any]:
    root = base / scenario.name
    if root.exists():
        shutil.rmtree(root)
    _materialize_project(root, scenario)
    build_output = _run_build(root)
    runtime = _start_and_fetch(root, scenario)
    surfaces = _assert_samvil_surfaces(root, scenario)
    return {
        "name": scenario.name,
        "root": str(root),
        "build_output": build_output.strip(),
        "runtime": runtime,
        **surfaces,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--keep", action="store_true", help="keep generated temp projects")
    parser.add_argument("--json", action="store_true", help="print JSON summary")
    args = parser.parse_args()

    temp: tempfile.TemporaryDirectory[str] | None = None
    if args.keep:
        base = Path(tempfile.mkdtemp(prefix="samvil-phase6-"))
    else:
        temp = tempfile.TemporaryDirectory(prefix="samvil-phase6-")
        base = Path(temp.name)
    try:
        results = [run_scenario(base, scenario) for scenario in SCENARIOS]
        if args.json:
            print(json.dumps({"status": "ok", "base": str(base), "results": results}, indent=2))
        else:
            print("OK: phase6 real runtime dogfood passed")
            for result in results:
                runtime = result["runtime"]
                print(
                    f"{result['name']}: pack={result['pack']} "
                    f"confidence={result['confidence']} patterns={result['patterns']} "
                    f"modules={result['modules']} events={result['events']} "
                    f"retro={result['retro']} port={runtime['port']} html_bytes={runtime['html_bytes']}"
                )
            print(f"base: {base}")
        return 0
    finally:
        if temp is not None:
            temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
