"""Module Boundary E2E scenario test.

Simulates a real project with 3 modules and verifies:
1. Contract validation (valid/invalid)
2. Boundary enforcement (detects cross-module violations)
3. Aggregate state (inventory + graph + cycles)
4. Integration with skill-level workflow
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from samvil_mcp.module_boundary import (
    aggregate_module_state,
    enforce_boundary,
    validate_contract,
)


@pytest.fixture
def project_with_modules():
    """Create a realistic project with auth, core, billing modules."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = os.path.realpath(tmpdir)

        # Core module
        _write_module(root, "core", {
            "schema_version": "1.0",
            "module_name": "core",
            "version": "1.0.0",
            "description": "Core utilities and config",
            "file_patterns": ["src/core/**"],
            "public_api": [
                {"name": "core.config", "type": "function", "exported_from": "src/core/config.ts"},
                {"name": "core.logger", "type": "function", "exported_from": "src/core/logger.ts"},
            ],
            "depends_on": [],
            "owners": ["default"],
        })
        # Create core source files
        _write_source(root, "src/core/config.ts", "export const config = {}")
        _write_source(root, "src/core/logger.ts", "export const logger = console")

        # Auth module (depends on core)
        _write_module(root, "auth", {
            "schema_version": "1.0",
            "module_name": "auth",
            "version": "1.0.0",
            "description": "Authentication and authorization",
            "file_patterns": ["src/auth/**"],
            "public_api": [
                {"name": "auth.login", "type": "function", "exported_from": "src/auth/index.ts"},
                {"name": "auth.UserSession", "type": "type", "exported_from": "src/auth/types.ts"},
            ],
            "depends_on": ["core"],
            "owners": ["default"],
        })
        # Auth imports from core (allowed)
        _write_source(root, "src/auth/index.ts", "import { config } from '../core/config'")
        _write_source(root, "src/auth/types.ts", "export interface UserSession { id: string }")
        # Auth imports from billing (VIOLATION - not in depends_on)
        _write_source(root, "src/auth/service.ts", "import { getInvoice } from '../billing/service'")

        # Billing module (depends on core)
        _write_module(root, "billing", {
            "schema_version": "1.0",
            "module_name": "billing",
            "version": "1.0.0",
            "description": "Billing and invoicing",
            "file_patterns": ["src/billing/**"],
            "public_api": [
                {"name": "billing.getInvoice", "type": "function"},
            ],
            "depends_on": ["core"],
            "owners": ["default"],
        })
        _write_source(root, "src/billing/service.ts", "import { config } from '../core/config'")

        yield root


def _write_module(root, name, contract):
    mod_dir = os.path.join(root, ".samvil", "modules", name)
    os.makedirs(mod_dir, exist_ok=True)
    with open(os.path.join(mod_dir, "contract.json"), "w") as f:
        json.dump(contract, f)


def _write_source(root, rel_path, content):
    full = os.path.join(root, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(content)


class TestContractValidation:
    def test_all_valid(self, project_with_modules):
        for name in ["core", "auth", "billing"]:
            v = validate_contract(project_with_modules, name)
            assert v["valid"], f"{name}: {v['errors']}"

    def test_invalid_missing_fields(self, project_with_modules):
        _write_module(project_with_modules, "broken", {
            "schema_version": "1.0",
            "module_name": "broken",
        })
        v = validate_contract(project_with_modules, "broken")
        assert not v["valid"]
        assert any("missing required" in e for e in v["errors"])

    def test_self_dependency_detected(self, project_with_modules):
        _write_module(project_with_modules, "selfdep", {
            "schema_version": "1.0",
            "module_name": "selfdep",
            "version": "1.0.0",
            "file_patterns": ["src/selfdep/**"],
            "depends_on": ["selfdep"],
        })
        v = validate_contract(project_with_modules, "selfdep")
        assert not v["valid"]
        assert any("depends on itself" in e for e in v["errors"])


class TestBoundaryEnforcement:
    def test_core_no_violations(self, project_with_modules):
        e = enforce_boundary(project_with_modules, "core")
        assert e["violation_count"] == 0

    def test_billing_no_violations(self, project_with_modules):
        e = enforce_boundary(project_with_modules, "billing")
        assert e["violation_count"] == 0

    def test_auth_has_billing_violation(self, project_with_modules):
        e = enforce_boundary(project_with_modules, "auth")
        assert e["violation_count"] == 1
        v = e["violations"][0]
        assert v["source_module"] == "auth"
        assert v["target_module"] == "billing"
        assert v["violation_type"] == "import"

    def test_specific_file_paths(self, project_with_modules):
        e = enforce_boundary(
            project_with_modules,
            "auth",
            ["src/auth/index.ts"],  # only the clean file
        )
        assert e["violation_count"] == 0


class TestAggregateState:
    def test_total_modules(self, project_with_modules):
        s = aggregate_module_state(project_with_modules)
        assert s["total_modules"] == 3

    def test_dependency_graph(self, project_with_modules):
        s = aggregate_module_state(project_with_modules)
        assert "core" in s["dependency_graph"]
        assert s["dependency_graph"]["core"] == []
        assert set(s["dependency_graph"]["auth"]) == {"core"}

    def test_no_cycles(self, project_with_modules):
        s = aggregate_module_state(project_with_modules)
        assert s["cycles"] == []

    def test_public_api_count(self, project_with_modules):
        s = aggregate_module_state(project_with_modules)
        # core: 2, auth: 2, billing: 1 = 5
        assert s["total_public_apis"] == 5


class TestSkillWorkflow:
    """Simulates what a build/QA skill would do."""

    def test_build_preflight_check(self, project_with_modules):
        # Skill reads modules, validates contracts, checks boundaries
        s = aggregate_module_state(project_with_modules)
        all_valid = all(m["contract_valid"] for m in s["modules"])
        assert all_valid

        # Check auth module boundaries before build
        e = enforce_boundary(project_with_modules, "auth")
        # Build should be warned about the billing violation
        assert e["violation_count"] > 0

    def test_qa_contract_validation(self, project_with_modules):
        # QA validates each module contract
        for name in ["core", "auth", "billing"]:
            v = validate_contract(project_with_modules, name)
            assert v["valid"], f"QA: {name} contract invalid: {v['errors']}"
