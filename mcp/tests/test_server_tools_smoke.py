"""v3.1.0 Polish #7 — runtime smoke tests for v3.1.0 MCP tools.

These go through the async tool functions directly (as opposed to unit tests
against helper modules) so we catch wiring regressions between `server.py`
and the underlying modules — the kind of bug that unit tests pass but the
real MCP round-trip fails.
"""
from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from samvil_mcp.server import (
    build_reawake_message,
    build_qa_recovery_routing,
    build_rebuild_reentry,
    build_post_rebuild_qa,
    build_final_e2e_bundle,
    evaluate_qa_convergence,
    get_tier_phases,
    heartbeat_state,
    increment_stall_recovery_count,
    is_state_stalled,
    materialize_qa_synthesis,
    materialize_qa_recovery_routing,
    materialize_evolve_context,
    materialize_evolve_proposal,
    materialize_evolve_apply_plan,
    apply_evolve_apply_plan,
    materialize_evolve_rebuild_handoff,
    materialize_rebuild_reentry,
    materialize_post_rebuild_qa,
    materialize_final_e2e_bundle,
    suggest_ac_split,
    synthesize_qa_evidence,
    get_stage_envelope,
    begin_stage,
    commit_stage_transition,
    gate_check,
)
from samvil_mcp.event_store import EventStore


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def _write_mechanical_command(project: Path, field: str, argv: list[str]) -> None:
    samvil_root = project / ".samvil"
    samvil_root.mkdir(parents=True, exist_ok=True)
    command = shlex.join(argv)
    (samvil_root / "mechanical.toml").write_text(
        f"{field} = {json.dumps(command)}\n",
        encoding="utf-8",
    )


