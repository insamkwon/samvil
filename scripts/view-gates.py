#!/usr/bin/env python3
"""view-gates — render latest gate verdicts for a 1-dev user.

Sprint 1 observability. Pulls `gate_verdict` claims from
`.samvil/claims.jsonl` (when present) and renders the latest verdict per
gate. Also surfaces thresholds from `references/gate_config.yaml` so the
user can see what a gate is measuring.

Output:
  default (human)  — one-line summary per gate with last verdict + reason
  --format json    — machine-readable full dump

Examples:
  python scripts/view-gates.py
  python scripts/view-gates.py --samvil-tier thorough
  python scripts/view-gates.py --format json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_LEDGER = REPO / ".samvil" / "claims.jsonl"
DEFAULT_CONFIG = REPO / "references" / "gate_config.yaml"

GATE_ORDER = [
    "interview_to_seed",
    "seed_to_council",
    "council_to_design",
    "design_to_scaffold",
    "scaffold_to_build",
    "build_to_qa",
    "qa_to_deploy",
    "any_to_retro",
]

VERDICT_GLYPH = {
    "pass": "✓",
    "block": "✗",
    "escalate": "↑",
    "skip": "-",
    "pending": "·",
}


def load_gate_config(path: Path) -> dict:
    """Minimal YAML parse. We don't depend on PyYAML here because view
    scripts should run on bare Python. The YAML used in gate_config.yaml
    is a narrow subset we can parse with regex.
    """
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore

        return yaml.safe_load(path.read_text()) or {}
    except Exception:
        return {}


def load_latest_gate_verdicts(ledger_path: Path) -> dict[str, dict]:
    """Return the most recent `gate_verdict` claim per subject.

    Per v3.2, gate verdicts are claims. `subject` is the gate name so we
    pick the latest row per gate-name.
    """
    if not ledger_path.exists():
        return {}
    latest: dict[str, dict] = {}
    for line in ledger_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("type") != "gate_verdict":
            continue
        subject = row.get("subject", "")
        ts = row.get("ts", "")
        if subject not in latest or latest[subject].get("ts", "") < ts:
            latest[subject] = row
    return latest


def fmt_human(cfg: dict, verdicts: dict[str, dict], samvil_tier: str) -> str:
    lines: list[str] = []
    lines.append(f"gates (tier = {samvil_tier})")
    lines.append("-" * 60)
    gates_cfg = (cfg or {}).get("gates", {}) or {}
    for g in GATE_ORDER:
        v = verdicts.get(g)
        if v is None:
            verdict = "pending"
            reason = "no verdict recorded yet"
        else:
            # Verdict claim statements are free text from gate_check; we
            # parse the JSON stored in meta when the skill recorded one.
            meta = v.get("meta", {}) or {}
            verdict = meta.get("verdict", "pass")
            reason = meta.get("reason", v.get("statement", ""))
        glyph = VERDICT_GLYPH.get(verdict, "?")
        thr = gates_cfg.get(g, {}).get("thresholds", {}).get(samvil_tier, {})
        thr_str = ", ".join(f"{k}={v}" for k, v in thr.items()) or "(none)"
        line = f"  {glyph} {g:<22} {verdict:<9} {reason[:60]}"
        lines.append(line)
        lines.append(f"     thresholds[{samvil_tier}]: {thr_str}")
    return "\n".join(lines)


def fmt_json(cfg: dict, verdicts: dict[str, dict], samvil_tier: str) -> str:
    out = []
    gates_cfg = (cfg or {}).get("gates", {}) or {}
    for g in GATE_ORDER:
        v = verdicts.get(g)
        out.append(
            {
                "gate": g,
                "samvil_tier": samvil_tier,
                "thresholds": (
                    gates_cfg.get(g, {}).get("thresholds", {}).get(samvil_tier, {})
                ),
                "last_verdict": v,
            }
        )
    return json.dumps(out, ensure_ascii=False, indent=2)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    p.add_argument("--config", default=str(DEFAULT_CONFIG))
    p.add_argument("--samvil-tier", default="standard")
    p.add_argument("--format", choices=["human", "json"], default="human")
    args = p.parse_args()

    cfg = load_gate_config(Path(args.config))
    verdicts = load_latest_gate_verdicts(Path(args.ledger))

    if args.format == "json":
        print(fmt_json(cfg, verdicts, args.samvil_tier))
    else:
        print(fmt_human(cfg, verdicts, args.samvil_tier))
    return 0


if __name__ == "__main__":
    sys.exit(main())
