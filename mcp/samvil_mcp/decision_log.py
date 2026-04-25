"""Decision Log / ADR layer for SAMVIL v3.3.

`.samvil/decisions/*.md` stores durable architecture and product decisions as
PM-readable ADR files. Week 2 starts with the schema and markdown format; file
I/O, supersession, council promotion, and MCP wrappers are added in following
tasks.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ADR_STATUSES: tuple[str, ...] = ("proposed", "accepted", "superseded", "rejected")

_FRONTMATTER_KEYS: tuple[str, ...] = (
    "id",
    "title",
    "status",
    "created_at",
    "last_reviewed_at",
    "superseded_by",
    "authors",
    "evidence",
    "tags",
    "supersedes",
)

_ADR_ID_RE = re.compile(r"^adr_[A-Za-z0-9T_.-]+$")


class DecisionLogError(ValueError):
    """Raised when a decision-log operation violates ADR invariants."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def adr_id_for_title(title: str, *, ts: str | None = None) -> str:
    """Return a sortable, filesystem-safe ADR id from timestamp + title."""
    if not title.strip():
        raise DecisionLogError("title is required")
    ts = ts or _now_iso()
    compact_ts = ts.replace(":", "-").rstrip("Z")
    slug = _slugify(title)
    slug = slug[:64].strip("-") or "decision"
    return f"adr_{compact_ts}_{slug}"


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def decision_dir(project_root: str | os.PathLike) -> Path:
    """Return the project-local decision directory."""
    return Path(project_root) / ".samvil" / "decisions"


def adr_path(project_root: str | os.PathLike, adr_id: str) -> Path:
    """Return the markdown path for an ADR id.

    ADR ids are filenames, so reject path separators and traversal instead of
    silently normalizing them.
    """
    if not _ADR_ID_RE.match(adr_id):
        raise DecisionLogError(f"invalid ADR id: {adr_id!r}")
    return decision_dir(project_root) / f"{adr_id}.md"


@dataclass
class DecisionADR:
    """A single Architecture Decision Record stored as markdown."""

    adr_id: str
    title: str
    authors: list[str] = field(default_factory=list)
    status: str = "proposed"
    created_at: str = field(default_factory=_now_iso)
    last_reviewed_at: str = ""
    superseded_by: str | None = None
    context: str = ""
    decision: str = ""
    consequences: str = ""
    alternatives: str = ""
    evidence: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    supersedes: list[str] = field(default_factory=list)
    supersession_reason: str = ""

    def __post_init__(self) -> None:
        if not self.adr_id:
            raise DecisionLogError("adr_id is required")
        if not self.title:
            raise DecisionLogError("title is required")
        if self.status not in ADR_STATUSES:
            raise DecisionLogError(
                f"status {self.status!r} not in whitelist {ADR_STATUSES}"
            )
        if not self.authors:
            raise DecisionLogError("authors are required")
        if not self.last_reviewed_at:
            self.last_reviewed_at = self.created_at

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["id"] = data.pop("adr_id")
        return data

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "DecisionADR":
        return DecisionADR(
            adr_id=data["id"],
            title=data["title"],
            status=data.get("status", "proposed"),
            created_at=data.get("created_at", _now_iso()),
            last_reviewed_at=data.get("last_reviewed_at", ""),
            superseded_by=data.get("superseded_by"),
            authors=list(data.get("authors", [])),
            context=data.get("context", ""),
            decision=data.get("decision", ""),
            consequences=data.get("consequences", ""),
            alternatives=data.get("alternatives", ""),
            evidence=list(data.get("evidence", [])),
            tags=list(data.get("tags", [])),
            supersedes=list(data.get("supersedes", [])),
            supersession_reason=data.get("supersession_reason", ""),
        )


def render_adr_markdown(adr: DecisionADR) -> str:
    """Render an ADR as markdown with JSON-valued frontmatter."""
    data = adr.to_dict()
    frontmatter = []
    for key in _FRONTMATTER_KEYS:
        frontmatter.append(f"{key}: {json.dumps(data[key], ensure_ascii=False)}")

    sections = [
        ("Context", adr.context),
        ("Decision", adr.decision),
        ("Consequences", adr.consequences),
        ("Alternatives", adr.alternatives),
    ]
    if adr.supersession_reason:
        sections.append(("Supersession Reason", adr.supersession_reason))

    body = [f"# {adr.title}"]
    for heading, content in sections:
        body.append("")
        body.append(f"## {heading}")
        body.append(content.strip())

    return "---\n" + "\n".join(frontmatter) + "\n---\n\n" + "\n".join(body) + "\n"


