"""Tests for scaffold dependency matrix validation.

Validates references/dependency-matrix.json structure, required fields,
version format consistency, and cross-stack integrity.
"""

import json
import re

import pytest

from pathlib import Path

REFERENCE_DIR = Path(__file__).parent.parent.parent / "references"
MATRIX_PATH = REFERENCE_DIR / "dependency-matrix.json"

REQUIRED_STACKS = ("nextjs14", "vite-react", "astro")

# Fields every stack must define (except shadcn_components which is a list)
REQUIRED_STACK_FIELDS = ("cli_command", "framework", "react", "typescript")

# Common section must include these packages
REQUIRED_COMMON_DEPS = ("supabase_js", "playwright")

SEMVER_PATTERN = re.compile(r"^@?\d+\.\d+\.\d+$")


@pytest.fixture(scope="module")
def matrix():
    """Load and parse dependency-matrix.json once for all tests."""
    with open(MATRIX_PATH) as f:
        return json.load(f)


# ── File existence and validity ─────────────────────────────────


def test_dependency_matrix_exists():
    """dependency-matrix.json 파일이 references/ 디렉토리에 존재해야 함."""
    assert MATRIX_PATH.exists(), f"Missing: {MATRIX_PATH}"


def test_dependency_matrix_valid_json(matrix):
    """유효한 JSON이어야 하며 최상위가 dict여야 함."""
    assert isinstance(matrix, dict)


# ── Stack presence ───────────────────────────────────────────────


def test_all_stacks_present(matrix):
    """nextjs14, vite-react, astro 3개 스택이 모두 있어야 함."""
    for stack in REQUIRED_STACKS:
        assert stack in matrix, f"Missing stack: {stack}"


def test_common_section_present(matrix):
    """common 섹션이 있어야 함."""
    assert "common" in matrix, "Missing 'common' section"


# ── Required fields per stack ────────────────────────────────────


def test_each_stack_has_required_fields(matrix):
    """각 스택에 cli_command, framework, react, typescript 필드가 있어야 함."""
    for stack in REQUIRED_STACKS:
        stack_data = matrix[stack]
        for field in REQUIRED_STACK_FIELDS:
            assert field in stack_data, (
                f"Stack '{stack}' missing required field: {field}"
            )


def test_cli_commands_are_valid(matrix):
    """cli_command가 실행 가능한 명령어 형태여야 함."""
    for stack in REQUIRED_STACKS:
        cli = matrix[stack]["cli_command"]
        # Must start with npx or npm
        assert cli.startswith(("npx ", "npm ")), (
            f"Stack '{stack}' cli_command must start with npx or npm: {cli}"
        )
        # Must contain at least a major-version pin (@X or @X.Y or @X.Y.Z).
        # Note: some CLI scaffolders (e.g. create-vite) only accept major pins.
        assert re.search(r"@\d+", cli), (
            f"Stack '{stack}' cli_command must include a pinned version (at least major): {cli}"
        )


# ── Version format consistency ───────────────────────────────────


def test_version_format_consistency(matrix):
    """버전 번호가 semver 형식(package@major.minor.patch)이어야 함."""
    for stack in REQUIRED_STACKS:
        stack_data = matrix[stack]
        for key, value in stack_data.items():
            if key in ("cli_command", "shadcn_components", "notes"):
                continue
            if isinstance(value, str) and "@" in value:
                # Format: "package@X.Y.Z" or "@scope/package@X.Y.Z"
                # Extract the version part (last @X.Y.Z)
                match = re.search(r"@(\d+\.\d+\.\d+)$", value)
                assert match, (
                    f"Stack '{stack}' field '{key}' has non-semver version: {value}"
                )


# ── Common dependencies ──────────────────────────────────────────


def test_common_deps_present(matrix):
    """common 섹션에 필수 의존성(supabase_js, playwright)이 있어야 함."""
    common = matrix["common"]
    for dep in REQUIRED_COMMON_DEPS:
        assert dep in common, f"Missing common dependency: {dep}"


def test_common_deps_have_versions(matrix):
    """common 의존성이 모두 버전이 명시된 형태여야 함."""
    common = matrix["common"]
    for key, value in common.items():
        if key.startswith("_"):
            continue
        assert re.search(r"@\d+\.\d+\.\d+$", value), (
            f"Common dep '{key}' missing pinned version: {value}"
        )


# ── Cross-stack integrity ────────────────────────────────────────


def test_no_duplicate_versions_across_stacks(matrix):
    """같은 패키지의 버전이 스택 간에 충돌하지 않아야 함.

    react, react-dom, typescript, clsx, tailwind-merge는
    모든 스택에서 동일한 버전을 사용해야 함.
    """
    shared_packages = ("react", "react_dom", "typescript", "clsx", "tailwind_merge")
    version_map: dict[str, dict[str, str]] = {}

    for stack in REQUIRED_STACKS:
        stack_data = matrix[stack]
        for pkg_key in shared_packages:
            if pkg_key not in stack_data:
                continue
            version = stack_data[pkg_key]
            if pkg_key not in version_map:
                version_map[pkg_key] = {}
            version_map[pkg_key][stack] = version

    for pkg_key, versions in version_map.items():
        unique_versions = set(versions.values())
        assert len(unique_versions) == 1, (
            f"Version mismatch for {pkg_key}: {versions}"
        )


def test_shadcn_components_is_list(matrix):
    """shadcn_components 필드는 배열이어야 함."""
    for stack in REQUIRED_STACKS:
        if "shadcn_components" in matrix[stack]:
            assert isinstance(matrix[stack]["shadcn_components"], list), (
                f"Stack '{stack}' shadcn_components must be a list"
            )


def test_framework_matches_cli_command(matrix):
    """framework 필드와 cli_command이 동일한 패키지를 참조해야 함."""
    for stack in REQUIRED_STACKS:
        stack_data = matrix[stack]
        framework = stack_data["framework"]
        cli = stack_data["cli_command"]

        # Extract package name from framework field (e.g., "next@14.2.35" -> "next")
        pkg_match = re.match(r"^(@?[\w-]+)@", framework)
        assert pkg_match, f"Cannot parse framework field: {framework}"
        pkg_name = pkg_match.group(1)

        # CLI command should reference the same package
        assert pkg_name in cli, (
            f"Stack '{stack}': framework uses '{pkg_name}' "
            f"but cli_command doesn't reference it: {cli}"
        )
