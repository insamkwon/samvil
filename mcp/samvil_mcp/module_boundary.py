"""Module Boundary — Contract Validation & Boundary Enforcement (M1).

Validates module contracts (.samvil/modules/<name>/contract.json),
detects cross-module boundary violations, and aggregates project module
state (inventory + dependency graph).

Single-source-of-truth aggregate MCP pattern:
  - validate_contract() → contract schema + semantic validation
  - enforce_boundary() → cross-module import/file violation detection
  - aggregate_module_state() → inventory + graph + health
"""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Module contract schema version this code understands.
CONTRACT_SCHEMA_VERSION = "1.0"


# ── Data classes ──────────────────────────────────────────────────────


@dataclass
class ContractValidationResult:
    """Result of validating a single module contract."""

    module_name: str
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "module_name": self.module_name,
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class BoundaryViolation:
    """A single cross-module boundary violation."""

    source_module: str
    target_module: str
    file_path: str
    line_number: int
    imported_symbol: str
    violation_type: str  # "import" | "file_access"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_module": self.source_module,
            "target_module": self.target_module,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "imported_symbol": self.imported_symbol,
            "violation_type": self.violation_type,
        }


@dataclass
class BoundaryEnforcementResult:
    """Result of checking module boundaries across a project."""

    violations: list[BoundaryViolation] = field(default_factory=list)
    modules_checked: int = 0
    files_scanned: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "violations": [v.to_dict() for v in self.violations],
            "modules_checked": self.modules_checked,
            "files_scanned": self.files_scanned,
            "violation_count": len(self.violations),
        }


@dataclass
class ModuleState:
    """Aggregated state of all modules in a project."""

    modules: list[dict[str, Any]] = field(default_factory=list)
    dependency_graph: dict[str, list[str]] = field(default_factory=dict)
    cycles: list[list[str]] = field(default_factory=list)
    total_modules: int = 0
    total_public_apis: int = 0
    contract_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "modules": self.modules,
            "dependency_graph": self.dependency_graph,
            "cycles": self.cycles,
            "total_modules": self.total_modules,
            "total_public_apis": self.total_public_apis,
            "contract_errors": self.contract_errors,
        }


# ── Contract loading & validation ─────────────────────────────────


def _load_contract(contract_path: Path) -> dict[str, Any] | None:
    """Load and parse a contract.json file."""
    try:
        return json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def validate_contract(
    project_root: str | Path,
    module_name: str,
) -> dict[str, Any]:
    """Validate a single module's contract.json.

    Checks:
      1. File exists and is valid JSON.
      2. Required fields present (schema_version, module_name, version, file_patterns).
      3. module_name matches directory name.
      4. schema_version matches expected version.
      5. file_patterns entries are non-empty globs.
      6. depends_on references are valid module names.
      7. No self-dependency.

    Returns ContractValidationResult as dict.
    """
    root = Path(project_root).resolve()
    contract_path = root / ".samvil" / "modules" / module_name / "contract.json"

    result = ContractValidationResult(module_name=module_name)

    contract = _load_contract(contract_path)
    if contract is None:
        result.errors.append(f"contract.json not found or invalid JSON at {contract_path}")
        result.valid = False
        return result.to_dict()

    # Required fields
    for req_field in ("schema_version", "module_name", "version", "file_patterns"):
        if req_field not in contract:
            result.errors.append(f"missing required field: {req_field}")

    if result.errors:
        result.valid = False
        return result.to_dict()

    # module_name consistency
    if contract["module_name"] != module_name:
        result.errors.append(
            f"contract module_name={contract['module_name']!r} "
            f"does not match directory name {module_name!r}"
        )

    # schema_version
    if contract["schema_version"] != CONTRACT_SCHEMA_VERSION:
        result.warnings.append(
            f"schema_version {contract['schema_version']!r} != expected "
            f"{CONTRACT_SCHEMA_VERSION!r}; validation may be incomplete"
        )

    # version format
    version = contract.get("version", "")
    if not re.match(r"^\d+\.\d+\.\d+$", str(version)):
        result.errors.append(f"version {version!r} is not semver (X.Y.Z)")

    # file_patterns
    patterns = contract.get("file_patterns", [])
    if not isinstance(patterns, list) or len(patterns) == 0:
        result.errors.append("file_patterns must be a non-empty array")
    else:
        for i, pat in enumerate(patterns):
            if not isinstance(pat, str) or not pat.strip():
                result.errors.append(f"file_patterns[{i}] is empty or not a string")

    # depends_on
    depends_on = contract.get("depends_on", [])
    if not isinstance(depends_on, list):
        result.errors.append("depends_on must be an array")
    else:
        for dep in depends_on:
            if not isinstance(dep, str) or not re.match(r"^[a-z][a-z0-9_-]*$", dep):
                result.errors.append(f"depends_on entry {dep!r} is not a valid module name")

        # Self-dependency check
        if module_name in depends_on:
            result.errors.append(f"module depends on itself: {module_name!r}")

    result.valid = len(result.errors) == 0
    return result.to_dict()


def _resolve_file_to_module(
    file_path: str,
    module_patterns: dict[str, list[str]],
) -> str | None:
    """Determine which module a file belongs to based on file_patterns."""
    for mod_name, patterns in module_patterns.items():
        for pat in patterns:
            if fnmatch.fnmatch(file_path, pat):
                return mod_name
    return None


# Import pattern matching — catches ES/TS and Python imports.
_IMPORT_PATTERNS = [
    # ES/TS: import ... from '...'
    re.compile(r"""(?:import\s+.*?\s+from\s+['"])([^'"]+)"""),
    # Python: from ... import / import ...
    re.compile(r"""(?:from\s+)([\w.]+)(?:\s+import)"""),
    re.compile(r"""(?:import\s+)([\w.]+)"""),
]


