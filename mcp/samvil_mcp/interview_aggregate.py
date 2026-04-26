"""Boot-time aggregator for samvil-interview (T4.6 ultra-thin migration).

Single best-effort call that collects everything the (now ~180-LOC) skill
body needs but that is not already covered by `score_ambiguity`,
`scan_manifest`, `route_question`, `update_answer_streak`, `manage_tracks`,
`get_tier_phases`, `compute_seed_readiness`, `gate_check`, etc.

Specifically:

  1. **tier** — resolves `samvil_tier` from project.config.json /
     project.state.json with the same precedence the orchestrator uses
     (state > config > default), preserving the v3.1 `deep` alias only
     for interview's own threshold logic (interview supports 5 tiers
     including `deep`; pipeline routes through `full` post-interview).
  2. **phases** — resolved required interview phases for the chosen
     tier (`tier_phases` mirror) + ambiguity target threshold.
  3. **mode** — Zero-Question vs Normal mode detection from the
     orchestrator-supplied prompt (Korean + English signal words).
  4. **preset** — keyword match against the built-in preset table +
     scan of `~/.samvil/presets/*.json` for custom presets.
  5. **manifest** — best-effort `scan_manifest(project_root)` so the
     skill can route Path 1a (auto_confirm) without a second call.
  6. **paths** — interview-summary.md target, custom-preset directory,
     state.json / config.json paths the skill must read or write.

The skill body still owns:
  - AskUserQuestion checkpoints (mode + tier + preset + Phase 1–4
    question loops + summary verification).
  - Per-question routing call to `route_question` (per-question, not
    pre-flightable here).
  - Final `compute_seed_readiness` + `gate_check` + `claim_post`
    (post_stage Contract Layer step — owned by skill).

All reads are best-effort. Missing files yield empty defaults and a
non-fatal entry in `errors[]`. Never raises. Honors INV-1 (file is SSOT)
and INV-5 (graceful degradation).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

INTERVIEW_AGGREGATE_SCHEMA_VERSION = "1.0"

# Tier ladder for interview (full + v3.1 deep). Pipeline-side `samvil_tier`
# remains 4-valued; interview internally uses the 5th `deep` for stricter
# ambiguity thresholds when the user opts in via --deeper.
INTERVIEW_TIERS: tuple[str, ...] = (
    "minimal",
    "standard",
    "thorough",
    "full",
    "deep",
)

# Mirrors interview_engine.TIER_TARGETS so the skill can render the threshold
# without a second MCP roundtrip; the engine remains the source of truth and
# is re-checked at score_ambiguity time.
TIER_AMBIGUITY_TARGETS: dict[str, float] = {
    "minimal": 0.10,
    "standard": 0.05,
    "thorough": 0.02,
    "full": 0.01,
    "deep": 0.005,
}

# Tier → required phases mirror (kept in sync with
# interview_engine.TIER_REQUIRED_PHASES).
TIER_REQUIRED_PHASES: dict[str, tuple[str, ...]] = {
    "minimal": ("core", "scope"),
    "standard": ("core", "scope", "lifecycle"),
    "thorough": ("core", "scope", "lifecycle", "unknown", "nonfunc", "inversion"),
    "full": (
        "core",
        "scope",
        "lifecycle",
        "unknown",
        "nonfunc",
        "inversion",
        "stakeholder",
        "research",
    ),
    "deep": (
        "core",
        "scope",
        "lifecycle",
        "unknown",
        "nonfunc",
        "inversion",
        "stakeholder",
        "research",
        "domain_deep",
    ),
}

# Zero-Question Mode signal words (Korean + English).
_ZERO_QUESTION_SIGNALS: tuple[str, ...] = (
    "그냥 만들어",
    "ㄱ",
    "고",
    "대충",
    "빨리",
    "skip",
    "just build",
    "just do it",
    "no questions",
)

# Built-in preset keyword map. Mirrors references/app-presets.md and the
# legacy SKILL Step 1b table. Custom presets in ~/.samvil/presets/*.json
# take precedence (handled below).
_BUILTIN_PRESET_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("todo", ("할일", "todo", "task", "to-do")),
    ("dashboard", ("대시보드", "dashboard", "kpi", "analytics")),
    ("blog", ("블로그", "blog")),
    ("kanban", ("칸반", "kanban", "보드")),
    ("landing-page", ("랜딩", "landing")),
    ("e-commerce", ("쇼핑", "shop", "commerce", "결제")),
    ("calculator", ("계산기", "calculator")),
    ("chat", ("채팅", "chat", "messaging")),
    ("portfolio", ("포트폴리오", "portfolio")),
    ("form-builder", ("폼", "설문", "survey", "form")),
)


def _read_json(path: Path) -> dict[str, Any]:
    """Best-effort JSON read. Returns {} on any failure."""
    try:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _resolve_tier(state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Resolve interview tier with precedence state > config > default.

    Recognises both `samvil_tier` (v3.2) and legacy `selected_tier`. Maps
    no v3.1 alias here — interview is the one place `deep` survives as a
    real tier (stricter ambiguity target). Pipeline-side normalisation is
    the orchestrator's job.
    """
    valid = set(INTERVIEW_TIERS)
    chosen = ""
    source = "default"
    for src_label, src_dict in (("state", state), ("config", config)):
        if not isinstance(src_dict, dict):
            continue
        candidate = (
            (src_dict.get("samvil_tier") or src_dict.get("selected_tier") or "")
            .strip()
            .lower()
        )
        if candidate in valid:
            chosen = candidate
            source = src_label
            break
    if not chosen:
        chosen = "standard"
        source = "default"
    return {
        "samvil_tier": chosen,
        "source": source,
        "valid_tiers": list(INTERVIEW_TIERS),
    }


