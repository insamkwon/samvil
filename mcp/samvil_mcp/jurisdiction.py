"""Jurisdiction (⑦) — AI / User / External decision layer.

Per HANDOFF-v3.2-DECISIONS.md §3.⑦, every action the harness is about to
take must pass through a jurisdiction check. Three buckets:

  * `AI`        — harness proceeds automatically.
  * `External`  — requires a non-harness check (external documentation
                  lookup, dependency advisory, pricing pull, etc.).
  * `User`      — requires an explicit human confirmation.

Conflict resolution: **strictest wins** (`AI < External < User`).
Overlap defaults to the higher. The detector is purely lexical to keep
decisions deterministic and auditable; boundary cases go in
`references/jurisdiction-boundary-cases.md`.

Detection rules (§3.⑦):
  * User-gated keywords on diffs / filenames: auth, password, secret,
    api_key, apikey, deletion, migration, payment, charge.
  * External-gated keywords: pricing, cve, license, new-package install,
    deprecated.
  * Irreversibility flags always escalate to User: git push, reset
    --hard, push --force, branch -D; `rm`/`rmdir` with `-r`/`-f`;
    database migration; deployment to non-preview env.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Jurisdiction(str, Enum):
    AI = "ai"
    EXTERNAL = "external"
    USER = "user"

    @property
    def rank(self) -> int:
        return {Jurisdiction.AI: 0, Jurisdiction.EXTERNAL: 1, Jurisdiction.USER: 2}[
            self
        ]

    @classmethod
    def strictest(cls, *js: "Jurisdiction") -> "Jurisdiction":
        out = cls.AI
        for j in js:
            if j.rank > out.rank:
                out = j
        return out


# ── Keyword matchers ─────────────────────────────────────────────────


# User-gated: the action touches sensitive data or authentication
# primitives. Matched as word boundaries so "authentication" and "auth"
# both land.
_USER_KEYWORDS = (
    r"\bauth(entication)?\b",
    r"\bpassword\b",
    r"\bsecret\b",
    r"\bapi[_-]?key\b",
    r"\bdeletion\b",
    r"\bmigration\b",
    r"\bpayment\b",
    r"\bcharge\b",
)
_USER_RE = re.compile("|".join(_USER_KEYWORDS), re.IGNORECASE)

# External-gated: third-party status, policy, or legal concerns.
_EXTERNAL_KEYWORDS = (
    r"\bpricing\b",
    r"\bcve\b",
    r"\blicense\b",
    r"\bdeprecat(ed|ion)\b",
    r"\bnew[- ]?package\b",
    r"\bnpm install\b",
    r"\bpip install\b",
    r"\buv add\b",
    r"\bpoetry add\b",
)
_EXTERNAL_RE = re.compile("|".join(_EXTERNAL_KEYWORDS), re.IGNORECASE)

# Irreversible commands — always User gated.
_IRREVERSIBLE_RE = re.compile(
    r"git\s+push\s+(?:--force|-f)\b"
    r"|git\s+push\b"
    r"|git\s+reset\s+--hard\b"
    r"|git\s+branch\s+-D\b"
    r"|rm\s+-[rRf]+\s"
    r"|rmdir\s+-[rf]+"
    r"|ALTER\s+TABLE"
    r"|DROP\s+TABLE"
    r"|DROP\s+DATABASE"
    r"|vercel\s+--prod"
    r"|coolify\s+deploy\s+--prod"
    r"|railway\s+deploy\s+--prod",
    re.IGNORECASE,
)


@dataclass
class JurisdictionVerdict:
    jurisdiction: str  # AI / external / user
    matched_rules: list[str] = field(default_factory=list)
    reason: str = ""
    irreversible: bool = False

    def to_dict(self) -> dict:
        return {
            "jurisdiction": self.jurisdiction,
            "matched_rules": self.matched_rules,
            "reason": self.reason,
            "irreversible": self.irreversible,
        }


def check_jurisdiction(
    *,
    action_description: str = "",
    command: str = "",
    filenames: list[str] | None = None,
    diff_text: str = "",
) -> JurisdictionVerdict:
    """Return the jurisdiction for a candidate action.

    `action_description` is a human-readable label (used for matching).
    `command` is the shell command (if any) that would run.
    `filenames` are paths the action would touch.
    `diff_text` is the pending diff (for keyword scans).

    The function scans each piece of context and takes the strictest
    jurisdiction across matches. It returns the reason so retro can
    audit why an action was escalated.
    """
    matched: list[str] = []
    jurisdictions: list[Jurisdiction] = [Jurisdiction.AI]
    irreversible = False

    corpus = " ".join(
        [
            action_description or "",
            command or "",
            " ".join(filenames or []),
            diff_text or "",
        ]
    )

    if _IRREVERSIBLE_RE.search(command or ""):
        matched.append("irreversible_command")
        jurisdictions.append(Jurisdiction.USER)
        irreversible = True

    user_hits = sorted({m.group(0) for m in _USER_RE.finditer(corpus)})
    for h in user_hits:
        matched.append(f"user_keyword:{h}")
    if user_hits:
        jurisdictions.append(Jurisdiction.USER)

    external_hits = sorted({m.group(0) for m in _EXTERNAL_RE.finditer(corpus)})
    for h in external_hits:
        matched.append(f"external_keyword:{h}")
    if external_hits:
        jurisdictions.append(Jurisdiction.EXTERNAL)

    decision = Jurisdiction.strictest(*jurisdictions)

    reason_parts: list[str] = []
    if irreversible:
        reason_parts.append("irreversible command detected")
    if user_hits:
        reason_parts.append(f"sensitive keywords: {user_hits}")
    if external_hits and decision != Jurisdiction.USER:
        reason_parts.append(f"external signals: {external_hits}")
    if not reason_parts:
        reason_parts.append("no triggers matched → AI autonomous")

    return JurisdictionVerdict(
        jurisdiction=decision.value,
        matched_rules=matched,
        reason="; ".join(reason_parts),
        irreversible=irreversible,
    )


# ── Grant memory (once-off, single-session) ──────────────────────────


@dataclass
class Grant:
    action_fingerprint: str
    granted_at: str
    valid_for: str = "1_session"

    def is_valid(self, session_id: str, grant_session_id: str) -> bool:
        if self.valid_for == "1_session":
            return session_id == grant_session_id
        return False


class GrantLedger:
    """In-memory session-scoped grants. Cross-session persistence needs
    explicit re-grant — intentionally no disk persistence here.
    """

    def __init__(self) -> None:
        self._by_session: dict[str, dict[str, Grant]] = {}

    def grant(self, session_id: str, action_fingerprint: str, ts: str) -> Grant:
        g = Grant(action_fingerprint=action_fingerprint, granted_at=ts)
        self._by_session.setdefault(session_id, {})[action_fingerprint] = g
        return g

    def has_grant(self, session_id: str, action_fingerprint: str) -> bool:
        return action_fingerprint in self._by_session.get(session_id, {})

    def clear_session(self, session_id: str) -> None:
        self._by_session.pop(session_id, None)


# ── Automatic loop-stop detector ─────────────────────────────────────


def loop_should_stop(
    *,
    last_failure_signature: str,
    failure_history: list[str],
    ac_mutation_needed: bool = False,
    seed_contradiction: bool = False,
    irreversible_next: bool = False,
    model_confidence_below: bool = False,
) -> tuple[bool, str]:
    """Return (stop, reason). Auto-stop conditions from §3.⑦."""
    if failure_history.count(last_failure_signature) >= 2:
        return True, f"repeated failure signature: {last_failure_signature}"
    if ac_mutation_needed:
        return True, "AC mutation required"
    if seed_contradiction:
        return True, "seed contradiction detected"
    if irreversible_next:
        return True, "next step would be irreversible"
    if model_confidence_below:
        return True, "model confidence below threshold"
    return False, ""
