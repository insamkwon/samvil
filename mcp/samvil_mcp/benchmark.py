"""External benchmark module (v4.29.0 — backs samvil-benchmark SKILL).

samvil-benchmark SKILL (v4.26) described the behavior — fetch external
AI coding harness changelogs, classify each item, append paradigm gaps
to harness-feedback.log. v4.29 ships the real implementation so the
SKILL is no longer aspirational.

Three pure functions + one registry helper:
    fetch_external_changelog(url, timeout) → {ok, items[], error?}
    classify_changelog_items(items, samvil_signals) → categorized
    append_gap_to_feedback_log(gap, log_path) → {ok, appended_id}
    load_benchmark_targets(config_path) → list of target dicts

Pure: no MCP, no side-effects beyond the explicit append helper.
INV-5: every function returns ok=False rather than raising on failure.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_TARGETS = [
    {
        "name": "ouroboros",
        "url": "https://raw.githubusercontent.com/Q00/ouroboros/main/CHANGELOG.md",
        "why": "Closest sibling — same Skill/MCP architecture, different philosophy",
    },
    {
        "name": "opendevin",
        "url": "https://raw.githubusercontent.com/All-Hands-AI/OpenHands/main/CHANGELOG.md",
        "why": "Open competitor — what's the community converging on?",
    },
]


def fetch_external_changelog(url: str, timeout: float = 5.0) -> dict:
    """Fetch a remote CHANGELOG file and extract the latest 3 release sections.

    Returns ``{ok, items: [{version, date, bullets[]}], error?}``.
    Markdown heading ``## <version>`` is the section delimiter (Keep-a-
    Changelog standard). Each section's ``- ...`` bullets are collected
    as items.

    Best-effort: network errors / non-markdown content return ok=False
    rather than raising. Caller decides whether to skip or warn.
    """
    if not url or not isinstance(url, str):
        return {"ok": False, "error": "url is required"}
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "samvil-benchmark/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("latin-1", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "url": url}

    # Parse Keep-a-Changelog style. Section markers like:
    #   ## [1.2.3] - 2026-05-16   OR   ## v1.2.3 — 2026-05-16
    # We accept either ``## [vN.N.N]`` or ``## vN.N.N`` or bare ``## N.N.N``
    section_re = re.compile(r"^##\s+\[?v?([0-9][\w.\-]*)\]?\s*[-—]?\s*(\d{4}-\d{2}-\d{2})?",
                            re.MULTILINE)
    sections: list[dict] = []
    matches = list(section_re.finditer(text))
    for i, m in enumerate(matches[:3]):  # keep latest 3
        version = m.group(1)
        date = m.group(2) or ""
        start = m.end()
        end = matches[i + 1].start() if (i + 1) < len(matches) else len(text)
        body = text[start:end]
        bullets = [
            ln.strip().lstrip("-*").strip()
            for ln in body.splitlines()
            if ln.strip().startswith(("- ", "* "))
        ]
        sections.append({
            "version": version,
            "date": date,
            "bullets": [b for b in bullets if b],
        })

    if not sections:
        return {"ok": False, "error": "no parseable release sections found", "url": url}
    return {"ok": True, "items": sections, "url": url}


def classify_changelog_items(
    items: list[dict],
    samvil_already_have: list[str] | None = None,
    samvil_rejected: list[str] | None = None,
) -> dict:
    """Classify each bullet into already_have / rejected / gap.

    ``samvil_already_have``: tokens / phrases SAMVIL is known to have
        (e.g. ``["refine gate", "epic claim", "ac tree"]``). Caller
        typically derives these from `references/glossary.md` and
        recent `CHANGELOG.md` entries.

    ``samvil_rejected``: tokens / phrases SAMVIL deliberately rejected
        (from `docs/samvil-v2-roadmap.md §Non-Goals` and `§Out-of-Scope`).

    Returns ``{ok, categorized: {already_have[], rejected[], gaps[]}}``
    where each entry is ``{section, bullet, matched_token?}``.

    Matching is whitespace-token overlap (case-insensitive). Strict
    string equality would miss too much, full NLP is overkill — this is
    a "find candidates for human review" heuristic.
    """
    if not isinstance(items, list):
        return {"ok": False, "error": "items must be a list"}
    have = [t.lower().strip() for t in (samvil_already_have or []) if t]
    rejected = [t.lower().strip() for t in (samvil_rejected or []) if t]

    categorized: dict[str, list[dict]] = {
        "already_have": [],
        "rejected": [],
        "gaps": [],
    }
    for section in items:
        if not isinstance(section, dict):
            continue
        version = section.get("version", "?")
        for bullet in section.get("bullets", []) or []:
            if not isinstance(bullet, str) or not bullet.strip():
                continue
            blower = bullet.lower()
            matched = None
            for tok in have:
                if tok and tok in blower:
                    matched = tok
                    break
            if matched:
                categorized["already_have"].append({
                    "section": version, "bullet": bullet, "matched_token": matched,
                })
                continue
            for tok in rejected:
                if tok and tok in blower:
                    matched = tok
                    break
            if matched:
                categorized["rejected"].append({
                    "section": version, "bullet": bullet, "matched_token": matched,
                })
                continue
            categorized["gaps"].append({"section": version, "bullet": bullet})

    return {"ok": True, "categorized": categorized,
            "counts": {k: len(v) for k, v in categorized.items()}}


def _short_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:8]


def render_gap_entry(gap: dict, target_name: str, target_url: str) -> dict:
    """Render a `gaps[]` item into a `harness-feedback.log` entry.

    Returns the entry dict ready for append. ``priority: BENEFIT`` per
    SKILL anti-patterns (gaps are enhancement candidates, not bugs).
    """
    bullet = gap.get("bullet", "").strip()
    section = gap.get("section", "?")
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    entry_id = f"benchmark-{ts}-{_short_hash(bullet)}"
    return {
        "id": entry_id,
        "priority": "BENEFIT",
        "component": f"external:{target_name}",
        "name": bullet[:80],
        "problem": f"SAMVIL is missing — {target_name} v{section} ships: {bullet}",
        "fix": "Plan in next architecture conversation. Adapt to SAMVIL's Korean / solo-developer / file-SSOT identity, or reject with rationale.",
        "expected_impact": "TBD — depends on adaptation plan",
        "source": "samvil-benchmark",
        "target_url": target_url,
        "section": section,
        "appended_at": datetime.now(timezone.utc).isoformat(),
    }


def append_gap_to_feedback_log(
    gap_entry: dict,
    feedback_log_path: str | Path,
) -> dict:
    """Append a single gap entry to ``harness-feedback.log`` atomically.

    ``harness-feedback.log`` is a JSON *array* file (per existing
    samvil-retro contract), not JSONL. We read-modify-write.
    Best-effort; file errors return ok=False without raising.
    """
    if not isinstance(gap_entry, dict) or "id" not in gap_entry:
        return {"ok": False, "error": "gap_entry must be a dict with 'id'"}
    path = Path(feedback_log_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing: list = []
        if path.exists():
            try:
                raw = path.read_text(encoding="utf-8")
                if raw.strip():
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        existing = parsed
                    else:
                        return {"ok": False,
                                "error": f"existing log is not a JSON array: {type(parsed).__name__}",
                                "path": str(path)}
            except json.JSONDecodeError as exc:
                return {"ok": False,
                        "error": f"existing log not valid JSON: {exc}",
                        "path": str(path)}

        # Dedup by id
        if any(isinstance(e, dict) and e.get("id") == gap_entry["id"] for e in existing):
            return {"ok": True, "appended": False, "reason": "duplicate id",
                    "appended_id": gap_entry["id"], "path": str(path)}

        existing.append(gap_entry)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.rename(path)
        return {"ok": True, "appended": True, "appended_id": gap_entry["id"], "path": str(path)}
    except (OSError, PermissionError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "path": str(path)}


def load_benchmark_targets(config_path: str | Path | None = None) -> dict:
    """Load benchmark targets: defaults + user overrides from config_path.

    ``config_path`` defaults to ``~/.samvil/benchmark-targets.json``.
    Schema: ``[{name, url, why}, ...]``. User entries override defaults
    by name (so user can replace e.g. Ouroboros URL with a fork).

    Returns ``{ok, targets: [{name, url, why}, ...], source}`` where
    source explains where each target came from.
    """
    targets: dict[str, dict] = {t["name"]: {**t, "source": "default"} for t in DEFAULT_TARGETS}
    overrides_path = Path(config_path) if config_path else (Path.home() / ".samvil" / "benchmark-targets.json")

    overrides_applied = 0
    if overrides_path.exists():
        try:
            raw = overrides_path.read_text(encoding="utf-8")
            user_entries = json.loads(raw)
            if isinstance(user_entries, list):
                for entry in user_entries:
                    if not isinstance(entry, dict):
                        continue
                    name = entry.get("name")
                    url = entry.get("url")
                    if not name or not url:
                        continue
                    targets[name] = {
                        "name": name,
                        "url": url,
                        "why": entry.get("why", "user-defined"),
                        "source": "user",
                    }
                    overrides_applied += 1
        except (OSError, PermissionError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": f"could not read overrides: {exc}",
                    "targets": list(targets.values()),
                    "overrides_applied": 0}

    return {"ok": True, "targets": list(targets.values()),
            "overrides_applied": overrides_applied,
            "overrides_path": str(overrides_path)}