def detect_zero_question_mode(prompt: str) -> dict[str, Any]:
    """Detect Zero-Question Mode signals in the orchestrator prompt.

    Returns: {is_zero_question, matched_signals}.
    Signal matching is whole-word for short tokens (`ㄱ`/`고`) to avoid
    false positives, substring for multi-char phrases.
    """
    text = (prompt or "").strip().lower()
    if not text:
        return {"is_zero_question": False, "matched_signals": []}
    matched: list[str] = []
    tokens = text.split()
    for sig in _ZERO_QUESTION_SIGNALS:
        sig_l = sig.lower()
        if len(sig_l) <= 2:
            # Whole-token match for very short signals.
            if sig_l in tokens:
                matched.append(sig)
        elif sig_l in text:
            matched.append(sig)
    return {
        "is_zero_question": bool(matched),
        "matched_signals": matched,
    }


def _match_builtin_preset(prompt: str) -> dict[str, Any]:
    """Match built-in preset by keyword. Returns the first hit or empty."""
    text = (prompt or "").lower()
    if not text:
        return {"name": "", "keywords": [], "source": ""}
    for name, kws in _BUILTIN_PRESET_RULES:
        hits = [kw for kw in kws if kw in text]
        if hits:
            return {"name": name, "keywords": hits, "source": "builtin"}
    return {"name": "", "keywords": [], "source": ""}


def _scan_custom_presets(custom_dir: Path) -> list[dict[str, Any]]:
    """Read each `*.json` in the custom preset directory.

    Returns a list of `{name, keywords, description, path}` records.
    Failures on individual files are silently skipped — preset loading
    must never break the interview.
    """
    presets: list[dict[str, Any]] = []
    if not custom_dir.exists() or not custom_dir.is_dir():
        return presets
    try:
        for entry in sorted(custom_dir.glob("*.json")):
            data = _read_json(entry)
            if not data:
                continue
            name = str(data.get("name", "") or entry.stem)
            kws = data.get("keywords", []) or []
            desc = str(data.get("description", "") or "")
            if not isinstance(kws, list):
                kws = []
            presets.append(
                {
                    "name": name,
                    "keywords": [str(k) for k in kws],
                    "description": desc,
                    "path": str(entry),
                }
            )
    except OSError:
        pass
    return presets


def _match_custom_preset(prompt: str, custom: list[dict[str, Any]]) -> dict[str, Any]:
    """Best-of-N keyword match against custom presets. Most-keywords wins."""
    text = (prompt or "").lower()
    if not text or not custom:
        return {}
    best: dict[str, Any] = {}
    best_hits = 0
    for p in custom:
        hits = [kw for kw in p.get("keywords", []) if kw.lower() in text]
        if hits and len(hits) > best_hits:
            best_hits = len(hits)
            best = {
                "name": p.get("name", ""),
                "keywords": hits,
                "description": p.get("description", ""),
                "source": "custom",
                "path": p.get("path", ""),
            }
    return best


def _resolve_preset(
    prompt: str,
    custom_presets: list[dict[str, Any]],
) -> dict[str, Any]:
    """Custom > built-in. Always returns a dict (possibly all-empty)."""
    custom_match = _match_custom_preset(prompt, custom_presets)
    if custom_match:
        return custom_match
    builtin = _match_builtin_preset(prompt)
    if builtin["name"]:
        return builtin
    return {"name": "", "keywords": [], "source": "none"}


