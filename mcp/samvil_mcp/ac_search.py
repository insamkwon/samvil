"""AC Tree BM25 full-text search — context-window efficiency for large seeds.

Stores AC leaves in a SQLite FTS5 database (.samvil/ac-search.db) so
samvil-build can fetch only the relevant leaves instead of passing the full
tree JSON to every dispatch_build_batch call.

Two-table design:
  ac_fts  — FTS5 virtual table indexed on `description` for BM25 ranking.
  ac_meta — Regular table storing leaf metadata (joined by rowid).

Usage pattern:
  1. index_ac_tree(project_root, features_json)  — once at build start
  2. search_ac_tree(project_root, query)          — per-batch to fetch relevant leaves
  3. search_ac_tree_by_feature(project_root, fid) — to get all leaves for one feature
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

DB_FILENAME = "ac-search.db"
SAMVIL_DIR = ".samvil"

_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS ac_fts USING fts5(
    description,
    tokenize='unicode61'
);

CREATE TABLE IF NOT EXISTS ac_meta (
    rowid INTEGER PRIMARY KEY,
    leaf_id TEXT NOT NULL,
    feature_id TEXT NOT NULL,
    feature_name TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ac_meta_feature ON ac_meta(feature_id);
"""


def _db_path(project_root: str) -> Path:
    d = (Path(project_root) if project_root else Path(".")) / SAMVIL_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d / DB_FILENAME


def _flatten_leaves(
    node: dict[str, Any],
    feature_id: str,
    feature_name: str,
) -> list[dict[str, Any]]:
    """Recursively extract leaf nodes (children == []) from an AC tree dict."""
    children = node.get("children") or []
    if not children:
        return [{
            "leaf_id": node.get("id", ""),
            "feature_id": feature_id,
            "feature_name": feature_name,
            "description": node.get("description", ""),
            "status": node.get("status", "pending"),
        }]
    result: list[dict[str, Any]] = []
    for child in children:
        result.extend(_flatten_leaves(child, feature_id, feature_name))
    return result


def index_ac_tree(project_root: str, features_json: str) -> dict[str, Any]:
    """Index all AC leaves from a features list into FTS5.

    Args:
        project_root: project root directory
        features_json: JSON list of {id, name, acceptance_criteria} dicts.
                       acceptance_criteria is the AC tree dict.

    Returns:
        {"indexed": int, "features": int}
    """
    try:
        features = json.loads(features_json)
        if not isinstance(features, list):
            return {"indexed": 0, "features": 0, "error": "features_json must be a list"}
    except (json.JSONDecodeError, ValueError) as e:
        return {"indexed": 0, "features": 0, "error": str(e)}

    db = _db_path(project_root)
    con = sqlite3.connect(str(db))
    try:
        con.executescript(_SCHEMA)
        con.execute("DELETE FROM ac_fts")
        con.execute("DELETE FROM ac_meta")

        total = 0
        for feat in features:
            fid = feat.get("id") or feat.get("name") or ""
            fname = feat.get("name") or fid
            ac_tree = feat.get("acceptance_criteria")
            if not ac_tree:
                continue
            leaves = _flatten_leaves(ac_tree, fid, fname)
            for leaf in leaves:
                cur = con.execute(
                    "INSERT INTO ac_fts(description) VALUES (?)",
                    (leaf["description"],),
                )
                rowid = cur.lastrowid
                con.execute(
                    "INSERT INTO ac_meta(rowid, leaf_id, feature_id, feature_name, status) VALUES (?,?,?,?,?)",
                    (rowid, leaf["leaf_id"], leaf["feature_id"], leaf["feature_name"], leaf["status"]),
                )
                total += 1

        con.commit()
        return {"indexed": total, "features": len(features)}
    finally:
        con.close()


def search_ac_tree(
    project_root: str,
    query: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """BM25 full-text search on AC leaf descriptions.

    Returns leaves ordered by relevance (best match first).
    Returns [] if DB not found or query is empty.
    """
    if not query or not query.strip():
        return []
    db = _db_path(project_root)
    if not db.exists():
        return []
    con = sqlite3.connect(str(db))
    try:
        rows = con.execute(
            """
            SELECT m.leaf_id, m.feature_id, m.feature_name, f.description, m.status
            FROM ac_fts f
            JOIN ac_meta m ON m.rowid = f.rowid
            WHERE ac_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()
        return [
            {
                "leaf_id": r[0],
                "feature_id": r[1],
                "feature_name": r[2],
                "description": r[3],
                "status": r[4],
            }
            for r in rows
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()


def search_ac_tree_by_feature(
    project_root: str,
    feature_id: str,
) -> list[dict[str, Any]]:
    """Return all AC leaves for a specific feature (exact match on feature_id)."""
    if not feature_id:
        return []
    db = _db_path(project_root)
    if not db.exists():
        return []
    con = sqlite3.connect(str(db))
    try:
        rows = con.execute(
            """
            SELECT m.leaf_id, m.feature_id, m.feature_name, f.description, m.status
            FROM ac_meta m
            JOIN ac_fts f ON f.rowid = m.rowid
            WHERE m.feature_id = ?
            ORDER BY m.rowid
            """,
            (feature_id,),
        ).fetchall()
        return [
            {
                "leaf_id": r[0],
                "feature_id": r[1],
                "feature_name": r[2],
                "description": r[3],
                "status": r[4],
            }
            for r in rows
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()
