#!/usr/bin/env python3
"""Run Phase 5 dual dogfood for SaaS dashboard and browser game.

The script is deterministic and network-free. It creates two temporary SAMVIL
projects, materializes seed/blueprint/source files, runs domain/pattern/manifest
context checks, writes stage events and claims, builds run reports, checks
status output, and verifies retro candidates stay empty on a successful run.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.domain_packs import match_domain_packs, render_domain_packs  # noqa: E402
from samvil_mcp.domain_packs import get_domain_pack  # noqa: E402
from samvil_mcp.manifest import build_manifest, render_for_context, write_manifest  # noqa: E402
from samvil_mcp.pattern_registry import list_patterns, render_patterns  # noqa: E402
from samvil_mcp.telemetry import (  # noqa: E402
    build_run_report,
    derive_retro_observations,
    write_run_report,
)


@dataclass(frozen=True)
class Scenario:
    name: str
    expected_pack: str
    framework: str
    seed: dict[str, Any]
    blueprint: dict[str, Any]


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        name="saas-dashboard",
        expected_pack="saas-dashboard",
        framework="vite-react",
        seed={
            "name": "saas-dashboard",
            "solution_type": "dashboard",
            "domain": "saas",
            "app_idea": "Admin metrics dashboard with KPI cards, date range filters, reporting table, and analytics chart.",
            "tech_stack": {"framework": "vite-react"},
            "acceptance_criteria": [
                "KPI cards summarize revenue, active users, and churn.",
                "Date range filter updates chart and table together.",
                "Empty data state is visible and non-breaking.",
            ],
        },
        blueprint={
            "screens": ["Dashboard"],
            "components": ["KpiCards", "DateRangeFilter", "RevenueChart", "ReportTable"],
            "data_model": ["Metric", "DateRange", "ReportRow"],
        },
    ),
    Scenario(
        name="browser-game",
        expected_pack="browser-game",
        framework="phaser",
        seed={
            "name": "browser-game",
            "solution_type": "game",
            "domain": "game",
            "app_idea": "Browser game where the player collects points, avoids collision, sees score, and can restart.",
            "tech_stack": {"framework": "phaser"},
            "acceptance_criteria": [
                "Game surface renders a canvas.",
                "Keyboard input moves the player.",
                "Collision changes score or game-over state.",
                "Restart returns the loop to the initial state.",
            ],
        },
        blueprint={
            "scenes": ["BootScene", "GameScene", "GameOverScene"],
            "systems": ["input", "collision", "score", "restart"],
        },
    ),
)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def _status_module():
    script = REPO / "scripts" / "samvil-status.py"
    spec = importlib.util.spec_from_file_location("samvil_status_script", script)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load samvil-status.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _project_root(base: Path, scenario: Scenario) -> Path:
    return base / scenario.name


def _materialize_project(root: Path, scenario: Scenario) -> None:
    (root / ".samvil").mkdir(parents=True, exist_ok=True)
    _write_json(root / "project.state.json", {
        "session_id": f"phase5-{scenario.name}",
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
    _write_json(root / "project.blueprint.json", scenario.blueprint)
    _write_json(root / "package.json", {
        "name": scenario.name,
        "private": True,
        "scripts": {"build": "echo deterministic-dogfood-build"},
        "dependencies": {"@vitejs/plugin-react": "latest"},
    })
    if scenario.name == "saas-dashboard":
        _write_dashboard_source(root)
    elif scenario.name == "browser-game":
        _write_game_source(root)
    else:
        raise AssertionError(f"unknown scenario {scenario.name}")
    _write_events_and_claims(root, scenario)


def _write_dashboard_source(root: Path) -> None:
    (root / "src" / "components").mkdir(parents=True, exist_ok=True)
    (root / "src" / "data").mkdir(parents=True, exist_ok=True)
    (root / "src" / "App.tsx").write_text(
        """import { Dashboard } from './components/Dashboard';

export default function App() {
  return <Dashboard />;
}
""",
        encoding="utf-8",
    )
    (root / "src" / "data" / "metrics.ts").write_text(
        """export type Metric = { date: string; revenue: number; activeUsers: number; churn: number };

export const metrics: Metric[] = [
  { date: '2026-04-20', revenue: 12000, activeUsers: 430, churn: 0.04 },
  { date: '2026-04-21', revenue: 14600, activeUsers: 455, churn: 0.03 },
  { date: '2026-04-22', revenue: 9800, activeUsers: 401, churn: 0.05 },
];
""",
        encoding="utf-8",
    )
    (root / "src" / "components" / "Dashboard.tsx").write_text(
        """import { metrics } from '../data/metrics';

const dateRange = { from: '2026-04-20', to: '2026-04-22' };

