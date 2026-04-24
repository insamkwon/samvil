#!/usr/bin/env python3
"""Seed every `(initial estimate)` constant in v3.2 as an experimental policy.

Sprint 1 bootstrap per HANDOFF-v3.2-DECISIONS.md §7:

> Numbers-as-experiments bootstrap: `scripts/seed-experiments.py` registers
> every `(initial estimate)` in this handoff as an `experimental_policy`.

Scans:
  1. `~/docs/ouroboros-absorb/HANDOFF-v3.2-DECISIONS.md` (primary source —
     tables and paragraphs tagged "(initial estimate)").
  2. `references/gate_config.yaml` (threshold defaults — every non-boolean
     numeric value is treated as an estimate until calibration).
  3. Inline `DEFAULT_CONFIG` in `mcp/samvil_mcp/gates.py` (same numbers,
     dual-encoded by design).

Writes:
  `.samvil/experiments.jsonl` — append-only JSONL. Each line:
    {
      "experiment_id": "exp_<source>_<key>",
      "name": "build_to_qa:standard:implementation_rate",
      "source": "references/gate_config.yaml",
      "source_line": 74,
      "initial_value": 0.85,
      "stage": "experimental",
      "observations": [],
      "registered_at": "2026-04-24T..."
    }

Idempotent: re-running reconciles by experiment_id (does not duplicate
existing rows). Observations added later survive across re-runs.

Usage:
  python scripts/seed-experiments.py               # register into repo
  python scripts/seed-experiments.py --dry-run     # preview only
  python scripts/seed-experiments.py --root PATH   # alternate project root
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

HANDOFF_PATH = Path.home() / "docs" / "ouroboros-absorb" / "HANDOFF-v3.2-DECISIONS.md"
GATE_CONFIG_PATH = REPO / "references" / "gate_config.yaml"

EXP_PATH_DEFAULT = REPO / ".samvil" / "experiments.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Source: gate_config.yaml ─────────────────────────────────────────

# We don't require PyYAML here because the script should run on plain
# Python. Regex extraction is good enough for the narrow YAML subset used
# in gate_config.yaml.
_YAML_NUMERIC = re.compile(
    r"^\s*(?P<tier>minimal|standard|thorough|full|deep)\s*:\s*\{\s*"
    r"(?P<pairs>.+?)\s*\}\s*$"
)


def extract_gate_config_estimates(path: Path) -> list[dict]:
    """Parse each tier row and emit one experiment per numeric threshold.

    Boolean thresholds (schema_valid: true) are skipped — they're not
    experimental, they're definitional.
    """
    if not path.exists():
        return []
    out: list[dict] = []
    current_gate: str | None = None
    for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
        stripped = raw.strip()
        # Gate header: "  build_to_qa:" at 2-space indent
        m_gate = re.match(r"^\s{2}([a-z_]+):\s*$", raw)
        if m_gate:
            current_gate = m_gate.group(1)
            continue
        m = _YAML_NUMERIC.match(raw)
        if not m or current_gate is None:
            continue
        tier = m.group("tier")
        pairs = m.group("pairs")
        for pair in pairs.split(","):
            if ":" not in pair:
                continue
            key, val = pair.split(":", 1)
            key = key.strip()
            val = val.strip()
            # numeric only
            try:
                num = float(val)
            except ValueError:
                continue
            out.append(
                {
                    "experiment_id": f"exp_gate_{current_gate}_{tier}_{key}",
                    "name": f"{current_gate}:{tier}:{key}",
                    "source": str(path.relative_to(REPO)),
                    "source_line": lineno,
                    "initial_value": num,
                    "stage": "experimental",
                    "observations": [],
                    "registered_at": _now(),
                    "notes": "Sprint 1 bootstrap; (initial estimate) from v3.2 handoff §3.⑥",
                }
            )
    return out


# ── Source: HANDOFF doc ───────────────────────────────────────────────

# Match free-text sentences flagged "(initial estimate)". We capture the
# leading words (2-6 tokens) to form a readable experiment name, plus the
# whole sentence/line as context.
_INITIAL_ESTIMATE_LINE = re.compile(r"\(initial\s+estimate[^)]*\)")


def extract_handoff_estimates(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
        if not _INITIAL_ESTIMATE_LINE.search(raw):
            continue
        context = raw.strip()
        # Derive a short name from the first ~8 words of the context.
        words = re.sub(r"[^\w\s]", " ", context).split()
        short = "_".join(words[:8])[:80].lower()
        out.append(
            {
                "experiment_id": f"exp_handoff_{lineno}_{short[:40]}",
                "name": f"handoff:line-{lineno}:{short[:40]}",
                "source": str(path),
                "source_line": lineno,
                "initial_value": None,  # text-only — actual numbers are in gate_config
                "stage": "experimental",
                "observations": [],
                "registered_at": _now(),
                "notes": "Sprint 1 bootstrap; (initial estimate) phrase in HANDOFF",
                "context": context[:280],
            }
        )
    return out


# ── Reconciliation & write ────────────────────────────────────────────


def load_existing(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    rows: dict[str, dict] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        eid = r.get("experiment_id")
        if eid:
            rows[eid] = r
    return rows


def merge(existing: dict, proposed: dict) -> dict:
    """Keep observations + stage from existing; refresh source_line, notes."""
    merged = dict(proposed)
    merged["observations"] = existing.get("observations", [])
    merged["stage"] = existing.get("stage", proposed["stage"])
    merged["registered_at"] = existing.get("registered_at", proposed["registered_at"])
    if "notes" in existing:
        merged["notes"] = existing["notes"]
    return merged


def write_all(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Rewrite the whole file in reconciled order. The file is append-only
    # in spirit (experiments are rarely removed), but since we merge on
    # re-run, a full rewrite is simpler and keeps the file compact.
    lines = [json.dumps(r, ensure_ascii=False) for r in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--root", default=None, help="Alternate project root for experiments.jsonl")
    parser.add_argument(
        "--handoff",
        default=str(HANDOFF_PATH),
        help=f"Handoff doc path (default: {HANDOFF_PATH})",
    )
    args = parser.parse_args()

    gate_rows = extract_gate_config_estimates(GATE_CONFIG_PATH)
    handoff_rows = extract_handoff_estimates(Path(args.handoff))
    proposed = {r["experiment_id"]: r for r in gate_rows + handoff_rows}

    target = (
        Path(args.root) / ".samvil" / "experiments.jsonl"
        if args.root
        else EXP_PATH_DEFAULT
    )
    existing = load_existing(target)
    reconciled: list[dict] = []
    added = 0
    updated = 0
    for eid, p in proposed.items():
        if eid in existing:
            reconciled.append(merge(existing[eid], p))
            updated += 1
        else:
            reconciled.append(p)
            added += 1
    # Preserve experiments that are in existing but not in proposed (e.g.,
    # manually added ones) so we don't nuke custom state.
    for eid, e in existing.items():
        if eid not in proposed:
            reconciled.append(e)

    print(f"gate_config entries: {len(gate_rows)}")
    print(f"handoff entries:     {len(handoff_rows)}")
    print(f"target:              {target}")
    print(f"added:   {added}")
    print(f"updated: {updated}")
    print(f"total:   {len(reconciled)}")

    if args.dry_run:
        print("(dry-run) no file written")
        return 0

    write_all(target, reconciled)
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
