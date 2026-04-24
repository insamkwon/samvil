"""Model routing for SAMVIL v3.2 — ④ Absorption.

Per HANDOFF-v3.2-DECISIONS.md §3.④, this module picks which model a task
should run on, based on:

  1. **cost_tier** (per v3.2 glossary): `frugal` | `balanced` | `frontier`.
  2. **task_role** (from §3.⑤, Sprint 3): generator / reviewer / judge /
     repairer / researcher / compressor. Each role has a default
     cost_tier; users override via `model_profiles.yaml`.
  3. **Escalation**: on non-terminal failure, move up one cost_tier.
  4. **Downgrade**: when the performance budget consumed ≥ threshold,
     move down one cost_tier.
  5. **Deterministic tie-break**: when multiple models match, pick the
     first listed (not random; reproducibility > load balancing for a
     1-dev tool).

The provider adapter layer is intentionally **not** ported. In SAMVIL the
"provider" is Claude Code itself — skills execute the model via their
environment. This module's output is an advisory `RoutingDecision` that
the skill records (model name, cost_tier, reason) and passes to the
caller. Sprint 3 wires `RoutingDecision` into the claim ledger via a
`policy_adoption` claim.

Implementation shape inspired by Ouroboros v0.29.2 `src/ouroboros/routing`
but rewritten to SAMVIL conventions: ClaimLedger integration, YAML
profiles rooted at `.samvil/model_profiles.yaml`, Korean-friendly errors,
no dependency on `ouroboros.core.*`.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

try:
    import yaml  # optional — fall back to packaged defaults
except Exception:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


# ── Enum + constants ──────────────────────────────────────────────────


class CostTier(str, Enum):
    """Per v3.2 glossary: distinct from `samvil_tier` (pipeline rigor)
    and `interview_level` (interview intensity). Values are intentionally
    non-overlapping.
    """

    FRUGAL = "frugal"
    BALANCED = "balanced"
    FRONTIER = "frontier"

    @property
    def cost_multiplier(self) -> int:
        """Coarse cost factor; used for budget accounting only."""
        return {CostTier.FRUGAL: 1, CostTier.BALANCED: 10, CostTier.FRONTIER: 30}[
            self
        ]

    @property
    def rank(self) -> int:
        return {CostTier.FRUGAL: 0, CostTier.BALANCED: 1, CostTier.FRONTIER: 2}[self]

    def escalate(self) -> "CostTier":
        """Move one step up; FRONTIER is a fixed point."""
        return {
            CostTier.FRUGAL: CostTier.BALANCED,
            CostTier.BALANCED: CostTier.FRONTIER,
            CostTier.FRONTIER: CostTier.FRONTIER,
        }[self]

    def downgrade(self) -> "CostTier":
        """Move one step down; FRUGAL is a fixed point."""
        return {
            CostTier.FRONTIER: CostTier.BALANCED,
            CostTier.BALANCED: CostTier.FRUGAL,
            CostTier.FRUGAL: CostTier.FRUGAL,
        }[self]


# Task role → default cost_tier. User overrides via model_profiles.yaml.
# Sprint 3 will extend this with ⑤ model_role mapping; for Sprint 2 we
# accept task_role as a free-form string and fall back to balanced.
DEFAULT_ROLE_TO_TIER: dict[str, CostTier] = {
    # Generator roles — most code-writing goes through balanced.
    "build-worker": CostTier.BALANCED,
    "frontend-dev": CostTier.BALANCED,
    "backend-dev": CostTier.BALANCED,
    "mobile-developer": CostTier.BALANCED,
    "game-developer": CostTier.BALANCED,
    "ux-designer": CostTier.BALANCED,
    "tech-architect": CostTier.BALANCED,
    "scaffolder": CostTier.FRUGAL,
    "ui-builder": CostTier.BALANCED,
    # Judge roles — verification needs capability; default frontier.
    "qa-functional": CostTier.FRONTIER,
    "qa-mechanical": CostTier.BALANCED,
    "qa-quality": CostTier.FRONTIER,
    "product-owner": CostTier.FRONTIER,
    # Reviewer — balanced is enough.
    "tech-lead": CostTier.BALANCED,
    "ui-designer": CostTier.BALANCED,
    "dependency-auditor": CostTier.FRUGAL,
    "security-auditor": CostTier.BALANCED,
    "performance-auditor": CostTier.BALANCED,
    "accessibility-expert": CostTier.BALANCED,
    "responsive-checker": CostTier.FRUGAL,
    # Researcher — frontier for synthesis, frugal for lookups.
    "competitor-analyst": CostTier.BALANCED,
    "business-analyst": CostTier.BALANCED,
    # Repairer — balanced; Sprint 3 may move to frontier for stuck cases.
    "error-handler": CostTier.BALANCED,
    # Compressor — frugal is fine for summaries.
    "compressor": CostTier.FRUGAL,
}


# ── Data classes ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class ModelProfile:
    """One entry in model_profiles.yaml.

    Fields:
      provider  — e.g. 'anthropic' / 'openai' / 'google' / 'claude-code' / 'codex-cli'.
      model_id  — provider-specific id. E.g. 'claude-opus-4-7', 'gpt-5-codex'.
      cost_tier — which bucket this model fits.
      nickname  — short human-readable label (used in reason strings).
      max_tokens_out — soft ceiling for routing decisions only.
      notes     — free text. Shown in `samvil status --profiles`.
    """

    provider: str
    model_id: str
    cost_tier: CostTier
    nickname: str = ""
    max_tokens_out: int = 4096
    notes: str = ""

    def key(self) -> str:
        return f"{self.provider}/{self.model_id}"


@dataclass(frozen=True)
class RoutingDecision:
    """Output of `route_task`.

    The skill records this into the claim ledger as a `policy_adoption`
    claim (Sprint 3) so retro can audit model usage per role/cost_tier.
    """

    task_role: str
    requested_cost_tier: CostTier
    chosen_cost_tier: CostTier
    profile: ModelProfile
    reason: str = ""
    escalation_depth: int = 0
    downgraded: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_role": self.task_role,
            "requested_cost_tier": self.requested_cost_tier.value,
            "chosen_cost_tier": self.chosen_cost_tier.value,
            "provider": self.profile.provider,
            "model_id": self.profile.model_id,
            "nickname": self.profile.nickname,
            "reason": self.reason,
            "escalation_depth": self.escalation_depth,
            "downgraded": self.downgraded,
        }


# ── Profile loading ───────────────────────────────────────────────────


# Default profiles ship with the repo. Users copy
# `references/model_profiles.defaults.yaml` to `.samvil/model_profiles.yaml`
# and edit. The defaults below mirror the scaffold file so both live in
# one source.
DEFAULT_PROFILES: list[ModelProfile] = [
    ModelProfile(
        provider="anthropic",
        model_id="claude-haiku-4-5",
        cost_tier=CostTier.FRUGAL,
        nickname="haiku-4.5",
        max_tokens_out=8192,
        notes="Fast/cheap; routine tasks, dependency audits, UI lint.",
    ),
    ModelProfile(
        provider="anthropic",
        model_id="claude-sonnet-4-6",
        cost_tier=CostTier.BALANCED,
        nickname="sonnet-4.6",
        max_tokens_out=8192,
        notes="Default balanced; most build + QA work.",
    ),
    ModelProfile(
        provider="anthropic",
        model_id="claude-opus-4-7",
        cost_tier=CostTier.FRONTIER,
        nickname="opus-4.7",
        max_tokens_out=32000,
        notes="Complex planning, tricky debugging, Judge role for tough ACs.",
    ),
    ModelProfile(
        provider="openai",
        model_id="gpt-5-codex",
        cost_tier=CostTier.FRONTIER,
        nickname="codex",
        max_tokens_out=16000,
        notes="Alternative frontier for Judge role — 'build on Opus, QA on Codex'.",
    ),
    ModelProfile(
        provider="openai",
        model_id="gpt-4o-mini",
        cost_tier=CostTier.FRUGAL,
        nickname="gpt-4o-mini",
        max_tokens_out=16000,
        notes="Frugal alternative for lookup-heavy researcher roles.",
    ),
]


def _profiles_from_yaml_root(root: dict) -> list[ModelProfile]:
    """Shape expected:

    profiles:
      - provider: anthropic
        model_id: claude-sonnet-4-6
        cost_tier: balanced
        nickname: sonnet-4.6
        max_tokens_out: 8192
        notes: "..."
    """
    out: list[ModelProfile] = []
    for entry in root.get("profiles", []) or []:
        try:
            out.append(
                ModelProfile(
                    provider=str(entry["provider"]),
                    model_id=str(entry["model_id"]),
                    cost_tier=CostTier(entry["cost_tier"]),
                    nickname=str(entry.get("nickname", "")),
                    max_tokens_out=int(entry.get("max_tokens_out", 4096)),
                    notes=str(entry.get("notes", "")),
                )
            )
        except (KeyError, ValueError):
            continue
    return out


def load_profiles(
    path: str | Path | None = None,
    *,
    fall_back_to_defaults: bool = True,
) -> list[ModelProfile]:
    """Read profiles from `path`; fall back to DEFAULT_PROFILES if missing
    or unparseable (and `fall_back_to_defaults` is True).

    Users put a yaml at `.samvil/model_profiles.yaml`. The function also
    accepts None to mean "defaults only".
    """
    if path is None:
        return copy.copy(DEFAULT_PROFILES) if fall_back_to_defaults else []
    p = Path(path)
    if not p.exists() or yaml is None:
        return copy.copy(DEFAULT_PROFILES) if fall_back_to_defaults else []
    try:
        root = yaml.safe_load(p.read_text()) or {}
    except Exception:
        return copy.copy(DEFAULT_PROFILES) if fall_back_to_defaults else []
    parsed = _profiles_from_yaml_root(root)
    if not parsed and fall_back_to_defaults:
        return copy.copy(DEFAULT_PROFILES)
    return parsed


# ── Role → cost_tier overrides ────────────────────────────────────────


def _role_to_tier_map(root: dict | None) -> dict[str, CostTier]:
    merged = dict(DEFAULT_ROLE_TO_TIER)
    if not root:
        return merged
    overrides = root.get("role_overrides") or {}
    for role, tier in overrides.items():
        try:
            merged[str(role)] = CostTier(tier)
        except ValueError:
            continue
    return merged


def load_role_overrides(path: str | Path | None = None) -> dict[str, CostTier]:
    if path is None:
        return dict(DEFAULT_ROLE_TO_TIER)
    p = Path(path)
    if not p.exists() or yaml is None:
        return dict(DEFAULT_ROLE_TO_TIER)
    try:
        root = yaml.safe_load(p.read_text()) or {}
    except Exception:
        return dict(DEFAULT_ROLE_TO_TIER)
    return _role_to_tier_map(root)


# ── Core: pick a model ────────────────────────────────────────────────


class RoutingError(ValueError):
    pass


def _first_profile_in_tier(
    profiles: list[ModelProfile], tier: CostTier
) -> ModelProfile | None:
    for p in profiles:
        if p.cost_tier == tier:
            return p
    return None


def route_task(
    *,
    task_role: str,
    profiles: list[ModelProfile] | None = None,
    role_overrides: dict[str, CostTier] | None = None,
    requested_cost_tier: CostTier | None = None,
    escalation_depth: int = 0,
    budget_pressure: float = 0.0,
    downgrade_threshold: float = 0.80,
) -> RoutingDecision:
    """Decide which model runs `task_role`.

    Precedence for cost_tier:
      1. Explicit `requested_cost_tier` (caller demand).
      2. `role_overrides[task_role]` (user config).
      3. `DEFAULT_ROLE_TO_TIER[task_role]` (baked defaults).
      4. BALANCED if role is unknown.

    Then `escalation_depth` bumps the tier up (capped at frontier) and
    `budget_pressure >= downgrade_threshold` bumps it down (capped at
    frugal). If both fire, escalation wins (we'd rather run correctly and
    blow the budget than downgrade on a stuck task).

    Raises RoutingError if no profile exists in the chosen tier even
    after a one-step back-off (e.g. user wiped the defaults).
    """
    profiles = profiles if profiles is not None else list(DEFAULT_PROFILES)
    overrides = role_overrides if role_overrides is not None else dict(
        DEFAULT_ROLE_TO_TIER
    )

    base = requested_cost_tier or overrides.get(task_role, CostTier.BALANCED)
    chosen = base
    reason_parts: list[str] = [f"base={base.value} (role={task_role})"]

    # Escalation (dominant)
    if escalation_depth > 0:
        for _ in range(escalation_depth):
            next_ = chosen.escalate()
            if next_ == chosen:
                break
            chosen = next_
        reason_parts.append(f"escalated+{escalation_depth} → {chosen.value}")

    # Downgrade only if we haven't already escalated
    downgraded = False
    if escalation_depth == 0 and budget_pressure >= downgrade_threshold:
        next_ = chosen.downgrade()
        if next_ != chosen:
            chosen = next_
            downgraded = True
            reason_parts.append(
                f"downgraded → {chosen.value} (budget {budget_pressure:.2f} ≥ "
                f"{downgrade_threshold:.2f})"
            )

    # Profile lookup with single back-off
    profile = _first_profile_in_tier(profiles, chosen)
    if profile is None:
        # Try escalating once so we don't starve on a user that only
        # listed balanced+frontier profiles.
        fallback = chosen.escalate()
        profile = _first_profile_in_tier(profiles, fallback)
        if profile is None:
            raise RoutingError(
                f"no profile matches cost_tier={chosen.value} nor fallback "
                f"{fallback.value}; check .samvil/model_profiles.yaml"
            )
        reason_parts.append(
            f"backoff {chosen.value} → {fallback.value} (no profile in chosen tier)"
        )
        chosen = fallback

    return RoutingDecision(
        task_role=task_role,
        requested_cost_tier=requested_cost_tier or overrides.get(
            task_role, CostTier.BALANCED
        ),
        chosen_cost_tier=chosen,
        profile=profile,
        reason="; ".join(reason_parts),
        escalation_depth=escalation_depth,
        downgraded=downgraded,
    )


# ── Escalation helper ─────────────────────────────────────────────────


@dataclass
class EscalationState:
    """Tracks retries for a given (task_role, subject) pair so callers
    can pass `escalation_depth` into `route_task` without hand-counting."""

    attempts: int = 0
    last_tier: CostTier | None = None

    def bump(self) -> int:
        self.attempts += 1
        return self.attempts


def escalation_from_attempts(attempts: int) -> int:
    """Map number of failed attempts to escalation depth.

    attempt 1 (first failure) → 1 step up
    attempt 2                 → 2 steps up
    attempt ≥3                → capped at 2
    """
    if attempts <= 0:
        return 0
    return min(attempts, 2)


# ── Downgrade helper ──────────────────────────────────────────────────


def downgrade_from_budget(consumed: dict[str, float], ceiling: dict[str, float]) -> float:
    """Return the **max** consumption ratio across budget dimensions.

    Sprint 6 wires this up to the performance_budget.yaml file.
    """
    if not ceiling:
        return 0.0
    max_ratio = 0.0
    for key, max_ in ceiling.items():
        if not max_:
            continue
        c = consumed.get(key, 0.0) or 0.0
        ratio = c / max_
        if ratio > max_ratio:
            max_ratio = ratio
    return max_ratio


# ── Validation ────────────────────────────────────────────────────────


def validate_profiles(profiles: list[ModelProfile]) -> list[str]:
    """Return a list of human-readable issues. Empty list = valid.

    Checks:
      * at least one profile per cost_tier (so routing never starves)
      * unique (provider, model_id) keys
    """
    issues: list[str] = []
    seen: set[str] = set()
    per_tier: dict[CostTier, int] = {t: 0 for t in CostTier}
    for p in profiles:
        k = p.key()
        if k in seen:
            issues.append(f"duplicate profile key: {k}")
        seen.add(k)
        per_tier[p.cost_tier] = per_tier.get(p.cost_tier, 0) + 1
    for t, count in per_tier.items():
        if count == 0:
            issues.append(f"no profile for cost_tier={t.value}")
    return issues