def _write_passing_build_seed(project: Path) -> None:
    (project / "project.seed.json").write_text(
        json.dumps(
            {
                "features": [
                    {
                        "name": "verified feature",
                        "acceptance_criteria": [
                            {"id": "AC-1", "status": "pass"}
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_get_store_does_not_cache_an_instance_whose_initialize_was_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.server as server

    original_initialize = EventStore.initialize
    calls = 0

    async def cancel_once(store):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise asyncio.CancelledError()
        await original_initialize(store)

    monkeypatch.setattr(server, "_store", None)
    monkeypatch.setattr(server, "DB_PATH", tmp_path / "store.db")
    monkeypatch.setattr(EventStore, "initialize", cancel_once)

    with pytest.raises(asyncio.CancelledError):
        _run(server.get_store())

    assert server._store is None
    recovered = _run(server.get_store())
    assert recovered is server._store
    assert calls == 2


def test_verification_command_does_not_use_unbounded_capture_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.server as server
    import tempfile

    monkeypatch.setattr(
        server.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("unbounded capture_output is forbidden")
        ),
    )
    monkeypatch.setattr(
        tempfile,
        "TemporaryFile",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("unbounded temporary capture is forbidden")
        ),
    )

    exit_code, output = server._run_verification_command(
        tmp_path,
        [sys.executable, "-c", "print('bounded output')"],
        5,
    )

    assert exit_code == 0
    assert "bounded output" in output
    assert len(output.encode("utf-8")) <= 2_000_000

    exit_code, output = server._run_verification_command(
        tmp_path,
        [sys.executable, "-c", "import os; os.write(1, b'\\xff' * 4_000_000)"],
        5,
    )

    assert exit_code == 0
    assert len(output.encode("utf-8")) <= 2_000_000


def test_verification_command_fails_closed_without_process_containment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.server as server

    monkeypatch.setattr(server.os, "name", "nt")

    with pytest.raises(RuntimeError, match="requires a POSIX host"):
        server._run_verification_command(
            tmp_path, [sys.executable, "-c", "print('must not launch')"], 5
        )


@pytest.mark.skipif(os.name != "posix", reason="process identity is POSIX-only")
def test_verification_process_identity_rejects_pid_reuse() -> None:
    import samvil_mcp.server as server

    identity = server._process_identity(os.getpid())

    assert identity is not None
    assert server._live_tracked_pids({os.getpid(): identity}) == {os.getpid()}
    assert server._live_tracked_pids({os.getpid(): f"{identity}:reused"}) == set()


def test_verification_tracker_prunes_reused_pid_before_following_children(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import samvil_mcp.server as server

    identities = {100: "leader", 200: "new-owner", 300: "unrelated-child"}
    descendants = {100: set(), 200: {300}, 300: set()}
    monkeypatch.setattr(
        server, "_process_identity", lambda pid: identities.get(pid)
    )
    monkeypatch.setattr(
        server, "_descendant_pids", lambda pid: descendants.get(pid, set())
    )
    tracked = {200: "old-owner"}

    server._refresh_tracked_descendants(100, "leader", tracked)

    assert tracked == {}


@pytest.mark.skipif(os.name != "posix", reason="process-group semantics are POSIX-only")
def test_verification_timeout_kills_spawned_process_group(tmp_path: Path) -> None:
    import samvil_mcp.server as server

    pid_path = tmp_path / "grandchild.pid"
    script = (
        "import pathlib, subprocess, sys, time; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'], "
        "start_new_session=True); "
        f"pathlib.Path({str(pid_path)!r}).write_text(str(child.pid)); "
        "time.sleep(30)"
    )
    grandchild_pid = 0
    try:
        started_at = time.monotonic()
        exit_code, output = server._run_verification_command(
            tmp_path, [sys.executable, "-c", script], 1
        )
        elapsed = time.monotonic() - started_at
        assert exit_code == 124
        assert "verification timed out" in output
        assert elapsed < 4
        grandchild_pid = int(pid_path.read_text(encoding="utf-8"))
        for _ in range(20):
            try:
                os.kill(grandchild_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            pytest.fail("verification grandchild survived timeout")
    finally:
        if grandchild_pid:
            try:
                os.kill(grandchild_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.skipif(os.name != "posix", reason="process tracking is POSIX-only")
def test_verification_timeout_kills_reparented_double_fork(tmp_path: Path) -> None:
    import samvil_mcp.server as server

    pid_path = tmp_path / "double-fork-grandchild.pid"
    grandchild_script = "import time; time.sleep(30)"
    child_script = (
        "import pathlib, subprocess, sys; "
        f"grandchild=subprocess.Popen([sys.executable,'-c',{grandchild_script!r}], "
        "start_new_session=True); "
        f"pathlib.Path({str(pid_path)!r}).write_text(str(grandchild.pid))"
    )
    parent_script = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable,'-c',{child_script!r}], "
        "start_new_session=True); "
        "time.sleep(30)"
    )
    grandchild_pid = 0
    try:
        exit_code, output = server._run_verification_command(
            tmp_path, [sys.executable, "-c", parent_script], 1
        )

        assert exit_code == 124
        assert "verification timed out" in output
        grandchild_pid = int(pid_path.read_text(encoding="utf-8"))
        for _ in range(20):
            try:
                os.kill(grandchild_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            pytest.fail("reparented verification grandchild survived timeout")
    finally:
        if grandchild_pid:
            try:
                os.kill(grandchild_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.skipif(sys.platform != "darwin", reason="native macOS containment fixture")
def test_verification_sentinel_tracks_fast_native_detached_double_fork(
    tmp_path: Path,
) -> None:
    import samvil_mcp.server as server

    compiler = shutil.which("cc")
    if not compiler:
        pytest.skip("C compiler is unavailable")
    source = tmp_path / "fast-detach.c"
    binary = tmp_path / "fast-detach"
    pid_path = tmp_path / "fast-detach.pid"
    source.write_text(
        """
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/types.h>
#include <unistd.h>

int main(int argc, char **argv) {
    pid_t child = fork();
    if (child < 0) return 2;
    if (child > 0) return 0;
    if (setsid() < 0) _exit(3);
    pid_t grandchild = fork();
    if (grandchild < 0) _exit(4);
    if (grandchild > 0) _exit(0);
    int fd = open(argv[1], O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd >= 0) {
        dprintf(fd, "%d", getpid());
        close(fd);
    }
    sleep(30);
    return 0;
}
""",
        encoding="utf-8",
    )
    subprocess.run(
        [compiler, str(source), "-o", str(binary)],
        check=True,
        capture_output=True,
        text=True,
    )
    grandchild_pid = 0
    try:
        exit_code, _ = server._run_verification_command(
            tmp_path, [str(binary), str(pid_path)], 2
        )

        assert exit_code == 0
        grandchild_pid = int(pid_path.read_text(encoding="utf-8"))
        for _ in range(40):
            try:
                os.kill(grandchild_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            pytest.fail("fast detached native grandchild survived verification")
    finally:
        if grandchild_pid:
            try:
                os.kill(grandchild_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.skipif(os.name != "posix", reason="process-group semantics are POSIX-only")
def test_verification_does_not_wait_for_stdout_inheriting_child(tmp_path: Path) -> None:
    import samvil_mcp.server as server

    pid_path = tmp_path / "inheriting-child.pid"
    script = (
        "import pathlib, subprocess, sys; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'], "
        "start_new_session=True); "
        f"pathlib.Path({str(pid_path)!r}).write_text(str(child.pid)); "
        "print('parent complete')"
    )
    child_pid = 0
    try:
        started_at = time.monotonic()
        exit_code, output = server._run_verification_command(
            tmp_path, [sys.executable, "-c", script], 2
        )
        elapsed = time.monotonic() - started_at

        assert exit_code == 0
        assert "parent complete" in output
        assert elapsed < 4
        child_pid = int(pid_path.read_text(encoding="utf-8"))
        for _ in range(20):
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            pytest.fail("stdout-inheriting verification child survived parent exit")
    finally:
        if child_pid:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.skipif(os.name != "posix", reason="process-group semantics are POSIX-only")
def test_verification_reaps_fast_leader_after_background_group_cleanup(
    tmp_path: Path,
) -> None:
    import samvil_mcp.server as server

    pid_path = tmp_path / "fast-background-child.pid"
    command = [
        "/bin/sh",
        "-c",
        f"sleep 30 & child=$!; echo $child > {shlex.quote(str(pid_path))}",
    ]
    child_pid = 0
    try:
        exit_code, _ = server._run_verification_command(tmp_path, command, 2)

        assert exit_code == 0
        child_pid = int(pid_path.read_text(encoding="utf-8"))
        for _ in range(20):
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            pytest.fail("same-group background child survived leader exit")
    finally:
        if child_pid:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_codex_transition_tools_are_thin_and_fail_closed(tmp_path: Path) -> None:
    envelope = json.loads(_run(get_stage_envelope(str(tmp_path), "codex_cli")))
    assert envelope["status"] == "fresh"
    invalid = json.loads(_run(begin_stage(str(tmp_path), "run", "samvil-interview", True)))
    assert invalid["status"] == "blocked"
    malformed = json.loads(_run(commit_stage_transition(
        str(tmp_path), "run", "samvil-interview", 0, "claim", "PASS", "[]"
    )))
    assert malformed["status"] == "blocked"


def test_commit_stage_transition_wrapper_retries_with_same_transition_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.server as server

    project = tmp_path / "wrapper-idempotency"
    project.mkdir()
    store = EventStore(str(tmp_path / "events.db"))
    _run(store.initialize())
    session = _run(store.create_session("display-name", "minimal", str(project)))
    monkeypatch.setattr(server, "_store", store)
    (project / "interview-summary.md").write_text("verified interview\n", encoding="utf-8")

    claim = json.loads(_run(begin_stage(str(project), session.id, "samvil-interview", 0)))
    empty = json.loads(_run(commit_stage_transition(
        str(project), session.id, "samvil-interview", 0,
        claim["claim_id"], "PASS", "{}", "", "wrapper-empty-evidence",
    )))
    assert empty["status"] == "blocked"
    first = json.loads(_run(commit_stage_transition(
        str(project), session.id, "samvil-interview", 0,
        claim["claim_id"], "PASS", '{"artifact":"interview-summary.md:1"}', "", "wrapper-transition-1",
    )))
    second = json.loads(_run(commit_stage_transition(
        str(project), session.id, "samvil-interview", 0,
        claim["claim_id"], "PASS", '{"artifact":"interview-summary.md:1"}', "", "wrapper-transition-1",
    )))

    assert first["status"] == "committed"
    assert second == first


def test_wrapper_recovery_accepts_envelope_route_after_default_route_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.server as server

    project = tmp_path / "wrapper-default-route-recovery"
    project.mkdir()
    (project / "interview-summary.md").write_text("verified interview\n", encoding="utf-8")
    store = EventStore(str(tmp_path / "default-route-recovery.db"))
    _run(store.initialize())
    session = _run(store.create_session("display-name", "minimal", str(project)))
    monkeypatch.setattr(server, "_store", store)
    claim = json.loads(_run(begin_stage(str(project), session.id, "samvil-interview", 0)))
    original_complete = store.mark_stage_claim_completed
    failed = False

    async def fail_once(claim_id, transition_id):
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("after receipt saved")
        return await original_complete(claim_id, transition_id)

    monkeypatch.setattr(store, "mark_stage_claim_completed", fail_once)
    first = json.loads(_run(commit_stage_transition(
        str(project), session.id, "samvil-interview", 0, claim["claim_id"], "PASS",
        '{"artifact":"interview-summary.md:1"}', "", "default-route-recovery-id",
    )))
    envelope = json.loads(_run(get_stage_envelope(str(project), "codex_cli")))
    retry = json.loads(_run(commit_stage_transition(
        str(project), session.id, envelope["stage"], envelope["marker_revision"],
        envelope["claim_id"], envelope["verdict"], json.dumps(envelope["evidence"]),
        envelope["requested_next_skill"], envelope["transition_id"],
    )))

    assert first["status"] == "blocked"
    assert envelope["requested_next_skill"] == "samvil-seed"
    assert retry["status"] == "committed"


def test_wrapper_recovery_finishes_legacy_transition_without_fresh_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.server as server
    from samvil_mcp.transition_controller import TransitionController

    project = tmp_path / "legacy-wrapper-recovery"
    project.mkdir()
    store = EventStore(str(tmp_path / "legacy-wrapper-recovery.db"))
    _run(store.initialize())
    session = _run(store.create_session("display-name", "minimal", str(project)))
    monkeypatch.setattr(server, "_store", store)
    claim = json.loads(_run(begin_stage(str(project), session.id, "samvil-interview", 0)))
    controller = TransitionController(store)
    original_append = server._append_project_event
    failed = False

    def fail_once(*args, **kwargs):
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("stop after DB commit")
        return original_append(*args, **kwargs)

    monkeypatch.setattr(server, "_append_project_event", fail_once)
    with pytest.raises(OSError, match="stop after DB commit"):
        _run(controller.commit_stage_transition(
            str(project),
            session.id,
            claim["claim_id"],
            "samvil-interview",
            "samvil-seed",
            0,
            data={"verdict": "pass", "stage": "interview", "trusted_transition": True},
            transition_id="legacy-wrapper-recovery-id",
        ))

    envelope = json.loads(_run(get_stage_envelope(str(project), "codex_cli")))
    recovered = json.loads(_run(commit_stage_transition(
        str(project),
        envelope["run_id"],
        envelope["stage"],
        envelope["marker_revision"],
        envelope["claim_id"],
        envelope["verdict"],
        json.dumps(envelope["evidence"]),
        envelope["requested_next_skill"],
        envelope["transition_id"],
    )))

    assert recovered["status"] == "committed"
    assert recovered["transition_id"] == "legacy-wrapper-recovery-id"


def test_wrapper_replay_rejects_explicit_nondefault_route_changed_to_blank(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.server as server
    from samvil_mcp.models import Stage

    project = tmp_path / "wrapper-explicit-route-conflict"
    project.mkdir()
    (project / "project.seed.json").write_text('{"schema_version":"3.3"}\n', encoding="utf-8")
    store = EventStore(str(tmp_path / "explicit-route-conflict.db"))
    _run(store.initialize())
    session = _run(store.create_session("display-name", "standard", str(project)))
    _run(store.update_session_stage(session.id, Stage.SEED))
    monkeypatch.setattr(server, "_store", store)
    claim = json.loads(_run(begin_stage(str(project), session.id, "samvil-seed", 0)))

    first = json.loads(_run(commit_stage_transition(
        str(project), session.id, "samvil-seed", 0, claim["claim_id"], "PASS",
        '{"artifact":"project.seed.json:1"}', "samvil-council", "explicit-route-id",
    )))
    changed = json.loads(_run(commit_stage_transition(
        str(project), session.id, "samvil-seed", 0, claim["claim_id"], "PASS",
        '{"artifact":"project.seed.json:1"}', "", "explicit-route-id",
    )))

    assert first["to_stage"] == "samvil-council"
    assert changed["status"] == "blocked"
    assert "different route" in changed["error"]


def test_commit_stage_transition_wrapper_rejects_failed_verdict_and_sanitizes_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.server as server

    project = tmp_path / "wrapper-authority"
    project.mkdir()
    store = EventStore(str(tmp_path / "authority.db"))
    _run(store.initialize())
    session = _run(store.create_session("display-name", "minimal", str(project)))
    monkeypatch.setattr(server, "_store", store)
    (project / "interview-summary.md").write_text("verified interview\n", encoding="utf-8")
    claim = json.loads(_run(begin_stage(str(project), session.id, "samvil-interview", 0)))

    rejected = json.loads(_run(commit_stage_transition(
        str(project), session.id, "samvil-interview", 0,
        claim["claim_id"], "FAIL", "{}", "samvil-seed", "failed-transition",
    )))

    assert rejected["status"] == "ready"
    assert rejected["next_skill"] == "samvil-interview"
    assert _run(store.get_events(session.id)) == []

    secret = "ghp" + "_fixture_secret"
    committed = json.loads(_run(commit_stage_transition(
        str(project), session.id, "samvil-interview", 0,
        claim["claim_id"], "PASS",
        json.dumps({
            "artifact": "interview-summary.md:1",
            "contact": "person@example.com",
            "token": secret,
        }),
        "samvil-seed", "sanitized-transition",
    )))
    assert committed["status"] == "committed"
    serialized = str(_run(store.get_events(session.id))[0].data)
    assert "person@example.com" not in serialized
    assert secret not in serialized


def test_commit_stage_transition_rejects_evidence_outside_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.server as server

    project = tmp_path / "contained-evidence"
    project.mkdir()
    (tmp_path / "interview-summary.md").write_text("outside\n", encoding="utf-8")
    store = EventStore(str(tmp_path / "contained.db"))
    _run(store.initialize())
    session = _run(store.create_session("display-name", "minimal", str(project)))
    monkeypatch.setattr(server, "_store", store)
    claim = json.loads(_run(begin_stage(str(project), session.id, "samvil-interview", 0)))

    result = json.loads(_run(commit_stage_transition(
        str(project), session.id, "samvil-interview", 0,
        claim["claim_id"], "PASS", '{"artifact":"../interview-summary.md:1"}',
        "", "outside-evidence-transition",
    )))

    assert result["status"] == "blocked"
    assert result["evidence_validation"]["all_valid"] is False


def test_terminal_transition_wrapper_retry_returns_identical_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.server as server
    from samvil_mcp.models import Stage

    project = tmp_path / "terminal-wrapper"
    (project / ".samvil").mkdir(parents=True)
    (project / ".samvil" / "retro-results.md").write_text("complete\n", encoding="utf-8")
    store = EventStore(str(tmp_path / "terminal.db"))
    _run(store.initialize())
    session = _run(store.create_session("display-name", "minimal", str(project)))
    _run(store.update_session_stage(session.id, Stage.RETRO))
    monkeypatch.setattr(server, "_store", store)
    claim = json.loads(_run(begin_stage(str(project), session.id, "samvil-retro", 0)))
    args = (
        str(project), session.id, "samvil-retro", 0, claim["claim_id"],
        "PASS", '{"artifact":".samvil/retro-results.md:1"}', "", "terminal-wrapper-id",
    )

    first = json.loads(_run(commit_stage_transition(*args)))
    second = json.loads(_run(commit_stage_transition(*args)))
    other_project = tmp_path / "other-terminal-wrapper"
    (other_project / ".samvil").mkdir(parents=True)
    (other_project / ".samvil" / "retro-results.md").write_text("complete\n", encoding="utf-8")
    cross_project = json.loads(_run(commit_stage_transition(
        str(other_project), *args[1:]
    )))

    assert first["status"] == "committed"
    assert second == first
    assert cross_project["status"] == "blocked"
    assert "project root" in cross_project["error"]


def test_qa_recovery_transition_requires_current_pass_gate_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.server as server
    from samvil_mcp.models import Stage

    project = tmp_path / "qa-recovery-receipt"
    (project / ".samvil").mkdir(parents=True)
    (project / ".samvil" / "qa-results.json").write_text(
        json.dumps({"synthesis": {"verdict": "FAIL"}, "convergence": {"verdict": "blocked"}}),
        encoding="utf-8",
    )
    store = EventStore(str(tmp_path / "qa-recovery.db"))
    _run(store.initialize())
    session = _run(store.create_session("display-name", "minimal", str(project)))
    _run(store.update_session_stage(session.id, Stage.QA))
    monkeypatch.setattr(server, "_store", store)
    claim = json.loads(_run(begin_stage(str(project), session.id, "samvil-qa", 0)))
    import hashlib
    qa_hash = hashlib.sha256((project / ".samvil" / "qa-results.json").read_bytes()).hexdigest()
    fake_receipt = project / ".samvil" / "gate-receipts" / "any_to_retro.json"
    fake_receipt.parent.mkdir(parents=True)
    fake_receipt.write_text(
        json.dumps({
            "kind": "gate_receipt",
            "gate": "any_to_retro",
            "verdict": "pass",
            "qa_results_sha256": qa_hash,
        }),
        encoding="utf-8",
    )
    args = (
        str(project), session.id, "samvil-qa", 0, claim["claim_id"], "FAIL",
        '{"artifact":".samvil/qa-results.json:1"}', "samvil-retro", "qa-recovery-transition",
    )

    blocked = json.loads(_run(commit_stage_transition(*args)))
    gate = json.loads(_run(gate_check(
        "any_to_retro", "minimal", '{"always_run":true}', str(project)
    )))
    (project / ".samvil" / "qa-results.json").write_text(
        json.dumps({
            "synthesis": {"verdict": "FAIL"},
            "convergence": {"verdict": "blocked"},
            "rerun": 2,
        }),
        encoding="utf-8",
    )
    latest_gate = json.loads(_run(gate_check(
        "any_to_retro", "minimal", '{"always_run":true}', str(project)
    )))
    committed = json.loads(_run(commit_stage_transition(*args)))

    assert blocked["status"] == "blocked"
    assert gate["verdict"] == "pass"
    assert latest_gate["verdict"] == "pass"
    assert committed["status"] == "committed"


def test_build_transition_requires_mechanical_gate_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.server as server
    from samvil_mcp.models import Stage

    project = tmp_path / "build-gate-required"
    (project / ".samvil").mkdir(parents=True)
    (project / ".samvil" / "build.log").write_text("stub\n", encoding="utf-8")
    store = EventStore(str(tmp_path / "build-gate.db"))
    _run(store.initialize())
    session = _run(store.create_session("display-name", "minimal", str(project)))
    _run(store.update_session_stage(session.id, Stage.BUILD))
    monkeypatch.setattr(server, "_store", store)
    claim = json.loads(_run(begin_stage(str(project), session.id, "samvil-build", 0)))

    gate = json.loads(_run(gate_check(
        "build_to_qa", "minimal", '{"implementation_rate":1.0}', str(project)
    )))
    result = json.loads(_run(commit_stage_transition(
        str(project), session.id, "samvil-build", 0, claim["claim_id"], "PASS",
        '{"artifact":".samvil/build.log:1"}', "", "build-without-proof",
    )))

    assert gate["verdict"] == "block"
    assert result["status"] == "blocked"
    assert "trusted gate receipt for build_to_qa" in result["reason"]


def test_build_transition_uses_run_bound_trusted_receipts_after_event_growth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.server as server
    from samvil_mcp.models import EventType, Stage

    project = tmp_path / "run-bound-build"
    command = [sys.executable, "-c", "print('verified build')"]
    _write_mechanical_command(project, "build", command)
    _write_passing_build_seed(project)
    store = EventStore(str(tmp_path / "run-bound.db"))
    _run(store.initialize())
    active = _run(store.create_session("active-display", "minimal", str(project)))
    _run(store.update_session_stage(active.id, Stage.BUILD))
    monkeypatch.setattr(server, "_store", store)
    claim = json.loads(_run(begin_stage(str(project), active.id, "samvil-build", 0)))
    _run(store.create_session("newer-display", "minimal", str(project)))

    runner = getattr(server, "run_stage_verification", None)
    assert callable(runner), "trusted runtime verification tool is required"
    runtime = json.loads(_run(runner(
        str(project),
        active.id,
        "samvil-build",
        json.dumps(command),
    )))
    evidence = json.loads(_run(server.collect_stage_evidence(str(project), "build")))
    gate = json.loads(_run(gate_check(
        "build_to_qa", "minimal", '{"implementation_rate":1.0}', str(project)
    )))
    for index in range(51):
        _run(store.save_event(
            active.id,
            EventType.DECISION,
            Stage.BUILD,
            {"kind": "unrelated", "index": index},
        ))
    result = json.loads(_run(commit_stage_transition(
        str(project), active.id, "samvil-build", 0, claim["claim_id"], "PASS",
        '{"artifact":".samvil/build.log:1"}', "", "run-bound-build-transition",
    )))

    assert runtime["status"] == "passed"
    assert runtime["trusted_by"] == "samvil_mcp_subprocess"
    assert evidence["build"]["runtime_verified"] is True
    assert gate["verdict"] == "pass"
    assert _run(store.get_gate_receipt(active.id, "build_to_qa"))["verdict"] == "pass"
    assert _run(store.get_gate_receipt(active.id, "build_to_qa"))["session_id"] == active.id
    assert result["status"] == "committed"


def test_runtime_receipt_projection_failure_does_not_leave_trusted_db_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.server as server
    from samvil_mcp.models import Stage

    project = tmp_path / "runtime-receipt-projection-failure"
    receipt_root = project / ".samvil" / "runtime-receipts"
    receipt_root.mkdir(parents=True)
    (receipt_root / "build.json").mkdir()
    command = [sys.executable, "-c", "print('verified build')"]
    _write_mechanical_command(project, "build", command)
    _write_passing_build_seed(project)
    store = EventStore(str(tmp_path / "runtime-receipt-projection-failure.db"))
    _run(store.initialize())
    session = _run(store.create_session("projection-failure", "minimal", str(project)))
    _run(store.update_session_stage(session.id, Stage.BUILD))
    monkeypatch.setattr(server, "_store", store)
    _run(begin_stage(str(project), session.id, "samvil-build", 0))

    runtime = json.loads(
        _run(
            server.run_stage_verification(
                str(project),
                session.id,
                "samvil-build",
                json.dumps(command),
            )
        )
    )
    gate = json.loads(
        _run(
            gate_check(
                "build_to_qa",
                "minimal",
                '{"implementation_rate":1.0}',
                str(project),
            )
        )
    )

    assert runtime["status"] == "blocked"
    assert _run(store.get_runtime_receipt(session.id, "samvil-build")) is None
    assert gate["verdict"] == "block"


def test_runtime_verification_rejects_command_outside_mechanical_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.server as server
    from samvil_mcp.models import Stage

    project = tmp_path / "command-contract"
    expected = [sys.executable, "-c", "print('contract build')"]
    _write_mechanical_command(project, "build", expected)
    _write_passing_build_seed(project)
    store = EventStore(str(tmp_path / "command-contract.db"))
    _run(store.initialize())
    session = _run(store.create_session("command-contract", "minimal", str(project)))
    _run(store.update_session_stage(session.id, Stage.BUILD))
    monkeypatch.setattr(server, "_store", store)
    _run(begin_stage(str(project), session.id, "samvil-build", 0))

    runtime = json.loads(
        _run(
            server.run_stage_verification(
                str(project),
                session.id,
                "samvil-build",
                json.dumps(["/usr/bin/true"]),
            )
        )
    )

    assert runtime["status"] == "blocked"
    assert "mechanical contract" in runtime["error"]
    assert not (project / ".samvil" / "build.log").exists()


def test_build_gate_uses_seed_implementation_rate_not_reported_metric(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.server as server
    from samvil_mcp.models import Stage

    project = tmp_path / "mechanical-build-rate"
    command = [sys.executable, "-c", "print('real build ran')"]
    _write_mechanical_command(project, "build", command)
    (project / "project.seed.json").write_text(
        json.dumps(
            {
                "features": [
                    {
                        "name": "unfinished feature",
                        "acceptance_criteria": [
                            {"id": "AC-1", "status": "pending"}
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    store = EventStore(str(tmp_path / "mechanical-build-rate.db"))
    _run(store.initialize())
    session = _run(store.create_session("mechanical-build-rate", "minimal", str(project)))
    _run(store.update_session_stage(session.id, Stage.BUILD))
    monkeypatch.setattr(server, "_store", store)
    _run(begin_stage(str(project), session.id, "samvil-build", 0))
    runtime = json.loads(
        _run(
            server.run_stage_verification(
                str(project), session.id, "samvil-build", json.dumps(command)
            )
        )
    )
    gate = json.loads(
        _run(
            gate_check(
                "build_to_qa",
                "minimal",
                '{"implementation_rate":1.0}',
                str(project),
            )
        )
    )

    assert runtime["status"] == "passed"
    assert gate["verdict"] == "block"
    assert gate["mechanical_metrics"]["implementation_rate"] == 0.0
    assert gate["metric_mismatches"] == [
        {"metric": "implementation_rate", "reported": 1.0, "mechanical": 0.0}
    ]


def test_runtime_verification_drops_host_secrets_and_redacts_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.server as server
    from samvil_mcp.models import Stage

    project = tmp_path / "runtime-secret-boundary"
    secret = "sk-" + "live-" + "abcdefghijkl"
    command = [
        sys.executable,
        "-c",
        (
            "import os; "
            "print(os.environ.get('SAMVIL_PRIVATE_TOKEN', 'HOST_SECRET_MISSING')); "
            "print('sk-' + 'live-' + 'abcdefghijkl')"
        ),
    ]
    _write_mechanical_command(project, "build", command)
    _write_passing_build_seed(project)
    monkeypatch.setenv("SAMVIL_PRIVATE_TOKEN", secret)
    store = EventStore(str(tmp_path / "runtime-secret-boundary.db"))
    _run(store.initialize())
    session = _run(store.create_session("runtime-secret-boundary", "minimal", str(project)))
    _run(store.update_session_stage(session.id, Stage.BUILD))
    monkeypatch.setattr(server, "_store", store)
    _run(begin_stage(str(project), session.id, "samvil-build", 0))

    runtime = json.loads(
        _run(
            server.run_stage_verification(
                str(project), session.id, "samvil-build", json.dumps(command)
            )
        )
    )
    log_text = (project / ".samvil" / "build.log").read_text(encoding="utf-8")
    persisted = _run(store.get_runtime_receipt(session.id, "samvil-build"))
    combined = json.dumps({"runtime": runtime, "persisted": persisted}) + log_text

    assert runtime["status"] == "passed"
    assert "HOST_SECRET_MISSING" in log_text
    assert "[REDACTED_TOKEN]" in log_text
    assert secret not in combined


def test_prior_build_receipts_cannot_authorize_a_new_marker_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.server as server
    from samvil_mcp.chain_markers import build_driver_marker, write_driver_marker
    from samvil_mcp.models import Stage

    project = tmp_path / "build-reentry"
    command = [sys.executable, "-c", "print('same build artifact')"]
    _write_mechanical_command(project, "build", command)
    _write_passing_build_seed(project)
    store = EventStore(str(tmp_path / "build-reentry.db"))
    _run(store.initialize())
    session = _run(store.create_session("build-reentry", "minimal", str(project)))
    _run(store.update_session_stage(session.id, Stage.BUILD))
    monkeypatch.setattr(server, "_store", store)
    first_claim = json.loads(
        _run(begin_stage(str(project), session.id, "samvil-build", 0))
    )
    runtime = json.loads(
        _run(
            server.run_stage_verification(
                str(project),
                session.id,
                "samvil-build",
                json.dumps(command),
            )
        )
    )
    gate = json.loads(
        _run(
            gate_check(
                "build_to_qa",
                "minimal",
                '{"implementation_rate":1.0}',
                str(project),
            )
        )
    )
    _run(store.mark_stage_claim_completed(first_claim["claim_id"], "old-transition"))
    second_claim = _run(store.create_stage_claim(session.id, "samvil-build", 2))
    write_driver_marker(
        str(project),
        build_driver_marker(
            run_id=session.id,
            revision=2,
            status="in_progress",
            host_name="codex_cli",
            from_stage="samvil-build",
            next_skill="",
            reason="build re-entered",
        ),
    )

    result = json.loads(
        _run(
            commit_stage_transition(
                str(project),
                session.id,
                "samvil-build",
                2,
                second_claim["claim_id"],
                "PASS",
                '{"artifact":".samvil/build.log:1"}',
                "",
                "build-reentry-transition",
            )
        )
    )

    assert runtime["status"] == "passed"
    assert gate["verdict"] == "pass"
    assert result["status"] == "blocked"
    assert "trusted gate receipt" in result["reason"]


def test_untrusted_decision_event_cannot_authorize_build_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib
    import samvil_mcp.server as server
    from samvil_mcp.models import Stage

    project = tmp_path / "untrusted-gate-event"
    (project / ".samvil" / "gate-receipts").mkdir(parents=True)
    build_log = project / ".samvil" / "build.log"
    build_log.write_text("compiled\nSAMVIL_EXIT:0\n", encoding="utf-8")
    build_hash = hashlib.sha256(build_log.read_bytes()).hexdigest()
    store = EventStore(str(tmp_path / "untrusted-gate.db"))
    _run(store.initialize())
    session = _run(store.create_session("display", "minimal", str(project)))
    _run(store.update_session_stage(session.id, Stage.BUILD))
    monkeypatch.setattr(server, "_store", store)
    claim = json.loads(_run(begin_stage(str(project), session.id, "samvil-build", 0)))
    receipt = {
        "kind": "gate_receipt",
        "gate": "build_to_qa",
        "verdict": "pass",
        "authority_path": ".samvil/build.log",
        "authority_sha256": build_hash,
    }
    (project / ".samvil" / "gate-receipts" / "build_to_qa.json").write_text(
        json.dumps(receipt), encoding="utf-8"
    )
    _run(server.save_event(
        session.id,
        "decision",
        "build",
        json.dumps(receipt),
    ))

    result = json.loads(_run(commit_stage_transition(
        str(project), session.id, "samvil-build", 0, claim["claim_id"], "PASS",
        '{"artifact":".samvil/build.log:1"}', "", "untrusted-gate-transition",
    )))

    assert result["status"] == "blocked"
    assert "trusted gate receipt" in result["reason"]


def test_qa_to_evolve_gate_ignores_conflicting_reported_pass(tmp_path: Path) -> None:
    (tmp_path / ".samvil").mkdir()
    (tmp_path / ".samvil" / "qa-results.json").write_text(
        json.dumps({
            "synthesis": {
                "verdict": "FAIL",
                "pass1": {"status": "FAIL"},
                "pass2": {"counts": {"FAIL": 1, "UNIMPLEMENTED": 1}},
                "pass3": {"verdict": "FAIL"},
            },
            "convergence": {"verdict": "blocked"},
        }),
        encoding="utf-8",
    )

    gate = json.loads(_run(gate_check(
        "qa_to_evolve",
        "minimal",
        '{"three_pass_pass":true,"zero_stubs":true}',
        str(tmp_path),
    )))

    assert gate["verdict"] == "block"
    assert gate["mechanical_metrics"]["three_pass_pass"] is False
    assert gate["metrics"]["zero_stubs"] is False


# ── Tier phases (Polish #5) ────────────────────────────────────


def test_get_tier_phases_returns_expected_structure() -> None:
    out = _run(get_tier_phases(tier="thorough"))
    data = json.loads(out)
    assert data["tier"] == "thorough"
    assert "phases" in data and isinstance(data["phases"], list)
    assert data["ambiguity_target"] == 0.02
    assert "deep" in data["all_tiers"]


def test_get_tier_phases_deep_includes_domain_deep() -> None:
    data = json.loads(_run(get_tier_phases(tier="deep")))
    assert "domain_deep" in data["phases"]
    assert data["ambiguity_target"] == 0.005


def test_synthesize_qa_evidence_tool_returns_central_verdict() -> None:
    out = _run(synthesize_qa_evidence(evidence_json=json.dumps({
        "pass1": {"status": "PASS"},
        "pass2": {"items": [
            {"id": "AC-1", "criterion": "Create task", "verdict": "UNIMPLEMENTED", "reason": "stub"}
        ]},
        "pass3": {"verdict": "PASS"},
    })))
    data = json.loads(out)
    assert data["gate"] == "qa_synthesis"
    assert data["verdict"] == "REVISE"
    assert data["next_action"] == "replace stubs or hardcoded paths with real implementation"


def test_materialize_qa_synthesis_tool_writes_results(tmp_path: Path) -> None:
    synthesis = json.loads(_run(synthesize_qa_evidence(evidence_json=json.dumps({
        "pass1": {"status": "PASS"},
        "pass2": {"items": [
            {"id": "AC-1", "criterion": "Create task", "verdict": "PASS", "evidence": ["app/page.tsx:10"]}
        ]},
        "pass3": {"verdict": "PASS"},
    }))))

    out = _run(materialize_qa_synthesis(project_root=str(tmp_path), synthesis_json=json.dumps(synthesis)))
    data = json.loads(out)

    assert data["status"] == "ok"
    assert data["verdict"] == "PASS"
    assert (tmp_path / ".samvil" / "qa-results.json").exists()
    assert (tmp_path / ".samvil" / "qa-report.md").exists()


def test_evaluate_qa_convergence_tool_reads_history(tmp_path: Path) -> None:
    (tmp_path / "project.state.json").write_text(json.dumps({
        "qa_history": [{
            "iteration": 1,
            "verdict": "REVISE",
            "issue_ids": ["pass2:AC-1:UNIMPLEMENTED"],
        }]
    }), encoding="utf-8")
    synthesis = json.loads(_run(synthesize_qa_evidence(evidence_json=json.dumps({
        "iteration": 2,
        "max_iterations": 3,
        "pass1": {"status": "PASS"},
        "pass2": {"items": [
            {"id": "AC-1", "criterion": "Create task", "verdict": "UNIMPLEMENTED", "reason": "stub"}
        ]},
        "pass3": {"verdict": "PASS"},
    }))))

    out = _run(evaluate_qa_convergence(project_root=str(tmp_path), synthesis_json=json.dumps(synthesis)))
    data = json.loads(out)

    assert data["gate"] == "qa_convergence"
    assert data["verdict"] == "blocked"


def test_qa_recovery_routing_tools_write_next_skill_marker(tmp_path: Path) -> None:
    (tmp_path / ".samvil").mkdir()
    (tmp_path / ".samvil" / "qa-results.json").write_text(json.dumps({
        "synthesis": {
            "verdict": "REVISE",
            "issue_ids": ["pass2:AC-1:UNIMPLEMENTED"],
        },
        "convergence": {
            "verdict": "blocked",
            "reason": "identical QA issues persisted across two consecutive iterations",
            "issue_ids": ["pass2:AC-1:UNIMPLEMENTED"],
        },
    }), encoding="utf-8")

    built = json.loads(_run(build_qa_recovery_routing(project_root=str(tmp_path))))
    materialized = json.loads(_run(materialize_qa_recovery_routing(project_root=str(tmp_path))))

    assert built["primary_route"]["next_skill"] == "samvil-retro"
    assert materialized["primary_route"]["next_skill"] == "samvil-retro"
    assert (tmp_path / ".samvil" / "next-skill.json").exists()


def test_evolve_context_tools_write_context(tmp_path: Path) -> None:
    (tmp_path / ".samvil").mkdir()
    (tmp_path / "project.seed.json").write_text(json.dumps({
        "name": "task-app",
        "mode": "web",
        "version": 1,
        "core_experience": {"description": "Create tasks"},
        "features": [{"name": "tasks"}],
    }), encoding="utf-8")
    (tmp_path / ".samvil" / "qa-results.json").write_text(json.dumps({
        "synthesis": {"verdict": "REVISE", "issue_ids": ["pass2:AC-1:UNIMPLEMENTED"]},
        "convergence": {"verdict": "blocked", "issue_ids": ["pass2:AC-1:UNIMPLEMENTED"]},
    }), encoding="utf-8")
    (tmp_path / ".samvil" / "qa-routing.json").write_text(json.dumps({
        "primary_route": {"next_skill": "samvil-evolve", "route_type": "seed_evolve"},
    }), encoding="utf-8")

    materialized = json.loads(_run(materialize_evolve_context(project_root=str(tmp_path))))

    assert materialized["next_skill"] == "samvil-evolve"
    assert (tmp_path / ".samvil" / "evolve-context.json").exists()


def test_evolve_proposal_tools_write_artifacts(tmp_path: Path) -> None:
    (tmp_path / ".samvil").mkdir()
    (tmp_path / ".samvil" / "evolve-context.json").write_text(json.dumps({
        "current_seed": {"name": "task-app", "version": 1},
        "qa": {"issue_ids": ["pass2:AC-1:UNIMPLEMENTED"]},
        "focus": {"area": "functional_spec", "issue_ids": ["pass2:AC-1:UNIMPLEMENTED"]},
        "routing": {"next_skill": "samvil-evolve", "route_type": "seed_evolve"},
    }), encoding="utf-8")

    materialized = json.loads(_run(materialize_evolve_proposal(project_root=str(tmp_path))))

    assert materialized["changes"] == 1
    assert (tmp_path / ".samvil" / "evolve-proposal.json").exists()
    assert (tmp_path / ".samvil" / "evolve-proposal.md").exists()


def test_evolve_apply_tools_write_and_apply_seed(tmp_path: Path) -> None:
    (tmp_path / ".samvil").mkdir()
    (tmp_path / "project.seed.json").write_text(json.dumps({
        "schema_version": "3.2",
        "name": "task-app",
        "mode": "web",
        "version": 1,
        "core_experience": {"description": "Create tasks"},
        "features": [{
            "name": "tasks",
            "acceptance_criteria": [
                {"id": "AC-1", "description": "Create task", "children": [], "status": "pending", "evidence": []}
            ],
        }],
    }), encoding="utf-8")
    (tmp_path / ".samvil" / "evolve-proposal.json").write_text(json.dumps({
        "status": "ready",
        "from_version": 1,
        "to_version": 2,
        "proposed_changes": [{"type": "clarify_or_split_ac", "target": "AC-1"}],
    }), encoding="utf-8")

    materialized = json.loads(_run(materialize_evolve_apply_plan(project_root=str(tmp_path))))
    applied = json.loads(_run(apply_evolve_apply_plan(project_root=str(tmp_path))))

    assert materialized["mutations"] == 1
    assert applied["status"] == "applied"
    assert (tmp_path / "seed_history" / "v1.json").exists()


def test_evolve_rebuild_tools_write_next_skill_marker(tmp_path: Path) -> None:
    (tmp_path / ".samvil").mkdir()
    (tmp_path / ".samvil" / "evolve-apply-plan.json").write_text(json.dumps({
        "status": "applied",
        "from_version": 1,
        "to_version": 2,
    }), encoding="utf-8")

    materialized = json.loads(_run(materialize_evolve_rebuild_handoff(project_root=str(tmp_path))))
    marker = json.loads((tmp_path / ".samvil" / "next-skill.json").read_text(encoding="utf-8"))

    assert materialized["next_skill"] == "samvil-scaffold"
    assert marker["from_stage"] == "evolve"


def test_rebuild_reentry_tools_write_scaffold_input(tmp_path: Path) -> None:
    (tmp_path / ".samvil").mkdir()
    (tmp_path / "project.seed.json").write_text(json.dumps({
        "name": "task-app",
        "version": 2,
    }), encoding="utf-8")
    (tmp_path / ".samvil" / "evolve-rebuild.json").write_text(json.dumps({
        "status": "ready",
        "from_version": 1,
        "to_version": 2,
        "next_skill": "samvil-scaffold",
    }), encoding="utf-8")
    (tmp_path / ".samvil" / "next-skill.json").write_text(json.dumps({
        "schema_version": "1.0",
        "chain_via": "file_marker",
        "next_skill": "samvil-scaffold",
        "from_stage": "evolve",
        "reason": "rebuild",
    }), encoding="utf-8")

    built = json.loads(_run(build_rebuild_reentry(project_root=str(tmp_path))))
    materialized = json.loads(_run(materialize_rebuild_reentry(project_root=str(tmp_path))))

    assert built["status"] == "ready"
    assert materialized["status"] == "ready"
    assert (tmp_path / ".samvil" / "scaffold-input.json").exists()


def test_post_rebuild_qa_tools_write_next_skill_marker(tmp_path: Path) -> None:
    import hashlib

    seed = {"name": "task-app", "version": 2}
    digest = hashlib.sha256(
        json.dumps(seed, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    (tmp_path / ".samvil").mkdir()
    (tmp_path / "project.seed.json").write_text(json.dumps(seed), encoding="utf-8")
    (tmp_path / ".samvil" / "rebuild-reentry.json").write_text(json.dumps({
        "status": "ready",
        "seed_name": "task-app",
        "seed_version": 2,
        "seed_sha256": digest,
        "next_skill": "samvil-scaffold",
    }), encoding="utf-8")
    (tmp_path / ".samvil" / "scaffold-input.json").write_text(json.dumps({
        "seed_name": "task-app",
        "seed_version": 2,
        "seed_sha256": digest,
        "next_skill": "samvil-scaffold",
    }), encoding="utf-8")
    (tmp_path / ".samvil" / "scaffold-output.json").write_text(json.dumps({
        "status": "built",
        "seed_version": 2,
        "seed_sha256": digest,
        "artifacts": ["package.json"],
    }), encoding="utf-8")
    (tmp_path / ".samvil" / "qa-results.json").write_text(json.dumps({
        "synthesis": {"verdict": "REVISE", "issue_ids": ["pass2:AC-1:UNIMPLEMENTED"]},
        "convergence": {"verdict": "blocked", "issue_ids": ["pass2:AC-1:UNIMPLEMENTED"]},
    }), encoding="utf-8")

    built = json.loads(_run(build_post_rebuild_qa(project_root=str(tmp_path))))
    materialized = json.loads(_run(materialize_post_rebuild_qa(project_root=str(tmp_path))))
    marker = json.loads((tmp_path / ".samvil" / "next-skill.json").read_text(encoding="utf-8"))

    assert built["status"] == "ready"
    assert materialized["next_skill"] == "samvil-qa"
    assert marker["from_stage"] == "scaffold"


def test_final_e2e_tools_write_bundle(tmp_path: Path) -> None:
    import hashlib

    seed = {"name": "task-app", "version": 2}
    digest = hashlib.sha256(
        json.dumps(seed, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    (tmp_path / ".samvil").mkdir()
    (tmp_path / "project.seed.json").write_text(json.dumps(seed), encoding="utf-8")
    fixtures = {
        "qa-results.json": {"synthesis": {"verdict": "PASS", "iteration": 3}, "convergence": {"verdict": "pass"}},
        "qa-routing.json": {"primary_route": {"next_skill": "samvil-evolve"}},
        "evolve-context.json": {"focus": {"area": "functional_spec"}},
        "evolve-proposal.json": {"status": "ready"},
        "evolve-apply-plan.json": {"status": "applied"},
        "evolve-rebuild.json": {"status": "ready", "next_skill": "samvil-scaffold"},
        "rebuild-reentry.json": {"status": "ready", "next_skill": "samvil-scaffold", "seed_version": 2, "seed_sha256": digest},
        "scaffold-input.json": {"seed_version": 2, "seed_sha256": digest},
        "scaffold-output.json": {"status": "built", "seed_version": 2, "seed_sha256": digest},
        "post-rebuild-qa.json": {"status": "ready", "next_skill": "samvil-qa", "seed_version": 2, "seed_sha256": digest},
        "evolve-cycle.json": {"status": "ready", "verdict": "closed", "next_skill": "samvil-retro", "seed_version": 2, "seed_sha256": digest},
        "run-report.json": {"evolve_cycle": {"present": True, "verdict": "closed"}},
    }
    for name, payload in fixtures.items():
        (tmp_path / ".samvil" / name).write_text(json.dumps(payload), encoding="utf-8")

    built = json.loads(_run(build_final_e2e_bundle(project_root=str(tmp_path))))
    materialized = json.loads(_run(materialize_final_e2e_bundle(project_root=str(tmp_path))))

    assert built["status"] == "pass"
    assert materialized["status"] == "pass"
    assert (tmp_path / ".samvil" / "final-e2e-bundle.json").exists()


# ── AC split (v3-011) ──────────────────────────────────────────


def test_suggest_ac_split_short_desc_returns_no_split() -> None:
    data = json.loads(_run(suggest_ac_split(description="User can add")))
    assert data["should_split"] is False


def test_suggest_ac_split_compound_returns_split() -> None:
    desc = (
        "Authenticated user can create, edit, and delete their own saved "
        "workouts, and share them with other users"
    )
    data = json.loads(_run(suggest_ac_split(description=desc)))
    assert data["should_split"] is True


# ── heartbeat + stall round-trip (v3-016) ─────────────────────


def test_heartbeat_and_stall_round_trip(tmp_path: Path) -> None:
    state_path = tmp_path / "project.state.json"

    # 1. heartbeat creates the file
    out1 = _run(heartbeat_state(state_path=str(state_path), now_iso="2026-04-21T12:00:00+00:00"))
    d1 = json.loads(out1)
    assert d1["ok"] is True
    assert d1["last_progress_at"] == "2026-04-21T12:00:00+00:00"

    # 2. within threshold: not stalled
    out2 = _run(is_state_stalled(
        state_path=str(state_path),
        now_iso="2026-04-21T12:03:00+00:00",
        threshold_seconds=300,
    ))
    d2 = json.loads(out2)
    assert d2["stalled"] is False
    assert d2["elapsed_seconds"] == 180.0

    # 3. past threshold: stalled
    out3 = _run(is_state_stalled(
        state_path=str(state_path),
        now_iso="2026-04-21T12:06:00+00:00",
        threshold_seconds=300,
    ))
    d3 = json.loads(out3)
    assert d3["stalled"] is True

    # 4. recovery count bumps
    out4 = _run(increment_stall_recovery_count(state_path=str(state_path)))
    d4 = json.loads(out4)
    assert d4["ok"] is True
    assert d4["count"] == 1

    out5 = _run(increment_stall_recovery_count(state_path=str(state_path)))
    d5 = json.loads(out5)
    assert d5["count"] == 2

    # 5. reawake message
    out6 = _run(build_reawake_message(
        stage="design",
        detail_json=out3,  # stalled verdict
        count=1,
    ))
    d6 = json.loads(out6)
    assert d6["ok"] is True
    assert "design" in d6["message"]


def test_is_state_stalled_missing_file_does_not_raise(tmp_path: Path) -> None:
    out = _run(is_state_stalled(state_path=str(tmp_path / "missing.json")))
    data = json.loads(out)
    assert data["stalled"] is False
    assert data["reason"] == "state_missing"


def test_health_check_returns_required_fields() -> None:
    from samvil_mcp.server import health_check
    out = _run(health_check())
    data = json.loads(out)
    assert "samvil_version" in data
    assert "tool_count" in data
    assert "db_ok" in data
    assert "python_version" in data
    assert "summary" in data
    assert data["samvil_version"]
    assert isinstance(data["tool_count"], int)
    assert isinstance(data["db_ok"], bool)
    assert "." in data["python_version"]
