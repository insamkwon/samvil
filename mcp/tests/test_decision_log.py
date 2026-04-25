"""Unit tests for v3.3 Decision Log / ADR schema."""

from __future__ import annotations

import pytest

from samvil_mcp.decision_log import (
    ADR_STATUSES,
    DecisionADR,
    DecisionLogError,
    adr_path,
    adr_id_for_title,
    decision_dir,
    find_adrs_referencing,
    list_adrs,
    parse_adr_markdown,
    read_adr,
    render_adr_markdown,
    supersede_adr,
    supersession_chain,
    write_adr,
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


def test_write_adr_writes_under_samvil_decisions(tmp_path) -> None:
    adr = DecisionADR(
        adr_id="adr_2026-04-25T10-20-30_choose-api",
        title="Choose API",
        authors=["samvil-council"],
        decision="Use dict output.",
    )

    path = write_adr(adr, tmp_path)

    assert path == tmp_path / ".samvil" / "decisions" / f"{adr.adr_id}.md"
    assert path.exists()
    assert not path.with_suffix(".tmp").exists()
    assert read_adr(tmp_path, adr.adr_id).decision == "Use dict output."


def test_read_adr_returns_none_when_missing(tmp_path) -> None:
    assert read_adr(tmp_path, "adr_missing") is None


def test_read_adr_returns_none_when_corrupted(tmp_path) -> None:
    path = adr_path(tmp_path, "adr_bad")
    path.parent.mkdir(parents=True)
    path.write_text("not an ADR", encoding="utf-8")

    assert read_adr(tmp_path, "adr_bad") is None


def test_list_adrs_sorted_by_created_at_then_id(tmp_path) -> None:
    later = DecisionADR(
        adr_id="adr_b",
        title="B",
        authors=["samvil-council"],
        created_at="2026-04-25T10:20:31Z",
    )
    first = DecisionADR(
        adr_id="adr_a",
        title="A",
        authors=["samvil-council"],
        created_at="2026-04-25T10:20:30Z",
    )
    same_time = DecisionADR(
        adr_id="adr_c",
        title="C",
        authors=["samvil-council"],
        created_at="2026-04-25T10:20:30Z",
    )
    write_adr(later, tmp_path)
    write_adr(same_time, tmp_path)
    write_adr(first, tmp_path)

    assert [adr.adr_id for adr in list_adrs(tmp_path)] == ["adr_a", "adr_c", "adr_b"]


def test_list_adrs_filters_by_status(tmp_path) -> None:
    write_adr(
        DecisionADR(
            adr_id="adr_accepted",
            title="Accepted",
            status="accepted",
            authors=["samvil-council"],
        ),
        tmp_path,
    )
    write_adr(
        DecisionADR(adr_id="adr_proposed", title="Proposed", authors=["user"]),
        tmp_path,
    )

    assert [adr.adr_id for adr in list_adrs(tmp_path, status="accepted")] == [
        "adr_accepted"
    ]


def test_decision_dir_is_project_local(tmp_path) -> None:
    assert decision_dir(tmp_path) == tmp_path / ".samvil" / "decisions"


def test_adr_path_rejects_path_traversal(tmp_path) -> None:
    with pytest.raises(DecisionLogError, match="ADR id"):
        adr_path(tmp_path, "../outside")


def test_supersede_adr_updates_old_record(tmp_path) -> None:
    old = DecisionADR(
        adr_id="adr_old",
        title="Use local JSON",
        status="accepted",
        authors=["samvil-council"],
        created_at="2026-04-25T10:20:30Z",
    )
    new = DecisionADR(
        adr_id="adr_new",
        title="Use markdown ADR",
        status="accepted",
        authors=["samvil-council"],
        created_at="2026-04-25T10:30:30Z",
    )
    write_adr(old, tmp_path)
    write_adr(new, tmp_path)

    updated = supersede_adr(
        tmp_path,
        "adr_old",
        "adr_new",
        "Markdown is easier for PM audit.",
        reviewed_at="2026-04-25T10:40:30Z",
    )

    assert updated.status == "superseded"
    assert updated.superseded_by == "adr_new"
    assert updated.last_reviewed_at == "2026-04-25T10:40:30Z"
    assert updated.supersession_reason == "Markdown is easier for PM audit."
    assert read_adr(tmp_path, "adr_old").status == "superseded"


def test_supersede_adr_requires_existing_old_and_new(tmp_path) -> None:
    write_adr(
        DecisionADR(adr_id="adr_new", title="New", authors=["samvil-council"]),
        tmp_path,
    )

    with pytest.raises(DecisionLogError, match="old ADR"):
        supersede_adr(tmp_path, "adr_missing", "adr_new", "reason")

    with pytest.raises(DecisionLogError, match="replacement ADR"):
        supersede_adr(tmp_path, "adr_new", "adr_missing", "reason")


def test_supersede_adr_idempotent_for_same_target(tmp_path) -> None:
    old = DecisionADR(
        adr_id="adr_old",
        title="Old",
        status="superseded",
        superseded_by="adr_new",
        authors=["samvil-council"],
    )
    new = DecisionADR(adr_id="adr_new", title="New", authors=["samvil-council"])
    write_adr(old, tmp_path)
    write_adr(new, tmp_path)

    updated = supersede_adr(tmp_path, "adr_old", "adr_new", "same")

    assert updated.superseded_by == "adr_new"


def test_supersede_adr_rejects_conflicting_target(tmp_path) -> None:
    old = DecisionADR(
        adr_id="adr_old",
        title="Old",
        status="superseded",
        superseded_by="adr_new",
        authors=["samvil-council"],
    )
    new = DecisionADR(adr_id="adr_new", title="New", authors=["samvil-council"])
    other = DecisionADR(adr_id="adr_other", title="Other", authors=["samvil-council"])
    write_adr(old, tmp_path)
    write_adr(new, tmp_path)
    write_adr(other, tmp_path)

    with pytest.raises(DecisionLogError, match="already superseded"):
        supersede_adr(tmp_path, "adr_old", "adr_other", "conflict")


def test_supersession_chain_follows_replacements(tmp_path) -> None:
    write_adr(
        DecisionADR(
            adr_id="adr_a",
            title="A",
            status="superseded",
            superseded_by="adr_b",
            authors=["samvil-council"],
        ),
        tmp_path,
    )
    write_adr(
        DecisionADR(
            adr_id="adr_b",
            title="B",
            status="superseded",
            superseded_by="adr_c",
            authors=["samvil-council"],
        ),
        tmp_path,
    )
    write_adr(
        DecisionADR(adr_id="adr_c", title="C", authors=["samvil-council"]),
        tmp_path,
    )

    assert [adr.adr_id for adr in supersession_chain(tmp_path, "adr_a")] == [
        "adr_a",
        "adr_b",
        "adr_c",
    ]


def test_supersession_chain_stops_on_loop(tmp_path) -> None:
    write_adr(
        DecisionADR(
            adr_id="adr_a",
            title="A",
            status="superseded",
            superseded_by="adr_b",
            authors=["samvil-council"],
        ),
        tmp_path,
    )
    write_adr(
        DecisionADR(
            adr_id="adr_b",
            title="B",
            status="superseded",
            superseded_by="adr_a",
            authors=["samvil-council"],
        ),
        tmp_path,
    )

    assert [adr.adr_id for adr in supersession_chain(tmp_path, "adr_a")] == [
        "adr_a",
        "adr_b",
    ]


def test_find_adrs_referencing_matches_evidence_body_and_tags(tmp_path) -> None:
    write_adr(
        DecisionADR(
            adr_id="adr_api",
            title="API",
            authors=["samvil-council"],
            evidence=["mcp/samvil_mcp/server.py:2925"],
            context="Manifest tools need server wiring.",
        ),
        tmp_path,
    )
    write_adr(
        DecisionADR(
            adr_id="adr_tags",
            title="Tags",
            authors=["samvil-council"],
            tags=["decision-log"],
            decision="Use markdown ADR files.",
        ),
        tmp_path,
    )
    write_adr(
        DecisionADR(
            adr_id="adr_unrelated",
            title="Other",
            authors=["samvil-council"],
            context="No match here.",
        ),
        tmp_path,
    )

    assert find_adrs_referencing(tmp_path, "server.py") == ["adr_api"]
    assert find_adrs_referencing(tmp_path, "decision-log") == ["adr_tags"]
    assert find_adrs_referencing(tmp_path, "markdown ADR") == ["adr_tags"]


def test_find_adrs_referencing_is_case_sensitive(tmp_path) -> None:
    write_adr(
        DecisionADR(
            adr_id="adr_api",
            title="API",
            authors=["samvil-council"],
            context="Manifest tools need server wiring.",
        ),
        tmp_path,
    )

    assert find_adrs_referencing(tmp_path, "manifest") == []
    assert find_adrs_referencing(tmp_path, "Manifest") == ["adr_api"]


def test_find_adrs_referencing_handles_empty_dir(tmp_path) -> None:
    assert find_adrs_referencing(tmp_path, "anything") == []


def test_find_adrs_referencing_requires_target(tmp_path) -> None:
    with pytest.raises(DecisionLogError, match="target"):
        find_adrs_referencing(tmp_path, "")
