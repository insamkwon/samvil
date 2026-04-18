"""Per-AC Checklist Aggregator (v2.5.0, Ouroboros #08).

Structures QA verdicts as per-AC checklists with:
  - Individual check items (pass/fail + evidence)
  - Aggregation to PASS/PARTIAL/FAIL verdict
  - Cross-AC summary (RunFeedback)

Aligns with v3 P1 Evidence-based Assertions — every passed check
must cite file:line evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal


Verdict = Literal["PASS", "PARTIAL", "FAIL"]


@dataclass(frozen=True)
class ACCheckItem:
    """Single check item within an AC."""
    description: str
    passed: bool
    evidence: tuple[str, ...] = ()  # file:line references
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "passed": self.passed,
            "evidence": list(self.evidence),
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class ACChecklist:
    """Checklist of items for a single AC."""
    ac_id: str
    ac_description: str
    items: tuple[ACCheckItem, ...] = ()

    @property
    def passed_count(self) -> int:
        return sum(1 for i in self.items if i.passed)

    @property
    def total_count(self) -> int:
        return len(self.items)

    @property
    def verdict(self) -> Verdict:
        if not self.items:
            return "FAIL"
        if self.passed_count == self.total_count:
            return "PASS"
        if self.passed_count == 0:
            return "FAIL"
        return "PARTIAL"

    def to_dict(self) -> dict:
        return {
            "ac_id": self.ac_id,
            "ac_description": self.ac_description,
            "items": [i.to_dict() for i in self.items],
            "passed_count": self.passed_count,
            "total_count": self.total_count,
            "verdict": self.verdict,
        }


@dataclass(frozen=True)
class RunFeedback:
    """Aggregated feedback across multiple ACs."""
    ac_full_pass: int
    ac_partial: int
    ac_fail: int
    item_pass_rate: float
    missing_evidence_count: int
    checklists: tuple[ACChecklist, ...] = ()

    @property
    def overall_verdict(self) -> Verdict:
        total_acs = self.ac_full_pass + self.ac_partial + self.ac_fail
        if total_acs == 0:
            return "FAIL"
        if self.ac_fail > 0:
            return "FAIL"
        if self.ac_partial > 0:
            return "PARTIAL"
        return "PASS"

    def to_dict(self) -> dict:
        return {
            "ac_full_pass": self.ac_full_pass,
            "ac_partial": self.ac_partial,
            "ac_fail": self.ac_fail,
            "item_pass_rate": self.item_pass_rate,
            "missing_evidence_count": self.missing_evidence_count,
            "overall_verdict": self.overall_verdict,
            "checklists": [c.to_dict() for c in self.checklists],
        }


def aggregate(checklists: list[ACChecklist]) -> RunFeedback:
    """Aggregate multiple AC checklists into a RunFeedback."""
    ac_full_pass = sum(1 for c in checklists if c.verdict == "PASS")
    ac_partial = sum(1 for c in checklists if c.verdict == "PARTIAL")
    ac_fail = sum(1 for c in checklists if c.verdict == "FAIL")

    total_items = sum(c.total_count for c in checklists)
    passed_items = sum(c.passed_count for c in checklists)
    item_pass_rate = (passed_items / total_items) if total_items > 0 else 0.0

    missing_evidence_count = sum(
        1 for c in checklists
        for i in c.items
        if i.passed and not i.evidence
    )

    return RunFeedback(
        ac_full_pass=ac_full_pass,
        ac_partial=ac_partial,
        ac_fail=ac_fail,
        item_pass_rate=round(item_pass_rate, 3),
        missing_evidence_count=missing_evidence_count,
        checklists=tuple(checklists),
    )


def checklist_from_dict(data: dict) -> ACChecklist:
    """Deserialize ACChecklist from dict."""
    items = tuple(
        ACCheckItem(
            description=i["description"],
            passed=bool(i.get("passed", False)),
            evidence=tuple(i.get("evidence", [])),
            rationale=i.get("rationale", ""),
        )
        for i in data.get("items", [])
    )
    return ACChecklist(
        ac_id=data.get("ac_id", ""),
        ac_description=data.get("ac_description", ""),
        items=items,
    )


def validate_evidence_mandatory(checklist: ACChecklist) -> list[str]:
    """Apply P1 Evidence-mandatory rule: PASS items must have evidence.

    Returns list of violation messages. Empty = all compliant.
    """
    violations = []
    for item in checklist.items:
        if item.passed and not item.evidence:
            violations.append(
                f"{checklist.ac_id}: '{item.description}' marked PASS but no evidence — auto-FAIL per P1"
            )
    return violations


def enforce_evidence_mandatory(checklist: ACChecklist) -> ACChecklist:
    """Downgrade PASS items without evidence to FAIL (P1 enforcement)."""
    new_items = []
    for item in checklist.items:
        if item.passed and not item.evidence:
            new_items.append(ACCheckItem(
                description=item.description,
                passed=False,
                evidence=(),
                rationale=f"{item.rationale} [Auto-FAIL: P1 Evidence-mandatory violation]".strip(),
            ))
        else:
            new_items.append(item)
    return ACChecklist(
        ac_id=checklist.ac_id,
        ac_description=checklist.ac_description,
        items=tuple(new_items),
    )
