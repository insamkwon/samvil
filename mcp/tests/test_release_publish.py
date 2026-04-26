from __future__ import annotations

from samvil_mcp.release_publish import evaluate_publish_guard, release_tag, render_publish_guard


def _state(**overrides):
    state = {
        "version": "3.19.0",
        "tag": "v3.19.0",
        "branch": "main",
        "target_branch": "main",
        "head": "abc123",
        "clean": True,
        "version_synced": True,
        "local_tag_exists": False,
        "remote_tag_exists": False,
        "remote_branch_pushed": True,
        "local_release_gate": {"verdict": "pass", "next_action": "ready to tag release"},
        "remote_release_gate": {
            "verdict": "pass",
            "next_action": "ready to tag release",
            "run": {"id": 123},
        },
    }
    state.update(overrides)
    return state


def test_release_tag_adds_v_prefix() -> None:
    assert release_tag("3.19.0") == "v3.19.0"
    assert release_tag("v3.19.0") == "v3.19.0"


def test_publish_guard_passes_when_all_evidence_is_ready() -> None:
    gate = evaluate_publish_guard(_state())

    assert gate["verdict"] == "pass"
    assert gate["tag"] == "v3.19.0"
    assert gate["remote_run_id"] == 123


def test_publish_guard_blocks_dirty_tree() -> None:
    gate = evaluate_publish_guard(_state(clean=False))

    assert gate["verdict"] == "blocked"
    assert "working tree is not clean" in gate["reason"]
    assert gate["next_action"] == "commit or discard local changes"


def test_publish_guard_blocks_existing_remote_tag() -> None:
    gate = evaluate_publish_guard(_state(remote_tag_exists=True))

    assert gate["verdict"] == "blocked"
    assert "remote tag already exists" in gate["reason"]
    assert gate["next_action"] == "choose a new version"


def test_publish_guard_blocks_remote_gate_failure() -> None:
    gate = evaluate_publish_guard(
        _state(remote_release_gate={"verdict": "blocked", "next_action": "fix remote release check run"})
    )

    assert gate["verdict"] == "blocked"
    assert "remote release gate is not pass" in gate["reason"]
    assert gate["next_action"] == "fix remote release check run"


def test_render_publish_guard_includes_decision() -> None:
    text = render_publish_guard(evaluate_publish_guard(_state()))

    assert "# Verified Release Publisher" in text
    assert "Verdict: pass" in text
    assert "Tag: v3.19.0" in text
