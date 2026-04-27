"""Tests for chain_markers module (M2 file-marker chaining)."""

import json
import pytest
from pathlib import Path

from samvil_mcp.chain_markers import (
    write_chain_marker,
    read_chain_marker,
    clear_chain_marker,
    advance_chain,
    get_pipeline_status,
    MARKER_FILENAME,
    SAMVIL_DIR,
)


@pytest.fixture
def project_root(tmp_path):
    """Create a temp project root with .samvil dir."""
    return str(tmp_path)


@pytest.fixture
def project_with_marker(project_root):
    """Project root with an initial marker at samvil-build."""
    write_chain_marker(project_root, "codex_cli", "samvil-design")
    return project_root


class TestWriteChainMarker:
    def test_creates_marker_file(self, project_root):
        result = write_chain_marker(project_root, "codex_cli", "samvil-build")
        marker_path = Path(project_root) / SAMVIL_DIR / MARKER_FILENAME
        assert marker_path.exists()

    def test_marker_content(self, project_root):
        result = write_chain_marker(project_root, "codex_cli", "samvil-build")
        assert result["next_skill"] == "samvil-qa"
        assert result["chain_via"] == "file_marker"
        assert result["host_name"] == "codex_cli"
        assert "written_at" in result

    def test_creates_samvil_dir(self, project_root):
        samvil_dir = Path(project_root) / SAMVIL_DIR
        assert not samvil_dir.exists()
        write_chain_marker(project_root, "generic", "samvil")
        assert samvil_dir.exists()

    def test_overwrites_existing(self, project_root):
        write_chain_marker(project_root, "generic", "samvil")
        write_chain_marker(project_root, "generic", "samvil-build")
        result = read_chain_marker(project_root)
        assert result["next_skill"] == "samvil-qa"

    def test_claude_code_uses_skill_tool(self, project_root):
        result = write_chain_marker(project_root, "claude_code", "samvil-build")
        assert result["chain_via"] == "skill_tool"

    def test_terminal_skill_empty_next(self, project_root):
        result = write_chain_marker(project_root, "generic", "samvil-retro")
        assert result["next_skill"] == ""


class TestReadChainMarker:
    def test_returns_none_when_no_marker(self, project_root):
        assert read_chain_marker(project_root) is None

    def test_returns_marker_dict(self, project_root):
        write_chain_marker(project_root, "generic", "samvil-build")
        result = read_chain_marker(project_root)
        assert isinstance(result, dict)
        assert result["next_skill"] == "samvil-qa"

    def test_handles_corrupt_json(self, project_root):
        marker_path = Path(project_root) / SAMVIL_DIR / MARKER_FILENAME
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text("not json{")
        assert read_chain_marker(project_root) is None


class TestClearChainMarker:
    def test_removes_marker(self, project_with_marker):
        assert read_chain_marker(project_with_marker) is not None
        result = clear_chain_marker(project_with_marker)
        assert result is True
        assert read_chain_marker(project_with_marker) is None

    def test_returns_false_when_no_marker(self, project_root):
        result = clear_chain_marker(project_root)
        assert result is False


class TestAdvanceChain:
    def test_advances_to_next(self, project_with_marker):
        # Marker was written after samvil-design → next is samvil-scaffold
        # advance_chain reads next_skill (scaffold), writes new marker for scaffold
        # new marker's next_skill = build (next after scaffold)
        result = advance_chain(project_with_marker, "codex_cli")
        assert result["next_skill"] == "samvil-build"

    def test_pipeline_complete(self, project_root):
        write_chain_marker(project_root, "generic", "samvil-retro")
        result = advance_chain(project_root, "generic")
        assert result["status"] == "pipeline_complete"

    def test_no_marker(self, project_root):
        result = advance_chain(project_root, "generic")
        assert result["status"] == "pipeline_complete"


class TestGetPipelineStatus:
    def test_no_marker(self, project_root):
        result = get_pipeline_status(project_root)
        assert result["has_marker"] is False
        assert result["total_skills"] == 15

    def test_with_marker(self, project_with_marker):
        result = get_pipeline_status(project_with_marker)
        assert result["has_marker"] is True
        assert "pipeline_progress" in result
        assert result["total_skills"] == 15

    def test_progress_count(self, project_root):
        write_chain_marker(project_root, "generic", "samvil")
        result = get_pipeline_status(project_root)
        assert result["completed_count"] == 1

    def test_mid_pipeline(self, project_root):
        write_chain_marker(project_root, "generic", "samvil-build")
        result = get_pipeline_status(project_root)
        assert result["completed_count"] == 8  # build is 8th skill (0-indexed 7)

    def test_written_at_preserved(self, project_root):
        write_chain_marker(project_root, "generic", "samvil-build")
        result = get_pipeline_status(project_root)
        assert result["written_at"] is not None
