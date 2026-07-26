"""Single source of truth for SAMVIL stage names and valid transitions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StageSpec:
    skill_name: str
    state_stage: str | None
    instruction: str
    valid_next: tuple[str, ...] = ()
    auto_proceed: bool = True
    requires_user_checkpoint: bool = False
    terminal: bool = False
    dynamic_next: bool = False


_STAGE_SPECS: tuple[StageSpec, ...] = (
    StageSpec(
        "samvil-interview", "interview", "references/codex-commands/samvil-interview.md", ("samvil-seed",)
    ),
    StageSpec(
        "samvil-seed", "seed", "references/codex-commands/samvil-seed.md", ("samvil-council", "samvil-design"), dynamic_next=True
    ),
    StageSpec(
        "samvil-council", "council", "references/codex-commands/samvil-council.md", ("samvil-design",)
    ),
    StageSpec(
        "samvil-design", "design", "references/codex-commands/samvil-design.md", ("samvil-scaffold",)
    ),
    StageSpec(
        "samvil-scaffold", "scaffold", "references/codex-commands/samvil-scaffold.md", ("samvil-build",)
    ),
    StageSpec(
        "samvil-build", "build", "references/codex-commands/samvil-build.md", ("samvil-qa",)
    ),
    StageSpec(
        "samvil-qa",
        "qa",
        "references/codex-commands/samvil-qa.md",
        ("samvil-qa", "samvil-deploy", "samvil-evolve", "samvil-retro"),
        dynamic_next=True,
    ),
    StageSpec(
        "samvil-deploy", "deploy", "references/codex-commands/samvil-deploy.md", ("samvil-retro",), requires_user_checkpoint=True
    ),
    StageSpec(
        "samvil-evolve", "evolve", "references/codex-commands/samvil-evolve.md", ("samvil-build", "samvil-retro"), dynamic_next=True
    ),
    StageSpec(
        "samvil-retro", "retro", "references/codex-commands/samvil-retro.md", (), terminal=True
    ),
    StageSpec(
        "samvil-analyze",
        None,
        "references/codex-commands/samvil-analyze.md",
        ("samvil-interview", "samvil-seed", "samvil-design", "samvil-qa"),
        dynamic_next=True,
        requires_user_checkpoint=True,
    ),
    StageSpec("samvil-doctor", None, "references/codex-commands/samvil-doctor.md", (), terminal=True),
    StageSpec("samvil-update", None, "references/codex-commands/samvil-update.md", (), terminal=True),
    StageSpec("samvil-resume", None, "references/codex-commands/samvil.md", (), terminal=True),
)

_AUXILIARY_SPECS: tuple[StageSpec, ...] = (
    StageSpec("samvil", None, "references/codex-commands/samvil.md", ("samvil-interview",)),
    StageSpec("samvil-pm-interview", None, "references/codex-commands/samvil-pm-interview.md", ("samvil-design",)),
)

_BY_SKILL = {spec.skill_name: spec for spec in (*_STAGE_SPECS, *_AUXILIARY_SPECS)}
_BY_STATE = {spec.state_stage: spec for spec in _STAGE_SPECS if spec.state_stage}

PIPELINE_STATE_STAGES: tuple[str, ...] = (
    "interview",
    "seed",
    "council",
    "design",
    "scaffold",
    "build",
    "qa",
    "deploy",
    "retro",
    "evolve",
    "complete",
)


def get_stage_spec(skill_name: str) -> StageSpec:
    try:
        return _BY_SKILL[skill_name]
    except KeyError as exc:
        raise ValueError(f"unknown stage skill: {skill_name!r}") from exc


def iter_stage_specs() -> tuple[StageSpec, ...]:
    return _STAGE_SPECS


def state_stage_for(stage_or_skill: str) -> str:
    if stage_or_skill in _BY_STATE:
        return stage_or_skill
    spec = _BY_SKILL.get(stage_or_skill)
    if spec is None or spec.state_stage is None:
        raise ValueError(f"unknown state stage: {stage_or_skill!r}")
    return spec.state_stage


def skill_for_state_stage(state_stage: str) -> str:
    try:
        return _BY_STATE[state_stage].skill_name
    except KeyError as exc:
        raise ValueError(f"unknown state stage: {state_stage!r}") from exc


def validate_stage_transition(from_skill: str, to_skill: str) -> bool:
    source = _BY_SKILL.get(from_skill)
    if source is None or to_skill not in _BY_SKILL:
        return False
    return to_skill in source.valid_next


def instruction_path_for(skill_name: str, repository_root: Path) -> Path:
    if not skill_name or skill_name.startswith("/") or ".." in Path(skill_name).parts:
        raise ValueError(f"unsafe stage skill: {skill_name!r}")
    spec = get_stage_spec(skill_name)
    root = Path(repository_root).expanduser().resolve(strict=False)
    candidate = (root / spec.instruction).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"instruction escapes repository root: {candidate}") from exc
    return candidate


__all__ = [
    "StageSpec",
    "PIPELINE_STATE_STAGES",
    "get_stage_spec",
    "instruction_path_for",
    "iter_stage_specs",
    "skill_for_state_stage",
    "state_stage_for",
    "validate_stage_transition",
]
