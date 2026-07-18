"""Static and runtime guards for hook state read-modify-write safety."""

from __future__ import annotations

import json
import os
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
source {HELPERS!s}
for i in $(seq 1 40); do
  samvil_contract_update_state {project!s} key_$i value_$i &
done
wait
"""
    env = os.environ.copy()
    env["CLAUDE_PLUGIN_ROOT"] = str(REPO)
    env["HOME"] = str(tmp_path / "home")

    subprocess.run(["bash", "-c", script], check=True, env=env, cwd=project)

    state = json.loads((project / "project.state.json").read_text(encoding="utf-8"))
    assert {f"key_{i}" for i in range(1, 41)} <= set(state)
