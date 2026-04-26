#!/usr/bin/env python3
"""Build .samvil/release-summary.md from the latest release report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.release import (  # noqa: E402
    build_release_evidence_bundle,
    render_release_evidence_bundle,
    write_release_evidence_bundle,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(REPO), help="project root")
    parser.add_argument("--no-persist", action="store_true", help="do not write .samvil/release-summary.md")
    parser.add_argument("--format", choices=["human", "json"], default="human")
    args = parser.parse_args()

    root = Path(args.root)
    bundle = build_release_evidence_bundle(root)
    path = ""
    if not args.no_persist:
        path = str(write_release_evidence_bundle(bundle, root))

    if args.format == "json":
        print(json.dumps({"status": "ok", "path": path, "bundle": bundle}, indent=2, ensure_ascii=False))
    else:
        print(render_release_evidence_bundle(bundle))
        if path:
            print(f"bundle: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
