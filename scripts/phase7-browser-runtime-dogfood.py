#!/usr/bin/env python3
"""Run Phase 7 browser runtime dogfood with real npm install and Playwright."""

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
from samvil_mcp.telemetry import build_run_report, derive_retro_observations, write_run_report  # noqa: E402


@dataclass(frozen=True)
class BrowserScenario:
    name: str
    expected_pack: str
    framework: str
    seed: dict[str, Any]
    dependencies: dict[str, str]
    dev_dependencies: dict[str, str]


SCENARIOS: tuple[BrowserScenario, ...] = (
    BrowserScenario(
        name="vite-saas-dashboard-browser",
        expected_pack="saas-dashboard",
        framework="vite-react",
        seed={
            "name": "vite-saas-dashboard-browser",
            "solution_type": "dashboard",
            "domain": "saas",
            "app_idea": "Vite React SaaS dashboard with KPI cards, filter interaction, chart, and table.",
            "tech_stack": {"framework": "vite-react"},
        },
        dependencies={"react": "18.3.1", "react-dom": "18.3.1"},
        dev_dependencies={
            "@vitejs/plugin-react": "4.3.4",
            "vite": "5.4.21",
            "typescript": "5.7.3",
            "playwright": "1.52.0",
        },
    ),
    BrowserScenario(
        name="vite-phaser-game-browser",
        expected_pack="browser-game",
        framework="phaser",
        seed={
            "name": "vite-phaser-game-browser",
            "solution_type": "game",
            "domain": "game",
            "app_idea": "Vite Phaser browser game with canvas, keyboard input, score loop, collision, and restart.",
            "tech_stack": {"framework": "phaser"},
        },
        dependencies={"phaser": "3.80.0"},
        dev_dependencies={"vite": "5.4.21", "typescript": "5.7.3", "playwright": "1.52.0"},
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


def _materialize_project(root: Path, scenario: BrowserScenario) -> None:
    (root / ".samvil").mkdir(parents=True, exist_ok=True)
    _write_json(root / "project.state.json", {
        "session_id": f"phase7-{scenario.name}",
        "project_name": scenario.name,
        "current_stage": "complete",
        "samvil_tier": "standard",
        "seed_version": 1,
    })
    _write_json(root / "project.config.json", {"samvil_tier": "standard", "selected_tier": "standard"})
    _write_json(root / "project.seed.json", scenario.seed)
    _write_json(root / "project.blueprint.json", {
        "name": scenario.name,
        "framework": scenario.framework,
        "runtime": "vite-browser",
    })
    _write_json(root / "package.json", {
        "name": scenario.name,
        "private": True,
        "type": "module",
        "scripts": {
            "build": "vite build",
            "dev": "vite --host 127.0.0.1",
            "browser-check": "node scripts/browser-check.mjs",
        },
        "dependencies": scenario.dependencies,
        "devDependencies": scenario.dev_dependencies,
    })
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    if scenario.expected_pack == "saas-dashboard":
        _write_dashboard_app(root)
    else:
        _write_phaser_app(root)
    _write_events_and_claims(root, scenario)


def _write_dashboard_app(root: Path) -> None:
    (root / "index.html").write_text(
        """<div id="root"></div><script type="module" src="/src/main.jsx"></script>\n""",
        encoding="utf-8",
    )
    (root / "vite.config.js").write_text(
        """import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
});
""",
        encoding="utf-8",
    )
    (root / "src" / "main.jsx").write_text(
        """import React, { useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const rows = [
  { date: '2026-04-20', segment: 'all', revenue: 12000, users: 430 },
  { date: '2026-04-21', segment: 'all', revenue: 14600, users: 455 },
  { date: '2026-04-22', segment: 'enterprise', revenue: 18200, users: 180 },
];

function App() {
  const [enterpriseOnly, setEnterpriseOnly] = useState(false);
  const filtered = useMemo(
    () => rows.filter((row) => !enterpriseOnly || row.segment === 'enterprise'),
    [enterpriseOnly],
  );
  const revenue = filtered.reduce((sum, row) => sum + row.revenue, 0);
  const users = filtered.reduce((sum, row) => sum + row.users, 0);

  return (
    <main aria-label="Browser SaaS Dashboard">
      <h1>Browser SaaS Dashboard</h1>
      <section data-testid="kpi-cards">
        <strong>Revenue ${revenue}</strong>
        <strong>Active users {users}</strong>
        <strong>Rows {filtered.length}</strong>
      </section>
      <button data-testid="filter-toggle" onClick={() => setEnterpriseOnly((v) => !v)}>
        Date range filter: {enterpriseOnly ? 'Enterprise' : 'All'}
      </button>
      <section data-testid="chart">Revenue chart points: {filtered.length}</section>
      <table data-testid="report-table">
        <tbody>{filtered.map((row) => <tr key={row.date}><td>{row.date}</td><td>{row.revenue}</td></tr>)}</tbody>
      </table>
      <p data-testid="empty-state">{filtered.length === 0 ? 'No data for selected range' : 'Empty state ready'}</p>
    </main>
  );
}

createRoot(document.getElementById('root')).render(<App />);
""",
        encoding="utf-8",
    )
    (root / "src" / "style.css").write_text(
        """body { font-family: Inter, system-ui, sans-serif; margin: 24px; }
main { max-width: 900px; margin: 0 auto; }
section { margin: 16px 0; }
strong { display: inline-block; margin-right: 16px; }
button { padding: 8px 12px; }
""",
        encoding="utf-8",
    )
    (root / "scripts" / "browser-check.mjs").write_text(
        """import { chromium } from 'playwright';
import assert from 'node:assert/strict';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1024, height: 768 } });
await page.goto(process.env.APP_URL, { waitUntil: 'networkidle' });
await page.screenshot({ path: 'browser-dashboard.png', fullPage: true });
await page.getByRole('heading', { name: 'Browser SaaS Dashboard' }).waitFor();
await page.getByTestId('kpi-cards').waitFor();
assert.match(await page.getByTestId('chart').innerText(), /Revenue chart points: 3/);
await page.getByTestId('filter-toggle').click();
assert.match(await page.getByTestId('filter-toggle').innerText(), /Enterprise/);
assert.match(await page.getByTestId('chart').innerText(), /Revenue chart points: 1/);
assert.match(await page.getByTestId('report-table').innerText(), /18200/);
assert.match(await page.getByTestId('empty-state').innerText(), /Empty state ready/);
await browser.close();
console.log('dashboard browser check ok');
""",
        encoding="utf-8",
    )


def _write_phaser_app(root: Path) -> None:
    (root / "index.html").write_text(
        """<div id="game"></div><button id="restart">Restart</button><p id="score-text">Score 0</p><script type="module" src="/src/main.js"></script>\n""",
        encoding="utf-8",
    )
    (root / "src" / "main.js").write_text(
        """import Phaser from 'phaser';

window.__samvilGameState = { playerX: 80, score: 0, restarted: false, ready: false };

class GameScene extends Phaser.Scene {
  constructor() { super('GameScene'); }
  create() {
    this.player = this.add.rectangle(80, 120, 32, 32, 0x3b82f6);
    this.enemy = this.add.rectangle(250, 120, 32, 32, 0xef4444);
    this.score = 0;
    this.scoreText = this.add.text(16, 16, 'Score 0', { color: '#ffffff' });
    this.cursors = this.input.keyboard.createCursorKeys();
    window.__samvilGameState.ready = true;
    window.__samvilGameState.playerX = this.player.x;
    window.__samvilGameState.score = this.score;
    document.getElementById('restart').addEventListener('click', () => {
      this.score = 0;
      this.player.x = 80;
      this.scoreText.setText('Score 0');
      document.getElementById('score-text').textContent = 'Score 0';
      window.__samvilGameState.restarted = true;
      window.__samvilGameState.score = 0;
      window.__samvilGameState.playerX = this.player.x;
    });
  }
  update() {
    if (this.cursors.right.isDown) {
      this.player.x += 3;
      this.score += 1;
    }
    const collision = Phaser.Geom.Intersects.RectangleToRectangle(this.player.getBounds(), this.enemy.getBounds());
    this.scoreText.setText(`Score ${this.score}`);
    document.getElementById('score-text').textContent = `Score ${this.score}`;
    window.__samvilGameState.playerX = this.player.x;
    window.__samvilGameState.score = this.score;
    window.__samvilGameState.collision = collision;
  }
}

new Phaser.Game({
  type: Phaser.CANVAS,
  parent: 'game',
  width: 400,
  height: 240,
  backgroundColor: '#111827',
  scene: GameScene,
});
""",
        encoding="utf-8",
    )
    (root / "scripts" / "browser-check.mjs").write_text(
        """import { chromium } from 'playwright';
import assert from 'node:assert/strict';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 640, height: 480 } });
await page.goto(process.env.APP_URL, { waitUntil: 'networkidle' });
await page.waitForFunction(() => window.__samvilGameState?.ready === true);
await page.screenshot({ path: 'browser-game.png', fullPage: true });
const nonBlank = await page.$eval('canvas', (canvas) => {
  const ctx = canvas.getContext('2d');
  const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
  for (let i = 0; i < data.length; i += 4) {
    if (data[i] || data[i + 1] || data[i + 2]) return true;
  }
  return false;
});
assert.equal(nonBlank, true);
const before = await page.evaluate(() => window.__samvilGameState.playerX);
await page.keyboard.down('ArrowRight');
await page.waitForTimeout(250);
await page.keyboard.up('ArrowRight');
const after = await page.evaluate(() => window.__samvilGameState.playerX);
assert.ok(after > before, `expected playerX to increase: ${before} -> ${after}`);
const score = await page.evaluate(() => window.__samvilGameState.score);
assert.ok(score > 0, `expected score to increase, got ${score}`);
await page.locator('#restart').click();
await page.waitForFunction(() => window.__samvilGameState.restarted === true && window.__samvilGameState.score === 0);
await browser.close();
console.log('game browser check ok');
""",
        encoding="utf-8",
    )


def _write_events_and_claims(root: Path, scenario: BrowserScenario) -> None:
    stages = ["interview", "seed", "design", "scaffold", "install", "build", "browser", "qa", "retro"]
    complete = {
        "interview": "interview_complete",
        "seed": "seed_generated",
        "design": "blueprint_generated",
        "scaffold": "scaffold_complete",
        "install": "install_complete",
        "build": "build_stage_complete",
        "browser": "browser_check_complete",
        "qa": "qa_pass",
        "retro": "retro_complete",
    }
    events: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    minute = 0
    for stage in stages:
        start_ts = f"2026-04-26T05:{minute:02d}:00Z"
        end_ts = f"2026-04-26T05:{minute + 1:02d}:00Z"
        events.append({"event_type": f"{stage}_started", "stage": stage, "timestamp": start_ts})
        events.append({"event_type": complete[stage], "stage": stage, "timestamp": end_ts})
        claims.append({
            "claim_id": f"{scenario.name}-{stage}-gate",
            "type": "gate_verdict",
            "subject": f"gate:{stage}_exit",
            "statement": f"verdict=pass for {stage}",
            "authority_file": "project.state.json",
            "evidence": [f"event:{complete[stage]}"],
            "claimed_by": "agent:phase7-browser-dogfood",
            "status": "verified",
            "ts": end_ts,
            "meta": {"verdict": "pass", "event_type": complete[stage]},
        })
        minute += 2
    _write_jsonl(root / ".samvil" / "events.jsonl", events)
    _write_jsonl(root / ".samvil" / "claims.jsonl", claims)
    _write_jsonl(root / ".samvil" / "mcp-health.jsonl", [
        {"status": "ok", "tool": "browser_runtime_dogfood", "timestamp": "2026-04-26T05:00:00Z"},
        {"status": "ok", "tool": "build_run_report", "timestamp": "2026-04-26T05:01:00Z"},
    ])


def _run(command: list[str], *, cwd: Path, timeout: int, env: dict[str, str] | None = None) -> str:
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    result = subprocess.run(
        command,
        cwd=cwd,
        env=process_env,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"command failed in {cwd}: {' '.join(command)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result.stdout + result.stderr


def _start_vite(root: Path, port: int) -> subprocess.Popen[str]:
    proc = subprocess.Popen(
        ["npm", "run", "dev", "--", "--port", str(port), "--strictPort"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _wait_for_http(f"http://127.0.0.1:{port}/", timeout=20)
    return proc


def _wait_for_http(url: str, *, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # noqa: BLE001 - retry until ready
            last_error = exc
        time.sleep(0.2)
    raise AssertionError(f"server did not become ready: {last_error}")


def _assert_samvil_surfaces(root: Path, scenario: BrowserScenario) -> dict[str, Any]:
    matches = match_domain_packs(scenario.seed)
    if not matches or matches[0]["pack_id"] != scenario.expected_pack:
        raise AssertionError(f"{scenario.name}: domain pack mismatch {matches}")
    patterns = list_patterns(solution_type=scenario.seed["solution_type"], framework=scenario.framework)
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
        raise AssertionError(f"{scenario.name}: successful browser dogfood produced retro candidates: {retro}")
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


def _status_module():
    script = REPO / "scripts" / "samvil-status.py"
    spec = importlib.util.spec_from_file_location("samvil_status_script", script)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load samvil-status.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_scenario(base: Path, scenario: BrowserScenario) -> dict[str, Any]:
    root = base / scenario.name
    if root.exists():
        shutil.rmtree(root)
    _materialize_project(root, scenario)
    install_output = _run(["npm", "install"], cwd=root, timeout=240)
    build_output = _run(["npm", "run", "build"], cwd=root, timeout=120)
    port = _free_port()
    proc = _start_vite(root, port)
    try:
        browser_output = _run(
            ["npm", "run", "browser-check"],
            cwd=root,
            timeout=80,
            env={"APP_URL": f"http://127.0.0.1:{port}/"},
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    surfaces = _assert_samvil_surfaces(root, scenario)
    screenshot = "browser-dashboard.png" if scenario.expected_pack == "saas-dashboard" else "browser-game.png"
    if not (root / screenshot).exists():
        raise AssertionError(f"{scenario.name}: missing screenshot artifact")
    return {
        "name": scenario.name,
        "root": str(root),
        "install_lines": len(install_output.splitlines()),
        "build_output": build_output.strip().splitlines()[-1] if build_output.strip() else "",
        "browser_output": browser_output.strip().splitlines()[-1] if browser_output.strip() else "",
        "screenshot": screenshot,
        **surfaces,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--keep", action="store_true", help="keep generated temp projects")
    parser.add_argument("--json", action="store_true", help="print JSON summary")
    args = parser.parse_args()

    temp: tempfile.TemporaryDirectory[str] | None = None
    if args.keep:
        base = Path(tempfile.mkdtemp(prefix="samvil-phase7-"))
    else:
        temp = tempfile.TemporaryDirectory(prefix="samvil-phase7-")
        base = Path(temp.name)
    try:
        results = [run_scenario(base, scenario) for scenario in SCENARIOS]
        if args.json:
            print(json.dumps({"status": "ok", "base": str(base), "results": results}, indent=2))
        else:
            print("OK: phase7 browser runtime dogfood passed")
            for result in results:
                print(
                    f"{result['name']}: pack={result['pack']} confidence={result['confidence']} "
                    f"patterns={result['patterns']} modules={result['modules']} events={result['events']} "
                    f"retro={result['retro']} browser='{result['browser_output']}' screenshot={result['screenshot']}"
                )
            print(f"base: {base}")
        return 0
    finally:
        if temp is not None:
            temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
