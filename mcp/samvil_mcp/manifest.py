"""Codebase Manifest — Layer 4 SSOT for SAMVIL v3.3+.

`.samvil/manifest.json` is an auto-generated description of project structure:
modules, public APIs, dependencies, conventions. Loaded at every stage entry
to give AI a 5K-token snapshot of the codebase regardless of total LOC.

This module is responsible for:
  - The schema (Manifest + ModuleEntry dataclasses)
  - Filesystem walking + module discovery
  - Convention detection (lint config, tsconfig, etc.)
  - Atomic file I/O
  - Rendering compressed context strings for AI sessions

It is NOT responsible for:
  - Deciding when to regenerate (orchestrator does that)
  - Mutating modules (manifest is read-mostly; regenerate to update)
  - Cross-module verification (gates / claim_ledger do that)
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_SCHEMA_VERSION = "1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class ModuleEntry:
    """A single module in the codebase."""

    name: str
    path: str  # relative to project_root
    public_api: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    summary: str = ""
    files: list[str] = field(default_factory=list)
    convention_tags: list[str] = field(default_factory=list)
    last_updated: str = ""


@dataclass(frozen=True)
class Manifest:
    """Top-level manifest. Materialized to .samvil/manifest.json."""

    schema_version: str
    project_name: str
    project_root: str
    generated_at: str
    modules: list[ModuleEntry] = field(default_factory=list)
    conventions: dict[str, str] = field(default_factory=dict)
    public_apis: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "project_name": self.project_name,
            "project_root": self.project_root,
            "generated_at": self.generated_at,
            "modules": [asdict(m) for m in self.modules],
            "conventions": dict(self.conventions),
            "public_apis": {k: list(v) for k, v in self.public_apis.items()},
        }

    @staticmethod
    def from_dict(d: dict) -> Manifest:
        return Manifest(
            schema_version=d["schema_version"],
            project_name=d["project_name"],
            project_root=d["project_root"],
            generated_at=d["generated_at"],
            modules=[ModuleEntry(**m) for m in d.get("modules", [])],
            conventions=dict(d.get("conventions", {})),
            public_apis={k: list(v) for k, v in d.get("public_apis", {}).items()},
        )
