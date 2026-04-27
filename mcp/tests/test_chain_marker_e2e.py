"""E2E integration tests for chain marker pipeline (Option A dogfood)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "scripts" / "host-continuation-smoke.py"

from samvil_mcp.chain_markers import write_chain_marker, read_chain_marker


class TestSmokeScriptIntegration:
    """Run host-continuation-smoke.py as a subprocess against generated markers."""

    @pytest.fixture
    def project_dir(self, tmp_path):
        return tmp_path

    def test_smoke_passes_for_valid_codex_marker(self, project_dir):
        write_chain_marker(str(project_dir), "codex_cli", "samvil")
        result = subprocess.run(
            [sys.executable, str(SMOKE), str(project_dir)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"smoke failed:\n{result.stderr}"
        assert "OK" in result.stdout

    def test_smoke_passes_for_valid_opencode_marker(self, project_dir):
        write_chain_marker(str(project_dir), "opencode", "samvil-seed")
        result = subprocess.run(
            [sys.executable, str(SMOKE), str(project_dir)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"smoke failed:\n{result.stderr}"

    def test_smoke_passes_for_valid_gemini_marker(self, project_dir):
        write_chain_marker(str(project_dir), "gemini_cli", "samvil-design")
        result = subprocess.run(
            [sys.executable, str(SMOKE), str(project_dir)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"smoke failed:\n{result.stderr}"

    def test_smoke_expect_next_flag(self, project_dir):
        write_chain_marker(str(project_dir), "codex_cli", "samvil")
        result = subprocess.run(
            [sys.executable, str(SMOKE), str(project_dir), "--expect-next", "samvil-interview"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"smoke failed:\n{result.stderr}"

    def test_smoke_fails_on_missing_marker(self, project_dir):
        result = subprocess.run(
            [sys.executable, str(SMOKE), str(project_dir)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0


class TestMarkerSchemaCompliance:
    """Generated markers must contain all required fields from host-continuation.md."""

    REQUIRED_FIELDS = ("schema_version", "chain_via", "next_skill", "reason", "from_stage")

    @pytest.fixture
    def project_dir(self, tmp_path):
        return tmp_path

    @pytest.mark.parametrize("host", ["codex_cli", "opencode", "gemini_cli"])
    def test_required_fields_present(self, project_dir, host):
        m = write_chain_marker(str(project_dir), host, "samvil-build")
        for field in self.REQUIRED_FIELDS:
            assert field in m, f"{host} marker missing field: {field}"

    @pytest.mark.parametrize("host", ["codex_cli", "opencode", "gemini_cli"])
    def test_chain_via_is_file_marker(self, project_dir, host):
        m = write_chain_marker(str(project_dir), host, "samvil-seed")
        assert m["chain_via"] == "file_marker"

    @pytest.mark.parametrize("host", ["codex_cli", "opencode", "gemini_cli"])
    def test_schema_version_is_1_0(self, project_dir, host):
        m = write_chain_marker(str(project_dir), host, "samvil")
        assert m["schema_version"] == "1.0"

    @pytest.mark.parametrize("host", ["codex_cli", "opencode", "gemini_cli"])
    def test_next_skill_dir_exists(self, project_dir, host):
        m = write_chain_marker(str(project_dir), host, "samvil")
        next_skill = m["next_skill"]
        skill_path = REPO / "skills" / next_skill / "SKILL.md"
        assert skill_path.exists(), f"skills/{next_skill}/SKILL.md missing"
