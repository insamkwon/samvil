#!/usr/bin/env python3
"""MCP stdio round-trip test — empirically verify the contract-layer path.

Why this exists: our Sprint 6 dogfood showed that MCP calls happen
(mcp-health.jsonl has save_event entries) but claims.jsonl stayed
empty. The fix was to instrument save_event to auto-post claims. This
script proves the path works **through the actual stdio transport**,
not just via in-process asyncio — closing the gap between "local smoke
test" and "real Claude Code invocation".

What it does:
  1. Spawns samvil-mcp as a subprocess (same command Claude uses).
  2. Sends JSON-RPC 2.0 messages over stdin.
  3. Calls `create_session` + several `save_event` invocations.
  4. Verifies that `.samvil/claims.jsonl` was populated in the project
     directory.

Usage:
  python3 scripts/test-mcp-stdio-roundtrip.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
MCP_DIR = REPO / "mcp"
PYTHON = MCP_DIR / ".venv" / "bin" / "python"


def send(proc: subprocess.Popen, msg: dict) -> None:
    line = json.dumps(msg) + "\n"
    proc.stdin.write(line.encode())
    proc.stdin.flush()


def recv(proc: subprocess.Popen, timeout: float = 5.0) -> dict | None:
    """Read one line of JSON-RPC from the child. Blocks up to timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.05)
            continue
        try:
            return json.loads(line.decode().strip())
        except json.JSONDecodeError:
            continue
    return None


def call_tool(proc: subprocess.Popen, req_id: int, tool: str, args: dict) -> dict | None:
    send(proc, {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "tools/call",
        "params": {"name": tool, "arguments": args},
    })
    resp = recv(proc)
    return resp


def main() -> int:
    # 1. Prepare a throwaway project dir at ~/dev/<name>. The MCP server
    #    resolves project_path via `~/dev/<project_name>` convention —
    #    same logic the contract-layer auto-claim uses.
    project_name = "samvil-mcp-roundtrip-check"
    project_path = Path.home() / "dev" / project_name
    if project_path.exists():
        shutil.rmtree(project_path)
    project_path.mkdir(parents=True)
    (project_path / "project.state.json").write_text('{"samvil_tier":"standard"}')

    # 2. Spawn samvil-mcp as a subprocess via stdio.
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [str(PYTHON), "-m", "samvil_mcp.server"],
        cwd=str(MCP_DIR),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    try:
        # 3. JSON-RPC handshake. MCP protocol expects initialize first.
        send(proc, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "samvil-roundtrip-test", "version": "1.0"},
            },
        })
        init_resp = recv(proc, timeout=10.0)
        if init_resp is None or "error" in (init_resp or {}):
            print(f"  ✗ initialize failed: {init_resp}")
            return 1
        print("  ✓ initialize OK")

        # Send the initialized notification (required by MCP spec).
        send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})

        # 4. Call create_session.
        resp = call_tool(proc, 2, "create_session", {
            "project_name": project_name,
            "samvil_tier": "standard",
        })
        if resp is None or "error" in (resp or {}):
            print(f"  ✗ create_session failed: {resp}")
            return 1
        # The result is wrapped: {"result": {"content": [{"text": "..."}]}}
        content = resp.get("result", {}).get("content", [])
        if not content:
            print(f"  ✗ create_session: empty content: {resp}")
            return 1
        payload = json.loads(content[0].get("text", "{}"))
        session_id = payload.get("session_id")
        if not session_id:
            print(f"  ✗ create_session: no session_id: {payload}")
            return 1
        print(f"  ✓ create_session → session_id={session_id}")

        # 5. Simulate a pipeline run via save_event calls.
        events = [
            ("interview_start", "interview"),
            ("interview_complete", "interview"),
            ("seed_generated", "seed"),
            ("scaffold_complete", "scaffold"),
            ("build_feature_start", "build"),
            ("build_stage_complete", "build"),
            ("qa_verdict", "qa"),
            ("retro_complete", "retro"),
        ]
        for i, (et, st) in enumerate(events, start=10):
            resp = call_tool(proc, i, "save_event", {
                "session_id": session_id,
                "event_type": et,
                "stage": st,
                "data": "{}",
            })
            if resp is None:
                print(f"  ✗ save_event({et}) no response")
                return 1
            if "error" in resp:
                print(f"  ✗ save_event({et}) error: {resp['error']}")
                return 1
        print(f"  ✓ {len(events)} save_event calls succeeded")

        # 6. Verify that claims.jsonl was created and populated.
        claims_path = project_path / ".samvil" / "claims.jsonl"
        if not claims_path.exists():
            print(f"  ✗ {claims_path} NOT created — auto-claim path broken")
            return 1
        lines = [
            l for l in claims_path.read_text().splitlines() if l.strip()
        ]
        print(f"  ✓ claims.jsonl created; {len(lines)} rows")

        # 7. Print the ledger summary.
        by_type: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for ln in lines:
            try:
                c = json.loads(ln)
            except Exception:
                continue
            by_type[c.get("type", "?")] = by_type.get(c.get("type", "?"), 0) + 1
            by_status[c.get("status", "?")] = by_status.get(c.get("status", "?"), 0) + 1
        print(f"    by_type:   {by_type}")
        print(f"    by_status: {by_status}")

        # 8. Expectations — we should see multiple evidence_posted and
        #    gate_verdict claims; pending + verified mixed.
        ok = (
            by_type.get("evidence_posted", 0) >= 1
            and by_type.get("gate_verdict", 0) >= 1
            and by_status.get("verified", 0) >= 1
        )
        if not ok:
            print("  ✗ ledger shape unexpected — auto-claim mapping may be incomplete")
            return 1
        print("  ✓ ledger shape OK (evidence_posted + gate_verdict + verified all present)")

    finally:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
        # Tidy up.
        if project_path.exists():
            shutil.rmtree(project_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
