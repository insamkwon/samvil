"""Tests for SAMVIL PATH routing (v2.4.0, Ouroboros #01 흡수)."""

import json
import pytest
from pathlib import Path

from samvil_mcp.path_router import (
    detect_routing_path,
    scan_manifest,
    extract_answer_source,
)


# ── scan_manifest tests ────────────────────────────────────────


def test_scan_manifest_greenfield(tmp_path):
    """Empty project returns detected=False."""
    result = scan_manifest(str(tmp_path))
    assert result["detected"] is False


def test_scan_manifest_nextjs(tmp_path):
    """Next.js project detection via package.json."""
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps({
        "name": "my-app",
        "dependencies": {
            "next": "14.2.0",
            "react": "18.2.0",
            "typescript": "5.3.0",
            "tailwindcss": "3.4.0",
        }
    }))
    result = scan_manifest(str(tmp_path))
    assert result["detected"] is True
    assert result["framework"] == "Next.js"
    assert result["framework_version"] == "14.2.0"
    assert result["language"] == "TypeScript"
    assert result["styling"] == "Tailwind CSS"


def test_scan_manifest_python_fastapi(tmp_path):
    """FastAPI project detection via pyproject.toml."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("""
[project]
name = "my-api"
python = "3.12"
dependencies = ["fastapi>=0.100.0"]
""")
    result = scan_manifest(str(tmp_path))
    assert result["detected"] is True
    assert result["framework"] == "FastAPI"
    assert result["language"] == "Python"
    assert result.get("python_version") == "3.12"


def test_scan_manifest_package_manager_pnpm(tmp_path):
    """pnpm detection via pnpm-lock.yaml."""
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"next": "14.0.0"}}))
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '6.0'")
    result = scan_manifest(str(tmp_path))
    assert result.get("package_manager") == "pnpm"


def test_scan_manifest_prisma_postgres(tmp_path):
    """Prisma + PostgreSQL detection."""
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"@prisma/client": "5.0.0"}}))
    prisma = tmp_path / "prisma"
    prisma.mkdir()
    (prisma / "schema.prisma").write_text("""
datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}
""")
    result = scan_manifest(str(tmp_path))
    assert result.get("orm") == "Prisma"
    assert result.get("database") == "PostgreSQL"


# ── detect_routing_path tests ──────────────────────────────────


def test_routing_force_user_rhythm_guard():
    """force_user=True (Rhythm Guard) → forced_user path."""
    result = detect_routing_path(
        "What framework?",
        manifest_facts={"framework": "Next.js", "detected": True, "source_files": ["package.json"]},
        force_user=True,
    )
    assert result["path"] == "forced_user"
    assert "Rhythm Guard" in result["rationale"]


def test_routing_decision_keyword():
    """Decision language → user (PATH 2)."""
    result = detect_routing_path(
        "What should we build for the goal?",
        manifest_facts={"framework": "Next.js", "detected": True},
    )
    assert result["path"] == "user"


def test_routing_research_keyword():
    """Research language (API spec, pricing) → research (PATH 4)."""
    result = detect_routing_path(
        "What are Stripe API rate limits?",
    )
    assert result["path"] == "research"


def test_routing_framework_auto_confirm():
    """Framework question + manifest → auto_confirm (PATH 1a)."""
    result = detect_routing_path(
        "What framework is used?",
        manifest_facts={
            "detected": True,
            "framework": "Next.js",
            "framework_version": "14.2.0",
            "source_files": ["package.json"],
        },
    )
    assert result["path"] == "auto_confirm"
    assert result["auto_answer"] is not None
    assert "[from-code][auto-confirmed]" in result["auto_answer"]
    assert "Next.js" in result["auto_answer"]


def test_routing_database_code_confirm():
    """Database inferred from Prisma → code_confirm (PATH 1b)."""
    result = detect_routing_path(
        "What database is used?",
        manifest_facts={
            "detected": True,
            "database": "PostgreSQL",
            "source_files": ["prisma/schema.prisma"],
        },
    )
    assert result["path"] == "code_confirm"
    assert "[from-code]" in result["auto_answer"]


def test_routing_greenfield_defaults_user():
    """No manifest detected → user (PATH 2) default."""
    result = detect_routing_path(
        "What framework for new project?",
        manifest_facts={"detected": False},
    )
    assert result["path"] == "user"


def test_routing_decision_overrides_manifest():
    """Decision keyword overrides manifest match."""
    result = detect_routing_path(
        "Which framework should we prefer for this?",
        manifest_facts={
            "detected": True,
            "framework": "Next.js",
        },
    )
    # Decision keywords ("should we prefer") → user
    assert result["path"] == "user"


# ── extract_answer_source tests ────────────────────────────────


def test_extract_source_auto_confirmed():
    assert extract_answer_source("[from-code][auto-confirmed] Next.js 14") == "from-code-auto"


def test_extract_source_from_code():
    assert extract_answer_source("[from-code] JWT auth") == "from-code"


def test_extract_source_from_user():
    assert extract_answer_source("[from-user] Stripe") == "from-user"


def test_extract_source_from_user_correction():
    assert extract_answer_source("[from-user][correction] Actually PostgreSQL") == "from-user-correction"


def test_extract_source_from_research():
    assert extract_answer_source("[from-research] 100 req/sec") == "from-research"


def test_extract_source_unprefixed_defaults_user():
    """Unprefixed answers → from-user (safe default)."""
    assert extract_answer_source("Something without prefix") == "from-user"
