"""Cross-host equivalence tests (MA5).

Verifies that all host adapters produce consistent results for the same
inputs — chain continuation, skill mapping count, and pipeline walk.
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from samvil_mcp.chain_markers import (
    advance_chain,
    clear_chain_marker,
    get_pipeline_status,
    read_chain_marker,
    write_chain_marker,
)
from samvil_mcp.host_adapters import (
    get_adapter,
    get_chain_continuation,
    list_adapters,
    _SKILL_CHAIN,
)

ALL_HOSTS = ["claude_code", "codex_cli", "opencode", "gemini_cli"]


class TestAdapterEquivalence:
    """All adapters must agree on structural properties."""

    def test_all_have_same_skill_count(self):
        adapters = {a["host_name"]: a for a in list_adapters()}
        counts = {name: adapters[name]["skill_count"] for name in ALL_HOSTS}
        assert len(set(counts.values())) == 1, f"Skill counts differ: {counts}"

    def test_all_have_15_skills(self):
        for host in ALL_HOSTS:
            a = get_adapter(host)
            assert len(a["skill_mappings"]) == 15, f"{host} has {len(a['skill_mappings'])}"

    def test_all_resolve_same_next_skill(self):
        """For a given current_skill, all hosts must agree on next_skill."""
        for entry in _SKILL_CHAIN:
            expected_next = entry["next"]
            for host in ALL_HOSTS:
                c = get_chain_continuation(host, entry["name"])
                assert c["next_skill"] == expected_next, (
                    f"{host}: {entry['name']} -> {c['next_skill']} != {expected_next}"
                )


class TestChainMarkerEquivalence:
    """Chain markers must work identically regardless of host."""

    @pytest.fixture
    def project_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.realpath(tmpdir)

    @pytest.mark.parametrize("host", ALL_HOSTS)
    def test_write_and_read_marker(self, project_dir, host):
        m = write_chain_marker(project_dir, host, "samvil")
        r = read_chain_marker(project_dir)
        assert r["next_skill"] == "samvil-interview"
        assert r["host_name"] == host

    @pytest.mark.parametrize("host", ALL_HOSTS)
    def test_full_pipeline_walk(self, project_dir, host):
        clear_chain_marker(project_dir)
        skill = "samvil"
        steps = []
        for _ in range(15):
            m = write_chain_marker(project_dir, host, skill)
            nxt = m.get("next_skill", "")
            steps.append(skill)
            if not nxt:
                break
            skill = nxt
        # All hosts must walk the same number of steps
        assert len(steps) == 11, f"{host}: expected 11 steps, got {len(steps)}"
        assert steps[0] == "samvil"
        assert steps[-1] == "samvil-retro"

    @pytest.mark.parametrize("host", ALL_HOSTS)
    def test_pipeline_status_progress(self, project_dir, host):
        write_chain_marker(project_dir, host, "samvil-build")
        s = get_pipeline_status(project_dir)
        assert s["has_marker"] is True
        assert s["total_skills"] == 15


class TestChainFormatConsistency:
    """Chain format must be consistent within host category."""

    def test_claude_code_uses_skill_tool(self):
        a = get_adapter("claude_code")
        assert a["chain_format"] == "skill_tool"

    def test_other_hosts_use_file_marker(self):
        for host in ["codex_cli", "opencode", "gemini_cli", "generic"]:
            a = get_adapter(host)
            assert a["chain_format"] == "file_marker", f"{host} chain_format={a['chain_format']}"
