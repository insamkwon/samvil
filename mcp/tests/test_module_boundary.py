"""Tests for module_boundary.py — M1 Module Boundary.

Covers: contract validation, boundary enforcement, aggregate state,
cycle detection, edge cases.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samvil_mcp.module_boundary import (
    CONTRACT_SCHEMA_VERSION,
    _detect_cycles,
    _extract_imports,
    _resolve_file_to_module,
    aggregate_module_state,
    enforce_boundary,
    validate_contract,
)


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture()
def project_with_modules(tmp_path: Path) -> Path:
    """Create a project with two valid modules: auth and api."""
    modules_dir = tmp_path / ".samvil" / "modules"

    # auth module
    auth_dir = modules_dir / "auth"
    auth_dir.mkdir(parents=True)
    (auth_dir / "contract.json").write_text(json.dumps({
        "schema_version": "1.0",
        "module_name": "auth",
        "version": "1.0.0",
        "description": "Authentication module",
        "file_patterns": ["src/auth/**", "lib/auth/**"],
        "public_api": [
            {"name": "auth.login", "type": "function", "exported_from": "src/auth/index.ts"},
            {"name": "UserSession", "type": "class", "exported_from": "src/auth/session.ts"},
        ],
        "depends_on": [],
        "owners": ["default"],
        "breaking_changes": [],
    }))

    # api module — depends on auth
    api_dir = modules_dir / "api"
    api_dir.mkdir(parents=True)
    (api_dir / "contract.json").write_text(json.dumps({
        "schema_version": "1.0",
        "module_name": "api",
        "version": "0.1.0",
        "description": "API routes",
        "file_patterns": ["src/api/**"],
        "public_api": [
            {"name": "api.handler", "type": "function"},
        ],
        "depends_on": ["auth"],
        "owners": ["default"],
        "breaking_changes": [],
    }))

    return tmp_path


@pytest.fixture()
def project_with_cycle(tmp_path: Path) -> Path:
    """Create a project with circular dependencies."""
    modules_dir = tmp_path / ".samvil" / "modules"

    mod_a = modules_dir / "mod-a"
    mod_a.mkdir(parents=True)
    (mod_a / "contract.json").write_text(json.dumps({
        "schema_version": "1.0",
        "module_name": "mod-a",
        "version": "1.0.0",
        "file_patterns": ["src/a/**"],
        "depends_on": ["mod-b"],
    }))

    mod_b = modules_dir / "mod-b"
    mod_b.mkdir(parents=True)
    (mod_b / "contract.json").write_text(json.dumps({
        "schema_version": "1.0",
        "module_name": "mod-b",
        "version": "1.0.0",
        "file_patterns": ["src/b/**"],
        "depends_on": ["mod-a"],
    }))

    return tmp_path


# ── validate_contract tests ────────────────────────────────────


class TestValidateContract:
    """Contract validation tests."""

    def test_valid_contract(self, project_with_modules: Path):
        result = validate_contract(project_with_modules, "auth")
        assert result["valid"] is True
        assert result["module_name"] == "auth"
        assert result["errors"] == []

    def test_valid_api_contract(self, project_with_modules: Path):
        result = validate_contract(project_with_modules, "api")
        assert result["valid"] is True

    def test_missing_module(self, tmp_path: Path):
        result = validate_contract(tmp_path, "nonexistent")
        assert result["valid"] is False
        assert any("not found" in e for e in result["errors"])

    def test_invalid_json(self, tmp_path: Path):
        mod_dir = tmp_path / ".samvil" / "modules" / "broken"
        mod_dir.mkdir(parents=True)
        (mod_dir / "contract.json").write_text("{invalid json")
        result = validate_contract(tmp_path, "broken")
        assert result["valid"] is False

    def test_missing_required_fields(self, tmp_path: Path):
        mod_dir = tmp_path / ".samvil" / "modules" / "minimal"
        mod_dir.mkdir(parents=True)
        (mod_dir / "contract.json").write_text(json.dumps({"module_name": "minimal"}))
        result = validate_contract(tmp_path, "minimal")
        assert result["valid"] is False
        assert any("schema_version" in e for e in result["errors"])
        assert any("version" in e for e in result["errors"])
        assert any("file_patterns" in e for e in result["errors"])

    def test_name_mismatch(self, tmp_path: Path):
        mod_dir = tmp_path / ".samvil" / "modules" / "wrong-name"
        mod_dir.mkdir(parents=True)
        (mod_dir / "contract.json").write_text(json.dumps({
            "schema_version": "1.0",
            "module_name": "different-name",
            "version": "1.0.0",
            "file_patterns": ["src/**"],
        }))
        result = validate_contract(tmp_path, "wrong-name")
        assert result["valid"] is False
        assert any("does not match" in e for e in result["errors"])

    def test_invalid_version_format(self, tmp_path: Path):
        mod_dir = tmp_path / ".samvil" / "modules" / "badver"
        mod_dir.mkdir(parents=True)
        (mod_dir / "contract.json").write_text(json.dumps({
            "schema_version": "1.0",
            "module_name": "badver",
            "version": "v1",
            "file_patterns": ["src/**"],
        }))
        result = validate_contract(tmp_path, "badver")
        assert result["valid"] is False
        assert any("semver" in e for e in result["errors"])

    def test_empty_file_patterns(self, tmp_path: Path):
        mod_dir = tmp_path / ".samvil" / "modules" / "nopat"
        mod_dir.mkdir(parents=True)
        (mod_dir / "contract.json").write_text(json.dumps({
            "schema_version": "1.0",
            "module_name": "nopat",
            "version": "1.0.0",
            "file_patterns": [],
        }))
        result = validate_contract(tmp_path, "nopat")
        assert result["valid"] is False
        assert any("non-empty" in e for e in result["errors"])

    def test_self_dependency(self, tmp_path: Path):
        mod_dir = tmp_path / ".samvil" / "modules" / "selfdep"
        mod_dir.mkdir(parents=True)
        (mod_dir / "contract.json").write_text(json.dumps({
            "schema_version": "1.0",
            "module_name": "selfdep",
            "version": "1.0.0",
            "file_patterns": ["src/**"],
            "depends_on": ["selfdep"],
        }))
        result = validate_contract(tmp_path, "selfdep")
        assert result["valid"] is False
        assert any("depends on itself" in e for e in result["errors"])

    def test_schema_version_warning(self, tmp_path: Path):
        mod_dir = tmp_path / ".samvil" / "modules" / "future"
        mod_dir.mkdir(parents=True)
        (mod_dir / "contract.json").write_text(json.dumps({
            "schema_version": "2.0",
            "module_name": "future",
            "version": "1.0.0",
            "file_patterns": ["src/**"],
        }))
        result = validate_contract(tmp_path, "future")
        assert result["valid"] is True
        assert len(result["warnings"]) >= 1
        assert any("schema_version" in w for w in result["warnings"])

    def test_invalid_depends_on_name(self, tmp_path: Path):
        mod_dir = tmp_path / ".samvil" / "modules" / "baddep"
        mod_dir.mkdir(parents=True)
        (mod_dir / "contract.json").write_text(json.dumps({
            "schema_version": "1.0",
            "module_name": "baddep",
            "version": "1.0.0",
            "file_patterns": ["src/**"],
            "depends_on": ["INVALID NAME!"],
        }))
        result = validate_contract(tmp_path, "baddep")
        assert result["valid"] is False
        assert any("not a valid module name" in e for e in result["errors"])


# ── enforce_boundary tests ─────────────────────────────────────


class TestEnforceBoundary:
    """Boundary enforcement tests."""

    def test_no_violations_isolated_modules(self, project_with_modules: Path):
        result = enforce_boundary(project_with_modules, "auth")
        assert result["violation_count"] == 0

    def test_missing_contract_returns_empty(self, tmp_path: Path):
        result = enforce_boundary(tmp_path, "nonexistent")
        assert result["modules_checked"] == 0

    def test_explicit_file_paths(self, project_with_modules: Path):
        # Create a file that imports from api module
        src_dir = project_with_modules / "src" / "auth"
        src_dir.mkdir(parents=True)
        (src_dir / "utils.ts").write_text(
            "import { handler } from '../api/routes';\n"
        )
        result = enforce_boundary(
            project_with_modules,
            "auth",
            file_paths=["src/auth/utils.ts"],
        )
        # auth doesn't depend on api, so this should be a violation
        assert result["violation_count"] >= 1
        assert result["violations"][0]["target_module"] == "api"

    def test_allowed_dependency_no_violation(self, project_with_modules: Path):
        # api depends on auth — importing from auth is fine
        src_dir = project_with_modules / "src" / "api"
        src_dir.mkdir(parents=True)
        (src_dir / "routes.ts").write_text(
            "import { login } from '../auth/index';\n"
        )
        result = enforce_boundary(
            project_with_modules,
            "api",
            file_paths=["src/api/routes.ts"],
        )
        assert result["violation_count"] == 0


# ── aggregate_module_state tests ───────────────────────────────


class TestAggregateModuleState:
    """Module state aggregation tests."""

    def test_aggregate_two_modules(self, project_with_modules: Path):
        result = aggregate_module_state(project_with_modules)
        assert result["total_modules"] == 2
        assert result["total_public_apis"] == 3  # auth(2) + api(1)
        assert "auth" in result["dependency_graph"]
        assert result["dependency_graph"]["auth"] == []
        assert result["dependency_graph"]["api"] == ["auth"]
        assert result["cycles"] == []

    def test_empty_project(self, tmp_path: Path):
        result = aggregate_module_state(tmp_path)
        assert result["total_modules"] == 0
        assert result["modules"] == []

    def test_no_modules_dir(self, tmp_path: Path):
        result = aggregate_module_state(tmp_path)
        assert result["total_modules"] == 0

    def test_cycle_detection_in_aggregate(self, project_with_cycle: Path):
        result = aggregate_module_state(project_with_cycle)
        assert result["total_modules"] == 2
        assert len(result["cycles"]) >= 1

    def test_invalid_contract_in_aggregate(self, tmp_path: Path):
        mod_dir = tmp_path / ".samvil" / "modules" / "bad"
        mod_dir.mkdir(parents=True)
        (mod_dir / "contract.json").write_text("{bad")
        result = aggregate_module_state(tmp_path)
        assert result["total_modules"] == 0
        assert len(result["contract_errors"]) >= 1

    def test_module_validity_included(self, project_with_modules: Path):
        result = aggregate_module_state(project_with_modules)
        for mod in result["modules"]:
            assert "contract_valid" in mod
            assert mod["contract_valid"] is True


# ── cycle detection tests ──────────────────────────────────────


class TestCycleDetection:
    """Direct cycle detection algorithm tests."""

    def test_no_cycles(self):
        graph = {"a": ["b"], "b": ["c"], "c": []}
        assert _detect_cycles(graph) == []

    def test_simple_cycle(self):
        graph = {"a": ["b"], "b": ["a"]}
        cycles = _detect_cycles(graph)
        assert len(cycles) >= 1

    def test_three_node_cycle(self):
        graph = {"a": ["b"], "b": ["c"], "c": ["a"]}
        cycles = _detect_cycles(graph)
        assert len(cycles) >= 1

    def test_self_loop(self):
        graph = {"a": ["a"]}
        cycles = _detect_cycles(graph)
        assert len(cycles) >= 1

    def test_empty_graph(self):
        assert _detect_cycles({}) == []

    def test_disconnected_with_cycle(self):
        graph = {"a": [], "b": ["c"], "c": ["b"]}
        cycles = _detect_cycles(graph)
        assert len(cycles) >= 1


# ── helper tests ───────────────────────────────────────────────


class TestHelpers:
    """Unit tests for helper functions."""

    def test_extract_es_imports(self):
        code = "import { foo } from '../auth/index';\nimport bar from './utils';"
        imports = _extract_imports(code)
        assert "../auth/index" in imports
        assert "./utils" in imports

    def test_extract_python_imports(self):
        code = "from auth.session import UserSession\nimport os"
        imports = _extract_imports(code)
        assert "auth.session" in imports
        assert "os" in imports

    def test_resolve_file_to_module(self):
        patterns = {
            "auth": ["src/auth/**"],
            "api": ["src/api/**"],
        }
        assert _resolve_file_to_module("src/auth/login.ts", patterns) == "auth"
        assert _resolve_file_to_module("src/api/routes.ts", patterns) == "api"
        assert _resolve_file_to_module("src/utils.ts", patterns) is None

    def test_contract_schema_version_constant(self):
        assert CONTRACT_SCHEMA_VERSION == "1.0"
