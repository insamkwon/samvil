"""Unit tests for v3.3 Decision Log / ADR schema."""

from __future__ import annotations

import pytest

from samvil_mcp.decision_log import (
    ADR_STATUSES,
    DecisionADR,
    DecisionLogError,
    adr_id_for_title,
    parse_adr_markdown,
    render_adr_markdown,
)


def test_adr_status_whitelist_is_explicit() -> None:
    assert ADR_STATUSES == ("proposed", "accepted", "superseded", "rejected")


def test_adr_id_for_title_is_sortable_and_filesystem_safe() -> None:
    adr_id = adr_id_for_title(
        "Use Next.js App Router?",
        ts="2026-04-25T10:20:30Z",
    )
    assert adr_id == "adr_2026-04-25T10-20-30_use-next-js-app-router"


def test_decision_adr_defaults_last_reviewed_to_created_at() -> None:
    adr = DecisionADR(
        adr_id="adr_1",
        title="Choose API shape",
        authors=["samvil-council"],
        created_at="2026-04-25T10:20:30Z",
        context="Need a stable API.",
        decision="Use JSON-in/dict-out.",
    )
    assert adr.status == "proposed"
    assert adr.last_reviewed_at == "2026-04-25T10:20:30Z"
    assert adr.superseded_by is None


def test_decision_adr_rejects_invalid_status() -> None:
    with pytest.raises(DecisionLogError, match="status"):
        DecisionADR(
            adr_id="adr_1",
            title="Bad status",
            status="done",
            authors=["tester"],
        )


def test_decision_adr_requires_authors() -> None:
    with pytest.raises(DecisionLogError, match="authors"):
        DecisionADR(adr_id="adr_1", title="No author")


def test_render_adr_markdown_contains_json_frontmatter() -> None:
    adr = DecisionADR(
        adr_id="adr_1",
        title="Choose routing mode",
        status="accepted",
        authors=["samvil-council", "user"],
        evidence=["references/model-profiles-schema.md:53"],
        tags=["routing"],
        context="Agents need deterministic model routing.",
        decision="Route by task role.",
        consequences="Routing decisions are auditable.",
        alternatives="Let each skill pick its own model.",
    )

    text = render_adr_markdown(adr)

    assert text.startswith("---\n")
    assert 'id: "adr_1"' in text
    assert 'status: "accepted"' in text
    assert 'authors: ["samvil-council", "user"]' in text
    assert "## Context\nAgents need deterministic model routing." in text


def test_parse_adr_markdown_roundtrip() -> None:
    adr = DecisionADR(
        adr_id="adr_1",
        title="Persist council decisions",
        status="accepted",
        created_at="2026-04-25T10:20:30Z",
        last_reviewed_at="2026-04-25T10:25:00Z",
        authors=["samvil-council"],
        evidence=["references/council-protocol.md:156"],
        tags=["council", "adr"],
        supersedes=["adr_old"],
        context="decisions.log is hard to audit.",
        decision="Promote binding decisions to ADR markdown.",
        consequences="PMs can read the decision history.",
        alternatives="Keep append-only JSONL only.",
    )

    parsed = parse_adr_markdown(render_adr_markdown(adr))

    assert parsed.adr_id == adr.adr_id
    assert parsed.title == adr.title
    assert parsed.status == "accepted"
    assert parsed.created_at == "2026-04-25T10:20:30Z"
    assert parsed.last_reviewed_at == "2026-04-25T10:25:00Z"
    assert parsed.authors == ["samvil-council"]
    assert parsed.evidence == ["references/council-protocol.md:156"]
    assert parsed.tags == ["council", "adr"]
    assert parsed.supersedes == ["adr_old"]
    assert parsed.context == "decisions.log is hard to audit."
    assert parsed.decision == "Promote binding decisions to ADR markdown."


def test_parse_adr_markdown_rejects_missing_frontmatter() -> None:
    with pytest.raises(DecisionLogError, match="frontmatter"):
        parse_adr_markdown("# Missing frontmatter")