def parse_adr_markdown(text: str) -> DecisionADR:
    """Parse the markdown emitted by `render_adr_markdown`."""
    if not text.startswith("---\n"):
        raise DecisionLogError("ADR frontmatter is required")

    parts = text.split("---\n", 2)
    if len(parts) != 3 or parts[0] != "":
        raise DecisionLogError("ADR frontmatter is malformed")

    frontmatter_text, body = parts[1], parts[2]
    data: dict[str, Any] = {}
    for line in frontmatter_text.splitlines():
        if not line.strip():
            continue
        key, sep, raw_value = line.partition(":")
        if not sep:
            raise DecisionLogError(f"invalid frontmatter line: {line!r}")
        key = key.strip()
        if key not in _FRONTMATTER_KEYS:
            continue
        try:
            data[key] = json.loads(raw_value.strip())
        except json.JSONDecodeError as e:
            raise DecisionLogError(f"invalid JSON frontmatter value: {key}") from e

    missing = [key for key in _FRONTMATTER_KEYS if key not in data]
    if missing:
        raise DecisionLogError(f"missing ADR frontmatter keys: {missing}")

    data["context"] = _section(body, "Context")
    data["decision"] = _section(body, "Decision")
    data["consequences"] = _section(body, "Consequences")
    data["alternatives"] = _section(body, "Alternatives")
    data["supersession_reason"] = _section(body, "Supersession Reason")

    return DecisionADR.from_dict(data)