export function Dashboard() {
  const filteredMetrics = metrics.filter((row) => row.date >= dateRange.from && row.date <= dateRange.to);
  const emptyState = filteredMetrics.length === 0 ? 'No data for the selected date range' : '';
  const revenue = filteredMetrics.reduce((sum, row) => sum + row.revenue, 0);
  const activeUsers = filteredMetrics.at(-1)?.activeUsers ?? 0;
  const churn = filteredMetrics.at(-1)?.churn ?? 0;
  const chartSeries = filteredMetrics.map((row) => ({ x: row.date, y: row.revenue }));
  const tableRows = filteredMetrics;

  return (
    <main aria-label="SaaS metrics dashboard">
      <section data-testid="kpi-cards">
        <strong>Revenue ${revenue}</strong>
        <strong>Active users {activeUsers}</strong>
        <strong>Churn {churn}</strong>
      </section>
      <label>Date range filter {dateRange.from} to {dateRange.to}</label>
      <section data-testid="revenue-chart">{chartSeries.length} chart points</section>
      <table data-testid="report-table"><tbody>{tableRows.map((row) => <tr key={row.date}><td>{row.date}</td></tr>)}</tbody></table>
      <p>{emptyState}</p>
    </main>
  );
}
""",
        encoding="utf-8",
    )


def _write_game_source(root: Path) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "main.ts").write_text(
        """import { startGame } from './game';

startGame(document.querySelector<HTMLCanvasElement>('#game')!);
""",
        encoding="utf-8",
    )
    (root / "src" / "game.ts").write_text(
        """type GameState = { score: number; running: boolean; playerX: number; enemyX: number };

