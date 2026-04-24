"""AC leaf schema (③) — 14 fields with ownership rules.

Per HANDOFF-v3.2-DECISIONS.md §3.③:

  * Epic / Feature / Leaf is the hierarchy.
  * Every leaf carries 14 metadata fields.
  * **User owns** `intent` and `verification` (AI proposes, user confirms,
    fields lock after approval).
  * **AI owns** 9 inferred fields filled during Seed / Design.
  * **Runtime owns** `status`, `evidence`, `failure_history` — only the
    Judge role may flip them (⑤ enforces via ledger).
  * A non-testable AC is not an AC — it becomes
    `seed.candidates[]`, not `features[].acceptance_criteria[]`.

This module defines:

  * `ACLeaf` dataclass covering all 14 fields.
  * Ownership constants (`USER_FIELDS`, `AI_SEED_FIELDS`, `AI_DESIGN_FIELDS`,
    `RUNTIME_FIELDS`).
  * Validator `validate_leaf(leaf, *, stage)` that checks which fields
    must be present at which stage (Interview / Seed / Design / Build+).
  * Parallel-safety helper `compute_parallel_safety(leaves)` — two leaves
    with overlapping `likely_files` or `shared_resources` are marked
    `parallel_safety=false`.
  * Testability sniff test `ac_is_testable(leaf)` — used to reject leaves
    whose `verification` lacks a measurable step.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Iterable


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LeafStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"


# Six-role enum mirror from model_role (kept local to avoid a circular
# import when seed_manager loads both modules).
class CostTierHint(str, Enum):
    FRUGAL = "frugal"
    BALANCED = "balanced"
    FRONTIER = "frontier"


@dataclass
class ACLeaf:
    """Leaf-level acceptance criterion with 14 metadata fields.

    Spec note: HANDOFF-v3.2-DECISIONS.md §3.③ describes "14 metadata
    fields", with a table listing 15 rows (2 user + 7 AI-seed + 3
    AI-design + 3 runtime = 15). The decision paragraph states "Twelve
    others are AI-inferred" which resolves to 2 + 12 = 14.

    Reconciliation: the 15th row, `failure_history`, is already captured
    in the claim ledger (every rejected claim carries `meta.reject_
    reason` + full lineage via append-only JSONL). Duplicating it on the
    leaf would create two sources of truth that drift. We keep the
    information in `claims.jsonl` and expose it through
    `ClaimLedger.query_by_subject(ac_id)`, matching the "14 field"
    count. See `model_role.py`'s Judge write-authority rule — Judge
    writes `status` + `evidence` on the leaf, and the per-attempt
    rejection history remains in the ledger.
    """

    # User-owned (2 — locked after approval)
    intent: str = ""
    verification: str = ""

    # AI-inferred at Seed gen (7)
    description: str = ""
    input: str = ""
    action: str = ""
    expected: str = ""
    depends_on: list[str] = field(default_factory=list)
    risk_level: str = RiskLevel.LOW.value
    model_tier_hint: str = CostTierHint.BALANCED.value  # glossary-allow: field name documented in schema

    # AI-inferred at Design (3)
    likely_files: list[str] = field(default_factory=list)
    shared_resources: list[str] = field(default_factory=list)
    parallel_safety: bool = True

    # Runtime — Judge writes (2; failure_history lives in claims.jsonl)
    status: str = LeafStatus.PENDING.value
    evidence: list[str] = field(default_factory=list)

    # Housekeeping (outside the 14; used to key the leaf inside a tree)
    id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "ACLeaf":
        known = {f for f in ACLeaf.__dataclass_fields__.keys()}
        kwargs = {k: v for k, v in d.items() if k in known}
        return ACLeaf(**kwargs)  # type: ignore[arg-type]


# ── Ownership constants ──────────────────────────────────────────────


USER_FIELDS: frozenset[str] = frozenset({"intent", "verification"})

AI_SEED_FIELDS: frozenset[str] = frozenset(
    {
        "description",
        "input",
        "action",
        "expected",
        "depends_on",
        "risk_level",
        "model_tier_hint",  # glossary-allow: v3.2 ③ schema field from handoff
    }
)

AI_DESIGN_FIELDS: frozenset[str] = frozenset(
    {"likely_files", "shared_resources", "parallel_safety"}
)

RUNTIME_FIELDS: frozenset[str] = frozenset({"status", "evidence"})

# The full 14 (housekeeping `id` is outside).
ALL_FIELDS: frozenset[str] = (
    USER_FIELDS | AI_SEED_FIELDS | AI_DESIGN_FIELDS | RUNTIME_FIELDS
)
assert len(ALL_FIELDS) == 14, "14 fields is a spec constant"


# Stage names match the pipeline gates (§3.⑥). Used by `validate_leaf`.
class Stage(str, Enum):
    INTERVIEW = "interview"
    SEED = "seed"
    DESIGN = "design"
    BUILD = "build"
    QA = "qa"


def _required_at_stage(stage: Stage) -> frozenset[str]:
    """Which fields must be non-empty at the end of which stage."""
    if stage == Stage.INTERVIEW:
        # Only user-owned fields must be present after interview.
        return USER_FIELDS
    if stage == Stage.SEED:
        return USER_FIELDS | AI_SEED_FIELDS
    if stage == Stage.DESIGN:
        return USER_FIELDS | AI_SEED_FIELDS | AI_DESIGN_FIELDS
    if stage in (Stage.BUILD, Stage.QA):
        return ALL_FIELDS  # runtime fields acquire values during these stages
    return frozenset()


# ── Testability check ────────────────────────────────────────────────


# Verbs that strongly signal a measurable verification step.
_TESTABLE_VERBS = re.compile(
    r"\b(returns?|contains?|shows?|renders?|logs?|emits?|equals?|matches?|is|are)\b"
    r"|\b(opens?|loads?|navigates?|clicks?|fills?|submits?)\b"
    r"|\b(under|within|at most|at least|exactly)\b",
    re.IGNORECASE,
)

# Red-flag vagueness that marks a verification as non-testable.
_VAGUE_WORDS = re.compile(
    r"\b(fast|nice|slick|clean|elegant|intuitive|modern|robust|"
    r"awesome|user[- ]friendly|seamless|smooth|beautiful|"
    r"production[- ]ready|enterprise[- ]grade)\b",
    re.IGNORECASE,
)


def ac_is_testable(leaf: ACLeaf) -> tuple[bool, str]:
    """Return (ok, reason). False means this leaf belongs in
    `seed.candidates[]`, not `features[].acceptance_criteria[]`.
    """
    verification = (leaf.verification or "").strip()
    if not verification:
        return False, "verification is empty"
    if _VAGUE_WORDS.search(verification):
        matched = _VAGUE_WORDS.findall(verification)
        return False, f"vague words in verification: {matched}"
    if not _TESTABLE_VERBS.search(verification):
        return (
            False,
            "verification lacks a measurable verb or condition "
            "(e.g. returns / renders / equals / within)",
        )
    return True, "OK"


# ── Leaf validation ───────────────────────────────────────────────────


@dataclass
class LeafValidationIssue:
    field: str
    code: str
    message: str


def validate_leaf(leaf: ACLeaf, *, stage: Stage) -> list[LeafValidationIssue]:
    """Return a list of issues; empty list means the leaf is stage-valid.

    Notes on semantics:
      * `depends_on` may be empty. Missing != invalid.
      * `parallel_safety` is True by default; recompute via
        `compute_parallel_safety` when files/resources land.
      * `evidence` must be non-empty only when `status == pass`. That
        constraint lives in the claim ledger, not here (the ledger is
        the SSOT for runtime fields).
    """
    issues: list[LeafValidationIssue] = []
    required = _required_at_stage(stage)
    d = leaf.to_dict()

    # Fields where an empty list is *semantically valid* (no dependency,
    # no observed evidence yet). Scoped per stage because e.g. likely_files
    # is mandatory at Design but optional before.
    #
    #   depends_on      — optional at every stage (a leaf may have no deps)
    #   likely_files    — required at Design; optional elsewhere
    #   shared_resources— required at Design; optional elsewhere
    #   evidence        — tied to `status == pass` (enforced by the ledger);
    #                     treat as optional at all stages here
    if stage == Stage.DESIGN:
        _list_optional = {"depends_on", "evidence"}
    else:
        _list_optional = {
            "depends_on",
            "likely_files",
            "shared_resources",
            "evidence",
        }
    for name in required:
        value = d.get(name)
        is_empty = value in (None, "", [])
        if not is_empty:
            continue
        if name in _list_optional:
            continue
        # Runtime fields are not required until Build/QA.
        if stage == Stage.SEED and name in RUNTIME_FIELDS:
            continue
        issues.append(
            LeafValidationIssue(
                field=name,
                code="missing",
                message=f"{name} is required at stage={stage.value}",
            )
        )

    # Testability — only enforce at Seed and beyond.
    if stage != Stage.INTERVIEW and leaf.verification:
        ok, reason = ac_is_testable(leaf)
        if not ok:
            issues.append(
                LeafValidationIssue(
                    field="verification",
                    code="not_testable",
                    message=reason,
                )
            )

    # risk_level must be an enum value.
    if leaf.risk_level and leaf.risk_level not in {r.value for r in RiskLevel}:
        issues.append(
            LeafValidationIssue(
                field="risk_level",
                code="bad_enum",
                message=(
                    f"risk_level {leaf.risk_level!r} not in "
                    f"{[r.value for r in RiskLevel]}"
                ),
            )
        )

    # status must be an enum value.
    if leaf.status and leaf.status not in {s.value for s in LeafStatus}:
        issues.append(
            LeafValidationIssue(
                field="status",
                code="bad_enum",
                message=(
                    f"status {leaf.status!r} not in "
                    f"{[s.value for s in LeafStatus]}"
                ),
            )
        )

    # model_tier_hint must be a cost_tier value (not a samvil_tier value).
    if leaf.model_tier_hint and leaf.model_tier_hint not in {
        c.value for c in CostTierHint
    }:
        issues.append(
            LeafValidationIssue(
                field="model_tier_hint",
                code="bad_enum",
                message=(
                    f"model_tier_hint {leaf.model_tier_hint!r} must be a "
                    f"cost_tier value: {[c.value for c in CostTierHint]}"
                ),
            )
        )

    return issues


# ── Parallel safety ──────────────────────────────────────────────────


def compute_parallel_safety(leaves: Iterable[ACLeaf]) -> dict[str, bool]:
    """Return a map `leaf_id → parallel_safety`.

    Rule (Ouroboros `routing/complexity.py` mirror): two leaves are
    pairwise-unsafe if they share any `likely_files` entry or any
    `shared_resources` entry. A leaf is `parallel_safety=False` if it
    has any unsafe peer in the collection.
    """
    leaf_list = list(leaves)
    safety: dict[str, bool] = {leaf.id: True for leaf in leaf_list if leaf.id}
    for i, a in enumerate(leaf_list):
        if not a.id:
            continue
        for b in leaf_list[i + 1 :]:
            if not b.id:
                continue
            if _overlap(a.likely_files, b.likely_files) or _overlap(
                a.shared_resources, b.shared_resources
            ):
                safety[a.id] = False
                safety[b.id] = False
    return safety


def _overlap(a: list[str], b: list[str]) -> bool:
    return bool(set(a or []) & set(b or []))


# ── Field locking ────────────────────────────────────────────────────


def lock_user_fields(leaf: ACLeaf) -> ACLeaf:
    """Produce a locked copy.

    We don't actually mutate the leaf — locking is enforced by the ledger
    (only Evolve can re-open user fields, and that flows through a
    `policy_adoption` claim). This helper exists so skills can pass the
    locked leaf to downstream stages with confidence that they're
    working from the approved values.
    """
    # Deep copy the lists so the returned leaf doesn't alias.
    return ACLeaf.from_dict(leaf.to_dict())