def _extract_imports(file_content: str) -> list[str]:
    """Extract import paths from source code."""
    imports = []
    for pat in _IMPORT_PATTERNS:
        for match in pat.finditer(file_content):
            imports.append(match.group(1))
    return imports


def enforce_boundary(
    project_root: str | Path,
    module_name: str,
    file_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Check whether a module's files import from modules not in depends_on.

    Scans files matching the module's file_patterns (or the provided
    file_paths override) and checks each import against the file_patterns
    of other modules. Any import landing in a module not listed in
    depends_on is a boundary violation.

    Returns BoundaryEnforcementResult as dict.
    """
    root = Path(project_root).resolve()
    modules_dir = root / ".samvil" / "modules"

    # Load target contract
    contract_path = modules_dir / module_name / "contract.json"
    contract = _load_contract(contract_path)
    if contract is None:
        return BoundaryEnforcementResult(
            modules_checked=0, files_scanned=0
        ).to_dict()

    depends_on = set(contract.get("depends_on", []))
    target_patterns = contract.get("file_patterns", [])

    # Load all other module contracts for pattern lookup
    module_patterns: dict[str, list[str]] = {}
    for mod_dir in sorted(modules_dir.iterdir()):
        if not mod_dir.is_dir():
            continue
        cp = mod_dir / "contract.json"
        c = _load_contract(cp)
        if c and c.get("module_name") != module_name:
            module_patterns[c["module_name"]] = c.get("file_patterns", [])

    # Add own module patterns for completeness
    module_patterns[module_name] = target_patterns

    # Determine files to scan
    files_to_scan: list[Path] = []
    if file_paths:
        files_to_scan = [root / fp for fp in file_paths]
    else:
        for pat in target_patterns:
            if pat.endswith("/**"):
                # ** matches dirs only; use rglob for recursive file discovery
                base = pat[:-3]  # strip /**
                base_dir = root / base if base else root
                if base_dir.is_dir():
                    files_to_scan.extend(base_dir.rglob("*"))
            else:
                files_to_scan.extend(root.glob(pat))

    result = BoundaryEnforcementResult(modules_checked=len(module_patterns))

    for fpath in files_to_scan:
        if not fpath.is_file():
            continue
        result.files_scanned += 1
        try:
            content = fpath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        rel_path = str(fpath.relative_to(root))
        imports = _extract_imports(content)

        for idx, imp in enumerate(imports):
            # Normalize import path relative to the importing file's directory
            imp_resolved = str(
                (fpath.parent / imp).resolve().relative_to(root)
            )

            # Check if this import lands inside another module
            for other_mod, other_patterns in module_patterns.items():
                if other_mod == module_name:
                    continue
                for opat in other_patterns:
                    if fnmatch.fnmatch(imp, opat) or fnmatch.fnmatch(
                        imp_resolved, opat
                    ):
                        if other_mod not in depends_on:
                            result.violations.append(
                                BoundaryViolation(
                                    source_module=module_name,
                                    target_module=other_mod,
                                    file_path=rel_path,
                                    line_number=idx + 1,
                                    imported_symbol=imp,
                                    violation_type="import",
                                )
                            )

    return result.to_dict()


# ── Dependency graph + cycle detection ─────────────────────────────


def _detect_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """Detect cycles in a directed graph using DFS."""
    cycles: list[list[str]] = []
    visited: set[str] = set()
    rec_stack: set[str] = set()
    path: list[str] = []

    def dfs(node: str) -> None:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                dfs(neighbor)
            elif neighbor in rec_stack:
                # Found cycle
                cycle_start = path.index(neighbor)
                cycles.append(list(path[cycle_start:]) + [neighbor])

        path.pop()
        rec_stack.discard(node)

    for node in graph:
        if node not in visited:
            dfs(node)

    return cycles


def aggregate_module_state(project_root: str | Path) -> dict[str, Any]:
    """Aggregate the state of all modules in a project.

    Returns inventory, dependency graph, cycle detection, and
    per-module contract validation status.

    Single-source-of-truth aggregate: this is the one call the
    skill needs to render the full module overview.
    """
    root = Path(project_root).resolve()
    modules_dir = root / ".samvil" / "modules"

    state = ModuleState()

    if not modules_dir.exists():
        return state.to_dict()

    # Load all contracts
    contracts: dict[str, dict[str, Any]] = {}
    for mod_dir in sorted(modules_dir.iterdir()):
        if not mod_dir.is_dir():
            continue
        cp = mod_dir / "contract.json"
        contract = _load_contract(cp)
        if contract is None:
            state.contract_errors.append(
                f"invalid contract in {mod_dir.name}"
            )
            continue
        mod_name = contract.get("module_name", mod_dir.name)
        contracts[mod_name] = contract

    # Build inventory + graph
    graph: dict[str, list[str]] = {}
    for mod_name, contract in contracts.items():
        validation = validate_contract(root, mod_name)
        api_count = len(contract.get("public_api", []))
        graph[mod_name] = list(contract.get("depends_on", []))

        state.modules.append({
            "module_name": mod_name,
            "version": contract.get("version", "0.0.0"),
            "description": contract.get("description", ""),
            "file_patterns": contract.get("file_patterns", []),
            "public_api_count": api_count,
            "depends_on": contract.get("depends_on", []),
            "contract_valid": validation["valid"],
            "validation_errors": validation["errors"],
            "validation_warnings": validation["warnings"],
        })
        state.total_public_apis += api_count

    state.total_modules = len(contracts)
    state.dependency_graph = graph
    state.cycles = _detect_cycles(graph)

    return state.to_dict()