def write_adr(adr: DecisionADR, project_root: str | os.PathLike) -> Path:
    """Atomically write an ADR under `.samvil/decisions/`."""
    target = adr_path(project_root, adr.adr_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(render_adr_markdown(adr), encoding="utf-8")
    os.replace(tmp, target)
    return target


def read_adr(project_root: str | os.PathLike, adr_id: str) -> DecisionADR | None:
    """Read a single ADR. Missing or malformed files return None."""
    try:
        path = adr_path(project_root, adr_id)
    except DecisionLogError:
        raise
    if not path.exists():
        return None
    try:
        return parse_adr_markdown(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, DecisionLogError):
        return None


def list_adrs(
    project_root: str | os.PathLike,
    *,
    status: str | None = None,
) -> list[DecisionADR]:
    """List readable ADRs sorted by creation time, then id."""
    if status is not None and status not in ADR_STATUSES:
        raise DecisionLogError(f"status {status!r} not in whitelist {ADR_STATUSES}")

    root = decision_dir(project_root)
    if not root.exists():
        return []

    out: list[DecisionADR] = []
    for path in sorted(root.glob("*.md")):
        try:
            adr = parse_adr_markdown(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, DecisionLogError):
            continue
        if status is not None and adr.status != status:
            continue
        out.append(adr)

    return sorted(out, key=lambda adr: (adr.created_at, adr.adr_id))


def supersede_adr(
    project_root: str | os.PathLike,
    old_id: str,
    new_id: str,
    reason: str,
    *,
    reviewed_at: str | None = None,
) -> DecisionADR:
    """Mark `old_id` as superseded by `new_id` and write it atomically."""
    old = read_adr(project_root, old_id)
    if old is None:
        raise DecisionLogError(f"old ADR not found: {old_id!r}")
    new = read_adr(project_root, new_id)
    if new is None:
        raise DecisionLogError(f"replacement ADR not found: {new_id!r}")
    if not reason:
        raise DecisionLogError("supersession reason is required")

    if old.status == "superseded":
        if old.superseded_by == new_id:
            return old
        raise DecisionLogError(
            f"ADR {old_id!r} is already superseded by {old.superseded_by!r}"
        )

    old.status = "superseded"
    old.superseded_by = new_id
    old.last_reviewed_at = reviewed_at or _now_iso()
    old.supersession_reason = reason
    write_adr(old, project_root)
    return old


def supersession_chain(
    project_root: str | os.PathLike,
    adr_id: str,
    *,
    max_depth: int = 50,
) -> list[DecisionADR]:
    """Return `adr_id` followed by replacement ADRs, stopping on loops."""
    chain: list[DecisionADR] = []
    seen: set[str] = set()
    current_id: str | None = adr_id

    while current_id and current_id not in seen and len(chain) < max_depth:
        seen.add(current_id)
        adr = read_adr(project_root, current_id)
        if adr is None:
            break
        chain.append(adr)
        current_id = adr.superseded_by

    return chain


def find_adrs_referencing(
    project_root: str | os.PathLike,
    target: str,
) -> list[str]:
    """Return ADR ids that mention `target` in evidence, tags, or body.

    Phase 1 keeps this deterministic and case-sensitive. Later phases can add
    indexes or semantic matching if the decision directory becomes large.
    """
    if not target:
        raise DecisionLogError("target is required")

    matches: list[str] = []
    for adr in list_adrs(project_root):
        haystacks = (
            adr.evidence
            + adr.tags
            + [
                adr.context,
                adr.decision,
                adr.consequences,
                adr.alternatives,
                adr.supersession_reason,
            ]
        )
        if any(target in value for value in haystacks):
            matches.append(adr.adr_id)

    return matches


def adr_from_council_decision(decision: dict[str, Any]) -> DecisionADR:
    """Promote a legacy council `decisions.log` row into an ADR object."""
    decision_text = str(decision.get("decision", "")).strip()
    if not decision_text:
        raise DecisionLogError("council decision text is required")

    legacy_id = str(decision.get("id", "")).strip()
    if legacy_id:
        adr_id = f"adr_council_{_slugify(legacy_id)}"
    else:
        adr_id = adr_id_for_title(f"council {decision_text}")

    binding = bool(decision.get("binding", False))
    applied = bool(decision.get("applied", False))
    dissenting = bool(decision.get("dissenting", False))
    consensus_score = decision.get("consensus_score")
    weak_consensus = (
        isinstance(consensus_score, int | float) and float(consensus_score) < 0.60
    )
    status = (
        "accepted"
        if binding and applied and not dissenting and not weak_consensus
        else "proposed"
    )

    agent = str(decision.get("agent", "")).strip()
    authors = ["samvil-council"]
    if agent:
        authors.append(agent)

    timestamp = str(decision.get("timestamp", "")).strip() or _now_iso()
    title = f"Council: {decision_text[:96]}".rstrip()
    gate = str(decision.get("gate", "")).strip()
    severity = str(decision.get("severity", "")).strip()

    context_lines = [
        _kv("Gate", gate),
        _kv("Round", decision.get("round")),
        _kv("Agent", agent),
        _kv("Reason", decision.get("reason")),
        _kv("Severity", severity),
        _kv("Consensus score", consensus_score),
        _kv("Binding", binding),
        _kv("Applied", applied),
        _kv("Dissenting", dissenting),
    ]
    context = "\n".join(line for line in context_lines if line)

    tags = ["council"]
    if gate:
        tags.append(f"gate:{gate}")
    if agent:
        tags.append(f"agent:{agent}")
    if severity:
        tags.append(f"severity:{severity.lower()}")
    if binding:
        tags.append("binding")
    if not applied:
        tags.append("unapplied")
    if dissenting:
        tags.append("dissenting")
    if weak_consensus:
        tags.append("weak-consensus")

    if status == "accepted":
        consequences = "Subsequent SAMVIL stages should respect this decision."
    else:
        consequences = "This council output is preserved but not binding until accepted."

    return DecisionADR(
        adr_id=adr_id,
        title=title,
        status=status,
        created_at=timestamp,
        last_reviewed_at=timestamp,
        authors=authors,
        context=context,
        decision=decision_text,
        consequences=consequences,
        evidence=list(decision.get("evidence", [])),
        tags=tags,
    )


def _kv(label: str, value: Any) -> str:
    if value is None or value == "":
        return ""
    return f"{label}: {value}"


def _section(body: str, heading: str) -> str:
    pattern = rf"^## {re.escape(heading)}\n(?P<content>.*?)(?=^## |\Z)"
    match = re.search(pattern, body, flags=re.M | re.S)
    if not match:
        return ""
    return match.group("content").strip()
