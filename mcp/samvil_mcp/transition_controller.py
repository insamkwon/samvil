"""Host-independent stage envelope and begin-stage controller."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .chain_markers import (
    build_driver_marker,
    inspect_chain_marker,
    write_driver_marker,
)
from .event_store import EventStore
from .stage_catalog import get_stage_spec, skill_for_state_stage


class TransitionError(RuntimeError):
    """Raised when a stage transition cannot be proven safe."""


class TransitionController:
    def __init__(self, store: EventStore):
        self.store = store

    async def _session_for_project(self, project_root: str):
        root = Path(project_root).expanduser().resolve(strict=False)
        return await self.store.find_session_by_project(root.name, str(root))

    @staticmethod
    def _marker_revision(inspection) -> int:
        if inspection.classification in {"missing", "legacy"}:
            return int((inspection.marker or {}).get("revision", 0))
        if inspection.classification == "valid":
            return int(inspection.marker["revision"])
        raise TransitionError(f"ambiguous marker: {inspection.classification}")

    async def get_stage_envelope(self, project_root: str, host_name: str) -> dict[str, Any]:
        root = Path(project_root).expanduser().resolve(strict=False)
        session = await self._session_for_project(str(root))
        if session is None:
            return {
                "run_id": "",
                "host_name": host_name,
                "stage": "samvil-interview",
                "status": "fresh",
                "marker_revision": 0,
                "instruction_path": "references/codex-commands/samvil-interview.md",
                "execution_policy": "auto",
                "stop_reason": "",
            }

        inspection = inspect_chain_marker(str(root))
        if inspection.classification in {"corrupt", "unsupported"}:
            return {
                "run_id": session.id,
                "host_name": host_name,
                "stage": skill_for_state_stage(session.current_stage.value),
                "status": "blocked",
                "marker_revision": 0,
                "instruction_path": "",
                "execution_policy": "stop",
                "stop_reason": inspection.reason or inspection.classification,
            }
        stage = skill_for_state_stage(session.current_stage.value)
        spec = get_stage_spec(stage)
        status = "waiting_user" if spec.requires_user_checkpoint else "ready"
        if inspection.classification == "valid" and inspection.marker.get("status") == "in_progress":
            status = "in_progress"
        return {
            "run_id": session.id,
            "host_name": host_name,
            "stage": stage,
            "status": status,
            "marker_revision": self._marker_revision(inspection),
            "instruction_path": spec.instruction,
            "execution_policy": "stop" if status == "waiting_user" else "auto",
            "stop_reason": "user checkpoint" if status == "waiting_user" else "",
        }

    async def begin_stage(
        self,
        project_root: str,
        run_id: str,
        stage: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        if type(expected_revision) is not int or expected_revision < 0:
            raise TransitionError("expected revision must be a non-negative integer")
        root = Path(project_root).expanduser().resolve(strict=False)
        session = await self.store.get_session(run_id)
        if session is None or Path(session.project_root).expanduser().resolve(strict=False) != root:
            raise TransitionError("run_id does not own project root")
        spec = get_stage_spec(stage)
        if spec.requires_user_checkpoint:
            raise TransitionError("stage requires user checkpoint")

        inspection = inspect_chain_marker(str(root))
        revision = self._marker_revision(inspection)
        if revision != expected_revision:
            raise TransitionError(f"stale marker revision: expected {expected_revision}, current {revision}")

        existing = await self.store.get_stage_claim(run_id, stage, revision)
        if existing is not None:
            return existing
        conflicts = await self.store.get_stage_claims_for_revision(run_id, revision)
        if conflicts:
            raise TransitionError("conflicting stage claim")

        claim = await self.store.create_stage_claim(run_id, stage, revision)
        marker = build_driver_marker(
            run_id=run_id,
            revision=revision,
            status="in_progress",
            host_name="codex_cli",
            from_stage=stage,
            next_skill="",
            reason=f"{stage} started",
        )
        try:
            write_driver_marker(str(root), marker)
        except Exception:
            await self.store.delete_stage_claim(claim["claim_id"])
            raise
        return claim


__all__ = ["TransitionController", "TransitionError"]
