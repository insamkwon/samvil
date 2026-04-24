"""Claim ledger — contract-layer SSOT for SAMVIL v3.2.

`.samvil/claims.jsonl` is an append-only ledger of verifiable statements.
Per HANDOFF-v3.2-DECISIONS.md §3.①.

Authority files (seed.json, qa-results.json, state.json) are **materialized
views** over verified claims. This module owns:

  - The schema (Claim dataclass + typed whitelist)
  - Status transitions (pending → verified | rejected)
  - The Generator ≠ Judge invariant (anti reward-hacking)
  - Evidence validation (non-empty + file:line resolves)
  - Low-level file I/O (append-only JSONL, no in-place edits)

MCP tool wiring lives in server.py. Anything outside the typed whitelist
belongs in events.jsonl, not the ledger.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

# Typed whitelist — Anything not in this set goes to events.jsonl, not claims.
CLAIM_TYPES: tuple[str, ...] = (
    "seed_field_set",
    "ac_verdict",
    "gate_verdict",
    "evolve_decision",
    "policy_adoption",
    "evidence_posted",
    "claim_disputed",
    "consensus_verdict",
    "migration_applied",
    "stagnation_declared",
)

CLAIM_STATUSES: tuple[str, ...] = ("pending", "verified", "rejected")

# Evidence format: "path/to/file.ext:line_no" or bare "path/to/file.ext".
# We accept both but require at least one element on verify.
_EVIDENCE_WITH_LINE = re.compile(r"^(?P<path>[^:]+):(?P<line>\d+)$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _claim_id(ts: str | None = None, seq: int = 1) -> str:
    ts = ts or _now_iso()
    # "claim_2026-04-23T12-34-56-0001" — stable, sortable, filesystem-safe
    compact = ts.replace(":", "-").rstrip("Z")
    return f"claim_{compact}-{seq:04d}"


@dataclass
class Claim:
    claim_id: str
    type: str
    subject: str
    statement: str
    authority_file: str
    evidence: list[str] = field(default_factory=list)
    claimed_by: str = ""
    verified_by: str | None = None
    status: str = "pending"
    ts: str = field(default_factory=_now_iso)

    # Optional free-form metadata block. Not part of the contract but preserved
    # across writes so skills can annotate (e.g., required_action payload).
    meta: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @staticmethod
    def from_dict(d: dict) -> "Claim":
        return Claim(
            claim_id=d["claim_id"],
            type=d["type"],
            subject=d["subject"],
            statement=d["statement"],
            authority_file=d["authority_file"],
            evidence=list(d.get("evidence", [])),
            claimed_by=d.get("claimed_by", ""),
            verified_by=d.get("verified_by"),
            status=d.get("status", "pending"),
            ts=d.get("ts", _now_iso()),
            meta=dict(d.get("meta", {})),
        )


class ClaimLedgerError(ValueError):
    """Raised when a claim operation would violate the ledger invariants."""


class ClaimLedger:
    """Append-only JSONL ledger rooted at `.samvil/claims.jsonl`.

    Design notes:
      * We never rewrite a line. A post/verify/reject each appends a new
        record. Callers reconstruct current state by taking the latest row
        keyed by `claim_id`.
      * File is scanned on every query. This is fine for solo-dev scale
        (< 10k claims per project). If the ledger grows past that, add an
        index file, don't add a DB.
      * Graceful degradation: if the directory doesn't exist we create it.
        If the file doesn't exist, reads return empty.
    """

    def __init__(self, path: str | os.PathLike = ".samvil/claims.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ── Internal helpers ──────────────────────────────────────────────

    def _append(self, claim: Claim) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(claim.to_json() + "\n")

    def _iter_raw(self) -> Iterator[dict]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    def _latest_by_id(self) -> dict[str, Claim]:
        """Collapse append-only rows into the current state per claim_id."""
        out: dict[str, Claim] = {}
        for row in self._iter_raw():
            try:
                c = Claim.from_dict(row)
            except (KeyError, TypeError):
                continue
            out[c.claim_id] = c
        return out

    @staticmethod
    def _next_seq(existing_ids: Iterable[str], ts: str) -> int:
        prefix_ts = ts.replace(":", "-").rstrip("Z")
        prefix = f"claim_{prefix_ts}-"
        seqs = []
        for cid in existing_ids:
            if cid.startswith(prefix):
                try:
                    seqs.append(int(cid.rsplit("-", 1)[-1]))
                except ValueError:
                    continue
        return (max(seqs) + 1) if seqs else 1

    # ── Public API ────────────────────────────────────────────────────

    def post(
        self,
        *,
        type: str,
        subject: str,
        statement: str,
        authority_file: str,
        claimed_by: str,
        evidence: list[str] | None = None,
        meta: dict | None = None,
    ) -> Claim:
        """Post a new `pending` claim.

        Validates the type is whitelisted. Does **not** validate evidence
        here — verification is the Judge's job. Caller may post with empty
        evidence; verify will reject if evidence is still empty.
        """
        if type not in CLAIM_TYPES:
            raise ClaimLedgerError(
                f"claim type {type!r} not in whitelist {CLAIM_TYPES}. "
                "Use events.jsonl for non-contract records."
            )
        if not claimed_by:
            raise ClaimLedgerError("claimed_by is required (Generator identity).")
        if not subject or not statement:
            raise ClaimLedgerError("subject and statement are required.")

        ts = _now_iso()
        existing = self._latest_by_id().keys()
        seq = self._next_seq(existing, ts)
        claim = Claim(
            claim_id=_claim_id(ts, seq),
            type=type,
            subject=subject,
            statement=statement,
            authority_file=authority_file,
            evidence=list(evidence or []),
            claimed_by=claimed_by,
            verified_by=None,
            status="pending",
            ts=ts,
            meta=dict(meta or {}),
        )
        self._append(claim)
        return claim

    def verify(
        self,
        claim_id: str,
        *,
        verified_by: str,
        evidence: list[str] | None = None,
        project_root: str | os.PathLike = ".",
        skip_file_resolution: bool = False,
    ) -> Claim:
        """Flip a claim from pending → verified.

        Enforces the anti-reward-hacking invariant:
          * `verified_by` is required and must differ from `claimed_by`.
          * Final evidence list (existing + newly provided) must be non-empty.
          * Every `file:line` evidence entry must resolve on disk
            (unless `skip_file_resolution=True`, which is intended only for
            synthetic/test scenarios — production callers should let the
            check run).
        """
        current = self._latest_by_id().get(claim_id)
        if current is None:
            raise ClaimLedgerError(f"claim {claim_id!r} does not exist.")
        if current.status == "verified":
            return current  # idempotent
        if current.status == "rejected":
            raise ClaimLedgerError(
                f"claim {claim_id!r} is already rejected; cannot verify."
            )

        if not verified_by:
            raise ClaimLedgerError("verified_by is required (Judge identity).")
        if verified_by == current.claimed_by:
            raise ClaimLedgerError(
                f"Generator ≠ Judge invariant violated: "
                f"{current.claimed_by!r} cannot verify its own claim."
            )

        merged_evidence = list(current.evidence) + list(evidence or [])
        # Preserve insertion order, drop dupes
        seen: set[str] = set()
        dedup: list[str] = []
        for e in merged_evidence:
            if e in seen:
                continue
            seen.add(e)
            dedup.append(e)
        merged_evidence = dedup

        if not merged_evidence:
            raise ClaimLedgerError(
                f"claim {claim_id!r} cannot be verified: evidence is empty."
            )

        if not skip_file_resolution:
            unresolved = _unresolved_evidence(merged_evidence, project_root)
            if unresolved:
                raise ClaimLedgerError(
                    f"claim {claim_id!r} has unresolved evidence entries: "
                    f"{unresolved}"
                )

        verified = Claim(
            claim_id=current.claim_id,
            type=current.type,
            subject=current.subject,
            statement=current.statement,
            authority_file=current.authority_file,
            evidence=merged_evidence,
            claimed_by=current.claimed_by,
            verified_by=verified_by,
            status="verified",
            ts=_now_iso(),
            meta=dict(current.meta),
        )
        self._append(verified)
        return verified

    def reject(
        self,
        claim_id: str,
        *,
        verified_by: str,
        reason: str = "",
    ) -> Claim:
        """Flip a claim from pending → rejected.

        Like verify, enforces Generator ≠ Judge and writes a new row. The
        reason is stored under `meta.reject_reason` so downstream tooling
        (retro, consensus) can inspect it without parsing free text.
        """
        current = self._latest_by_id().get(claim_id)
        if current is None:
            raise ClaimLedgerError(f"claim {claim_id!r} does not exist.")
        if current.status == "rejected":
            return current  # idempotent
        if current.status == "verified":
            raise ClaimLedgerError(
                f"claim {claim_id!r} is already verified; cannot reject."
            )

        if not verified_by:
            raise ClaimLedgerError("verified_by is required (Judge identity).")
        if verified_by == current.claimed_by:
            raise ClaimLedgerError(
                "Generator ≠ Judge invariant violated on reject."
            )

        meta = dict(current.meta)
        if reason:
            meta["reject_reason"] = reason

        rejected = Claim(
            claim_id=current.claim_id,
            type=current.type,
            subject=current.subject,
            statement=current.statement,
            authority_file=current.authority_file,
            evidence=list(current.evidence),
            claimed_by=current.claimed_by,
            verified_by=verified_by,
            status="rejected",
            ts=_now_iso(),
            meta=meta,
        )
        self._append(rejected)
        return rejected

    # ── Queries ────────────────────────────────────────────────────────

    def query_by_subject(self, subject: str) -> list[Claim]:
        return [c for c in self._latest_by_id().values() if c.subject == subject]

    def query_by_type(self, type: str) -> list[Claim]:
        return [c for c in self._latest_by_id().values() if c.type == type]

    def query_pending(self) -> list[Claim]:
        return [c for c in self._latest_by_id().values() if c.status == "pending"]

    def all_claims(self) -> list[Claim]:
        return list(self._latest_by_id().values())

    def stats(self) -> dict:
        by_status = {s: 0 for s in CLAIM_STATUSES}
        by_type: dict[str, int] = {}
        for c in self._latest_by_id().values():
            by_status[c.status] = by_status.get(c.status, 0) + 1
            by_type[c.type] = by_type.get(c.type, 0) + 1
        return {
            "total": sum(by_status.values()),
            "by_status": by_status,
            "by_type": by_type,
        }

    def materialize_view(
        self,
        authority_file: str,
        *,
        include_statuses: tuple[str, ...] = ("verified",),
    ) -> list[Claim]:
        """Return the verified claims that make up a given authority view.

        Materialization is intentionally read-only here. Skills are
        responsible for the file-writing side (they know the schema of
        seed.json vs qa-results.json). This keeps the ledger module
        schema-free.
        """
        return [
            c
            for c in self._latest_by_id().values()
            if c.authority_file == authority_file and c.status in include_statuses
        ]


# ── Evidence file:line resolution ──────────────────────────────────────


def _unresolved_evidence(
    evidence: list[str], project_root: str | os.PathLike
) -> list[str]:
    """Return the subset of evidence entries that do not resolve on disk."""
    root = Path(project_root)
    unresolved: list[str] = []
    for entry in evidence:
        m = _EVIDENCE_WITH_LINE.match(entry)
        if m:
            path = root / m.group("path")
            line = int(m.group("line"))
            if not path.exists() or not path.is_file():
                unresolved.append(entry)
                continue
            try:
                with path.open("rb") as f:
                    total = sum(1 for _ in f)
            except OSError:
                unresolved.append(entry)
                continue
            if line < 1 or line > total:
                unresolved.append(entry)
            continue
        # Bare path — existence is enough
        path = root / entry
        if not path.exists():
            unresolved.append(entry)
    return unresolved