def _custom_preset_dir() -> Path:
    """`~/.samvil/presets/`. Honors $HOME / $SAMVIL_PRESET_DIR override."""
    override = os.environ.get("SAMVIL_PRESET_DIR")
    if override:
        return Path(override)
    return Path.home() / ".samvil" / "presets"


def aggregate_interview_state(
    project_root: str | Path,
    *,
    prompt: str = "",
) -> dict[str, Any]:
    """Boot-time aggregator for the samvil-interview skill body (T4.6).

    Reads (best-effort) from `project_root`:
      - `project.state.json` — for prior tier + session_id.
      - `project.config.json` — for tier fallback.
      - `<project_root>/package.json` etc. via `scan_manifest`.

    Reads (best-effort) from `~/.samvil/presets/*.json`.

    The skill body still does:
      - AskUserQuestion checkpoints (Phase 1–4 + summary).
      - Per-question `route_question` calls (those need the live
        question text and current streak, not pre-flight).
      - Final `compute_seed_readiness` + `gate_check` + `claim_post`
        (post_stage Contract Layer step).

    Returns a dict with:
      - schema_version, project_root
      - session_id, current_stage (from state.json)
      - tier: {samvil_tier, source, valid_tiers}
      - ambiguity_target: float (matches interview_engine threshold)
      - required_phases: list[str] (in pipeline order)
      - mode: {is_zero_question, matched_signals}
      - preset: {name, keywords, source, description?, path?}
      - custom_presets_count: int (for the "감지된 커스텀 프리셋: N개" prompt)
      - manifest: dict (scan_manifest output, may be {})
      - paths: {interview_summary, state_file, config_file, preset_dir}
      - errors: [str]   (non-fatal)

    Never raises. On unexpected exception, the offending section is left
    as its empty default and a string is appended to `errors`.
    """
    errors: list[str] = []
    root = Path(project_root) if project_root else Path(".")

    state = _read_json(root / "project.state.json")
    if not state:
        # Tolerate older `.samvil/state.json` layout.
        state = _read_json(root / ".samvil" / "state.json")
    config = _read_json(root / "project.config.json")

    try:
        tier_block = _resolve_tier(state, config)
    except Exception as exc:  # pragma: no cover — defensive
        tier_block = {
            "samvil_tier": "standard",
            "source": "default",
            "valid_tiers": list(INTERVIEW_TIERS),
        }
        errors.append(f"tier: {exc}")

    chosen_tier = tier_block["samvil_tier"]
    ambiguity_target = TIER_AMBIGUITY_TARGETS.get(chosen_tier, 0.05)
    required_phases = list(
        TIER_REQUIRED_PHASES.get(chosen_tier, TIER_REQUIRED_PHASES["standard"])
    )

    try:
        mode_block = detect_zero_question_mode(prompt)
    except Exception as exc:  # pragma: no cover — defensive
        mode_block = {"is_zero_question": False, "matched_signals": []}
        errors.append(f"mode: {exc}")

    preset_dir = _custom_preset_dir()
    try:
        custom_presets = _scan_custom_presets(preset_dir)
    except Exception as exc:  # pragma: no cover — defensive
        custom_presets = []
        errors.append(f"custom_presets: {exc}")

    try:
        preset_block = _resolve_preset(prompt, custom_presets)
    except Exception as exc:  # pragma: no cover — defensive
        preset_block = {"name": "", "keywords": [], "source": "none"}
        errors.append(f"preset: {exc}")

    manifest: dict[str, Any] = {}
    try:
        # Local import — `path_router` carries its own `_read_json` etc.
        from .path_router import scan_manifest as _scan

        manifest = _scan(str(root)) or {}
    except Exception as exc:
        manifest = {}
        errors.append(f"manifest: {exc}")

    session_id = ""
    current_stage = ""
    if isinstance(state, dict):
        sid = state.get("session_id")
        if isinstance(sid, str):
            session_id = sid
        cs = state.get("current_stage")
        if isinstance(cs, str):
            current_stage = cs

    return {
        "schema_version": INTERVIEW_AGGREGATE_SCHEMA_VERSION,
        "project_root": str(root),
        "session_id": session_id,
        "current_stage": current_stage,
        "tier": tier_block,
        "ambiguity_target": ambiguity_target,
        "required_phases": required_phases,
        "mode": mode_block,
        "preset": preset_block,
        "custom_presets_count": len(custom_presets),
        "manifest": manifest,
        "paths": {
            "interview_summary": str(root / "interview-summary.md"),
            "state_file": str(root / "project.state.json"),
            "config_file": str(root / "project.config.json"),
            "preset_dir": str(preset_dir),
        },
        "errors": errors,
    }
