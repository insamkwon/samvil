"""Decision Log / ADR layer for SAMVIL v3.3.

`.samvil/decisions/*.md` stores durable architecture and product decisions as
PM-readable ADR files. Week 2 starts with the schema and markdown format; file
I/O, supersession, council promotion, and MCP wrappers are added in following
tasks.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
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
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    slug = slug[:64].strip("-") or "decision"
    return f"adr_{compact_ts}_{slug}"


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


def _section(body: str, heading: str) -> str:
    pattern = rf"^## {re.escape(heading)}\n(?P<content>.*?)(?=^## |\Z)"
    match = re.search(pattern, body, flags=re.M | re.S)
    if not match:
        return ""
    return match.group("content").strip()
