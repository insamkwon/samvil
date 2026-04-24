"""Performance budget (⑬) — per-samvil_tier ceilings.

Per HANDOFF-v3.2-DECISIONS.md §5.⑬:

  .samvil/performance_budget.yaml — per-tier ceilings on wall-time,
    LLM calls, and estimated cost.

Enforcement:
  * Warning at 80% consumed.
  * Hard stop at 150% (configurable via `hard_stop_multiplier`).
  * Retro posts an observation on overshoot.

Batching rules listed in §5.⑬:
  * Claim verification and gate checks run batched per feature, not per
    leaf. (Enforced at the skill layer, not here.)
  * Meta Self-Probe runs per phase, not per question. (Same.)
  * Consensus triggers are budget-doubling-exempt — when a dispute
    resolver runs, its cost does not count against the normal budget.

This module owns:
  * Budget defaults (mirror of performance_budget.defaults.yaml).
  * Loader.
  * `reserve` / `consume` helpers.
  * `report` — returns a dict of consumption / status per dimension.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml  # optional; we fall back to DEFAULTS when missing
except Exception:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


# (initial estimate) — registered as experimental_policy by
# scripts/seed-experiments.py
DEFAULT_BUDGET: dict[str, Any] = {
    "per_run": {
        "wall_time_minutes": {
            "minimal": 15,
            "standard": 40,
            "thorough": 90,
            "full": 180,
            "deep": 300,
        },
        "llm_calls": {
            "minimal": 50,
            "standard": 150,
            "thorough": 400,
            "full": 800,
            "deep": 1500,
        },
        "estimated_cost_usd": {
            "minimal": 0.5,
            "standard": 2,
            "thorough": 8,
            "full": 20,
            "deep": 40,
        },
    },
    "enforcement": {
        "warn_multiplier": 0.80,
        "hard_stop_multiplier": 1.50,
        "consensus_exempt": True,
    },
}


def load_budget(path: str | Path | None = None) -> dict:
    if path is None:
        return _deep_copy(DEFAULT_BUDGET)
    p = Path(path)
    if not p.exists() or yaml is None:
        return _deep_copy(DEFAULT_BUDGET)
    try:
        raw = yaml.safe_load(p.read_text()) or {}
    except Exception:
        return _deep_copy(DEFAULT_BUDGET)
    merged = _deep_copy(DEFAULT_BUDGET)
    _deep_merge(merged, raw)
    return merged


def _deep_copy(d: Any) -> Any:
    if isinstance(d, dict):
        return {k: _deep_copy(v) for k, v in d.items()}
    if isinstance(d, list):
        return [_deep_copy(v) for v in d]
    return d


def _deep_merge(base: dict, override: dict) -> None:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


# ── Consumption ledger ───────────────────────────────────────────────


@dataclass
class Consumption:
    wall_time_minutes: float = 0.0
    llm_calls: int = 0
    estimated_cost_usd: float = 0.0

    def to_dict(self) -> dict:
        return {
            "wall_time_minutes": self.wall_time_minutes,
            "llm_calls": self.llm_calls,
            "estimated_cost_usd": self.estimated_cost_usd,
        }


@dataclass
class BudgetStatus:
    samvil_tier: str
    ceiling: dict
    consumed: dict
    ratios: dict
    warnings: list[str] = field(default_factory=list)
    hard_stop: bool = False

    def to_dict(self) -> dict:
        return {
            "samvil_tier": self.samvil_tier,
            "ceiling": self.ceiling,
            "consumed": self.consumed,
            "ratios": self.ratios,
            "warnings": self.warnings,
            "hard_stop": self.hard_stop,
        }


def ceiling_for_tier(budget: dict, samvil_tier: str) -> dict:
    per_run = budget.get("per_run", {})
    return {
        "wall_time_minutes": per_run.get("wall_time_minutes", {}).get(samvil_tier),
        "llm_calls": per_run.get("llm_calls", {}).get(samvil_tier),
        "estimated_cost_usd": per_run.get("estimated_cost_usd", {}).get(samvil_tier),
    }


def evaluate_status(
    *,
    budget: dict,
    samvil_tier: str,
    consumed: Consumption,
    exempt_consensus: bool = True,
    consensus_cost: Consumption | None = None,
) -> BudgetStatus:
    """Compute ratios + warnings given consumption.

    If `exempt_consensus` is True and a `consensus_cost` is supplied,
    subtract it before ratio computation. Defaults align with the
    "consensus triggers are budget-doubling-exempt" rule.
    """
    ceiling = ceiling_for_tier(budget, samvil_tier)
    adjusted = Consumption(**consumed.to_dict())
    if exempt_consensus and consensus_cost is not None:
        adjusted.wall_time_minutes = max(
            0.0, adjusted.wall_time_minutes - consensus_cost.wall_time_minutes
        )
        adjusted.llm_calls = max(0, adjusted.llm_calls - consensus_cost.llm_calls)
        adjusted.estimated_cost_usd = max(
            0.0,
            adjusted.estimated_cost_usd - consensus_cost.estimated_cost_usd,
        )

    ratios: dict[str, float] = {}
    warnings: list[str] = []
    hard_stop = False
    enforcement = budget.get("enforcement", {}) or {}
    warn = float(enforcement.get("warn_multiplier", 0.80))
    stop = float(enforcement.get("hard_stop_multiplier", 1.50))

    for key in ("wall_time_minutes", "llm_calls", "estimated_cost_usd"):
        max_ = ceiling.get(key)
        if not max_:
            ratios[key] = 0.0
            continue
        actual = float(getattr(adjusted, key))
        ratio = actual / max_
        ratios[key] = ratio
        if ratio >= stop:
            hard_stop = True
            warnings.append(
                f"{key}: {actual:.2f} ≥ hard-stop ({stop*100:.0f}% of {max_})"
            )
        elif ratio >= warn:
            warnings.append(
                f"{key}: {actual:.2f} ≥ warn threshold ({warn*100:.0f}% of {max_})"
            )

    return BudgetStatus(
        samvil_tier=samvil_tier,
        ceiling=ceiling,
        consumed=adjusted.to_dict(),
        ratios=ratios,
        warnings=warnings,
        hard_stop=hard_stop,
    )
