"""Reference consolidation regression checks."""

from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
REFERENCES = REPO / "references"


def test_deprecated_reference_duplicates_are_absent() -> None:
    deprecated = {
        "decision-log-schema.md",
        "gate-vs-degradation.md",
        "host-capability-schema.md",
        "interview-levels.md",
        "manifest-schema.md",
        "migration-v2-to-v3.md",
        "orchestrator-schema.md",
        "plugin-api.md",
    }
    present = {path.name for path in REFERENCES.glob("*.md")}
    assert not (deprecated & present)
    assert len(present) <= 49
