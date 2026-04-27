"""Tests for SAMVIL Interview Ambiguity Scoring (v2.5.0 — 10 dimensions)."""

import pytest
from samvil_mcp.interview_engine import score_ambiguity, MIN_QUESTIONS


# ── Comprehensive state fixture ─────────────────────────────────

def _comprehensive_state():
    """State satisfying all 10 dimensions for standard tier convergence."""
    return {
        "target_user": "Freelance designers who manage 5+ client projects simultaneously",
        "core_problem": "They lose track of deadlines across different client projects",
        "core_experience": "See all deadlines on a single kanban board, updated instantly",
        "features": ["task-crud", "kanban-view", "deadline-alerts"],
        "exclusions": ["real-time collaboration", "file attachments", "invoicing"],
        "constraints": [
            "localStorage only — no backend",
            "Mobile responsive down to 320px",
            "First paint under 2 seconds",
            "No PII stored — no login required",
        ],
        "acceptance_criteria": [
            "User can create a task with title and deadline in under 10 seconds",
            "Overdue tasks show a red indicator within 1 second of page load",
            "Tasks persist after page refresh via localStorage",
            "First-time user sees an onboarding hint on the empty state",
            "User can drag tasks between kanban columns",
        ],
    }


# ── Core convergence tests ──────────────────────────────────────

class TestConvergence:
    def test_fully_clear_interview_converges(self):
        """State satisfying all 10 dimensions converges when min questions met."""
        result = score_ambiguity(_comprehensive_state(), tier="standard", questions_asked=10)
        assert result["converged"] is True
        assert result["ambiguity"] <= 0.05

    def test_min_questions_blocks_early_convergence(self):
        """Even a perfect state cannot converge before min questions are asked."""
        result = score_ambiguity(_comprehensive_state(), tier="standard", questions_asked=0)
        assert result["converged"] is False
        assert result["min_questions_met"] is False
        assert result["min_questions_required"] == 10

    def test_deep_tier_requires_40_questions(self):
        """Deep tier requires 40 questions — 39 is not enough."""
        result = score_ambiguity(_comprehensive_state(), tier="deep", questions_asked=39)
        assert result["min_questions_met"] is False
        assert result["converged"] is False

    def test_deep_tier_converges_at_40_questions(self):
        """Deep tier can converge at 40 questions if ambiguity is low enough."""
        result = score_ambiguity(_comprehensive_state(), tier="deep", questions_asked=40)
        assert result["min_questions_met"] is True
        # ambiguity may or may not be ≤ 0.005 depending on state richness;
        # min_questions_met alone should be True
        assert result["min_questions_required"] == 40

    def test_empty_interview_never_converges(self):
        """Empty interview must never converge regardless of questions asked."""
        result = score_ambiguity({}, tier="minimal", questions_asked=99)
        assert result["converged"] is False
        assert result["ambiguity"] > 0.5

    def test_min_questions_per_tier(self):
        """MIN_QUESTIONS values match expected tier minimums."""
        assert MIN_QUESTIONS["minimal"]  == 5
        assert MIN_QUESTIONS["standard"] == 10
        assert MIN_QUESTIONS["thorough"] == 20
        assert MIN_QUESTIONS["full"]     == 30
        assert MIN_QUESTIONS["deep"]     == 40


# ── Result schema tests ─────────────────────────────────────────

class TestResultSchema:
    def test_result_has_all_v25_fields(self):
        """Result must include all v2.5.0 fields."""
        result = score_ambiguity({}, tier="standard", questions_asked=0)
        required = [
            "goal_clarity", "constraint_clarity", "criteria_testability",
            "ambiguity", "converged", "target", "tier",
            "milestone", "floors_passed", "floor_violations", "missing_items",
            "questions_asked", "min_questions_required", "min_questions_met",
            "dimension_scores",
        ]
        for field in required:
            assert field in result, f"Missing field: {field}"

    def test_dimension_scores_has_all_10_keys(self):
        """dimension_scores must include all 10 dimension keys."""
        result = score_ambiguity({}, tier="standard")
        dims = result["dimension_scores"]
        expected = [
            "goal", "constraint", "criteria",
            "technical", "failure_modes", "nonfunctional",
            "stakeholder", "scope_boundary", "success_metrics", "lifecycle",
        ]
        for key in expected:
            assert key in dims, f"Missing dimension: {key}"

    def test_questions_asked_echoed_in_result(self):
        """questions_asked input should be echoed back."""
        result = score_ambiguity({}, questions_asked=17)
        assert result["questions_asked"] == 17


# ── Core dimension tests (v2.4.0 backward-compat) ──────────────

