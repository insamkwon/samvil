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
        assert "OK" in result.stdout

    def test_smoke_passes_for_valid_gemini_marker(self, project_dir):
        write_chain_marker(str(project_dir), "gemini_cli", "samvil-design")
        result = subprocess.run(
            [sys.executable, str(SMOKE), str(project_dir)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"smoke failed:\n{result.stderr}"
        assert "OK" in result.stdout

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


class TestCommandFileCorrectness:
    """All host command reference files must be complete and consistent."""

    CODEX_CMD_DIR = REPO / "references" / "codex-commands"
    GEMINI_CMD_DIR = REPO / "references" / "gemini-commands"
    EXPECTED_SKILLS = [
        "samvil", "samvil-interview", "samvil-pm-interview", "samvil-seed",
        "samvil-council", "samvil-design", "samvil-scaffold", "samvil-build",
        "samvil-qa", "samvil-deploy", "samvil-evolve", "samvil-retro",
        "samvil-analyze", "samvil-doctor", "samvil-update",
    ]

    def test_codex_has_all_15_skills(self):
        md_files = list(self.CODEX_CMD_DIR.glob("*.md"))
        names = {f.stem for f in md_files}
        for skill in self.EXPECTED_SKILLS:
            assert skill in names, f"codex-commands missing: {skill}.md"

    def test_gemini_has_all_15_skills(self):
        toml_files = list(self.GEMINI_CMD_DIR.glob("*.toml"))
        names = {f.stem for f in toml_files}
        for skill in self.EXPECTED_SKILLS:
            assert skill in names, f"gemini-commands missing: {skill}.toml"

    def test_all_codex_md_reference_read_chain_marker(self):
        for md_file in self.CODEX_CMD_DIR.glob("*.md"):
            content = md_file.read_text()
            assert "read_chain_marker" in content, (
                f"{md_file.name} does not reference read_chain_marker"
            )

    def test_all_codex_md_reference_write_chain_marker(self):
        for md_file in self.CODEX_CMD_DIR.glob("*.md"):
            content = md_file.read_text()
            assert "write_chain_marker" in content, (
                f"{md_file.name} does not reference write_chain_marker"
            )

    def test_all_gemini_toml_reference_mcp_tools(self):
        for toml_file in self.GEMINI_CMD_DIR.glob("*.toml"):
            content = toml_file.read_text()
            assert "read_chain_marker" in content or "write_chain_marker" in content, (
                f"{toml_file.name} does not reference any chain marker MCP tool"
            )

    def test_skill_dirs_exist_for_all_references(self):
        for skill in self.EXPECTED_SKILLS:
            skill_path = REPO / "skills" / skill / "SKILL.md"
            assert skill_path.exists(), f"skills/{skill}/SKILL.md missing"


class TestPhase2SmokeIntegration:
    """Run phase2-cross-host-smoke.py as a subprocess."""

    PHASE2_SMOKE = REPO / "scripts" / "phase2-cross-host-smoke.py"

    def test_phase2_smoke_passes(self):
        result = subprocess.run(
            [sys.executable, str(self.PHASE2_SMOKE)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"phase2 smoke failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
        assert "OK" in result.stdout


class TestCodexLayerConnectivity:
    """Verify the MCP layer a codex session would use is functional."""

    @pytest.fixture
    def project_dir(self, tmp_path):
        return tmp_path

    def test_write_then_read_roundtrip_codex_host(self, project_dir):
        """Exact path codex would take: write marker, read marker."""
        project_root = str(project_dir)
        written = write_chain_marker(project_root, "codex_cli", "samvil")
        assert written["next_skill"] == "samvil-interview"
        assert written["host_name"] == "codex_cli"

        read = read_chain_marker(project_root)
        assert read is not None
        assert read["next_skill"] == written["next_skill"]
        assert read["host_name"] == written["host_name"]

    def test_advance_chain_codex(self, project_dir):
        """advance_chain() simulates the codex session completing a stage."""
        from samvil_mcp.chain_markers import advance_chain
        project_root = str(project_dir)
        write_chain_marker(project_root, "codex_cli", "samvil")
        m1 = read_chain_marker(project_root)
        advance_chain(project_root, "codex_cli")
        m2 = read_chain_marker(project_root)
        # samvil → samvil-interview → samvil-seed
        assert m2["next_skill"] == "samvil-seed"

    def test_pipeline_status_after_advance(self, project_dir):
        """get_pipeline_status() returns correct progress after writes."""
        from samvil_mcp.chain_markers import get_pipeline_status
        project_root = str(project_dir)
        write_chain_marker(project_root, "codex_cli", "samvil-build")
        status = get_pipeline_status(project_root)
        assert status["has_marker"] is True
        assert status["next_skill"] == "samvil-qa"
        assert status["total_skills"] == 16
