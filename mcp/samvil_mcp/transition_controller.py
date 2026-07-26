"""Host-independent stage envelope and begin-stage controller."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from .chain_markers import (
    build_driver_marker,
    inspect_chain_marker,
    write_driver_marker,
)
from .event_store import EventStore
from .claim_ledger import ClaimLedger
from .models import EventType, Stage
from .ssot_io import atomic_write_text
from .stage_catalog import get_stage_spec, skill_for_state_stage, state_stage_for, validate_stage_transition


class TransitionError(RuntimeError):
    """Raised when a stage transition cannot be proven safe."""


class TransitionController:
    def __init__(self, store: EventStore):
        self.store = store

    @staticmethod
    def decide_next_stage(
        stage: str,
        verdict: str,
        *,
        requested_next_skill: str = "",
        council_opt_in: bool = False,
        qa_results: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a deterministic, non-authorizing driver route decision."""
        spec = get_stage_spec(stage)
        normalized = str(verdict or "").upper()
        if spec.requires_user_checkpoint:
            return {"status": "waiting_user", "next_skill": "", "reason": "user checkpoint"}
        if stage == "samvil-qa":
            synthesis = (qa_results or {}).get("synthesis") or {}
            if normalized not in {"PASS", "PASSED"} or synthesis.get("verdict") not in {"PASS", "PASSED"}:
                return {"status": "ready", "next_skill": "samvil-qa", "reason": "QA evidence requires revision"}
            candidate = requested_next_skill or "samvil-deploy"
            if candidate not in spec.valid_next or candidate == "samvil-deploy" and not qa_results:
                candidate = "samvil-qa"
            return {"status": "ready", "next_skill": candidate, "reason": "trusted QA route"}
        if normalized not in {"PASS", "PASSED", "OK", "COMPLETE"}:
            return {"status": "ready", "next_skill": stage, "reason": "stage remains for revision"}
        if stage == "samvil-seed" and council_opt_in:
            return {"status": "ready", "next_skill": "samvil-council", "reason": "explicit council opt-in"}
        default_next = "samvil-design" if stage == "samvil-seed" else (spec.valid_next[0] if spec.valid_next else "")
        candidate = requested_next_skill or default_next
        if candidate and candidate not in spec.valid_next:
            raise TransitionError(f"invalid requested next skill: {candidate}")
        return {"status": "ready", "next_skill": candidate, "reason": "catalog route"}

    @staticmethod
    def circuit_breaker(root_causes: list[str], *, threshold: int = 2) -> dict[str, Any]:
        """Trip only when the same normalized root cause repeats consecutively."""
        normalized = [str(item).strip().lower() for item in root_causes if str(item).strip()]
        latest = normalized[-1] if normalized else ""
        consecutive = 0
        for item in reversed(normalized):
            if item != latest:
                break
            consecutive += 1
        return {"halt": bool(latest and consecutive >= threshold), "root_cause": latest, "consecutive": consecutive, "threshold": threshold}

    async def _session_for_project(self, project_root: str):
        root = Path(project_root).expanduser().resolve(strict=False)
        return await self.store.find_session_by_root(str(root))

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

    @staticmethod
    def _journal_path(root: Path) -> Path:
        return root / ".samvil" / "transition-journal.json"

    @staticmethod
    def _state_path(root: Path) -> Path:
        return root / "project.state.json"

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise TransitionError(f"invalid JSON object: {path}")
        return parsed

    async def commit_stage_transition(
        self,
        project_root: str,
        run_id: str,
        claim_id: str,
        from_stage: str,
        to_stage: str,
        expected_revision: int,
        *,
        event_type: str = "stage_end",
        data: dict[str, Any] | None = None,
        transition_id: str | None = None,
        host_name: str = "codex_cli",
    ) -> dict[str, Any]:
        """Materialize one trusted transition in a fixed, recoverable order."""
        root = Path(project_root).expanduser().resolve(strict=False)
        transition_id = transition_id or f"transition-{uuid.uuid4().hex}"
        existing = await self.store.get_transition_receipt(transition_id)
        if existing is not None:
            return existing
        if not validate_stage_transition(from_stage, to_stage):
            raise TransitionError(f"invalid stage transition: {from_stage} -> {to_stage}")
        session = await self.store.get_session(run_id)
        if session is None or Path(session.project_root).expanduser().resolve(strict=False) != root:
            raise TransitionError("run_id does not own project root")
        if state_stage_for(from_stage) != session.current_stage.value:
            raise TransitionError("from_stage does not match current session stage")
        claim = await self.store.get_stage_claim(run_id, from_stage, expected_revision)
        if claim is None or claim["claim_id"] != claim_id:
            raise TransitionError("stage claim does not match transition")
        inspection = inspect_chain_marker(str(root))
        revision = self._marker_revision(inspection)
        if revision != expected_revision:
            raise TransitionError(f"stale marker revision: expected {expected_revision}, current {revision}")
        if from_stage == "samvil-qa":
            qa = self._read_json(root / ".samvil" / "qa-results.json")
            if not qa:
                return await self.store.save_transition_receipt(
                    transition_id,
                    run_id,
                    {"transition_id": transition_id, "status": "blocked", "stage": "samvil-qa", "reason": "missing QA evidence"},
                )

        event_payload = dict(data or {})
        event_payload.update({"transition_id": transition_id, "from_stage": from_stage, "to_stage": to_stage})
        event_id = f"event-{transition_id}"
        journal = {
            "transition_id": transition_id,
            "run_id": run_id,
            "claim_id": claim_id,
            "expected_revision": expected_revision,
            "from_stage": from_stage,
            "to_stage": to_stage,
            "event_id": event_id,
            "event_payload_hash": hashlib.sha256(json.dumps(event_payload, sort_keys=True).encode()).hexdigest(),
            "phase": "PREPARED",
        }
        atomic_write_text(self._journal_path(root), json.dumps(journal, indent=2, ensure_ascii=False))

        transition = await self.store.save_event_and_update_stage(
            run_id,
            EventType(event_type),
            Stage(state_stage_for(to_stage)),
            event_payload,
            expected_stage=Stage(state_stage_for(from_stage)),
            event_id=event_id,
            transition_id=transition_id,
        )
        journal["phase"] = "DB_COMMITTED"
        atomic_write_text(self._journal_path(root), json.dumps(journal, indent=2, ensure_ascii=False))

        from .server import _append_project_event
        await __import__("asyncio").to_thread(
            _append_project_event,
            root,
            timestamp=transition.event.timestamp,
            event_type=event_type,
            stage=state_stage_for(to_stage),
            session_id=run_id,
            data=event_payload,
            event_id=event_id,
        )
        ledger = ClaimLedger(root / ".samvil" / "claims.jsonl")
        ledger.append_transition_claim(
            transition_id=transition_id,
            subject=f"stage:{to_stage}",
            statement=f"{from_stage} transitioned to {to_stage}",
            authority_file=".samvil/events.jsonl",
            evidence=[f".samvil/events.jsonl:1"],
        )

        state = self._read_json(self._state_path(root))
        completed = list(state.get("completed_stages") or [])
        from_state = state_stage_for(from_stage)
        if from_state not in completed:
            completed.append(from_state)
        state.update({"current_stage": state_stage_for(to_stage), "completed_stages": completed, "stage_transition_id": transition_id, "transition_revision": expected_revision + 1})
        atomic_write_text(self._state_path(root), json.dumps(state, indent=2, ensure_ascii=False))
        next_skill = "" if to_stage == "samvil-retro" else to_stage
        marker_from_stage = from_stage if next_skill else to_stage
        marker = build_driver_marker(run_id=run_id, revision=expected_revision + 1, status="terminal" if not next_skill else "ready", host_name=host_name, from_stage=marker_from_stage, next_skill=next_skill, reason=f"{from_stage} completed")
        write_driver_marker(str(root), marker)
        receipt = {"transition_id": transition_id, "status": "committed", "event_id": event_id, "claim_id": claim_id, "from_stage": from_stage, "to_stage": to_stage, "marker_revision": expected_revision + 1}
        await self.store.save_transition_receipt(transition_id, run_id, receipt)
        await self.store.mark_stage_claim_completed(claim_id, transition_id)
        (self._journal_path(root)).unlink(missing_ok=True)
        return receipt


__all__ = ["TransitionController", "TransitionError"]
