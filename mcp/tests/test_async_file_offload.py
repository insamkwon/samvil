"""Large mechanical artifacts must not stall the MCP event loop."""

from __future__ import annotations

import asyncio
import json
import time

from samvil_mcp import server


async def _ticker_delay(awaitable) -> float:
    started = asyncio.get_running_loop().time()

    async def ticker() -> float:
        await asyncio.sleep(0.01)
        return asyncio.get_running_loop().time() - started

    _, delay = await asyncio.gather(awaitable, ticker())
    return delay


def test_mechanical_gate_collection_is_offloaded(monkeypatch) -> None:
    def slow_collect(project_root: str, gate_name: str):
        time.sleep(0.2)
        return ({"build_ok": True}, {"build_ok": True}, {})

    monkeypatch.setattr(server, "_mechanical_gate_evidence", slow_collect)
    delay = asyncio.run(
        _ticker_delay(
            server.gate_check(
                gate_name="build_to_qa",
                samvil_tier="standard",
                metrics_json=json.dumps({"implementation_rate": 1.0}),
                evidence_mode="mechanical",
            )
        )
    )
    assert delay < 0.1


def test_stage_evidence_collection_is_offloaded(monkeypatch) -> None:
    from samvil_mcp import stage_evidence

    def slow_collect(project_root: str, stage: str):
        time.sleep(0.2)
        return {stage: {}, "evidence_files": [], "missing": []}

    monkeypatch.setattr(stage_evidence, "collect_stage_evidence", slow_collect)
    delay = asyncio.run(
        _ticker_delay(server.collect_stage_evidence(".", "qa"))
    )
    assert delay < 0.1


def test_chain_marker_write_is_offloaded(monkeypatch) -> None:
    def slow_write(*args, **kwargs):
        time.sleep(0.2)
        return {"next_skill": "samvil-design"}

    monkeypatch.setattr(server, "_write_chain_marker", slow_write)
    delay = asyncio.run(
        _ticker_delay(
            server.write_chain_marker(
                ".",
                "codex_cli",
                "samvil-seed",
                next_skill="samvil-design",
            )
        )
    )
    assert delay < 0.1


def test_finalize_qa_verdict_file_work_is_offloaded(monkeypatch) -> None:
    def slow_finalize(*args, **kwargs):
        time.sleep(0.2)
        return {"next_skill_decision": {"suggested": "samvil-retro"}}

    monkeypatch.setattr(server, "_finalize_qa_verdict", slow_finalize)
    delay = asyncio.run(
        _ticker_delay(
            server.finalize_qa_verdict(
                project_path=".",
                evidence_json="{}",
                pending_ac_claims_json="[]",
            )
        )
    )
    assert delay < 0.1


def test_seed_v3_3_migration_is_offloaded(monkeypatch) -> None:
    from samvil_mcp import migrate_v3_3

    def slow_apply(project_root: str):
        time.sleep(0.2)
        return {"status": "ok"}

    monkeypatch.setattr(migrate_v3_3, "apply_migration", slow_apply)
    delay = asyncio.run(_ticker_delay(server.migrate_seed_v3_3(".")))
    assert delay < 0.1
