"""Host-independent stage envelope and begin-stage controller."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any

from .chain_markers import (
    build_driver_marker,
    inspect_chain_marker,
    write_driver_marker,
)
from .event_store import EventStore
from .event_sanitizer import sanitize_event_data
from .claim_ledger import ClaimLedger
from .models import EventType, Stage
from .runtime_layout import (
    RuntimeLayoutError,
    discover_repository_root,
    safe_child_directory,
)
from .ssot_io import atomic_write_text
from .stage_catalog import (
    get_stage_spec,
    instruction_path_for,
    skill_for_state_stage,
    state_stage_for,
    validate_stage_transition,
)
from .transition_lock import stage_transition_lock


_SAFE_TRANSITION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


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
            convergence = (qa_results or {}).get("convergence") or synthesis.get("convergence") or {}
            convergence_verdict = str(convergence.get("verdict") or "").casefold()
            if normalized not in {"PASS", "PASSED"} or synthesis.get("verdict") not in {"PASS", "PASSED"}:
                if (
                    convergence_verdict in {"blocked", "failed"}
                    and requested_next_skill in {"samvil-evolve", "samvil-retro"}
                ):
                    return {
                        "status": "ready",
                        "next_skill": requested_next_skill,
                        "reason": "trusted QA convergence recovery route",
                    }
                return {"status": "ready", "next_skill": "samvil-qa", "reason": "QA evidence requires revision"}
            candidate = requested_next_skill or "samvil-retro"
            if candidate not in spec.valid_next or candidate == "samvil-deploy" and not qa_results:
                candidate = "samvil-qa"
            if candidate == "samvil-deploy":
                return {
                    "status": "waiting_user",
                    "next_skill": "",
                    "reason": "deployment approval requires a trusted host attestation",
                }
            return {"status": "ready", "next_skill": candidate, "reason": "trusted QA route"}
        if normalized not in {"PASS", "PASSED", "OK", "COMPLETE"}:
            return {"status": "ready", "next_skill": stage, "reason": "stage remains for revision"}
        if spec.terminal:
            return {
                "status": "ready",
                "next_skill": "complete",
                "reason": "terminal stage completed",
            }
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
    def _session_skill(session: Any) -> str:
        if session.current_stage == Stage.COMPLETE:
            return "complete"
        active_skill = str(getattr(session, "active_skill", "") or "")
        if not active_skill:
            return skill_for_state_stage(session.current_stage.value)
        spec = get_stage_spec(active_skill)
        if spec.state_stage is not None and spec.state_stage != session.current_stage.value:
            raise TransitionError("active skill does not match current session stage")
        if spec.state_stage is None and active_skill not in {
            "samvil-pm-interview",
            "samvil-analyze",
        }:
            raise TransitionError("unsupported active session skill")
        return active_skill

    @staticmethod
    def _instruction_path(stage: str) -> str:
        relative = get_stage_spec(stage).instruction
        try:
            repository_root = discover_repository_root(
                relative,
                package_file=__file__,
            )
        except RuntimeLayoutError as exc:
            raise TransitionError(str(exc)) from exc
        return str(instruction_path_for(stage, repository_root))

    @staticmethod
    def _validate_project_layout(root: Path) -> None:
        try:
            safe_child_directory(root, ".samvil", label=".samvil")
        except RuntimeLayoutError as exc:
            raise TransitionError(str(exc)) from exc

    @staticmethod
    def _marker_revision(inspection) -> int:
        if inspection.classification in {"missing", "legacy"}:
            return int((inspection.marker or {}).get("revision", 0))
        if inspection.classification == "valid":
            return int(inspection.marker["revision"])
        raise TransitionError(f"ambiguous marker: {inspection.classification}")

    async def get_stage_envelope(self, project_root: str, host_name: str) -> dict[str, Any]:
        root = Path(project_root).expanduser().resolve(strict=False)
        try:
            self._validate_project_layout(root)
        except TransitionError as exc:
            return {
                "run_id": "",
                "host_name": host_name,
                "stage": "",
                "status": "blocked",
                "marker_revision": 0,
                "instruction_path": "",
                "execution_policy": "stop",
                "stop_reason": str(exc),
            }
        inspection = inspect_chain_marker(str(root))
        try:
            journal = self._read_json(self._journal_path(root))
            if journal:
                journal, _persisted_event = await self._authoritative_journal_context(root, journal)
                journal_run_id = str(journal["run_id"])
                event_payload = dict(journal.get("event_payload") or {})
                return {
                    "run_id": journal_run_id,
                    "host_name": host_name,
                    "stage": str(journal["from_stage"]),
                    "status": "in_progress",
                    "marker_revision": int(journal["expected_revision"]),
                    "instruction_path": self._instruction_path(str(journal["from_stage"])),
                    "execution_policy": "recover",
                    "stop_reason": "interrupted transition requires fixed-id retry",
                    "recovery_mode": "retry_commit",
                    "transition_id": str(journal["transition_id"]),
                    "claim_id": str(journal["claim_id"]),
                    "requested_next_skill": str(journal["to_stage"]),
                    "verdict": str(event_payload.get("verdict") or "PASS"),
                    "evidence": event_payload.get("evidence") or {},
                }
        except (OSError, json.JSONDecodeError, TransitionError, ValueError) as exc:
            return {
                "run_id": "",
                "host_name": host_name,
                "stage": "",
                "status": "blocked",
                "marker_revision": 0,
                "instruction_path": "",
                "execution_policy": "stop",
                "stop_reason": str(exc),
            }
        try:
            project_state = self._read_json(self._state_path(root))
        except (OSError, json.JSONDecodeError, TransitionError, ValueError) as exc:
            return {
                "run_id": "",
                "host_name": host_name,
                "stage": "",
                "status": "blocked",
                "marker_revision": 0,
                "instruction_path": "",
                "execution_policy": "stop",
                "stop_reason": str(exc),
            }
        state_run_id = str(project_state.get("session_id") or "")
        session = None
        if inspection.classification == "valid":
            marker_run_id = str(inspection.marker.get("run_id") or "")
            if state_run_id and state_run_id != marker_run_id:
                return {
                    "run_id": marker_run_id,
                    "host_name": host_name,
                    "stage": "",
                    "status": "blocked",
                    "marker_revision": 0,
                    "instruction_path": "",
                    "execution_policy": "stop",
                    "stop_reason": "marker run conflicts with project state session",
                }
            marker_session = await self.store.get_session(marker_run_id)
            if marker_session is None or Path(marker_session.project_root).expanduser().resolve(strict=False) != root:
                return {
                    "run_id": marker_run_id,
                    "host_name": host_name,
                    "stage": "",
                    "status": "blocked",
                    "marker_revision": 0,
                    "instruction_path": "",
                    "execution_policy": "stop",
                    "stop_reason": "marker run does not own project root",
                }
            session = marker_session
        elif state_run_id:
            state_session = await self.store.get_session(state_run_id)
            if state_session is not None:
                state_root = Path(state_session.project_root).expanduser().resolve(
                    strict=False
                )
                if state_session.project_root and state_root != root:
                    return {
                        "run_id": state_run_id,
                        "host_name": host_name,
                        "stage": "",
                        "status": "blocked",
                        "marker_revision": 0,
                        "instruction_path": "",
                        "execution_policy": "stop",
                        "stop_reason": "project state run does not own project root",
                    }
                if state_session.project_root:
                    session = state_session
        if session is None and not state_run_id:
            session = await self._session_for_project(str(root))
        if session is None:
            legacy_state_exists = any(
                candidate.is_file()
                for candidate in (
                    root / "project.state.json",
                    root / ".samvil" / "state.json",
                )
            )
            if legacy_state_exists or inspection.classification != "missing":
                return {
                    "run_id": "",
                    "host_name": host_name,
                    "stage": "",
                    "status": "blocked",
                    "marker_revision": 0,
                    "instruction_path": "",
                    "execution_policy": "migrate",
                    "stop_reason": "legacy project requires explicit session migration",
                }
            return {
                "run_id": "",
                "host_name": host_name,
                "stage": "samvil-interview",
                "status": "fresh",
                "marker_revision": 0,
                "instruction_path": self._instruction_path("samvil"),
                "execution_policy": "auto",
                "stop_reason": "",
            }

        try:
            session_skill = self._session_skill(session)
        except (TransitionError, ValueError) as exc:
            return {
                "run_id": session.id,
                "host_name": host_name,
                "stage": "",
                "status": "blocked",
                "marker_revision": 0,
                "instruction_path": "",
                "execution_policy": "stop",
                "stop_reason": str(exc),
            }

        if inspection.classification in {"corrupt", "unsupported"}:
            return {
                "run_id": session.id,
                "host_name": host_name,
                "stage": session_skill,
                "status": "blocked",
                "marker_revision": 0,
                "instruction_path": "",
                "execution_policy": "stop",
                "stop_reason": inspection.reason or inspection.classification,
            }
        if session.current_stage == Stage.COMPLETE:
            return {
                "run_id": session.id,
                "host_name": host_name,
                "stage": "complete",
                "status": "complete",
                "marker_revision": self._marker_revision(inspection),
                "instruction_path": "",
                "execution_policy": "stop",
                "stop_reason": "pipeline complete",
            }
        stage = session_skill
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
            "instruction_path": self._instruction_path(stage),
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
        self._validate_project_layout(root)
        session = await self.store.get_session(run_id)
        if session is None or Path(session.project_root).expanduser().resolve(strict=False) != root:
            raise TransitionError("run_id does not own project root")
        spec = get_stage_spec(stage)
        if stage != self._session_skill(session):
            raise TransitionError("stage does not match current session stage")
        if spec.requires_user_checkpoint:
            raise TransitionError("stage requires user checkpoint")

        inspection = inspect_chain_marker(str(root))
        if (
            inspection.classification == "valid"
            and inspection.marker.get("run_id") != run_id
        ):
            raise TransitionError("marker belongs to another run")
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

    @staticmethod
    def _write_journal(root: Path, journal: dict[str, Any], phase: str) -> None:
        journal["phase"] = phase
        atomic_write_text(
            TransitionController._journal_path(root),
            json.dumps(journal, indent=2, ensure_ascii=False),
        )

    def matches_transition_retry(
        self,
        project_root: str,
        *,
        transition_id: str,
        run_id: str,
        claim_id: str,
        from_stage: str,
        expected_revision: int,
    ) -> bool:
        """Return whether a durable journal already owns this exact retry."""
        root = Path(project_root).expanduser().resolve(strict=False)
        journal = self._read_json(self._journal_path(root))
        return bool(
            journal
            and journal.get("phase")
            in {
                "PREPARED",
                "DB_COMMITTED",
                "EVENT_WRITTEN",
                "CLAIM_WRITTEN",
                "STATE_WRITTEN",
                "MARKER_WRITTEN",
            }
            and all(
                journal.get(key) == expected
                for key, expected in (
                    ("transition_id", transition_id),
                    ("run_id", run_id),
                    ("claim_id", claim_id),
                    ("from_stage", from_stage),
                    ("expected_revision", expected_revision),
                )
            )
        )

    @staticmethod
    def _json_hash(value: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _event_evidence(root: Path, event_id: str) -> str:
        path = root / ".samvil" / "events.jsonl"
        if not path.is_file():
            return ""
        try:
            with path.open(encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    try:
                        row = json.loads(line)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if isinstance(row, dict) and row.get("event_id") == event_id:
                        return f".samvil/events.jsonl:{line_number}"
        except OSError:
            return ""
        return ""

    @staticmethod
    def _validate_transition_id(transition_id: str) -> None:
        if (
            not _SAFE_TRANSITION_ID.fullmatch(transition_id)
            or sanitize_event_data(transition_id) != transition_id
        ):
            raise TransitionError(
                "transition_id must be a bounded non-sensitive identifier"
            )

    @staticmethod
    def _validate_journal_integrity(journal: dict[str, Any]) -> None:
        try:
            transition_id = str(journal["transition_id"])
            from_stage = str(journal["from_stage"])
            to_stage = str(journal["to_stage"])
            event_payload = journal["event_payload"]
            if not isinstance(event_payload, dict):
                raise ValueError("event_payload")
            terminal = to_stage == "complete" and get_stage_spec(from_stage).terminal
            expected_target = "complete" if terminal else state_stage_for(to_stage)
            expected_event_id = f"event-{transition_id}"
            expected_hash = hashlib.sha256(
                json.dumps(event_payload, sort_keys=True).encode()
            ).hexdigest()
        except (KeyError, TypeError, ValueError) as exc:
            raise TransitionError("transition journal integrity check failed") from exc
        if (
            journal.get("target_state") != expected_target
            or journal.get("event_id") != expected_event_id
            or journal.get("event_payload_hash") != expected_hash
            or event_payload.get("transition_id") != transition_id
            or event_payload.get("from_stage") != from_stage
            or event_payload.get("to_stage") != to_stage
        ):
            raise TransitionError("transition journal integrity check failed")
        for payload_key, hash_key in (
            ("source_project_state", "source_project_state_hash"),
            ("target_project_state", "target_project_state_hash"),
            ("source_marker", "source_marker_hash"),
            ("target_marker", "target_marker_hash"),
            ("session_snapshot", "session_snapshot_hash"),
            ("claim_snapshot", "claim_snapshot_hash"),
        ):
            if payload_key not in journal and hash_key not in journal:
                continue
            payload = journal.get(payload_key)
            if (
                not isinstance(payload, dict)
                or journal.get(hash_key)
                != TransitionController._json_hash(payload)
            ):
                raise TransitionError("transition journal integrity check failed")

    async def _reconstruct_lost_db_context(
        self,
        root: Path,
        journal: dict[str, Any],
    ) -> None:
        """Recreate one transition only when journal and both file SSOTs agree."""
        if journal.get("phase") == "PREPARED":
            raise TransitionError("PREPARED journal cannot prove a committed DB transition")
        required_objects = (
            "source_project_state",
            "target_project_state",
            "source_marker",
            "target_marker",
            "session_snapshot",
            "claim_snapshot",
        )
        if any(not isinstance(journal.get(key), dict) for key in required_objects):
            raise TransitionError("lost DB recovery evidence is incomplete")
        if not str(journal.get("event_timestamp") or ""):
            raise TransitionError("lost DB recovery event timestamp is missing")

        source_state = dict(journal["source_project_state"])
        target_state = dict(journal["target_project_state"])
        source_marker = dict(journal["source_marker"])
        target_marker = dict(journal["target_marker"])
        session_snapshot = dict(journal["session_snapshot"])
        claim_snapshot = dict(journal["claim_snapshot"])
        run_id = str(journal["run_id"])
        from_stage = str(journal["from_stage"])
        expected_revision = int(journal["expected_revision"])

        current_state = self._read_json(self._state_path(root))
        current_marker = self._read_json(root / ".samvil" / "next-skill.json")
        if self._json_hash(current_state) not in {
            self._json_hash(source_state),
            self._json_hash(target_state),
        }:
            raise TransitionError("lost DB recovery project state is ambiguous")
        if self._json_hash(current_marker) not in {
            self._json_hash(source_marker),
            self._json_hash(target_marker),
        }:
            raise TransitionError("lost DB recovery marker is ambiguous")
        if (
            str(source_state.get("session_id") or "") != run_id
            or str(session_snapshot.get("id") or "") != run_id
            or str(session_snapshot.get("project_root") or "") != str(root)
            or str(claim_snapshot.get("session_id") or "") != run_id
            or str(claim_snapshot.get("stage") or "") != from_stage
            or int(claim_snapshot.get("marker_revision", -1)) != expected_revision
            or str(claim_snapshot.get("claim_id") or "") != str(journal["claim_id"])
            or str(source_marker.get("run_id") or "") != run_id
            or str(source_marker.get("from_stage") or "") != from_stage
            or str(source_marker.get("status") or "") != "in_progress"
            or int(source_marker.get("revision", -1)) != expected_revision
            or str(target_state.get("stage_transition_id") or "")
            != str(journal["transition_id"])
            or str(target_state.get("current_stage") or "")
            != str(journal["target_state"])
            or str(target_marker.get("run_id") or "") != run_id
            or int(target_marker.get("revision", -1)) != expected_revision + 1
        ):
            raise TransitionError("lost DB recovery evidence is inconsistent")

        await self.store.reconstruct_committed_transition(
            project_root=str(root),
            session_snapshot=session_snapshot,
            claim_snapshot=claim_snapshot,
            event_id=str(journal["event_id"]),
            event_type=str(journal["event_type"]),
            event_stage=str(journal["target_state"]),
            event_data=dict(journal["event_payload"]),
            event_timestamp=str(journal["event_timestamp"]),
            transition_id=str(journal["transition_id"]),
            active_skill=(
                "" if journal["to_stage"] == "complete" else str(journal["to_stage"])
            ),
        )

    async def _authoritative_journal_context(
        self,
        root: Path,
        journal: dict[str, Any],
    ) -> tuple[dict[str, Any], Any | None]:
        self._validate_journal_integrity(journal)
        run_id = str(journal["run_id"])
        from_stage = str(journal["from_stage"])
        target_state = str(journal["target_state"])
        event_id = str(journal["event_id"])
        session = await self.store.get_session(run_id)
        if session is None:
            await self._reconstruct_lost_db_context(root, journal)
            session = await self.store.get_session(run_id)
        if session is None or Path(session.project_root).expanduser().resolve(strict=False) != root:
            raise TransitionError("transition journal run does not own project root")

        persisted_event = await self.store.get_event_by_id(event_id)
        if persisted_event is not None:
            if (
                persisted_event.session_id != run_id
                or persisted_event.stage.value != target_state
                or persisted_event.data.get("transition_id") != journal["transition_id"]
                or persisted_event.data.get("from_stage") != from_stage
                or persisted_event.data.get("to_stage") != journal["to_stage"]
            ):
                raise TransitionError("transition journal integrity check failed")
            try:
                journal.update(
                    {
                        "claim_id": str(persisted_event.data["claim_id"]),
                        "expected_revision": int(persisted_event.data["expected_revision"]),
                        "host_name": str(persisted_event.data["host_name"]),
                        "event_payload": dict(persisted_event.data),
                        "event_type": persisted_event.event_type.value,
                        "event_timestamp": persisted_event.timestamp,
                        "event_payload_hash": hashlib.sha256(
                            json.dumps(persisted_event.data, sort_keys=True).encode()
                        ).hexdigest(),
                    }
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise TransitionError("persisted transition metadata is incomplete") from exc
        else:
            inspection = inspect_chain_marker(str(root))
            if (
                inspection.classification != "valid"
                or inspection.marker.get("run_id") != run_id
                or self._marker_revision(inspection) != int(journal["expected_revision"])
            ):
                raise TransitionError("transition journal does not match active marker")
            journal["host_name"] = str(inspection.marker.get("host_name") or "codex_cli")

        claim = await self.store.get_stage_claim(
            run_id,
            from_stage,
            int(journal["expected_revision"]),
        )
        if claim is None or claim["claim_id"] != journal["claim_id"]:
            raise TransitionError("transition journal does not match stage claim")
        return journal, persisted_event

    async def _finish_materialization(
        self,
        root: Path,
        journal: dict[str, Any],
    ) -> dict[str, Any]:
        from .server import _append_project_event, _canonical_project_event_exists

        journal, persisted_event = await self._authoritative_journal_context(root, journal)
        transition_id = str(journal["transition_id"])
        run_id = str(journal["run_id"])
        claim_id = str(journal["claim_id"])
        from_stage = str(journal["from_stage"])
        to_stage = str(journal["to_stage"])
        target_state = str(journal["target_state"])
        event_id = str(journal["event_id"])
        if persisted_event is None:
            raise TransitionError("transition journal integrity check failed")
        event_payload = dict(persisted_event.data)
        event_type = persisted_event.event_type.value
        timestamp = persisted_event.timestamp
        journal.update(
            {
                "event_payload": event_payload,
                "event_type": event_type,
                "event_timestamp": timestamp,
                "event_payload_hash": hashlib.sha256(
                    json.dumps(event_payload, sort_keys=True).encode()
                ).hexdigest(),
            }
        )
        expected_revision = int(journal["expected_revision"])
        host_name = str(journal["host_name"])

        evidence = await asyncio.to_thread(self._event_evidence, root, event_id)
        if not evidence:
            exists = await asyncio.to_thread(
                _canonical_project_event_exists,
                root,
                event_id,
            )
            if not exists:
                evidence = await asyncio.to_thread(
                    _append_project_event,
                    root,
                    timestamp=timestamp,
                    event_type=event_type,
                    stage=target_state,
                    session_id=run_id,
                    data=event_payload,
                    event_id=event_id,
                )
            else:
                evidence = await asyncio.to_thread(
                    self._event_evidence, root, event_id
                )
        if not evidence:
            raise TransitionError("canonical transition event evidence is missing")
        journal["event_evidence"] = evidence
        self._write_journal(root, journal, "EVENT_WRITTEN")

        ledger = ClaimLedger(root / ".samvil" / "claims.jsonl")
        ledger.append_transition_claim(
            transition_id=transition_id,
            subject=f"stage:{to_stage}",
            statement=f"{from_stage} transitioned to {to_stage}",
            authority_file=".samvil/events.jsonl",
            evidence=[evidence],
        )
        self._write_journal(root, journal, "CLAIM_WRITTEN")

        target_project_state = journal.get("target_project_state")
        if isinstance(target_project_state, dict):
            current_state = self._read_json(self._state_path(root))
            source_project_state = journal.get("source_project_state")
            if not isinstance(source_project_state, dict):
                raise TransitionError("transition journal source state is missing")
            transition_keys = (
                "session_id",
                "current_stage",
                "completed_stages",
                "stage_transition_id",
                "transition_revision",
            )

            def transition_projection(value: dict[str, Any]) -> dict[str, Any]:
                return {key: value.get(key) for key in transition_keys}

            current_projection = transition_projection(current_state)
            allowed_projections = (
                transition_projection(source_project_state),
                transition_projection(target_project_state),
            )
            if current_projection not in allowed_projections:
                raise TransitionError("project state changed during transition recovery")
            state = dict(current_state)
            for key in transition_keys:
                if key in target_project_state:
                    state[key] = target_project_state[key]
                else:
                    state.pop(key, None)
        else:
            state = self._read_json(self._state_path(root))
            completed = list(state.get("completed_stages") or [])
            try:
                from_state = state_stage_for(from_stage)
            except ValueError:
                from_state = from_stage.removeprefix("samvil-")
            if from_state not in completed:
                completed.append(from_state)
            state.update(
                {
                    "current_stage": target_state,
                    "completed_stages": completed,
                    "stage_transition_id": transition_id,
                    "transition_revision": expected_revision + 1,
                }
            )
        atomic_write_text(
            self._state_path(root),
            json.dumps(state, indent=2, ensure_ascii=False),
        )
        self._write_journal(root, journal, "STATE_WRITTEN")

        terminal = to_stage == "complete"
        marker = journal.get("target_marker")
        if not isinstance(marker, dict):
            marker = build_driver_marker(
                run_id=run_id,
                revision=expected_revision + 1,
                status="terminal" if terminal else "ready",
                host_name=host_name,
                from_stage=from_stage,
                next_skill="" if terminal else to_stage,
                reason=f"{from_stage} completed",
            )
        write_driver_marker(str(root), marker)
        self._write_journal(root, journal, "MARKER_WRITTEN")

        receipt = {
            "transition_id": transition_id,
            "status": "committed",
            "event_id": event_id,
            "claim_id": claim_id,
            "from_stage": from_stage,
            "to_stage": to_stage,
            "marker_revision": expected_revision + 1,
        }
        receipt = await self.store.save_transition_receipt(
            transition_id,
            run_id,
            receipt,
        )
        await self.store.mark_stage_claim_completed(claim_id, transition_id)
        await self.store.acknowledge_pending_project_event(event_id)
        self._journal_path(root).unlink(missing_ok=True)
        return receipt

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
        resolved_transition_id = transition_id or f"transition-{uuid.uuid4().hex}"
        self._validate_transition_id(resolved_transition_id)
        async with stage_transition_lock(self.store, run_id):
            return await self._commit_stage_transition_locked(
                project_root,
                run_id,
                claim_id,
                from_stage,
                to_stage,
                expected_revision,
                event_type=event_type,
                data=data,
                transition_id=resolved_transition_id,
                host_name=host_name,
            )

    async def _commit_stage_transition_locked(
        self,
        project_root: str,
        run_id: str,
        claim_id: str,
        from_stage: str,
        to_stage: str,
        expected_revision: int,
        *,
        event_type: str,
        data: dict[str, Any] | None,
        transition_id: str,
        host_name: str,
    ) -> dict[str, Any]:
        root = Path(project_root).expanduser().resolve(strict=False)
        self._validate_project_layout(root)
        session = await self.store.get_session(run_id)
        if session is None or Path(session.project_root).expanduser().resolve(strict=False) != root:
            raise TransitionError("run_id does not own project root")
        existing_record = await self.store.get_transition_receipt_record(transition_id)
        if existing_record is not None:
            owner, existing = existing_record
            if owner != run_id:
                raise TransitionError("transition receipt belongs to another run")
            if any(
                existing.get(key) != expected
                for key, expected in (
                    ("claim_id", claim_id),
                    ("from_stage", from_stage),
                    ("to_stage", to_stage),
                    ("marker_revision", expected_revision + 1),
                )
            ):
                raise TransitionError("transition id conflicts with a different transition")
            await self.store.mark_stage_claim_completed(claim_id, transition_id)
            await self.store.acknowledge_pending_project_event(
                str(existing.get("event_id") or "")
            )
            journal = self._read_json(self._journal_path(root))
            if journal.get("transition_id") == transition_id:
                self._journal_path(root).unlink(missing_ok=True)
            return existing

        journal = self._read_json(self._journal_path(root))
        if journal:
            journal, persisted_event = await self._authoritative_journal_context(root, journal)
            if journal.get("transition_id") != transition_id:
                raise TransitionError("another transition journal is in progress")
            if any(
                journal.get(key) != expected
                for key, expected in (
                    ("run_id", run_id),
                    ("claim_id", claim_id),
                    ("from_stage", from_stage),
                    ("to_stage", to_stage),
                    ("expected_revision", expected_revision),
                )
            ):
                raise TransitionError("transition journal conflicts with retry")
            if journal.get("phase") != "PREPARED":
                return await self._finish_materialization(root, journal)
            transition_state = await self.store.get_session_transition_state(run_id)
            if transition_state == (str(journal["target_state"]), transition_id):
                event = persisted_event or await self.store.get_event_by_id(str(journal["event_id"]))
                if (
                    event is None
                    or event.session_id != run_id
                    or event.stage.value != str(journal["target_state"])
                    or event.data != journal["event_payload"]
                ):
                    raise TransitionError("transition journal integrity check failed")
                journal["event_timestamp"] = event.timestamp
                self._write_journal(root, journal, "DB_COMMITTED")
                return await self._finish_materialization(root, journal)

        terminal_completion = (
            to_stage == "complete" and get_stage_spec(from_stage).terminal
        )
        if not terminal_completion and not validate_stage_transition(from_stage, to_stage):
            raise TransitionError(f"invalid stage transition: {from_stage} -> {to_stage}")
        if self._session_skill(session) != from_stage:
            raise TransitionError("from_stage does not match current session stage")
        claim = await self.store.get_stage_claim(run_id, from_stage, expected_revision)
        if claim is None or claim["claim_id"] != claim_id:
            raise TransitionError("stage claim does not match transition")
        inspection = inspect_chain_marker(str(root))
        if (
            inspection.classification == "valid"
            and inspection.marker.get("run_id") != run_id
        ):
            raise TransitionError("marker belongs to another run")
        revision = self._marker_revision(inspection)
        if revision != expected_revision:
            raise TransitionError(f"stale marker revision: expected {expected_revision}, current {revision}")
        if from_stage == "samvil-qa":
            qa = self._read_json(root / ".samvil" / "qa-results.json")
            if not qa:
                return {
                    "transition_id": transition_id,
                    "status": "blocked",
                    "stage": "samvil-qa",
                    "reason": "missing QA evidence",
                    "claim_id": claim_id,
                    "from_stage": from_stage,
                    "to_stage": to_stage,
                    "marker_revision": expected_revision,
                }

        event_payload = sanitize_event_data(dict(data or {}))
        event_payload.update(
            {
                "transition_id": transition_id,
                "from_stage": from_stage,
                "to_stage": to_stage,
                "claim_id": claim_id,
                "expected_revision": expected_revision,
                "host_name": host_name,
            }
        )
        event_id = f"event-{transition_id}"
        target_state = "complete" if terminal_completion else state_stage_for(to_stage)
        source_project_state = self._read_json(self._state_path(root))
        source_state_run_id = str(source_project_state.get("session_id") or "")
        if source_state_run_id and source_state_run_id != run_id:
            raise TransitionError("project state session does not match transition run")
        target_project_state = dict(source_project_state) or {"session_id": run_id}
        target_project_state.setdefault("session_id", run_id)
        completed = list(target_project_state.get("completed_stages") or [])
        try:
            completed_stage = state_stage_for(from_stage)
        except ValueError:
            completed_stage = from_stage.removeprefix("samvil-")
        if completed_stage not in completed:
            completed.append(completed_stage)
        target_project_state.update(
            {
                "current_stage": target_state,
                "completed_stages": completed,
                "stage_transition_id": transition_id,
                "transition_revision": expected_revision + 1,
            }
        )
        source_marker = self._read_json(root / ".samvil" / "next-skill.json")
        target_marker = build_driver_marker(
            run_id=run_id,
            revision=expected_revision + 1,
            status="terminal" if to_stage == "complete" else "ready",
            host_name=host_name,
            from_stage=from_stage,
            next_skill="" if to_stage == "complete" else to_stage,
            reason=f"{from_stage} completed",
        )
        session_snapshot = {
            "id": session.id,
            "project_name": session.project_name,
            "project_root": str(root),
            "seed_version": session.seed_version,
            "samvil_tier": session.samvil_tier,
            "created_at": session.created_at,
        }
        claim_snapshot = dict(claim)
        journal = {
            "transition_id": transition_id,
            "run_id": run_id,
            "claim_id": claim_id,
            "expected_revision": expected_revision,
            "from_stage": from_stage,
            "to_stage": to_stage,
            "target_state": target_state,
            "event_id": event_id,
            "event_type": event_type,
            "event_payload": event_payload,
            "host_name": host_name,
            "event_payload_hash": hashlib.sha256(json.dumps(event_payload, sort_keys=True).encode()).hexdigest(),
            "source_project_state": source_project_state,
            "source_project_state_hash": self._json_hash(source_project_state),
            "target_project_state": target_project_state,
            "target_project_state_hash": self._json_hash(target_project_state),
            "source_marker": source_marker,
            "source_marker_hash": self._json_hash(source_marker),
            "target_marker": target_marker,
            "target_marker_hash": self._json_hash(target_marker),
            "session_snapshot": session_snapshot,
            "session_snapshot_hash": self._json_hash(session_snapshot),
            "claim_snapshot": claim_snapshot,
            "claim_snapshot_hash": self._json_hash(claim_snapshot),
            "phase": "PREPARED",
        }
        self._write_journal(root, journal, "PREPARED")

        transition = await self.store.save_event_and_update_stage(
            run_id,
            EventType(event_type),
            Stage(target_state),
            event_payload,
            expected_stage=session.current_stage,
            event_id=event_id,
            transition_id=transition_id,
            active_skill="" if terminal_completion else to_stage,
        )
        journal["event_timestamp"] = transition.event.timestamp
        self._write_journal(root, journal, "DB_COMMITTED")
        return await self._finish_materialization(root, journal)


__all__ = ["TransitionController", "TransitionError"]
