"""Tests for Domain Packs."""

from samvil_mcp.domain_packs import (
    get_domain_pack,
    list_domain_packs,
    match_domain_packs,
    render_domain_packs,
)


def test_list_domain_packs_filters_solution_type():
    packs = list_domain_packs(solution_type="game")

    assert [pack.pack_id for pack in packs] == ["browser-game"]


def test_list_domain_packs_filters_domain_and_stage():
    packs = list_domain_packs(domain="saas", stage="qa")

    assert [pack.pack_id for pack in packs] == ["saas-dashboard"]
    assert "Metric" in packs[0].core_entities


def test_get_domain_pack_returns_none_for_missing():
    assert get_domain_pack("does-not-exist") is None


def test_render_domain_packs_can_scope_to_stage():
    pack = get_domain_pack("mobile-habit")
    assert pack is not None

    text = render_domain_packs([pack], stage="qa")

    assert "# Domain Packs" in text
    assert "mobile-habit" in text
    assert "QA focus" in text
    assert "Interview probes" not in text
    assert "Timezone boundaries" in text


def test_match_domain_packs_ranks_by_solution_type_and_signals():
    matches = match_domain_packs({
        "solution_type": "dashboard",
        "app_idea": "Admin metrics dashboard with reporting filters",
        "features": ["KPI cards", "date range analytics"],
    })

    assert matches[0]["pack_id"] == "saas-dashboard"
    assert matches[0]["confidence"] == "high"
    assert any(reason.startswith("solution_type:") for reason in matches[0]["reasons"])
    assert any(reason.startswith("signals:") for reason in matches[0]["reasons"])


def test_match_domain_packs_returns_empty_for_unknown_seed():
    assert match_domain_packs({"solution_type": "automation", "app_idea": "file renamer"}) == []
