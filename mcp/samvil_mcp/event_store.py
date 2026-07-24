"""SQLite-backed event store for SAMVIL session persistence."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from .models import Event, EventType, Session, SeedVersion, Stage

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    project_name TEXT NOT NULL,
    project_root TEXT DEFAULT '',
    seed_version INTEGER DEFAULT 1,
    current_stage TEXT DEFAULT 'interview',
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


def _migration_plan(
    *,
    events_columns: set[str],
    sessions_columns: set[str],
) -> list[str]:
    """Return only schema changes missing from the current database."""
    plan: list[str] = []
    if "token_count" not in events_columns:
        plan.append(TOKEN_COUNT_MIGRATION)
    if "samvil_tier" not in sessions_columns and "agent_tier" in sessions_columns:  # glossary-allow: legacy column detection
        plan.append(TIER_RENAME_MIGRATION)
        sessions_columns = (sessions_columns - {"agent_tier"}) | {"samvil_tier"}  # glossary-allow: migration projection
    if "project_root" not in sessions_columns:
        plan.append(PROJECT_ROOT_MIGRATION)
    return plan


async def _table_columns(db: aiosqlite.Connection, table: str) -> set[str]:
    cursor = await db.execute(f"PRAGMA table_info({table})")
    return {str(row[1]) for row in await cursor.fetchall()}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return uuid.uuid4().hex[:12]


class EventStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.executescript(SCHEMA)
            events_columns = await _table_columns(db, "events")
            sessions_columns = await _table_columns(db, "sessions")
            for migration in _migration_plan(
                events_columns=events_columns,
                sessions_columns=sessions_columns,
            ):
                await db.execute(migration)
            await db.commit()

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
                "UPDATE sessions SET current_stage = ?, updated_at = ? WHERE id = ?",
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

    async def delete_event(self, event_id: str) -> bool:
        """Compensate an event insert that could not reach the file SSOT."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("BEGIN")
            cursor = await db.execute("DELETE FROM events WHERE id = ?", (event_id,))
            await db.commit()
            return cursor.rowcount == 1

    async def get_events(
        self,
        session_id: str,
        event_type: EventType | None = None,
        limit: int = 50,
    ) -> list[Event]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if event_type:
                cursor = await db.execute(
                    "SELECT * FROM events WHERE session_id = ? AND event_type = ? ORDER BY timestamp DESC LIMIT ?",
                    (session_id, event_type.value, limit),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM events WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
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
