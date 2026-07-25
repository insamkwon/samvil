"""Deterministic interaction harness for end-to-end workflow dogfoods."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from samvil_mcp.interview_engine import score_ambiguity
from samvil_mcp.orchestrator import aggregate_orchestrator_state


@dataclass
class InteractionRecorder:
    """Capture each user interaction emitted by the exercised workflow."""

    touchpoints: list[dict[str, Any]] = field(default_factory=list)

    def ask(
        self,
        *,
        stage: str,
        checkpoint: str,
        questions: tuple[str, ...] = (),
    ) -> None:
        if questions and not 1 <= len(questions) <= 3:
            raise ValueError("one interaction may contain at most three questions")
        row: dict[str, Any] = {
            "stage": stage,
            "checkpoint": checkpoint,
            "calls": 1,
        }
        if questions:
            row["questions"] = len(questions)
        self.touchpoints.append(row)

    @property
    def calls(self) -> int:
        return sum(int(row["calls"]) for row in self.touchpoints)

    @property
    def questions_asked(self) -> int:
        return sum(int(row.get("questions", 0)) for row in self.touchpoints)


def run_standard_interaction_workflow(
    project_root: str | Path,
    *,
    prompt: str,
    interview_state: dict[str, Any],
    host_name: str = "codex_cli",
) -> dict[str, Any]:
    """Exercise the standard orchestrator, interview, and seed checkpoints."""
    recorder = InteractionRecorder()
    orchestrator = aggregate_orchestrator_state(
        str(project_root),
        prompt=prompt,
        cli_tier="",
        mode_hint="",
        host_name=host_name,
    )

    if orchestrator["tier"]["source"] == "default":
        recorder.ask(stage="orchestrator", checkpoint="tier")

    recorder.ask(stage="interview", checkpoint="epic_claim")
    batches = (
        (
            "core_batch",
            (
                "Who has this problem?",
                "What is the recurring pain?",
                "What should the core experience feel like?",
            ),
        ),
        (
            "scope_batch",
            (
                "Which capabilities are essential?",
                "What is explicitly out of scope?",
                "Which constraints are non-negotiable?",
            ),
        ),
        (
            "lifecycle_batch",
            (
                "What happens on first use?",
                "Why does the user return?",
            ),
        ),
        (
            "success_metric_batch",
            (
                "Which observable result proves success?",
                "Which failure must be caught?",
            ),
        ),
    )
    for checkpoint, questions in batches:
        recorder.ask(
            stage="interview",
            checkpoint=checkpoint,
            questions=questions,
        )

    interview = score_ambiguity(
        interview_state,
        tier="standard",
        questions_asked=recorder.questions_asked,
    )
    recorder.ask(stage="interview", checkpoint="summary_review")
    recorder.ask(stage="interview", checkpoint="restate_review")
    recorder.ask(stage="interview", checkpoint="pain_capture")

    if not interview_state.get("acceptance_criteria"):
        raise ValueError("seed review requires acceptance criteria")
    recorder.ask(stage="seed", checkpoint="principles_review")
    recorder.ask(stage="seed", checkpoint="behavior_review")
    recorder.ask(stage="seed", checkpoint="final_seed_approval")

    return {
        "orchestrator": orchestrator,
        "interview": interview,
        "touchpoints": recorder.touchpoints,
        "ask_user_question_calls": recorder.calls,
        "questions_asked": recorder.questions_asked,
    }
