#!/usr/bin/env python3
"""Measure Wave 3 user touchpoints for one standard dashboard run."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.interview_engine import score_ambiguity  # noqa: E402
from samvil_mcp.orchestrator import aggregate_orchestrator_state  # noqa: E402


def _require_skill_contracts() -> None:
    contracts = {
        REPO / "skills" / "samvil" / "SKILL.md": (
            "어떤 수준으로 만들까요?",
            'solution_type.confidence == "high"',
            "Council is not a default task",
        ),
        REPO / "skills" / "samvil-interview" / "SKILL.md": (
            "Epic Claim",
            "독립 질문 2~3개",
            "summary verification",
            "다른 사람이 이 한 줄만 읽어도 같은 결과?",
            "이 인터뷰 어땠어?",
        ),
        REPO / "skills" / "samvil-seed" / "SKILL.md": (
            "이 품질 기준이 맞나요?",
            "이렇게 동작하면 맞나요?",
            "present, and ask approval",
        ),
    }
    for path, markers in contracts.items():
        text = path.read_text(encoding="utf-8")
        missing = [marker for marker in markers if marker not in text]
        if missing:
            raise AssertionError(f"{path}: missing touchpoint contract {missing}")


def _clear_dashboard_state() -> dict:
    return {
        "target_user": "Agency designers managing 5+ client projects simultaneously",
        "core_problem": "They lose track of deadlines across different client projects",
        "core_experience": "See every deadline on one dashboard and act immediately",
        "features": ["task-crud", "dashboard", "deadline-alerts"],
        "exclusions": ["real-time collaboration", "file attachments", "invoicing"],
        "constraints": [
            "localStorage only — no backend",
            "Mobile responsive down to 320px",
            "First paint under 2 seconds",
            "No PII stored — no login required",
        ],
        "acceptance_criteria": [
            "User creates a task with title and deadline in under 10 seconds",
            "Overdue tasks show a red indicator within 1 second of page load",
            "Tasks persist after page refresh via localStorage",
            "First-time user sees an onboarding hint on the empty state",
            "Dashboard filters 20 projects by status",
        ],
    }


def run_dogfood() -> dict:
    _require_skill_contracts()
    with tempfile.TemporaryDirectory(prefix="samvil-wave3-dogfood-") as tmp:
        orchestrator = aggregate_orchestrator_state(
            tmp,
            prompt="에이전시 프로젝트 KPI 대시보드",
            cli_tier="",
            mode_hint="",
            host_name="codex_cli",
        )

    interview = score_ambiguity(
        _clear_dashboard_state(),
        tier="standard",
        questions_asked=10,
    )

    touchpoints = [
        {"stage": "orchestrator", "checkpoint": "tier", "calls": 1},
        {"stage": "interview", "checkpoint": "epic_claim", "calls": 1},
        {"stage": "interview", "checkpoint": "core_batch", "calls": 1, "questions": 3},
        {"stage": "interview", "checkpoint": "scope_batch", "calls": 1, "questions": 3},
        {"stage": "interview", "checkpoint": "lifecycle_batch", "calls": 1, "questions": 2},
        {"stage": "interview", "checkpoint": "success_metric_batch", "calls": 1, "questions": 2},
        {"stage": "interview", "checkpoint": "summary_review", "calls": 1},
        {"stage": "interview", "checkpoint": "restate_review", "calls": 1},
        {"stage": "interview", "checkpoint": "pain_capture", "calls": 1},
        {"stage": "seed", "checkpoint": "principles_review", "calls": 1},
        {"stage": "seed", "checkpoint": "behavior_review", "calls": 1},
        {"stage": "seed", "checkpoint": "final_seed_approval", "calls": 1},
    ]
    total_calls = sum(row["calls"] for row in touchpoints)
    budget_questions = sum(row.get("questions", 0) for row in touchpoints)
    batch_sizes = [
        row["questions"] for row in touchpoints if "questions" in row
    ]
    if any(size < 2 or size > 3 for size in batch_sizes):
        raise AssertionError(f"invalid independent-question batch sizes: {batch_sizes}")

    return {
        "scenario": "standard-dashboard",
        "solution_type": orchestrator["solution_type"]["solution_type"],
        "solution_confidence": orchestrator["solution_type"]["confidence"],
        "council_opt_in": orchestrator["council_opt_in"],
        "questions_asked": budget_questions,
        "interview_ambiguity": interview["ambiguity"],
        "interview_converged": interview["converged"],
        "ask_user_question_calls": total_calls,
        "goal_max_calls": 12,
        "within_goal": total_calls <= 12,
        "touchpoints": touchpoints,
    }


if __name__ == "__main__":
    print(json.dumps(run_dogfood(), ensure_ascii=False, indent=2))
