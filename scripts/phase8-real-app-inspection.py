#!/usr/bin/env python3
"""Run Phase 8 real app inspection dogfood with Playwright browser evidence."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.inspection import build_inspection_report, render_inspection_report, write_inspection_report  # noqa: E402


def _load_phase7():
    script = REPO / "scripts" / "phase7-browser-runtime-dogfood.py"
    spec = importlib.util.spec_from_file_location("phase7_browser_runtime_dogfood", script)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load phase7 browser dogfood")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PHASE7 = _load_phase7()
SCENARIOS = PHASE7.SCENARIOS


def _write_dashboard_inspection(root: Path) -> None:
    (root / "scripts" / "browser-check.mjs").write_text(
        """import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const artifactsDir = '.samvil/artifacts';
fs.mkdirSync(artifactsDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
const consoleErrors = [];
page.on('console', (msg) => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
page.on('pageerror', (err) => consoleErrors.push(err.message));

async function overflowRecords() {
  return await page.evaluate(() => Array.from(document.querySelectorAll('main, h1, section, button, table, p, strong, td'))
    .map((el) => {
      const rect = el.getBoundingClientRect();
      const overflow = el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1 || rect.right > window.innerWidth + 1;
      return {
        tag: el.tagName.toLowerCase(),
        testid: el.getAttribute('data-testid') || '',
        text: (el.textContent || '').trim().slice(0, 80),
        overflow,
      };
    })
    .filter((row) => row.overflow));
}

async function inspectViewport(name, width, height) {
  const start = consoleErrors.length;
  await page.setViewportSize({ width, height });
  await page.goto(process.env.APP_URL, { waitUntil: 'networkidle' });
  await page.getByRole('heading', { name: 'Browser SaaS Dashboard' }).waitFor();
  const screenshot = `${artifactsDir}/${name}.png`;
  await page.screenshot({ path: screenshot, fullPage: true });
  const overflow = await overflowRecords();
  return {
    name,
    width,
    height,
    loaded: true,
    console_errors: consoleErrors.slice(start),
    overflow_count: overflow.length,
    overflow,
    screenshot,
  };
}

const desktop = await inspectViewport('desktop', 1280, 800);
await page.getByTestId('filter-toggle').click();
const chartText = await page.getByTestId('chart').innerText();
const tableText = await page.getByTestId('report-table').innerText();
const filterText = await page.getByTestId('filter-toggle').innerText();
assert.match(filterText, /Enterprise/);
assert.match(chartText, /Revenue chart points: 1/);
assert.match(tableText, /18200/);

const mobile = await inspectViewport('mobile', 390, 844);
await browser.close();

const evidence = {
  schema_version: '1.0',
  scenario: 'vite-saas-dashboard-inspection',
  url: process.env.APP_URL,
  viewports: [desktop, mobile],
  interactions: [
    {
      id: 'dashboard-filter',
      status: 'pass',
      message: 'filter button updates chart and table text',
      details: { filterText, chartText, tableText },
    },
  ],
};
fs.writeFileSync('.samvil/inspection-evidence.json', JSON.stringify(evidence, null, 2));
console.log('dashboard inspection ok');
""",
        encoding="utf-8",
    )


def _write_game_inspection(root: Path) -> None:
    (root / "index.html").write_text(
        """<style>
body { margin: 0; font-family: system-ui, sans-serif; background: #f8fafc; }
#game { max-width: 100vw; overflow: hidden; }
canvas { display: block; max-width: 100%; height: auto !important; }
#restart { margin: 8px; padding: 8px 12px; }
#score-text { margin: 8px; }
</style><div id="game"></div><button id="restart">Restart</button><p id="score-text">Score 0</p><script type="module" src="/src/main.js"></script>\n""",
        encoding="utf-8",
    )
    (root / "scripts" / "browser-check.mjs").write_text(
        """import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const artifactsDir = '.samvil/artifacts';
fs.mkdirSync(artifactsDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
const consoleErrors = [];
page.on('console', (msg) => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
page.on('pageerror', (err) => consoleErrors.push(err.message));

async function isCanvasNonBlank() {
  return await page.$eval('canvas', (canvas) => {
    const ctx = canvas.getContext('2d');
    if (!ctx) return false;
    const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    for (let i = 0; i < data.length; i += 4) {
      if (data[i] || data[i + 1] || data[i + 2]) return true;
    }
    return false;
  });
}

async function overflowRecords() {
  return await page.evaluate(() => Array.from(document.querySelectorAll('#game, canvas, button, p'))
    .map((el) => {
      const rect = el.getBoundingClientRect();
      const overflow = el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1 || rect.right > window.innerWidth + 1;
      return {
        tag: el.tagName.toLowerCase(),
        id: el.id || '',
        text: (el.textContent || '').trim().slice(0, 80),
        overflow,
      };
    })
    .filter((row) => row.overflow));
}

async function inspectViewport(name, width, height) {
  const start = consoleErrors.length;
  await page.setViewportSize({ width, height });
  await page.goto(process.env.APP_URL, { waitUntil: 'networkidle' });
  await page.waitForFunction(() => window.__samvilGameState?.ready === true);
  const screenshot = `${artifactsDir}/${name}.png`;
  await page.screenshot({ path: screenshot, fullPage: true });
  const overflow = await overflowRecords();
  return {
    name,
    width,
    height,
    loaded: true,
    console_errors: consoleErrors.slice(start),
    overflow_count: overflow.length,
    overflow,
    canvas_nonblank: await isCanvasNonBlank(),
    screenshot,
  };
}

const desktop = await inspectViewport('desktop', 800, 600);
const before = await page.evaluate(() => window.__samvilGameState.playerX);
await page.keyboard.down('ArrowRight');
await page.waitForTimeout(250);
await page.keyboard.up('ArrowRight');
const after = await page.evaluate(() => window.__samvilGameState.playerX);
const score = await page.evaluate(() => window.__samvilGameState.score);
assert.ok(after > before, `expected playerX to increase: ${before} -> ${after}`);
assert.ok(score > 0, `expected score to increase, got ${score}`);
await page.locator('#restart').click();
await page.waitForFunction(() => window.__samvilGameState.restarted === true && window.__samvilGameState.score === 0);

const mobile = await inspectViewport('mobile', 390, 640);
await browser.close();

const evidence = {
  schema_version: '1.0',
  scenario: 'vite-phaser-game-inspection',
  url: process.env.APP_URL,
  viewports: [desktop, mobile],
  interactions: [
    {
      id: 'game-keyboard-score-restart',
      status: 'pass',
      message: 'ArrowRight moves player, score increases, and restart resets score',
      details: { before, after, score },
    },
  ],
};
fs.writeFileSync('.samvil/inspection-evidence.json', JSON.stringify(evidence, null, 2));
console.log('game inspection ok');
""",
        encoding="utf-8",
    )


def _prepare_project(root: Path, scenario: Any) -> None:
    PHASE7._materialize_project(root, scenario)
    if scenario.expected_pack == "saas-dashboard":
        _write_dashboard_inspection(root)
    else:
        _write_game_inspection(root)


def _assert_inspection(root: Path, scenario: Any) -> dict[str, Any]:
    report = build_inspection_report(root)
    write_inspection_report(report, root)
    rendered = render_inspection_report(report)
    summary = report["summary"]
    if summary["status"] != "pass":
        raise AssertionError(f"{scenario.name}: inspection failed: {rendered}")
    status = PHASE7._status_module()
    status_json = json.loads(status.render_json(root))
    inspection_status = status_json["inspection_report"]
    if not inspection_status["present"] or inspection_status["status"] != "pass":
        raise AssertionError(f"{scenario.name}: status did not expose passing inspection: {inspection_status}")
    return {
        "inspection_checks": summary["total_checks"],
        "inspection_failed": summary["failed_checks"],
        "console_errors": summary["console_errors"],
        "screenshots": summary["screenshots"],
        "viewports": summary["viewports"],
    }


def run_scenario(base: Path, scenario: Any) -> dict[str, Any]:
    root = base / scenario.name.replace("-browser", "-inspection")
    if root.exists():
        shutil.rmtree(root)
    _prepare_project(root, scenario)
    install_output = PHASE7._run(["npm", "install"], cwd=root, timeout=240)
    build_output = PHASE7._run(["npm", "run", "build"], cwd=root, timeout=120)
    port = PHASE7._free_port()
    proc = PHASE7._start_vite(root, port)
    try:
        browser_output = PHASE7._run(
            ["npm", "run", "browser-check"],
            cwd=root,
            timeout=120,
            env={"APP_URL": f"http://127.0.0.1:{port}/"},
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
            proc.wait(timeout=5)
    surfaces = PHASE7._assert_samvil_surfaces(root, scenario)
    inspection = _assert_inspection(root, scenario)
    return {
        "name": root.name,
        "root": str(root),
        "install_lines": len(install_output.splitlines()),
        "build_output": build_output.strip().splitlines()[-1] if build_output.strip() else "",
        "browser_output": browser_output.strip().splitlines()[-1] if browser_output.strip() else "",
        **surfaces,
        **inspection,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--keep", action="store_true", help="keep generated temp projects")
    parser.add_argument("--json", action="store_true", help="print JSON summary")
    args = parser.parse_args()

    temp: tempfile.TemporaryDirectory[str] | None = None
    if args.keep:
        base = Path(tempfile.mkdtemp(prefix="samvil-phase8-"))
    else:
        temp = tempfile.TemporaryDirectory(prefix="samvil-phase8-", ignore_cleanup_errors=True)
        base = Path(temp.name)
    try:
        results = [run_scenario(base, scenario) for scenario in SCENARIOS]
        if args.json:
            print(json.dumps({"status": "ok", "base": str(base), "results": results}, indent=2))
        else:
            print("OK: phase8 real app inspection passed")
            for result in results:
                print(
                    f"{result['name']}: pack={result['pack']} confidence={result['confidence']} "
                    f"checks={result['inspection_checks']} failed={result['inspection_failed']} "
                    f"console_errors={result['console_errors']} screenshots={result['screenshots']} "
                    f"viewports={result['viewports']} retro={result['retro']} browser='{result['browser_output']}'"
                )
            print(f"base: {base}")
        return 0
    finally:
        if temp is not None:
            temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
