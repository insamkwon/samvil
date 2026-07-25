"""Static and runtime guards for hook state read-modify-write safety."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
HELPERS = REPO / "hooks" / "_contract-helpers.sh"


def _function_block(text: str, name: str) -> str:
    start = text.index(f"{name}() {{")
    next_comment = text.find("\n# ", start)
    return text[start:] if next_comment < 0 else text[start:next_comment]


def test_state_mutation_heredocs_use_flock_and_atomic_replace() -> None:
    text = HELPERS.read_text(encoding="utf-8")
    for name in (
        "samvil_contract_update_state",
        "samvil_contract_append_stage_claim_to_state",
    ):
        block = _function_block(text, name)
        assert "fcntl.flock" in block
        assert "os.replace" in block
        assert "os.fsync" in block


def test_concurrent_hook_state_updates_preserve_every_key(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "project.state.json").write_text("{}", encoding="utf-8")
    script = f"""
set -e
source {shlex.quote(str(HELPERS))}
for i in $(seq 1 40); do
  samvil_contract_update_state {shlex.quote(str(project))} key_$i value_$i &
done
wait
"""
    env = os.environ.copy()
    env["CLAUDE_PLUGIN_ROOT"] = str(REPO)
    env["HOME"] = str(tmp_path / "home")

    subprocess.run(["bash", "-c", script], check=True, env=env, cwd=project)

    state = json.loads((project / "project.state.json").read_text(encoding="utf-8"))
    assert {f"key_{i}" for i in range(1, 41)} <= set(state)


def test_corrupt_state_is_not_silently_replaced(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    state_path = project / "project.state.json"
    state_path.write_text("{corrupt", encoding="utf-8")
    script = (
        f"source {shlex.quote(str(HELPERS))}; "
        f"samvil_contract_update_state {shlex.quote(str(project))} key value"
    )
    env = os.environ.copy()
    env["CLAUDE_PLUGIN_ROOT"] = str(REPO)

    subprocess.run(["bash", "-c", script], check=True, env=env, cwd=project)

    assert state_path.read_text(encoding="utf-8") == "{corrupt"
