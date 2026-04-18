"""Seed Migration v2 → v3 (v3.0.0).

Converts flat string/dict ACs to AC Tree structure.
Creates backup before migration.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def migrate_seed_v2_to_v3(seed: dict) -> dict:
    """Convert v2.x flat ACs to v3.0 tree structure."""
    for feature in seed.get("features", []):
        acs = feature.get("acceptance_criteria", [])
        new_acs = []
        for i, ac in enumerate(acs, 1):
            if isinstance(ac, str):
                new_acs.append({
                    "id": f"AC-{feature.get('name', 'X')}-{i}",
                    "description": ac,
                    "children": [],
                    "status": "pending",
                    "evidence": [],
                })
            elif isinstance(ac, dict):
                if "description" in ac:
                    ac.setdefault("id", f"AC-{i}")
                    ac.setdefault("children", [])
                    ac.setdefault("status", "pending")
                    ac.setdefault("evidence", [])
                    new_acs.append(ac)
                elif "criterion" in ac:
                    new_acs.append({
                        "id": f"AC-{i}",
                        "description": ac["criterion"],
                        "vague_words": ac.get("vague_words", []),
                        "children": [],
                        "status": "pending",
                        "evidence": [],
                    })
        feature["acceptance_criteria"] = new_acs
    seed.setdefault("schema_version", "3.0")
    return seed


def migrate_with_backup(seed_path: str) -> dict:
    """Migrate a seed file with automatic backup.

    - Reads the seed first.
    - Creates `.v2.backup.json` **only** when an actual migration happens
      (so re-running on a v3 seed doesn't produce a stale pre-v3 sidecar).
    - Never overwrites an existing backup.
    """
    p = Path(seed_path)
    if not p.exists():
        raise FileNotFoundError(f"Seed not found: {seed_path}")

    seed = json.loads(p.read_text())

    if seed.get("schema_version", "").startswith("3."):
        return seed

    backup = p.with_suffix(".v2.backup.json")
    if not backup.exists():
        shutil.copy2(p, backup)

    migrated = migrate_seed_v2_to_v3(seed)
    p.write_text(json.dumps(migrated, indent=2, ensure_ascii=False))
    return migrated