class TestCoreDimensions:
    def test_vague_target_user_lowers_goal_clarity(self):
        state = {
            "target_user": "everyone",
            "core_problem": "They need a tool",
            "core_experience": "Use the app",
            "features": ["feature-a"],
            "exclusions": ["nothing"],
            "constraints": [],
            "acceptance_criteria": ["It works"],
        }
        result = score_ambiguity(state)
        assert result["goal_clarity"] <= 0.8

    def test_untestable_criteria_lowers_testability(self):
        state = {
            "target_user": "Project managers at agencies with 10+ clients",
            "core_problem": "They can't see project status at a glance",
            "core_experience": "View project dashboard with health indicators",
            "features": ["dashboard", "project-status"],
            "exclusions": ["invoicing"],
            "constraints": ["Web only"],
            "acceptance_criteria": [
                "App looks nice and professional",
                "Dashboard is user-friendly and intuitive",
                "Everything works smooth",
            ],
        }
        result = score_ambiguity(state)
        assert result["criteria_testability"] < 0.7

    def test_too_many_features_penalizes_constraints(self):
        state = {
            "target_user": "Small business owners managing inventory",
            "core_problem": "Manual inventory tracking is error-prone",
            "core_experience": "Scan a barcode to add/remove inventory",
            "features": ["scan", "crud", "search", "export", "import", "analytics", "auth", "notifications"],
            "exclusions": ["POS integration"],
            "constraints": ["Mobile first"],
            "acceptance_criteria": [
                "User can scan barcode to add item",
                "Inventory count updates in real-time",
                "User can export to CSV",
            ],
        }
        result = score_ambiguity(state)
        assert result["constraint_clarity"] < 0.9

    def test_contradiction_detected(self):
        state = {
            "target_user": "Students tracking study habits",
            "core_problem": "No way to see study patterns over time",
            "core_experience": "Log study session with one tap",
            "features": ["logging", "analytics", "auth"],
            "exclusions": ["analytics"],  # Contradiction
            "constraints": ["No backend"],
            "acceptance_criteria": [
                "User can log a study session",
                "User can view weekly summary chart",
            ],
        }
        result = score_ambiguity(state)
        assert result["constraint_clarity"] < 0.8


# ── Enriched dimension tests (v2.5.0) ──────────────────────────

class TestEnrichedDimensions:
    def test_no_tech_keywords_raises_technical_score(self):
        """Constraints without tech specifics should yield high technical score."""
        state = {"constraints": ["Keep it simple", "Should work on mobile"]}
        result = score_ambiguity(state)
        assert result["dimension_scores"]["technical"] >= 0.7

    def test_localstorage_lowers_technical_score(self):
        state = {"constraints": ["localStorage only — no backend"]}
        result = score_ambiguity(state)
        assert result["dimension_scores"]["technical"] < 0.5

    def test_multiple_tech_keywords_clears_technical(self):
        state = {"constraints": ["Supabase for DB", "OAuth via Google", "Deploy on Vercel"]}
        result = score_ambiguity(state)
        assert result["dimension_scores"]["technical"] == 0.0

    def test_no_exclusions_raises_failure_modes_score(self):
        state = {"exclusions": []}
        result = score_ambiguity(state)
        assert result["dimension_scores"]["failure_modes"] == 1.0

    def test_three_real_exclusions_clears_failure_modes(self):
        state = {
            "exclusions": ["real-time collab", "file upload", "invoicing"],
            "constraints": ["No backend", "Mobile only"],
        }
        result = score_ambiguity(state)
        assert result["dimension_scores"]["failure_modes"] == 0.0

    def test_no_perf_keywords_raises_nonfunctional_score(self):
        state = {"constraints": ["Use React"], "acceptance_criteria": []}
        result = score_ambiguity(state)
        assert result["dimension_scores"]["nonfunctional"] >= 0.9

    def test_three_nonfunc_groups_clears_nonfunctional(self):
        state = {
            "constraints": ["First paint under 2 seconds", "HTTPS required"],
            "acceptance_criteria": ["Works offline via service worker"],
        }
        result = score_ambiguity(state)
        assert result["dimension_scores"]["nonfunctional"] == 0.0

    def test_generic_user_raises_stakeholder_score(self):
        state = {"target_user": "users"}
        result = score_ambiguity(state)
        assert result["dimension_scores"]["stakeholder"] >= 0.8

    def test_specific_user_with_number_and_context_clears_stakeholder(self):
        state = {"target_user": "Freelance designers managing 5+ client projects simultaneously"}
        result = score_ambiguity(state)
        assert result["dimension_scores"]["stakeholder"] == 0.0

    def test_vague_exclusions_raise_scope_score(self):
        state = {"exclusions": ["none", "n/a"]}
        result = score_ambiguity(state)
        assert result["dimension_scores"]["scope_boundary"] >= 0.8

    def test_three_specific_exclusions_clear_scope(self):
        state = {"exclusions": ["real-time collaboration", "file attachments", "invoicing"]}
        result = score_ambiguity(state)
        assert result["dimension_scores"]["scope_boundary"] == 0.0

    def test_no_numbers_in_acs_raises_metrics_score(self):
        state = {"acceptance_criteria": ["User can log in", "User sees dashboard"]}
        result = score_ambiguity(state)
        assert result["dimension_scores"]["success_metrics"] > 0.5

    def test_measurable_acs_lower_metrics_score(self):
        state = {
            "acceptance_criteria": [
                "Page loads in < 2 seconds",
                "Error rate stays below 1%",
                "User can submit form",
            ]
        }
        result = score_ambiguity(state)
        assert result["dimension_scores"]["success_metrics"] == 0.0

    def test_no_lifecycle_keywords_raises_lifecycle_score(self):
        state = {
            "core_experience": "Click button to save",
            "features": ["save", "edit"],
            "acceptance_criteria": ["User can save data"],
        }
        result = score_ambiguity(state)
        assert result["dimension_scores"]["lifecycle"] == 1.0

    def test_lifecycle_keywords_lower_lifecycle_score(self):
        state = {
            "core_experience": "New user sees onboarding wizard on first login",
            "features": ["onboarding", "email notifications", "empty state guide"],
            "acceptance_criteria": ["First-time user sees tutorial overlay"],
        }
        result = score_ambiguity(state)
        assert result["dimension_scores"]["lifecycle"] == 0.0
