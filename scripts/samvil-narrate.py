#!/usr/bin/env python3
"""`samvil narrate` CLI — Sprint 4 narrated observability.

Reads `.samvil/` files, builds the Compressor prompt, and prints both
the deterministic context summary and the prompt. The actual LLM call
belongs in the calling skill (`samvil-narrate` skill in v3.2+), but this
script works standalone for dogfood and debugging: pipe the prompt to
`llm` / `chatgpt` / `anthropic` etc., then run `--parse RAW_FILE` to
produce the markdown view.

Usage:
  python3 scripts/samvil-narrate.py --root . --since 2026-04-01
  python3 scripts/samvil-narrate.py --parse /tmp/narrate.txt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.narrate import (  # noqa: E402
    build_context,
    build_narrate_prompt,
    parse_narrative,
)


def cmd_prompt(args: argparse.Namespace) -> int:
    ctx = build_context(args.root, since=args.since or None)
    prompt = build_narrate_prompt(ctx)
    if args.show_context:
        print("=== context summary ===")
        print(ctx.to_summary())
        print()
    print("=== prompt ===")
    print(prompt)
    return 0


def cmd_parse(args: argparse.Namespace) -> int:
    raw_path = Path(args.parse)
    if not raw_path.exists():
        print(f"file not found: {raw_path}", file=sys.stderr)
        return 1
    n = parse_narrative(raw_path.read_text())
    print(n.to_markdown())
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", default=".")
    p.add_argument("--since", default="", help="ISO-8601 UTC; default last 7 days")
    p.add_argument(
        "--show-context",
        action="store_true",
        help="print the deterministic context summary before the prompt",
    )
    p.add_argument(
        "--parse",
        default="",
        help="parse an LLM response from the given file and print markdown",
    )
    args = p.parse_args()

    if args.parse:
        return cmd_parse(args)
    return cmd_prompt(args)


if __name__ == "__main__":
    sys.exit(main())
