"""Smoke tests for scripts/sync-cache.sh (Phase A.1).

The sync script copies the working-tree to the installed plugin cache
so changes take effect without manual `cp`. These tests verify:

- Script exists and is executable.
- --dry-run reports targets without modifying anything.
- A real run copies a curated whitelist of dirs/files into a fake cache.
- Idempotent: a second run produces identical content.
- Cache-side files NOT in the repo are preserved (no --delete).
- Graceful degradation when the cache directory doesn't exist.

Tests use HOME-override so they run against an isolated tmp cache,
not the real ~/.claude/plugins/cache/.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "sync-cache.sh"


def _run_sync(*args: str, env_overrides: dict | None = None) -> subprocess.CompletedProcess:
    """Run sync-cache.sh in a subprocess with optional HOME override."""
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )


def test_script_exists_and_executable() -> None:
    """The script file must exist and be executable."""
    assert SCRIPT.exists(), f"missing: {SCRIPT}"
    assert os.access(SCRIPT, os.X_OK), f"not executable: {SCRIPT}"


def test_dry_run_reports_targets_without_copying(tmp_path: Path) -> None:
    """--dry-run must list targets and exit 0, with no files copied."""
    fake_home = tmp_path / "home"
    fake_cache = fake_home / ".claude" / "plugins" / "cache" / "samvil" / "samvil"
    fake_cache.mkdir(parents=True)

    result = _run_sync("--dry-run", env_overrides={"HOME": str(fake_home)})

    assert result.returncode == 0, result.stderr
    assert "[dry-run]" in result.stdout
    assert "would sync" in result.stdout
    # Cache must remain empty
    assert list(fake_cache.iterdir()) == []


def test_real_run_copies_curated_whitelist(tmp_path: Path) -> None:
    """A real run must populate the cache with whitelisted targets."""
    fake_home = tmp_path / "home"
    fake_cache = fake_home / ".claude" / "plugins" / "cache" / "samvil" / "samvil"
    fake_cache.mkdir(parents=True)

    result = _run_sync(env_overrides={"HOME": str(fake_home)})

    assert result.returncode == 0, result.stderr
    # Spot-check the key targets exist in cache after sync
    assert (fake_cache / "skills").is_dir()
    assert (fake_cache / "mcp" / "samvil_mcp").is_dir()
    assert (fake_cache / "references").is_dir()
    assert (fake_cache / "CHANGELOG.md").is_file()
    assert (fake_cache / "README.md").is_file()
    # And content matches
    repo_changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    cached_changelog = (fake_cache / "CHANGELOG.md").read_text(encoding="utf-8")
    assert repo_changelog == cached_changelog


def test_idempotent_second_run(tmp_path: Path) -> None:
    """Running the sync twice must produce identical content."""
    fake_home = tmp_path / "home"
    fake_cache = fake_home / ".claude" / "plugins" / "cache" / "samvil" / "samvil"
    fake_cache.mkdir(parents=True)

    _run_sync(env_overrides={"HOME": str(fake_home)})
    snapshot_first = (fake_cache / "README.md").read_text(encoding="utf-8")
    _run_sync(env_overrides={"HOME": str(fake_home)})
    snapshot_second = (fake_cache / "README.md").read_text(encoding="utf-8")

    assert snapshot_first == snapshot_second


def test_preserves_cache_side_files_not_in_repo(tmp_path: Path) -> None:
    """Files present in the cache but absent from the repo must NOT be deleted.

    This protects CC-managed files like .mcp.json and .git-easy.json
    that the cache accumulates over time but are not part of the SAMVIL repo.
    """
    fake_home = tmp_path / "home"
    fake_cache = fake_home / ".claude" / "plugins" / "cache" / "samvil" / "samvil"
    fake_cache.mkdir(parents=True)
    sentinel = fake_cache / "ONLY_IN_CACHE.json"
    sentinel.write_text('{"created_by": "claude_code"}', encoding="utf-8")

    result = _run_sync(env_overrides={"HOME": str(fake_home)})

    assert result.returncode == 0
    assert sentinel.exists(), "sync must not delete cache-side files"


def test_graceful_when_cache_missing(tmp_path: Path) -> None:
    """If the cache directory doesn't exist, exit 0 with an info message."""
    fake_home = tmp_path / "home"  # cache subpath does NOT exist

    result = _run_sync(env_overrides={"HOME": str(fake_home)})

    assert result.returncode == 0
    assert "not found" in result.stdout or "not installed" in result.stdout


def test_quiet_mode_suppresses_output(tmp_path: Path) -> None:
    """--quiet must suppress per-target output."""
    fake_home = tmp_path / "home"
    fake_cache = fake_home / ".claude" / "plugins" / "cache" / "samvil" / "samvil"
    fake_cache.mkdir(parents=True)

    result = _run_sync("--quiet", env_overrides={"HOME": str(fake_home)})

    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_post_commit_hook_exists_and_executable() -> None:
    """The post-commit hook must exist and be executable for auto-sync."""
    hook = REPO_ROOT / ".githooks" / "post-commit"
    assert hook.exists(), f"missing: {hook}"
    assert os.access(hook, os.X_OK), f"not executable: {hook}"
    body = hook.read_text(encoding="utf-8")
    assert "sync-cache.sh" in body, "post-commit must invoke sync-cache.sh"