export function startGame(canvas: HTMLCanvasElement) {
  const context = canvas.getContext('2d');
  const state: GameState = { score: 0, running: true, playerX: 10, enemyX: 80 };

  function restart() {
    state.score = 0;
    state.running = true;
    state.playerX = 10;
    state.enemyX = 80;
  }

  function collision() {
    return Math.abs(state.playerX - state.enemyX) < 5;
  }

  window.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowRight') state.playerX += 5;
    if (event.key === 'r') restart();
  });

  function loop() {
    if (!context || !state.running) return;
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.fillRect(state.playerX, 20, 10, 10);
    context.fillText(`Score ${state.score}`, 10, 10);
    state.score += 1;
    if (collision()) state.running = false;
    requestAnimationFrame(loop);
  }

  loop();
  return { state, restart, collision };
}
""",
        encoding="utf-8",
    )


def _write_events_and_claims(root: Path, scenario: Scenario) -> None:
    stages = ["interview", "seed", "design", "scaffold", "build", "qa", "retro"]
    events: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    minute = 0
    complete_events = {
        "interview": "interview_complete",
        "seed": "seed_generated",
        "design": "blueprint_generated",
        "scaffold": "scaffold_complete",
        "build": "build_stage_complete",
        "qa": "qa_pass",
        "retro": "retro_complete",
    }
    for stage in stages:
        start_ts = f"2026-04-26T03:{minute:02d}:00Z"
        end_ts = f"2026-04-26T03:{minute + 1:02d}:00Z"
        events.append({"event_type": f"{stage}_started", "stage": stage, "timestamp": start_ts})
        events.append({"event_type": complete_events[stage], "stage": stage, "timestamp": end_ts})
        claims.append({
            "claim_id": f"{scenario.name}-{stage}-gate",
            "type": "gate_verdict",
            "subject": f"gate:{stage}_exit",
            "statement": f"verdict=pass for {stage}",
            "authority_file": "project.state.json",
            "evidence": [f"event:{complete_events[stage]}"],
            "claimed_by": "agent:phase5-dogfood",
            "status": "verified",
            "ts": end_ts,
            "meta": {"verdict": "pass", "event_type": complete_events[stage]},
        })
        minute += 2
    _write_jsonl(root / ".samvil" / "events.jsonl", events)
    _write_jsonl(root / ".samvil" / "claims.jsonl", claims)
    _write_jsonl(root / ".samvil" / "mcp-health.jsonl", [
        {"status": "ok", "tool": "match_domain_packs", "timestamp": "2026-04-26T03:00:00Z"},
        {"status": "ok", "tool": "render_domain_context", "timestamp": "2026-04-26T03:01:00Z"},
        {"status": "ok", "tool": "build_run_report", "timestamp": "2026-04-26T03:02:00Z"},
    ])


def _assert_contexts(root: Path, scenario: Scenario) -> dict[str, Any]:
    matches = match_domain_packs(scenario.seed)
    if not matches or matches[0]["pack_id"] != scenario.expected_pack:
        raise AssertionError(f"{scenario.name}: domain pack mismatch: {matches}")
    pack = get_domain_pack(scenario.expected_pack)
    if pack is None:
        raise AssertionError(f"{scenario.name}: missing expected pack")
    domain_context = render_domain_packs([pack], stage="qa")
    if "QA focus" not in domain_context:
        raise AssertionError(f"{scenario.name}: domain QA context missing")

    patterns = list_patterns(
        solution_type=scenario.seed["solution_type"],
        framework=scenario.framework,
    )
    if not patterns:
        raise AssertionError(f"{scenario.name}: no pattern context")
    pattern_context = render_patterns(patterns)
    if "# Pattern Registry" not in pattern_context:
        raise AssertionError(f"{scenario.name}: pattern context did not render")

    manifest = build_manifest(root, project_name=scenario.name)
    write_manifest(manifest, root)
    manifest_context = render_for_context(manifest)
    if "## Modules" not in manifest_context or not manifest.modules:
        raise AssertionError(f"{scenario.name}: manifest context missing modules")

    return {
        "domain_match": matches[0],
        "pattern_count": len(patterns),
        "manifest_modules": len(manifest.modules),
    }


def _assert_scenario_qa(root: Path, scenario: Scenario) -> list[str]:
    files = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((root / "src").rglob("*"))
        if path.is_file()
    )
    checks: list[tuple[str, bool]]
    if scenario.name == "saas-dashboard":
        checks = [
            ("kpi_cards", "kpi-cards" in files and "Revenue" in files),
            ("date_filter", "dateRange" in files and "filter" in files),
            ("empty_state", "No data" in files),
            ("chart_table_sync", "chartSeries" in files and "tableRows" in files and "filteredMetrics" in files),
        ]
    else:
        checks = [
            ("canvas_surface", "HTMLCanvasElement" in files and "getContext" in files),
            ("keyboard_input", "addEventListener('keydown'" in files),
            ("score_loop", "score" in files and "requestAnimationFrame" in files),
            ("collision_restart", "collision" in files and "restart" in files),
        ]
    failed = [name for name, passed in checks if not passed]
    if failed:
        raise AssertionError(f"{scenario.name}: QA checks failed: {failed}")
    return [name for name, _ in checks]


def _assert_telemetry(root: Path, scenario: Scenario) -> dict[str, Any]:
    report = build_run_report(root)
    write_run_report(report, root)
    if report["timeline"]["failure_count"] != 0:
        raise AssertionError(f"{scenario.name}: unexpected telemetry failures")
    if report["timeline"]["retry_count"] != 0:
        raise AssertionError(f"{scenario.name}: unexpected telemetry retries")
    if report["mcp_health"]["failures"] != 0:
        raise AssertionError(f"{scenario.name}: unexpected MCP health failures")
    statuses = {stage["stage"]: stage["status"] for stage in report["timeline"]["stages"]}
    for stage in ("interview", "seed", "design", "scaffold", "build", "qa", "retro"):
        if statuses.get(stage) != "complete":
            raise AssertionError(f"{scenario.name}: stage {stage} not complete: {statuses}")

    retro = derive_retro_observations(report)
    if retro:
        raise AssertionError(f"{scenario.name}: successful dogfood produced retro candidates: {retro}")

    status = _status_module()
    status_json = json.loads(status.render_json(root))
    if not status_json["run_report"]["present"]:
        raise AssertionError(f"{scenario.name}: status did not see run report")
    return {
        "events": report["events"]["total"],
        "stages": len(report["timeline"]["stages"]),
        "retro_candidates": len(retro),
        "status_stage": status_json["stage"],
    }


def run_scenario(base: Path, scenario: Scenario) -> dict[str, Any]:
    root = _project_root(base, scenario)
    if root.exists():
        shutil.rmtree(root)
    _materialize_project(root, scenario)
    context = _assert_contexts(root, scenario)
    qa_checks = _assert_scenario_qa(root, scenario)
    telemetry = _assert_telemetry(root, scenario)
    return {
        "name": scenario.name,
        "root": str(root),
        "domain_match": context["domain_match"],
        "pattern_count": context["pattern_count"],
        "manifest_modules": context["manifest_modules"],
        "qa_checks": qa_checks,
        "telemetry": telemetry,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--keep", action="store_true", help="keep generated temp projects")
    parser.add_argument("--json", action="store_true", help="print JSON summary")
    args = parser.parse_args()

    temp: tempfile.TemporaryDirectory[str] | None = None
    if args.keep:
        base = Path(tempfile.mkdtemp(prefix="samvil-phase5-"))
    else:
        temp = tempfile.TemporaryDirectory(prefix="samvil-phase5-")
        base = Path(temp.name)
    try:
        results = [run_scenario(base, scenario) for scenario in SCENARIOS]
        if args.json:
            print(json.dumps({"status": "ok", "base": str(base), "results": results}, indent=2))
        else:
            print("OK: phase5 dual dogfood passed")
            for result in results:
                match = result["domain_match"]
                telemetry = result["telemetry"]
                print(
                    f"{result['name']}: pack={match['pack_id']} "
                    f"confidence={match['confidence']} patterns={result['pattern_count']} "
                    f"modules={result['manifest_modules']} qa={len(result['qa_checks'])} "
                    f"events={telemetry['events']} retro={telemetry['retro_candidates']}"
                )
            print(f"base: {base}")
        return 0
    finally:
        if temp is not None:
            temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
