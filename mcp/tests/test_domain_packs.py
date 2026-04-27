"""Tests for Domain Packs."""

from samvil_mcp.domain_packs import (
    get_domain_pack,
    list_domain_packs,
    match_domain_packs,
    render_domain_packs,
)


def test_list_domain_packs_filters_solution_type():
    packs = list_domain_packs(solution_type="game")

    assert [pack.pack_id for pack in packs] == ["browser-game", "game-phaser"]


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


# ── M3: game-phaser domain pack ──────────────────────────────


def test_game_phaser_pack_exists():
    pack = get_domain_pack("game-phaser")
    assert pack is not None
    assert pack.domain == "game"
    assert "game" in pack.solution_types
    assert "phaser" in pack.signals
    assert "Scene" in pack.core_entities
    assert len(pack.interview_probes) >= 5
    assert len(pack.build_guidance) >= 5
    assert len(pack.qa_focus) >= 5


def test_game_phaser_matches_phaser_seed():
    matches = match_domain_packs({
        "solution_type": "game",
        "app_idea": "Phaser platformer with tilemap and sprite animation",
        "features": ["physics collision", "scene transitions"],
    })
    phaser_match = [m for m in matches if m["pack_id"] == "game-phaser"]
    assert len(phaser_match) == 1
    assert phaser_match[0]["score"] >= 5


def test_game_phaser_render_scoped():
    pack = get_domain_pack("game-phaser")
    text = render_domain_packs([pack], stage="build")
    assert "Build guidance" in text
    assert "Phaser.Scene" in text
    assert "Interview probes" not in text


def test_game_phaser_not_in_dashboard_filter():
    packs = list_domain_packs(solution_type="dashboard")
    ids = [p.pack_id for p in packs]
    assert "game-phaser" not in ids


# ── M3: webapp-enterprise domain pack ────────────────────────


def test_webapp_enterprise_pack_exists():
    pack = get_domain_pack("webapp-enterprise")
    assert pack is not None
    assert pack.domain == "enterprise"
    assert "web-app" in pack.solution_types
    assert "auth" in pack.signals
    assert "Organization" in pack.core_entities
    assert len(pack.key_workflows) >= 5
    assert len(pack.interview_probes) >= 5
    assert len(pack.qa_focus) >= 5


def test_webapp_enterprise_matches_enterprise_seed():
    matches = match_domain_packs({
        "solution_type": "web-app",
        "app_idea": "Team management with auth roles and organization settings",
        "features": ["role-based permissions", "team workspace", "audit log"],
    })
    ent_match = [m for m in matches if m["pack_id"] == "webapp-enterprise"]
    assert len(ent_match) == 1
    assert ent_match[0]["score"] >= 5


def test_webapp_enterprise_render_scoped():
    pack = get_domain_pack("webapp-enterprise")
    text = render_domain_packs([pack], stage="interview")
    assert "Interview probes" in text
    assert "RBAC" in text or "permission" in text.lower()
    assert "Build guidance" not in text


def test_webapp_enterprise_not_in_game_filter():
    packs = list_domain_packs(solution_type="game")
    ids = [p.pack_id for p in packs]
    assert "webapp-enterprise" not in ids


def test_total_pack_count():
    packs = list_domain_packs()
    assert len(packs) == 5


# ── Option D: Enterprise BFF/monorepo/SSO/OpenAPI ────────────


def test_webapp_enterprise_build_guidance_has_bff_pattern():
    pack = get_domain_pack("webapp-enterprise")
    guidance_text = " ".join(pack.build_guidance)
    assert "BFF" in guidance_text or "proxy" in guidance_text.lower()


def test_webapp_enterprise_build_guidance_has_monorepo_structure():
    pack = get_domain_pack("webapp-enterprise")
    guidance_text = " ".join(pack.build_guidance)
    assert "turborepo" in guidance_text.lower() or "monorepo" in guidance_text.lower()
    assert "packages/" in guidance_text


def test_webapp_enterprise_build_guidance_has_sso_providers():
    pack = get_domain_pack("webapp-enterprise")
    guidance_text = " ".join(pack.build_guidance)
    assert "Clerk" in guidance_text
