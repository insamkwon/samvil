#!/usr/bin/env python3
"""Sprint 3 exit-gate check.

Per HANDOFF-v3.2-DECISIONS.md §7 Sprint 3:

  * v3.1 project migrates and Build / QA respect role boundaries.
  * Claim ledger shows `claimed_by` and `verified_by` per AC.

This script verifies the role primitive is wired up end-to-end:

  A — every agents/*.md file carries a `model_role:` frontmatter key.
  B — the DEFAULT_ROLES registry matches the frontmatter values.
  C — a simulated Build/QA flow posts claims with proper roles and the
      ledger accepts the verified verdict when Judge ≠ Generator, and
      rejects it otherwise.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.ac_leaf_schema import ACLeaf, Stage, validate_leaf  # noqa: E402
from samvil_mcp.claim_ledger import ClaimLedger, ClaimLedgerError  # noqa: E402
from samvil_mcp.model_role import (  # noqa: E402
    DEFAULT_ROLES,
    OUT_OF_BAND,
    validate_role_separation,
)


AGENTS_DIR = REPO / "agents"
MODEL_ROLE_RE = re.compile(r"^model_role:\s*(\S+)\s*$", re.MULTILINE)


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}")


def check_a_frontmatter_present() -> bool:
    print("A) Every agent file has model_role frontmatter")
    missing: list[str] = []
    for path in sorted(AGENTS_DIR.glob("*.md")):
        if path.stem == "ROLE-INVENTORY":
            continue
        text = path.read_text()
        if not MODEL_ROLE_RE.search(text):
            missing.append(path.name)
    if missing:
        _fail(f"{len(missing)} agent(s) missing model_role frontmatter:")
        for m in missing[:10]:
            print(f"    - {m}")
        return False
    _ok(f"{len(list(AGENTS_DIR.glob('*.md'))) - 1} agents all tagged")
    return True


def check_b_frontmatter_matches_registry() -> bool:
    print("B) Frontmatter values match DEFAULT_ROLES / OUT_OF_BAND")
    mismatches: list[str] = []
    for path in sorted(AGENTS_DIR.glob("*.md")):
        if path.stem == "ROLE-INVENTORY":
            continue
        text = path.read_text()
        m = MODEL_ROLE_RE.search(text)
        if not m:
            continue
        file_value = m.group(1).strip()
        name = path.stem
        if name in DEFAULT_ROLES:
            expected = DEFAULT_ROLES[name].value
        elif name in OUT_OF_BAND:
            expected = "out_of_band"
        else:
            mismatches.append(f"{name}: not in registry (file says {file_value})")
            continue
        if file_value != expected:
            mismatches.append(f"{name}: file={file_value} expected={expected}")
    if mismatches:
        _fail(f"{len(mismatches)} mismatch(es):")
        for m in mismatches[:10]:
            print(f"    - {m}")
        return False
    _ok("all frontmatter values match registry")
    return True


def check_c_role_enforced_via_ledger() -> bool:
    print("C) Claim ledger enforces role separation")
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        src = project / "src"
        src.mkdir()
        (src / "auth.ts").write_text("export function login() {}\n")
        ledger = ClaimLedger(project / ".samvil" / "claims.jsonl")

        # Generator posts a claim for an AC verdict.
        claim = ledger.post(
            type="ac_verdict",
            subject="AC-1.1",
            statement="Login renders and returns 200",
            authority_file="qa-results.json",
            claimed_by="agent:build-worker",
            evidence=["src/auth.ts:1"],
        )

        # A sibling Generator tries to verify → semantic validator rejects.
        sr = validate_role_separation(
            claimed_by="agent:build-worker",
            verified_by="agent:frontend-dev",
        )
        if sr.valid:
            _fail("sibling Generator was accepted as Judge")
            return False
        _ok("sibling Generator rejected as Judge (role layer)")

        # Ledger.verify with same-identity is the identity-level check.
        try:
            ledger.verify(
                claim.claim_id,
                verified_by="agent:build-worker",
                project_root=project,
            )
            _fail("ledger accepted claimed_by == verified_by")
            return False
        except ClaimLedgerError:
            pass
        _ok("ledger blocks claimed_by == verified_by")

        # A real Judge verifies → ok.
        verified = ledger.verify(
            claim.claim_id,
            verified_by="agent:qa-functional",
            project_root=project,
        )
        if verified.status != "verified":
            _fail(f"Judge verify did not flip status (got {verified.status})")
            return False
        _ok("Judge verification flips status → verified")

    return True


def check_d_ac_leaf_validates() -> bool:
    print("D) AC leaf schema validates")
    leaf = ACLeaf(
        id="AC-1.1",
        intent="User logs in",
        verification="Login returns 200 on valid credentials",
        description="Auth endpoint",
        input="email + pw",
        action="POST /login",
        expected="200",
    )
    issues = validate_leaf(leaf, stage=Stage.SEED)
    if issues:
        _fail(f"minimal seed leaf flagged: {[i.code for i in issues]}")
        return False
    _ok("minimal seed leaf validates OK")

    bad = ACLeaf(
        id="AC-1.2",
        intent="Nice UI",
        verification="It looks clean",
    )
    issues = validate_leaf(bad, stage=Stage.SEED)
    if not any(i.code == "not_testable" for i in issues):
        _fail("vague verification was not flagged")
        return False
    _ok("vague verification rejected at seed")
    return True


def main() -> int:
    results = {
        "A": check_a_frontmatter_present(),
        "B": check_b_frontmatter_matches_registry(),
        "C": check_c_role_enforced_via_ledger(),
        "D": check_d_ac_leaf_validates(),
    }
    print()
    print("Summary")
    for k, v in results.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
