"""SQLite-backed event store for SAMVIL session persistence."""

from __future__ import annotations

import json
import uuid
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from .chain_markers import _build_chain_marker
from .claim_ledger import _locked
from .models import Event, EventType, Session, SeedVersion, Stage, StageTransition
from .ssot_io import atomic_write_text_unlocked

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    project_name TEXT NOT NULL,
    project_root TEXT DEFAULT '',
    seed_version INTEGER DEFAULT 1,
    current_stage TEXT DEFAULT 'interview',
    stage_transition_id TEXT DEFAULT '',
    samvil_tier TEXT DEFAULT 'standard',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    stage TEXT NOT NULL,
    data TEXT DEFAULT '{}',
    token_count INTEGER DEFAULT NULL,
    trusted_transition INTEGER NOT NULL DEFAULT 0,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS seed_versions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    seed_json TEXT NOT NULL,
    change_summary TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    UNIQUE(session_id, version)
);

CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(session_id, event_type);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_name);
CREATE INDEX IF NOT EXISTS idx_seed_versions_session ON seed_versions(session_id, version);
"""

# In-place migrations for already-initialized DBs. Initialization first
# introspects each table and executes only the statements whose target schema
# is absent. Keep the list short and strictly additive.
#
# - token_count column: added in v0.8.0.
# - samvil_tier rename: v3.2 glossary sweep. Old column name was the v3.1
#   field that actually held samvil_tier values (minimal/standard/...).
#   The rename aligns the DB with the settled vocabulary. The literal old
#   name must appear in the ALTER TABLE statement below, so both comment
#   and SQL are glossary-allow anchors.
TOKEN_COUNT_MIGRATION = "ALTER TABLE events ADD COLUMN token_count INTEGER DEFAULT NULL"
TIER_RENAME_MIGRATION = (
    "ALTER TABLE sessions RENAME COLUMN agent_tier TO samvil_tier"  # glossary-allow: rename source
)
PROJECT_ROOT_MIGRATION = (
    "ALTER TABLE sessions ADD COLUMN project_root TEXT DEFAULT ''"
)
STAGE_TRANSITION_ID_MIGRATION = (
    "ALTER TABLE sessions ADD COLUMN stage_transition_id TEXT DEFAULT ''"
)
TRUSTED_TRANSITION_MIGRATION = (
    "ALTER TABLE events ADD COLUMN trusted_transition INTEGER NOT NULL DEFAULT 0"
)
TRUSTED_TRANSITION_INDEX = """
CREATE INDEX IF NOT EXISTS idx_events_trusted_transition
ON events(session_id, trusted_transition, timestamp DESC)
"""


def _migration_plan(
    *,
    events_columns: set[str],
    sessions_columns: set[str],
) -> list[str]:
    """Return only schema changes missing from the current database."""
    plan: list[str] = []
    if "token_count" not in events_columns:
        plan.append(TOKEN_COUNT_MIGRATION)
    if "trusted_transition" not in events_columns:
        plan.append(TRUSTED_TRANSITION_MIGRATION)
    if "samvil_tier" not in sessions_columns and "agent_tier" in sessions_columns:  # glossary-allow: legacy column detection
        plan.append(TIER_RENAME_MIGRATION)
        sessions_columns = (sessions_columns - {"agent_tier"}) | {"samvil_tier"}  # glossary-allow: migration projection
    if "project_root" not in sessions_columns:
        plan.append(PROJECT_ROOT_MIGRATION)
    if "stage_transition_id" not in sessions_columns:
        plan.append(STAGE_TRANSITION_ID_MIGRATION)
    return plan


async def _table_columns(db: aiosqlite.Connection, table: str) -> set[str]:
    cursor = await db.execute(f"PRAGMA table_info({table})")
    return {str(row[1]) for row in await cursor.fetchall()}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return uuid.uuid4().hex[:12]


def _restore_legacy_recovery_files(
    backups: dict[Path, str | None],
) -> None:
    """Restore file contents while the caller still holds each file lock."""
    failures: list[Exception] = []
    for path, original in reversed(list(backups.items())):
        try:
            if original is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write_text_unlocked(path, original)
        except Exception as exc:
            failures.append(exc)
    if failures:
        details = "; ".join(str(failure) for failure in failures)
        raise RuntimeError(
            f"legacy recovery compensation failed: {details}"
        ) from ExceptionGroup("legacy recovery compensation failures", failures)


def _prepare_legacy_recovery_files(
    sessions: list[tuple[str, str]],
    locks: ExitStack,
    *,
    locked_roots: set[Path] | None = None,
) -> dict[Path, str | None]:
    """Rewind project SSOTs before the matching legacy DB sessions."""
    backups: dict[Path, str | None] = {}
    roots: dict[Path, str] = {}
    for session_id, raw_root in sessions:
        if not raw_root:
            continue
        root = Path(raw_root).expanduser().resolve(strict=False)
        if root.is_dir():
            roots.setdefault(root, session_id)
    try:
        for root, session_id in sorted(roots.items(), key=lambda item: str(item[0])):
            state_path = root / "project.state.json"
            marker_path = root / ".samvil" / "next-skill.json"
            if not state_path.exists() and not marker_path.parent.is_dir():
                continue
            if locked_roots is None or root not in locked_roots:
                locks.enter_context(_locked(state_path))
                locks.enter_context(_locked(marker_path))

            original_state = (
                state_path.read_text(encoding="utf-8")
                if state_path.exists()
                else None
            )
            original_marker = (
                marker_path.read_text(encoding="utf-8")
                if marker_path.exists()
                else None
            )
            backups[state_path] = original_state
            backups[marker_path] = original_marker

            state: dict[str, Any]
            if original_state is None:
                state = {"session_id": session_id}
            else:
                parsed_state = json.loads(original_state)
                if not isinstance(parsed_state, dict):
                    raise ValueError(
                        f"legacy recovery state must be an object: {state_path}"
                    )
                state = parsed_state
            state["current_stage"] = "interview"
            state["completed_stages"] = []
            state["stage_transition_id"] = ""
            state["recovery_reason"] = "trusted_transition_revalidation"
            atomic_write_text_unlocked(state_path, json.dumps(state, indent=2))

            host_name: str | None = None
            if original_marker is not None:
                try:
                    parsed_marker = json.loads(original_marker)
                except json.JSONDecodeError:
                    parsed_marker = None
                if isinstance(parsed_marker, dict):
                    raw_host = parsed_marker.get("host_name")
                    if isinstance(raw_host, str) and raw_host.strip():
                        host_name = raw_host
            marker = _build_chain_marker(host_name, "samvil")
            atomic_write_text_unlocked(marker_path, json.dumps(marker, indent=2))
    except Exception as recovery_error:
        try:
            _restore_legacy_recovery_files(backups)
        except Exception as compensation_error:
            raise RuntimeError(
                "legacy recovery failed and compensation was incomplete: "
                f"{recovery_error}; {compensation_error}"
            ) from ExceptionGroup(
                "legacy recovery and compensation failures",
                [recovery_error, compensation_error],
            )
        raise
    return backups


class EventStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.executescript(SCHEMA)
            legacy_recovery_backups: dict[Path, str | None] = {}
            legacy_recovery_locks = ExitStack()
            try:
                await db.execute("BEGIN IMMEDIATE")
                events_columns = await _table_columns(db, "events")
                sessions_columns = await _table_columns(db, "sessions")
                migrations = _migration_plan(
                    events_columns=events_columns,
                    sessions_columns=sessions_columns,
                )
                trusted_transition_added = TRUSTED_TRANSITION_MIGRATION in migrations
                for migration in migrations:
                    await db.execute(migration)
                if trusted_transition_added:
                    # Legacy JSON flags cannot prove provenance. Rewind only
                    # once, while adding the provenance column, so existing
                    # sessions can replay gates instead of remaining stranded
                    # at a stage whose prerequisites are now intentionally
                    # untrusted.
                    recovery_cursor = await db.execute(
                        """SELECT id, project_root FROM sessions
                        WHERE current_stage != 'interview' AND project_root != ''"""
                    )
                    legacy_recovery_backups = _prepare_legacy_recovery_files(
                        [
                            (str(row[0]), str(row[1] or ""))
                            for row in await recovery_cursor.fetchall()
                        ],
                        legacy_recovery_locks,
                    )
                    await db.execute(
                        """UPDATE sessions
                        SET current_stage = 'interview', stage_transition_id = ''
                        WHERE current_stage != 'interview' AND project_root != ''"""
                    )
                index_cursor = await db.execute(
                    "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
                    ("idx_events_trusted_transition",),
                )
                index_row = await index_cursor.fetchone()
                if index_row is not None and "json_extract" in str(index_row[0]):
                    await db.execute("DROP INDEX idx_events_trusted_transition")
                await db.execute(TRUSTED_TRANSITION_INDEX)
                await db.commit()
            except Exception:
                await db.rollback()
                try:
                    if legacy_recovery_backups:
                        _restore_legacy_recovery_files(legacy_recovery_backups)
                finally:
                    legacy_recovery_locks.close()
                raise
            else:
                legacy_recovery_locks.close()

    async def recover_legacy_session_project_root(
        self,
        session_id: str,
        project_root: str,
    ) -> bool:
        """Attach a rootless legacy session and replay its trust gates safely."""
        normalized_root = str(Path(project_root).expanduser().resolve())
        root = Path(normalized_root)
        state_path = root / "project.state.json"
        legacy_state_path = root / ".samvil" / "state.json"
        marker_path = root / ".samvil" / "next-skill.json"

        backups: dict[Path, str | None] = {}
        locks = ExitStack()
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("BEGIN IMMEDIATE")
                cursor = await db.execute(
                    """SELECT project_root, current_stage FROM sessions
                    WHERE id = ?""",
                    (session_id,),
                )
                row = await cursor.fetchone()
                if row is None or str(row[0] or ""):
                    await db.rollback()
                    return False
                locks.enter_context(_locked(state_path))
                locks.enter_context(_locked(marker_path))
                locks.enter_context(_locked(legacy_state_path))
                parsed_state = None
                for candidate in (state_path, legacy_state_path):
                    try:
                        candidate_state = json.loads(
                            candidate.read_text(encoding="utf-8")
                        )
                    except (json.JSONDecodeError, OSError, UnicodeError):
                        continue
                    if isinstance(candidate_state, dict) and str(
                        candidate_state.get("session_id") or ""
                    ):
                        parsed_state = candidate_state
                        break
                if not isinstance(parsed_state, dict):
                    await db.rollback()
                    return False
                file_session_id = str(parsed_state.get("session_id") or "")
                if file_session_id != session_id:
                    await db.rollback()
                    return False
                file_stage = str(parsed_state.get("current_stage") or "")
                try:
                    parsed_marker = json.loads(marker_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError, UnicodeError):
                    parsed_marker = None
                marker_skill = (
                    str(parsed_marker.get("next_skill") or "")
                    if isinstance(parsed_marker, dict)
                    else ""
                )
                trusted_cursor = await db.execute(
                    """SELECT COUNT(*) FROM events
                    WHERE session_id = ? AND trusted_transition = 1""",
                    (session_id,),
                )
                trusted_count = int((await trusted_cursor.fetchone())[0])
                current_stage = str(row[1] or "interview")
                needs_revalidation = trusted_count == 0 and (
                    current_stage != "interview"
                    or (file_stage and file_stage != "interview")
                    or marker_skill != "samvil-interview"
                )
                if needs_revalidation:
                    backups = _prepare_legacy_recovery_files(
                        [(session_id, normalized_root)],
                        locks,
                        locked_roots={root},
                    )
                    await db.execute(
                        """UPDATE sessions
                        SET project_root = ?, current_stage = 'interview',
                            stage_transition_id = '', updated_at = ?
                        WHERE id = ? AND project_root = ''""",
                        (normalized_root, _now(), session_id),
                    )
                else:
                    await db.execute(
                        """UPDATE sessions SET project_root = ?, updated_at = ?
                        WHERE id = ? AND project_root = ''""",
                        (normalized_root, _now(), session_id),
                    )
                await db.commit()
                return needs_revalidation
            except Exception:
                await db.rollback()
                if backups:
                    _restore_legacy_recovery_files(backups)
                raise
            finally:
                locks.close()

    # ── Sessions ──────────────────────────────────────────

    async def create_session(
        self,
        project_name: str,
        samvil_tier: str = "standard",
        project_root: str = "",
    ) -> Session:
        normalized_root = (
            str(Path(project_root).expanduser().resolve()) if project_root else ""
        )
        session = Session(
            id=_uuid(),
            project_name=project_name,
            project_root=normalized_root,
            samvil_tier=samvil_tier,
            created_at=_now(),
            updated_at=_now(),
        )
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("BEGIN")
            await db.execute(
                "INSERT INTO sessions (id, project_name, project_root, seed_version, current_stage, samvil_tier, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (session.id, session.project_name, session.project_root, session.seed_version, session.current_stage, session.samvil_tier, session.created_at, session.updated_at),
            )
            await db.commit()
        return session

    async def get_session(self, session_id: str) -> Session | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
            row = await cursor.fetchone()
            if not row:
                return None
            return Session(
                id=row["id"],
                project_name=row["project_name"],
                project_root=row["project_root"],
                seed_version=row["seed_version"],
                current_stage=Stage(row["current_stage"]),
                samvil_tier=row["samvil_tier"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    async def find_session_by_project(
        self,
        project_name: str,
        project_root: str | None = None,
    ) -> Session | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if project_root:
                normalized_root = str(Path(project_root).expanduser().resolve())
                cursor = await db.execute(
                    "SELECT * FROM sessions WHERE project_name = ? AND project_root = ? ORDER BY updated_at DESC LIMIT 1",
                    (project_name, normalized_root),
                )
                row = await cursor.fetchone()
            else:
                cursor = await db.execute(
                    "SELECT * FROM sessions WHERE project_name = ? ORDER BY updated_at DESC LIMIT 2",
                    (project_name,),
                )
                rows = await cursor.fetchall()
                row = rows[0] if len(rows) == 1 else None
            if not row:
                return None
            return Session(
                id=row["id"],
                project_name=row["project_name"],
                project_root=row["project_root"],
                seed_version=row["seed_version"],
                current_stage=Stage(row["current_stage"]),
                samvil_tier=row["samvil_tier"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    async def list_sessions(self, limit: int = 10) -> list[Session]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)
            )
            rows = await cursor.fetchall()
            return [
                Session(
                    id=r["id"],
                    project_name=r["project_name"],
                    project_root=r["project_root"],
                    seed_version=r["seed_version"],
                    current_stage=Stage(r["current_stage"]),
                    samvil_tier=r["samvil_tier"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
                for r in rows
            ]

    async def update_session_stage(self, session_id: str, stage: Stage) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("BEGIN")
            await db.execute(
                "UPDATE sessions SET current_stage = ?, stage_transition_id = '', updated_at = ? WHERE id = ?",
                (stage.value, _now(), session_id),
            )
            await db.commit()

    async def update_session_seed_version(self, session_id: str, version: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("BEGIN")
            await db.execute(
                "UPDATE sessions SET seed_version = ?, updated_at = ? WHERE id = ?",
                (version, _now(), session_id),
            )
            await db.commit()

    # ── Events ────────────────────────────────────────────

    async def save_event(
        self,
        session_id: str,
        event_type: EventType,
        stage: Stage,
        data: dict | None = None,
        token_count: int | None = None,
    ) -> Event:
        event = Event(
            id=_uuid(),
            session_id=session_id,
            event_type=event_type,
            stage=stage,
            data=data or {},
            timestamp=_now(),
        )
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("BEGIN")
            await db.execute(
                "INSERT INTO events (id, session_id, event_type, stage, data, token_count, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (event.id, event.session_id, event.event_type.value, event.stage.value, json.dumps(event.data), token_count, event.timestamp),
            )
            await db.commit()
        return event

    async def save_event_and_update_stage(
        self,
        session_id: str,
        event_type: EventType,
        stage: Stage,
        data: dict | None = None,
        token_count: int | None = None,
        expected_stage: Stage | None = None,
    ) -> StageTransition:
        """Persist an event and its session-stage transition atomically."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("BEGIN IMMEDIATE")
                event = Event(
                    id=_uuid(),
                    session_id=session_id,
                    event_type=event_type,
                    stage=stage,
                    data=data or {},
                    timestamp=_now(),
                )
                session_cursor = await db.execute(
                    "SELECT current_stage, stage_transition_id FROM sessions WHERE id = ?",
                    (session_id,),
                )
                session_row = await session_cursor.fetchone()
                if session_row is None:
                    raise ValueError(f"session {session_id} not found")
                previous_stage = Stage(str(session_row[0]))
                previous_transition_id = str(session_row[1] or "")
                if expected_stage is not None and previous_stage != expected_stage:
                    raise ValueError(
                        "stage transition conflict: "
                        f"expected {expected_stage.value}, found {previous_stage.value}"
                    )
                await db.execute(
                    "INSERT INTO events (id, session_id, event_type, stage, data, token_count, trusted_transition, timestamp) VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
                    (
                        event.id,
                        event.session_id,
                        event.event_type.value,
                        event.stage.value,
                        json.dumps(event.data),
                        token_count,
                        event.timestamp,
                    ),
                )
                cursor = await db.execute(
                    "UPDATE sessions SET current_stage = ?, stage_transition_id = ?, updated_at = ? WHERE id = ?",
                    (stage.value, event.id, event.timestamp, session_id),
                )
                if cursor.rowcount != 1:
                    raise ValueError(f"session {session_id} not found")
                await db.commit()
            except Exception:
                await db.rollback()
                raise
        return StageTransition(
            event=event,
            previous_stage=previous_stage,
            previous_transition_id=previous_transition_id,
        )

    async def delete_event(self, event_id: str) -> bool:
        """Compensate an event insert that could not reach the file SSOT."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("BEGIN")
            cursor = await db.execute("DELETE FROM events WHERE id = ?", (event_id,))
            await db.commit()
            return cursor.rowcount == 1

    async def delete_event_and_restore_stage(
        self,
        transition: StageTransition,
    ) -> bool:
        """Atomically compensate a DB event and its matching stage update.

        The unique event id is the transition ownership token. Compensation
        restores the stage observed inside the original write transaction only
        while that event still owns the latest transition.
        """
        event = transition.event
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("BEGIN IMMEDIATE")
                event_cursor = await db.execute(
                    "SELECT 1 FROM events WHERE id = ? AND session_id = ?",
                    (event.id, event.session_id),
                )
                event_row = await event_cursor.fetchone()
                session_cursor = await db.execute(
                    "SELECT current_stage, stage_transition_id FROM sessions WHERE id = ?",
                    (event.session_id,),
                )
                session_row = await session_cursor.fetchone()
                if event_row is None or session_row is None:
                    await db.rollback()
                    return False
                current_stage = str(session_row[0])
                current_transition_id = str(session_row[1] or "")
                if (
                    current_stage != event.stage.value
                    or current_transition_id != event.id
                ):
                    await db.rollback()
                    return False
                deleted = await db.execute(
                    "DELETE FROM events WHERE id = ? AND session_id = ?",
                    (event.id, event.session_id),
                )
                if deleted.rowcount != 1:
                    await db.rollback()
                    return False
                restored = await db.execute(
                    """UPDATE sessions
                    SET current_stage = ?, stage_transition_id = ?, updated_at = ?
                    WHERE id = ? AND current_stage = ? AND stage_transition_id = ?""",
                    (
                        transition.previous_stage.value,
                        transition.previous_transition_id,
                        _now(),
                        event.session_id,
                        event.stage.value,
                        event.id,
                    ),
                )
                if restored.rowcount != 1:
                    await db.rollback()
                    return False
                await db.commit()
                return True
            except Exception:
                await db.rollback()
                raise

    async def get_events(
        self,
        session_id: str,
        event_type: EventType | None = None,
        limit: int | None = 50,
    ) -> list[Event]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if event_type and limit is None:
                cursor = await db.execute(
                    "SELECT * FROM events WHERE session_id = ? AND event_type = ? ORDER BY timestamp DESC, rowid DESC",
                    (session_id, event_type.value),
                )
            elif event_type:
                cursor = await db.execute(
                    "SELECT * FROM events WHERE session_id = ? AND event_type = ? ORDER BY timestamp DESC, rowid DESC LIMIT ?",
                    (session_id, event_type.value, limit),
                )
            elif limit is None:
                cursor = await db.execute(
                    "SELECT * FROM events WHERE session_id = ? ORDER BY timestamp DESC, rowid DESC",
                    (session_id,),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM events WHERE session_id = ? ORDER BY timestamp DESC, rowid DESC LIMIT ?",
                    (session_id, limit),
                )
            rows = await cursor.fetchall()
            return [
                Event(
                    id=r["id"],
                    session_id=r["session_id"],
                    event_type=EventType(r["event_type"]),
                    stage=Stage(r["stage"]),
                    data=json.loads(r["data"]),
                    token_count=r["token_count"] if "token_count" in r.keys() else None,
                    timestamp=r["timestamp"],
                )
                for r in rows
            ]

    async def get_orchestration_events(
        self,
        session_id: str,
        recognized_event_types: set[str] | frozenset[str],
    ) -> list[Event]:
        """Load stage-decision rows without materializing unrelated telemetry."""
        event_types = sorted(recognized_event_types)
        if not event_types:
            return []
        placeholders = ", ".join("?" for _ in event_types)
        query = f"""
            SELECT * FROM events INDEXED BY idx_events_trusted_transition
            WHERE session_id = ?
              AND trusted_transition = 1
              AND (
                event_type IN ({placeholders})
                OR json_extract(data, '$.event_type_raw') IN ({placeholders})
              )
            ORDER BY timestamp DESC, rowid DESC
        """
        params = (session_id, *event_types, *event_types)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [
                Event(
                    id=row["id"],
                    session_id=row["session_id"],
                    event_type=EventType(row["event_type"]),
                    stage=Stage(row["stage"]),
                    data=json.loads(row["data"]),
                    token_count=(
                        row["token_count"] if "token_count" in row.keys() else None
                    ),
                    timestamp=row["timestamp"],
                )
                for row in rows
            ]

    # ── Seed Versions ─────────────────────────────────────

    async def save_seed_version(
        self,
        session_id: str,
        version: int,
        seed_json: str,
        change_summary: str = "",
    ) -> SeedVersion:
        sv = SeedVersion(
            id=_uuid(),
            session_id=session_id,
            version=version,
            seed_json=seed_json,
            change_summary=change_summary,
            created_at=_now(),
        )
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("BEGIN")
            await db.execute(
                "INSERT OR REPLACE INTO seed_versions (id, session_id, version, seed_json, change_summary, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (sv.id, sv.session_id, sv.version, sv.seed_json, sv.change_summary, sv.created_at),
            )
            await db.commit()
        return sv

    async def get_seed_versions(self, session_id: str) -> list[SeedVersion]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM seed_versions WHERE session_id = ? ORDER BY version ASC",
                (session_id,),
            )
            rows = await cursor.fetchall()
            return [
                SeedVersion(
                    id=r["id"],
                    session_id=r["session_id"],
                    version=r["version"],
                    seed_json=r["seed_json"],
                    change_summary=r["change_summary"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    # ── Integrity ─────────────────────────────────────────

    async def check_integrity(self) -> dict[str, str]:
        """Run PRAGMA integrity_check and return the result."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("PRAGMA integrity_check")
            row = await cursor.fetchone()
            status = row[0] if row else "unknown"
            return {"status": status}
