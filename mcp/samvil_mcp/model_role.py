"""Model role primitive (⑤) — runtime G ≠ J enforcement.

Per HANDOFF-v3.2-DECISIONS.md §3.⑤, every agent is tagged with a primary
`model_role`. Multi-role invocation is allowed per context: an agent can
be invoked in a different role at spawn time. The ledger is what enforces
the Generator ≠ Judge invariant — this module owns the enum and the
canonical agent → role mapping.

Why a separate module:

  * The claim ledger (claim_ledger.py) already enforces
    `verified_by != claimed_by` at the identity level. This module adds a
    semantic layer: "what kind of agent is claimed_by/verified_by?".
    Sprint 3+ consumes this to route escalations (Generator failed →
    bump to a more capable generator, not to a judge).
  * The 50 agents/*.md files need a programmatic inventory so retro can
    audit role drift without scraping frontmatter live.
  * Keeping the mapping in code (as a frozen dict) means `validate_role_
    separation` can run without reading any YAML, which matters for
    budget and speed.

The scanning utilities and the roll-forward hook that inserts
`model_role:` into frontmatter live in `scripts/apply-role-tags.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class ModelRole(str, Enum):
    """The six-role taxonomy from §3.⑤."""

    GENERATOR = "generator"
    REVIEWER = "reviewer"
    JUDGE = "judge"
    REPAIRER = "repairer"
    RESEARCHER = "researcher"
    COMPRESSOR = "compressor"


# Agents whose default role is explicit. Secondary roles are the contexts
# in which they can legitimately be spawned: e.g. build-worker is a
# Generator on first pass and a Repairer on rebuild.
#
# Out-of-band entries — interviewers, orchestrator, council 3-role — are
# intentionally absent. They are tagged `None` below so the scanner can
# say "not one of the six" explicitly instead of silently treating them
# as Generators.
DEFAULT_ROLES: dict[str, ModelRole] = {
    # Generators
    "build-worker": ModelRole.GENERATOR,
    "frontend-dev": ModelRole.GENERATOR,
    "backend-dev": ModelRole.GENERATOR,
    "mobile-developer": ModelRole.GENERATOR,
    "game-developer": ModelRole.GENERATOR,
    "ux-designer": ModelRole.GENERATOR,
    "tech-architect": ModelRole.GENERATOR,
    "scaffolder": ModelRole.GENERATOR,
    "ui-builder": ModelRole.GENERATOR,
    "infra-dev": ModelRole.GENERATOR,
    "test-writer": ModelRole.GENERATOR,
    "automation-engineer": ModelRole.GENERATOR,
    "mobile-architect": ModelRole.GENERATOR,
    "game-architect": ModelRole.GENERATOR,
    "automation-architect": ModelRole.GENERATOR,
    "game-art-architect": ModelRole.GENERATOR,
    "seed-architect": ModelRole.GENERATOR,
    "deployer": ModelRole.GENERATOR,
    # Reviewers
    "tech-lead": ModelRole.REVIEWER,
    "ui-designer": ModelRole.REVIEWER,
    "ux-researcher": ModelRole.REVIEWER,
    "dependency-auditor": ModelRole.REVIEWER,
    "performance-auditor": ModelRole.REVIEWER,
    "security-auditor": ModelRole.REVIEWER,
    "accessibility-expert": ModelRole.REVIEWER,
    "responsive-checker": ModelRole.REVIEWER,
    "scope-guard": ModelRole.REVIEWER,
    "simplifier": ModelRole.REVIEWER,
    "copywriter": ModelRole.REVIEWER,
    "retro-analyst": ModelRole.REVIEWER,
    "wonder-analyst": ModelRole.REVIEWER,
    "reflect-proposer": ModelRole.REVIEWER,
    "dog-fooder": ModelRole.REVIEWER,
    "ceo-advisor": ModelRole.REVIEWER,
    "growth-advisor": ModelRole.REVIEWER,
    # Judges — runtime AC verdicts, product-sign-off
    "qa-mechanical": ModelRole.JUDGE,
    "qa-functional": ModelRole.JUDGE,
    "qa-quality": ModelRole.JUDGE,
    "product-owner": ModelRole.JUDGE,
    "automation-qa": ModelRole.JUDGE,
    "game-qa": ModelRole.JUDGE,
    "mobile-qa": ModelRole.JUDGE,
    # Repairer
    "error-handler": ModelRole.REPAIRER,
    # Researchers
    "competitor-analyst": ModelRole.RESEARCHER,
    "business-analyst": ModelRole.RESEARCHER,
    # Compressor — no dedicated agent; inline skill function. Registered
    # for completeness so the tool `compressor` works in claimed_by.
    "compressor": ModelRole.COMPRESSOR,
}


# Secondary roles an agent is permitted to adopt at spawn time. Default:
# whatever fits naturally. Only two cases matter in v3.2:
#   * build-worker can be Repairer on rebuild.
#   * Generator ≠ Judge — any Generator trying to Judge its own subject
#     is rejected by the ledger regardless of what secondary list says.
ALLOWED_SECONDARY: dict[str, tuple[ModelRole, ...]] = {
    "build-worker": (ModelRole.REPAIRER,),
    "frontend-dev": (ModelRole.REPAIRER,),
    "backend-dev": (ModelRole.REPAIRER,),
    "mobile-developer": (ModelRole.REPAIRER,),
    "game-developer": (ModelRole.REPAIRER,),
    "error-handler": (ModelRole.GENERATOR,),
}


# Explicit out-of-band agents (not in the six-role taxonomy).
OUT_OF_BAND: frozenset[str] = frozenset(
    {
        "socratic-interviewer",
        "user-interviewer",
        "game-interviewer",
        "mobile-interviewer",
        "automation-interviewer",
        "orchestrator-agent",
    }
)


@dataclass(frozen=True)
class RoleSeparationResult:
    valid: bool
    reason: str = ""
    claimed_role: ModelRole | None = None
    verified_role: ModelRole | None = None


def _parse_agent_id(agent_id: str) -> str:
    """Accept either 'agent:foo' or 'foo'; return the bare name."""
    if agent_id.startswith("agent:"):
        return agent_id.split(":", 1)[1]
    return agent_id


def get_role(agent_id: str) -> ModelRole | None:
    """Return the primary role for an agent id, or None if out-of-band
    or unknown."""
    name = _parse_agent_id(agent_id)
    if name in OUT_OF_BAND:
        return None
    return DEFAULT_ROLES.get(name)


def is_judge_role(agent_id: str) -> bool:
    return get_role(agent_id) == ModelRole.JUDGE


def validate_role_separation(
    *,
    claimed_by: str,
    verified_by: str,
) -> RoleSeparationResult:
    """Apply the §3.⑤ runtime enforcement rule.

    Returns VALID iff:
      * claimed_by != verified_by (identity-level; claim ledger enforces).
      * verified_by is a Judge role (so a Generator can't rubber-stamp).
      * claimed_by is not a Judge for its own subject (via caller: the
        ledger scopes by `subject`, so this function only checks the
        Generator-vs-Judge side).

    Out-of-band identities (e.g., `agent:user`, `agent:orchestrator-agent`)
    are always allowed on the verifier side — they represent human or
    system confirmation, not a Generator.
    """
    if not claimed_by or not verified_by:
        return RoleSeparationResult(False, "both claimed_by and verified_by required")

    if claimed_by == verified_by:
        return RoleSeparationResult(
            False, "Generator ≠ Judge: same identity cannot self-verify"
        )

    claimed_role = get_role(claimed_by)
    verified_role = get_role(verified_by)

    # Human or orchestrator can always verify — they are the ground truth.
    name = _parse_agent_id(verified_by)
    if name in OUT_OF_BAND or name == "user":
        return RoleSeparationResult(
            True,
            reason="out-of-band verifier allowed",
            claimed_role=claimed_role,
            verified_role=None,
        )

    if verified_role != ModelRole.JUDGE:
        return RoleSeparationResult(
            False,
            reason=(
                f"verified_by role is {verified_role} — only Judge role may "
                "flip a verdict to verified"
            ),
            claimed_role=claimed_role,
            verified_role=verified_role,
        )

    if claimed_role == ModelRole.JUDGE:
        # A Judge cannot claim for its own verdict path unless it's wearing
        # a Generator hat via secondary role allocation, which is vanishing
        # rare. Reject as a precaution.
        return RoleSeparationResult(
            False,
            reason=(
                f"claimed_by {claimed_by!r} is a Judge; Judges cannot be "
                "Generators of the same claim (anti reward-hacking)"
            ),
            claimed_role=claimed_role,
            verified_role=verified_role,
        )

    return RoleSeparationResult(
        True,
        reason="OK",
        claimed_role=claimed_role,
        verified_role=verified_role,
    )


# ── Inventory rendering ────────────────────────────────────────────────


def inventory() -> dict[str, dict]:
    """Return a serializable summary of the full role registry.

    Used by `scripts/render-role-inventory.py` to produce
    `agents/ROLE-INVENTORY.md` and by MCP tool `list_model_roles`.
    """
    out: dict[str, dict] = {}
    for agent, role in sorted(DEFAULT_ROLES.items()):
        out[agent] = {
            "primary": role.value,
            "allowed_secondary": [
                r.value for r in ALLOWED_SECONDARY.get(agent, ())
            ],
        }
    for agent in sorted(OUT_OF_BAND):
        out[agent] = {"primary": None, "allowed_secondary": [], "out_of_band": True}
    return out


def agents_by_role() -> dict[str, list[str]]:
    """Roll-up for the human-readable inventory."""
    rollup: dict[str, list[str]] = {r.value: [] for r in ModelRole}
    rollup["out_of_band"] = []
    for agent, role in sorted(DEFAULT_ROLES.items()):
        rollup[role.value].append(agent)
    for agent in sorted(OUT_OF_BAND):
        rollup["out_of_band"].append(agent)
    return rollup


def all_roles() -> Iterable[ModelRole]:
    return list(ModelRole)
