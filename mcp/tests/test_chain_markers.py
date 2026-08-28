"""Tests for chain_markers module (M2 file-marker chaining)."""

import json
import pytest
from pathlib import Path

from samvil_mcp.chain_markers import (
    write_chain_marker,
    read_chain_marker,
    resolve_stage_next_skill,
    clear_chain_marker,
    advance_chain,
    get_pipeline_status,
    build_driver_marker,
    inspect_chain_marker,
    write_driver_marker,
    _validate_driver_marker,
    MARKER_FILENAME,
    SAMVIL_DIR,
)


class TestDriverMarkerV11:
    @pytest.mark.parametrize("next_skill", [None, False, 0, [], {}, pytest.param("__missing__")])
    def test_v11_rejects_non_string_next_skill(self, next_skill):
        marker = build_driver_marker(
            run_id="run-1",
            revision=0,
            status="in_progress",
            host_name="codex_cli",
            from_stage="samvil-build",
            next_skill="samvil-qa",
            reason="stage started",
        )
        if next_skill == "__missing__":
            del marker["next_skill"]
        else:
            marker["next_skill"] = next_skill

        with pytest.raises(ValueError, match="^next_skill must be a string$"):
            _validate_driver_marker(marker)

    def test_v10_reader_remains_compatible(self, project_root):
        write_chain_marker(project_root, "codex_cli", "samvil-build")
        inspection = inspect_chain_marker(project_root)
        assert inspection.classification == "legacy"
        assert inspection.marker["schema_version"] == "1.0"

    def test_v11_requires_revision_status_and_host_driver(self):
        marker = build_driver_marker(
            run_id="run-1",
            revision=3,
            status="ready",
            host_name="codex_cli",
            from_stage="samvil-build",
            next_skill="samvil-qa",
            reason="build gate passed",
        )
        assert marker["schema_version"] == "1.1"
        assert marker["chain_via"] == "host_driver"
        assert marker["revision"] == 3

    def test_legacy_writer_preserves_completed_driver_marker(self, project_root):
        marker = build_driver_marker(
            run_id="run-1",
            revision=4,
            status="ready",
            host_name="codex_cli",
            from_stage="samvil-build",
            next_skill="samvil-qa",
            reason="build completed",
        )
        write_driver_marker(project_root, marker)

        result = write_chain_marker(
            project_root,
            "codex_cli",
            "samvil-build",
            next_skill="samvil-qa",
        )

        assert result == marker
        assert inspect_chain_marker(project_root).classification == "valid"

    def test_legacy_writer_cannot_bypass_in_progress_driver_claim(self, project_root):
        marker = build_driver_marker(
            run_id="run-1",
            revision=4,
            status="in_progress",
            host_name="codex_cli",
            from_stage="samvil-build",
            next_skill="",
            reason="build started",
        )
        write_driver_marker(project_root, marker)

        with pytest.raises(ValueError, match="host driver owns transition"):
            write_chain_marker(
                project_root,
                "codex_cli",
                "samvil-build",
                next_skill="samvil-qa",
            )

    @pytest.mark.parametrize("host_name", ["claude_code", "gemini_cli", "generic"])
    def test_any_host_preserves_driver_owned_marker(self, project_root, host_name):
        marker = build_driver_marker(
            run_id="run-1",
            revision=4,
            status="ready",
            host_name="codex_cli",
            from_stage="samvil-build",
            next_skill="samvil-qa",
            reason="build completed",
        )
        write_driver_marker(project_root, marker)

        assert write_chain_marker(
            project_root,
            host_name,
            "samvil-build",
            next_skill="samvil-qa",
        ) == marker
        with pytest.raises(ValueError, match="host driver owns transition"):
            write_chain_marker(
                project_root,
                host_name,
                "samvil-qa",
                next_skill="samvil-retro",
            )

    @pytest.mark.parametrize("revision", [True, False, -1, "3"])
    def test_v11_rejects_invalid_revision(self, revision):
        with pytest.raises(ValueError):
            build_driver_marker(
                run_id="run-1",
                revision=revision,
                status="ready",
                host_name="codex_cli",
                from_stage="samvil-build",
                next_skill="samvil-qa",
                reason="build gate passed",
            )

    def test_inspection_classifies_missing_corrupt_and_unknown(self, project_root):
        assert inspect_chain_marker(project_root).classification == "missing"
        path = Path(project_root) / SAMVIL_DIR / MARKER_FILENAME
        path.parent.mkdir(parents=True)
        path.write_text("{broken", encoding="utf-8")
        assert inspect_chain_marker(project_root).classification == "corrupt"
        path.write_text(json.dumps({"schema_version": "9.9"}), encoding="utf-8")
        assert inspect_chain_marker(project_root).classification == "unsupported"

    def test_v11_writer_is_atomic_and_catalog_validates_stages(self, project_root):
        marker = build_driver_marker(
            run_id="run-1",
            revision=0,
            status="in_progress",
            host_name="codex_cli",
            from_stage="samvil-build",
            next_skill="samvil-qa",
            reason="stage started",
        )
        written = write_driver_marker(project_root, marker)
        assert written == marker
        inspection = inspect_chain_marker(project_root)
        assert inspection.classification == "valid"
        assert inspection.marker["run_id"] == "run-1"
        with pytest.raises(ValueError):
            build_driver_marker(
                run_id="run-1",
                revision=1,
                status="ready",
                host_name="codex_cli",
                from_stage="samvil-design",
                next_skill="samvil-interview",
                reason="invalid backwards route",
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
        assert result["command"] == "samvil samvil-qa"
        assert result["chain_via"] == "file_marker"
        assert result["host_name"] == "codex_cli"
        assert "written_at" in result

    def test_dynamic_override_updates_command_with_next_skill(self, project_root):
        result = write_chain_marker(
            project_root,
            "codex_cli",
            "samvil-qa",
            next_skill="samvil-evolve",
        )

        assert result["next_skill"] == "samvil-evolve"
        assert result["command"] == "samvil samvil-evolve"

    def test_orchestrator_dynamic_override_preserves_pm_route(self, project_root):
        result = write_chain_marker(
            project_root,
            "codex_cli",
            "samvil",
            next_skill="samvil-pm-interview",
        )

        assert result["next_skill"] == "samvil-pm-interview"
        assert result["command"] == "samvil samvil-pm-interview"

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

    @pytest.mark.parametrize("payload", [[], "samvil-qa", 1, True])
    def test_handles_parseable_non_object_json(self, project_root, payload):
        marker_path = Path(project_root) / SAMVIL_DIR / MARKER_FILENAME
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text(json.dumps(payload), encoding="utf-8")

        assert read_chain_marker(project_root) is None
        assert advance_chain(project_root, "codex_cli") == {
            "next_skill": "",
            "status": "pipeline_complete",
        }


def test_pm_council_override_is_disabled_for_minimal_tier(project_root):
    root = Path(project_root)
    (root / "project.state.json").write_text(
        json.dumps({"samvil_tier": "minimal"}),
        encoding="utf-8",
    )
    (root / "project.config.json").write_text(
        json.dumps({"flags": ["--council"]}),
        encoding="utf-8",
    )

    assert (
        resolve_stage_next_skill(project_root, "samvil-pm-interview")
        == "samvil-design"
    )


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

    def test_advance_chain_honors_pm_council_project_policy(self, project_root):
        root = Path(project_root)
        (root / "project.state.json").write_text(
            json.dumps({"samvil_tier": "standard"}),
            encoding="utf-8",
        )
        (root / "project.config.json").write_text(
            json.dumps({"flags": ["--council"]}),
            encoding="utf-8",
        )
        write_chain_marker(
            project_root,
            "codex_cli",
            "samvil",
            next_skill="samvil-pm-interview",
        )

        result = advance_chain(project_root, "codex_cli")

        assert result["from_stage"] == "samvil-pm-interview"
        assert result["next_skill"] == "samvil-council"

    def test_advance_chain_honors_failed_qa_project_policy(self, project_root):
        root = Path(project_root)
        (root / "project.state.json").write_text("{}", encoding="utf-8")
        (root / ".samvil").mkdir(exist_ok=True)
        (root / ".samvil" / "qa-results.json").write_text(
            json.dumps(
                {
                    "synthesis": {"verdict": "FAIL", "pass2": {"counts": {}}},
                    "convergence": {"verdict": "failed"},
                }
            ),
            encoding="utf-8",
        )
        write_chain_marker(
            project_root,
            "codex_cli",
            "samvil-build",
            next_skill="samvil-qa",
        )

        result = advance_chain(project_root, "codex_cli")

        assert result["from_stage"] == "samvil-qa"
        assert result["next_skill"] == "samvil-retro"

    @pytest.mark.parametrize("qa_results", [None, "not json{"])
    def test_advance_chain_keeps_qa_when_current_results_are_unavailable(
        self,
        project_root,
        qa_results,
    ):
        root = Path(project_root)
        (root / ".samvil").mkdir(exist_ok=True)
        if qa_results is not None:
            (root / ".samvil" / "qa-results.json").write_text(
                qa_results,
                encoding="utf-8",
            )
        write_chain_marker(
            project_root,
            "codex_cli",
            "samvil-build",
            next_skill="samvil-qa",
        )

        result = advance_chain(project_root, "codex_cli")

        assert result["next_skill"] == "samvil-qa"
        assert result["command"] == "samvil samvil-qa"
        assert result["status"] == "blocked_missing_qa_results"

    @pytest.mark.parametrize(
        "synthesis",
        [
            {"pass2": {"counts": {}}},
            {"verdict": "BOGUS", "pass2": {"counts": {}}},
        ],
    )
    def test_advance_chain_keeps_qa_for_untrusted_verdict(
        self,
        project_root,
        synthesis,
    ):
        root = Path(project_root)
        (root / ".samvil").mkdir(exist_ok=True)
        (root / ".samvil" / "qa-results.json").write_text(
            json.dumps({"synthesis": synthesis}),
            encoding="utf-8",
        )
        write_chain_marker(
            project_root,
            "codex_cli",
            "samvil-build",
            next_skill="samvil-qa",
        )

        result = advance_chain(project_root, "codex_cli")

        assert result["next_skill"] == "samvil-qa"
        assert result["status"] == "blocked_missing_qa_results"

    @pytest.mark.parametrize(
        "qa_results",
        [
            {"synthesis": "corrupt"},
            {
                "synthesis": {"verdict": "PASS", "pass2": {"counts": {}}},
                "convergence": ["corrupt"],
            },
            {
                "synthesis": {"verdict": "PASS", "pass2": {"counts": {}}},
                "convergence": [],
            },
            {"synthesis": {"verdict": "PASS", "pass2": "corrupt"}},
            {
                "synthesis": {
                    "verdict": "PASS",
                    "pass2": {"counts": ["corrupt"]},
                }
            },
            {
                "synthesis": {
                    "verdict": "PASS",
                    "pass2": {"counts": {"PARTIAL": "corrupt"}},
                }
            },
            {
                "synthesis": {
                    "verdict": "PASS",
                    "pass2": {"counts": {"PARTIAL": []}},
                }
            },
            {
                "synthesis": {
                    "verdict": "PASS",
                    "pass2": {"counts": {"PARTIAL": True}},
                }
            },
            {
                "synthesis": {
                    "verdict": "PASS",
                    "pass2": {"counts": {"PARTIAL": -1}},
                }
            },
        ],
    )
    def test_advance_chain_keeps_qa_for_parseable_structural_corruption(
        self,
        project_root,
        qa_results,
    ):
        root = Path(project_root)
        (root / ".samvil").mkdir(exist_ok=True)
        (root / ".samvil" / "qa-results.json").write_text(
            json.dumps(qa_results),
            encoding="utf-8",
        )
        write_chain_marker(
            project_root,
            "codex_cli",
            "samvil-build",
            next_skill="samvil-qa",
        )

        assert resolve_stage_next_skill(project_root, "samvil-qa") is None
        result = advance_chain(project_root, "codex_cli")

        assert result["next_skill"] == "samvil-qa"
        assert result["status"] == "blocked_missing_qa_results"

    @pytest.mark.parametrize(
        "state",
        [
            {"build_retries": "corrupt"},
            {"build_retries": []},
            {"build_retries": True},
            {"build_retries": -1},
            {"qa_history": "corrupt"},
        ],
    )
    def test_advance_chain_keeps_qa_for_corrupt_routing_state(
        self, project_root, state
    ):
        root = Path(project_root)
        (root / ".samvil").mkdir(exist_ok=True)
        (root / ".samvil" / "qa-results.json").write_text(
            json.dumps(
                {
                    "synthesis": {
                        "verdict": "PASS",
                        "pass2": {"counts": {"PARTIAL": 0}},
                    }
                }
            ),
            encoding="utf-8",
        )
        (root / "project.state.json").write_text(
            json.dumps(state),
            encoding="utf-8",
        )
        write_chain_marker(
            project_root,
            "codex_cli",
            "samvil-build",
            next_skill="samvil-qa",
        )

        assert resolve_stage_next_skill(project_root, "samvil-qa") is None
        result = advance_chain(project_root, "codex_cli")

        assert result["next_skill"] == "samvil-qa"
        assert result["status"] == "blocked_missing_qa_results"

    def test_advance_chain_keeps_qa_for_non_utf8_results(self, project_root):
        root = Path(project_root)
        (root / ".samvil").mkdir(exist_ok=True)
        (root / ".samvil" / "qa-results.json").write_bytes(b"\xff\xfe\x00")
        write_chain_marker(
            project_root,
            "codex_cli",
            "samvil-build",
            next_skill="samvil-qa",
        )

        assert resolve_stage_next_skill(project_root, "samvil-qa") is None
        result = advance_chain(project_root, "codex_cli")

        assert result["next_skill"] == "samvil-qa"
        assert result["status"] == "blocked_missing_qa_results"

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
        assert result["total_skills"] == 16

    def test_with_marker(self, project_with_marker):
        result = get_pipeline_status(project_with_marker)
        assert result["has_marker"] is True
        assert "pipeline_progress" in result
        assert result["total_skills"] == 16

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
