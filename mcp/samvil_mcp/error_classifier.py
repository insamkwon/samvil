"""Transient vs permanent failure classification (v4.30 W2.3).

A flaky npm registry timeout and a TypeScript error both used to consume
the same Circuit Breaker budget (MAX_RETRIES=2), so a bad network minute
could halt a whole pipeline run. This module separates them:

- **transient** — infrastructure hiccup (network/timeout/5xx/rate-limit).
  Recommendation: wait `backoff_seconds`, retry once, do NOT count the
  attempt against the circuit breaker.
- **permanent** — code/config defect. Recommendation: fix-then-retry via
  the normal circuit breaker path.

Classification is whitelist-based on the transient side (conservative:
unknown errors are treated as permanent so we never loop on a real bug).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Conservative transient whitelist. Case-insensitive substring/regex match.
# Every entry should describe an error that retrying *without a code
# change* can plausibly fix.
_TRANSIENT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("npm_network", r"npm err!.*network"),
    ("econnrefused", r"econnrefused"),
    ("econnreset", r"econnreset"),
    ("etimedout", r"etimedout"),
    ("eai_again", r"eai_again"),
    ("socket_hangup", r"socket hang ?up"),
    ("fetch_failed", r"fetch failed"),
    ("http_429", r"\b429\b.*(too many requests)|too many requests"),
    ("http_5xx", r"\b50[234]\b.*(bad gateway|service unavailable|gateway timeout)|service unavailable|bad gateway|gateway timeout"),
    ("registry_timeout", r"registry.*(timeout|timed out)"),
    ("generic_timeout", r"request.*timed? ?out|timeout.*exceeded"),
    ("dns_failure", r"getaddrinfo|enotfound"),
)

# Signals that force a permanent verdict even when a transient pattern
# also matched (e.g. a build log containing both a 503 warning and a
# real compile error must be fixed, not retried blindly).
_PERMANENT_OVERRIDES: tuple[tuple[str, str], ...] = (
    ("typescript", r"error ts\d+"),
    ("syntax", r"syntaxerror"),
    ("module_not_found", r"module not found|cannot find module(?!.*registry)"),
    ("type_error", r"\btypeerror\b"),
    ("reference_error", r"referenceerror"),
    ("compile_failed", r"failed to compile"),
    # Test-runner timeouts are code defects, not infrastructure — they
    # match the generic timeout pattern otherwise (v4.30.4 review finding).
    ("test_timeout", r"test timeout|timeout of \d+ ?ms exceeded|exceeded timeout of"),
)

DEFAULT_BACKOFF_SECONDS = 30
MAX_BACKOFF_SECONDS = 120


@dataclass
class FailureVerdict:
    failure_class: str  # "transient" | "permanent"
    matched_transient: list[str] = field(default_factory=list)
    matched_permanent: list[str] = field(default_factory=list)
    backoff_seconds: int = 0
    counts_against_circuit_breaker: bool = True
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_class": self.failure_class,
            "matched_transient": self.matched_transient,
            "matched_permanent": self.matched_permanent,
            "backoff_seconds": self.backoff_seconds,
            "counts_against_circuit_breaker": self.counts_against_circuit_breaker,
            "recommendation": self.recommendation,
        }


def classify_failure(log_text: str, attempt: int = 1) -> FailureVerdict:
    """Classify a failure log. Conservative: transient requires a
    whitelist hit AND no permanent override hit."""
    text = (log_text or "").lower()

    matched_transient = [
        name for name, pat in _TRANSIENT_PATTERNS if re.search(pat, text)
    ]
    matched_permanent = [
        name for name, pat in _PERMANENT_OVERRIDES if re.search(pat, text)
    ]

    if matched_transient and not matched_permanent:
        backoff = min(
            DEFAULT_BACKOFF_SECONDS * max(1, attempt), MAX_BACKOFF_SECONDS
        )
        # One free retry only — enforced here, not just in SKILL prose
        # (v4.30.4 review finding): a persistently flaky environment must
        # not loop outside the circuit breaker forever.
        if attempt >= 2:
            return FailureVerdict(
                failure_class="transient",
                matched_transient=matched_transient,
                matched_permanent=[],
                backoff_seconds=0,
                counts_against_circuit_breaker=True,
                recommendation=(
                    "Transient signature persisted after a free retry — "
                    "treat as permanent: investigate the environment or "
                    "escalate via the normal circuit-breaker path."
                ),
            )
        return FailureVerdict(
            failure_class="transient",
            matched_transient=matched_transient,
            matched_permanent=[],
            backoff_seconds=backoff,
            counts_against_circuit_breaker=False,
            recommendation=(
                f"Infrastructure hiccup ({', '.join(matched_transient)}). "
                f"Wait {backoff}s and retry the same command once without "
                "changing code. Do not consume a circuit-breaker attempt."
            ),
        )

    return FailureVerdict(
        failure_class="permanent",
        matched_transient=matched_transient,
        matched_permanent=matched_permanent,
        backoff_seconds=0,
        counts_against_circuit_breaker=True,
        recommendation=(
            "Code/config defect — read the error, apply a fix, then retry "
            "via the normal circuit-breaker path."
        ),
    )
