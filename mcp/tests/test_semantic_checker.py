"""Tests for semantic_checker.py (v2.5.0, Phase 3)."""

import pytest

from samvil_mcp.semantic_checker import (
    analyze_code_snippet,
    downgrade_on_high_risk,
)


def test_clean_code_low_risk():
    code = """
async function createUser(email: string, password: string) {
    const hash = await bcrypt.hash(password, 10);
    return await db.user.create({ data: { email, passwordHash: hash } });
}
"""
    result = analyze_code_snippet(code, context_hint="user signup")
    assert result["risk_level"] == "LOW"
    assert result["total_findings"] == 0


def test_mock_comment_detected():
    code = """
// mock: replace with real API
function getOrders() {
    return [{ id: 1, status: "mock" }];
}
"""
    result = analyze_code_snippet(code)
    assert result["risk_level"] in ("MEDIUM", "HIGH")
    assert any(f["pattern"] == "stub_marker" for f in result["findings"])


def test_return_mock_response():
    code = """
async function processPayment(amount) {
    return { status: "succeeded", id: "mock_123" };
}
"""
    result = analyze_code_snippet(code, context_hint="process payment")
    # Should detect "mock_123" as mock marker
    assert result["risk_level"] in ("MEDIUM", "HIGH")


def test_hardcoded_secret():
    code = 'const apiKey = "sk_live_abc123def456ghi789";'
    result = analyze_code_snippet(code)
    assert result["risk_level"] == "HIGH"
    assert any(f["pattern"] == "hardcoded_secret" for f in result["findings"])


def test_hardcoded_test_user():
    code = 'const userId = "test@example.com";'
    result = analyze_code_snippet(code)
    assert result["risk_level"] == "HIGH"
    assert any(f["pattern"] == "hardcoded_test_user" for f in result["findings"])


def test_empty_catch():
    code = """
try {
    await riskyOp();
} catch(e) {}
"""
    result = analyze_code_snippet(code)
    assert any(f["pattern"] == "silent_error" for f in result["findings"])


def test_sample_data_array():
    code = """
const sampleOrders = [
    { id: 1 },
    { id: 2 }
];
"""
    result = analyze_code_snippet(code)
    assert result["risk_level"] == "HIGH"
    assert any(f["pattern"] == "sample_data" for f in result["findings"])


def test_socratic_questions_generated():
    code = """
function submit() {
    return "mock";
}
"""
    result = analyze_code_snippet(code, context_hint="submit form")
    # Socratic questions should be generated for risky patterns
    assert len(result["socratic_questions"]) > 0


def test_downgrade_high_risk_pass_to_fail():
    verdict, rationale = downgrade_on_high_risk("PASS", "HIGH")
    assert verdict == "FAIL"
    assert "Reward Hacking" in rationale


def test_downgrade_medium_risk_pass_to_partial():
    verdict, rationale = downgrade_on_high_risk("PASS", "MEDIUM")
    assert verdict == "PARTIAL"


def test_downgrade_low_risk_unchanged():
    verdict, rationale = downgrade_on_high_risk("PASS", "LOW")
    assert verdict == "PASS"
    assert rationale == ""


def test_downgrade_fail_unchanged():
    verdict, rationale = downgrade_on_high_risk("FAIL", "HIGH")
    assert verdict == "FAIL"
