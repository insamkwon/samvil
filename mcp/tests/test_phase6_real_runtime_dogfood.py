"""Regression test for Phase 6 real runtime dogfood."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import ModuleType


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "phase6-real-runtime-dogfood.py"


def _load_phase6_module() -> ModuleType:
    import importlib.util

    spec = importlib.util.spec_from_file_location("phase6_real_runtime_dogfood", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_phase6_real_runtime_dogfood_script_passes():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=False,
        timeout=40,
    )

    assert result.returncode == 0, result.stderr
    assert "OK: phase6 real runtime dogfood passed" in result.stdout
    assert "saas-dashboard-runtime: pack=saas-dashboard" in result.stdout
    assert "browser-game-runtime: pack=browser-game" in result.stdout
    assert "retro=0" in result.stdout
    assert "html_bytes=" in result.stdout


def test_phase6_build_resolves_npm_from_fallback_dirs_when_path_is_minimal(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_phase6_module()
    fake_bin = tmp_path / "node-bin"
    fake_bin.mkdir()
    fake_npm = fake_bin / "npm"
    fake_npm.write_text(
        "#!/bin/sh\n"
        "test \"$1\" = \"run\"\n"
        "test \"$2\" = \"build\"\n"
        "echo fake npm build ok\n",
        encoding="utf-8",
    )
    fake_npm.chmod(0o755)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(module, "NODE_FALLBACK_DIRS", (fake_bin,), raising=False)

    output = module._run_build(tmp_path)

    assert "fake npm build ok" in output
