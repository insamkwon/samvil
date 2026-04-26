"""Smoke tests for samvil-update (T3.3 ultra-thin migration).

The samvil-update skill is intentionally host-bound: it shells out to
`gh repo clone`, `rsync`, `mv`, and `rm -rf` to physically swap the
plugin cache. None of those can move into MCP without losing the skill's
purpose (P8 — graceful degradation against host failures).

What CAN be machine-pinned, and is pinned here, are the migration MCP
tools the thin skill delegates to instead of inlining migration logic:

- `migrate_seed_file` — used by `--migrate` (no version) for v2→v3 seeds.
  Must be idempotent (already-v3 seeds must not be rewritten) and must
  produce a `.v2.backup.json` next to the seed.
- `migrate_plan` / `migrate_apply` — used by `--migrate v3.2` for
  v3.1→v3.2 project migration. `migrate_plan` is dry-run, never mutates;
  `migrate_apply` performs the swap and writes a rollback snapshot.
- All three must be registered on the live `samvil_mcp.server.mcp` so
  the skill's MCP-call lines actually resolve.
- All three must degrade gracefully on bad input (return JSON error
  envelope, never raise — INV-5 / P8).

Shell-bound behaviors (gh CLI presence, rsync of plugin cache, cache
folder rename, old-version cleanup with empty-string guard) stay in the
skill body and are validated by running `/samvil:samvil-update`
interactively against a real install.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# ── Fixtures ───────────────────────────────────────────────────


def _v2_seed() -> dict:
    """A minimal pre-v3 seed (flat acceptance_criteria) ready to migrate.

    Intentionally omits `schema_version`: that mirrors real v2 seeds in
    the wild (the field was introduced in v3) and lets the migrator stamp
    `schema_version: "3.0"` via setdefault, which the user-visible
    output then reflects.
    """
    return {
        "name": "demo",
        "vision": "demo vision",
        "solution_type": "web-app",
        "tech_stack": {"framework": "nextjs"},
        "core_experience": {"primary_screen": "/"},
        "acceptance_criteria": [
            "user can sign in",
            "user sees dashboard",
        ],
        "features": [
            {
                "name": "auth",
                "description": "auth feature",
                "acceptance_criteria": ["sign in works"],
            }
        ],
    }


def _v3_seed() -> dict:
    """A minimal v3 seed (AC tree) — already migrated."""
    return {
        "schema_version": "3.0",
        "name": "demo",
        "vision": "demo vision",
        "solution_type": "web-app",
        "tech_stack": {"framework": "nextjs"},
        "core_experience": {"primary_screen": "/"},
        "features": [
            {
                "name": "auth",
                "description": "auth feature",
                "acceptance_criteria": [
                    {"id": "AC-1", "description": "sign in works", "children": []},
                ],
            }
        ],
    }


# ── migrate_seed_file (used by `/samvil:update --migrate`) ────


@pytest.mark.asyncio
async def test_migrate_seed_file_v2_to_v3_creates_backup(tmp_path: Path) -> None:
    """The v2→v3 seed migration must create a .v2.backup.json sidecar."""
    from samvil_mcp.server import migrate_seed_file as tool

    seed_path = tmp_path / "project.seed.json"
    seed_path.write_text(json.dumps(_v2_seed()), encoding="utf-8")

    payload = json.loads(await tool(str(seed_path)))
    assert payload.get("status") == "ok", payload
    assert payload["schema_version"].startswith("3."), payload
    assert payload["already_v3"] is False
    assert payload["backup_path"], "v2 seed must produce a backup"
    assert Path(payload["backup_path"]).exists()


@pytest.mark.asyncio
async def test_migrate_seed_file_is_idempotent_for_v3(tmp_path: Path) -> None:
    """Running --migrate on an already-v3 seed must be a no-op (no rewrite)."""
    from samvil_mcp.server import migrate_seed_file as tool

    seed_path = tmp_path / "project.seed.json"
    seed_path.write_text(json.dumps(_v3_seed()), encoding="utf-8")

    payload = json.loads(await tool(str(seed_path)))
    assert payload.get("status") == "ok", payload
    assert payload["already_v3"] is True
    # Idempotent migrations must not need a backup file
    assert not payload.get("backup_path"), payload


@pytest.mark.asyncio
async def test_migrate_seed_file_missing_path_returns_error() -> None:
    """INV-5 / P8: a missing seed path must return a structured error."""
    from samvil_mcp.server import migrate_seed_file as tool

    payload = json.loads(await tool("/nonexistent/project.seed.json"))
    assert "error" in payload
    assert "not found" in payload["error"].lower() or "no such" in payload["error"].lower()


# ── migrate_plan / migrate_apply (used by `--migrate v3.2`) ───


@pytest.mark.asyncio
async def test_migrate_plan_is_dry_run_only(tmp_path: Path) -> None:
    """migrate_plan must not write project files — dry-run only contract."""
    from samvil_mcp.server import migrate_plan as tool

    # Seed a v3.1-shaped project root so plan has something to scan
    seed = _v3_seed()
    seed["schema_version"] = "3.1"
    (tmp_path / "project.seed.json").write_text(json.dumps(seed), encoding="utf-8")

    raw = await tool(str(tmp_path))
    payload = json.loads(raw)
    # Plan returns a structured payload, not an exception
    assert isinstance(payload, dict)
    # No claims ledger or rollback snapshot should exist after a plan call
    assert not (tmp_path / ".samvil" / "claims.jsonl").exists()
    assert not (tmp_path / ".samvil" / "rollback").exists()


@pytest.mark.asyncio
async def test_migrate_apply_dry_run_does_not_mutate(tmp_path: Path) -> None:
    """migrate_apply with dry_run=True must not write the rollback snapshot."""
    from samvil_mcp.server import migrate_apply as tool

    seed = _v3_seed()
    seed["schema_version"] = "3.1"
    seed_path = tmp_path / "project.seed.json"
    seed_path.write_text(json.dumps(seed), encoding="utf-8")
    pre_text = seed_path.read_text()

    raw = await tool(str(tmp_path), dry_run=True)
    payload = json.loads(raw)
    assert isinstance(payload, dict)
    # dry-run must leave the seed file byte-identical
    assert seed_path.read_text() == pre_text


@pytest.mark.asyncio
async def test_migrate_apply_dry_run_returns_json_for_missing_root(
    tmp_path: Path,
) -> None:
    """Dry-run against a path with no project.seed.json must not raise.

    INV-5 / P8: even a path that doesn't exist or has no seed must come
    back as a structured JSON payload so the skill can branch on it.
    """
    from samvil_mcp.server import migrate_apply as tool

    empty_root = tmp_path / "empty-project"
    empty_root.mkdir()
    raw = await tool(str(empty_root), dry_run=True)
    payload = json.loads(raw)
    assert isinstance(payload, dict)
    # Dry-run guarantee: the seed file (if any) is unmodified. No seed
    # exists in this fixture, so just verify the dry_run flag is honoured
    # and no rollback snapshot was written under the empty root.
    assert payload.get("dry_run") is True or payload.get("error")
    assert not (empty_root / ".samvil" / "rollback").exists()


# ── Wiring on live MCP server ─────────────────────────────────


def test_update_skill_tools_registered_on_server() -> None:
    """All three migration tools the thin skill calls must be wired."""
    from samvil_mcp.server import mcp

    tool_map = mcp._tool_manager._tools  # FastMCP internal registry
    names = set(tool_map.keys())
    # `--migrate` (no version) → v2→v3 path
    assert "migrate_seed_file" in names
    # `--migrate v3.2` → v3.1→v3.2 path
    assert "migrate_plan" in names
    assert "migrate_apply" in names
    # save_event is used by the skill's best-effort observability lines
    assert "save_event" in names
