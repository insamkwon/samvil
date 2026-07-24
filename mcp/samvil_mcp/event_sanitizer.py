"""Bounded redaction for event payloads persisted to DB and JSONL."""

from __future__ import annotations

import re
from typing import Any


_SENSITIVE_KEYS = re.compile(
    r"(?:^|_)(?:app|prompt|input|email|password|passwd|secret|token|api_?key|authorization|cookie)(?:$|_)",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_CREDENTIAL = re.compile(
    r"\b(api[_-]?key|secret|token|password)\s*[:=]\s*[^\s,;]+",
    re.IGNORECASE,
)
_TOKEN_LITERAL = re.compile(
    r"\b(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9_]{8,}|sk-[A-Za-z0-9_-]{8,})\b",
    re.IGNORECASE,
)
_MAX_STRING_LENGTH = 4096
_MAX_DEPTH = 8
_SAFE_EVENT_LABEL = re.compile(r"^[a-z][a-z0-9_:-]{0,63}$")


def _redact_string(value: str) -> str:
    redacted = _EMAIL.sub("[REDACTED_EMAIL]", value)
    redacted = _BEARER.sub("[REDACTED_TOKEN]", redacted)
    redacted = _CREDENTIAL.sub(lambda match: f"{match.group(1)}=[REDACTED]", redacted)
    redacted = _TOKEN_LITERAL.sub("[REDACTED_TOKEN]", redacted)
    if len(redacted) > _MAX_STRING_LENGTH:
        return redacted[:_MAX_STRING_LENGTH] + "...[TRUNCATED]"
    return redacted


def sanitize_event_data(value: Any, *, _depth: int = 0) -> Any:
    """Recursively redact prompts, credentials, email PII, and oversized text."""
    if _depth >= _MAX_DEPTH:
        return "[REDACTED_DEPTH_LIMIT]"
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for raw_key, child in value.items():
            key = str(raw_key)
            compact_key = re.sub(r"[^a-z0-9]", "", key.casefold())
            sensitive_suffixes = (
                "prompt",
                "email",
                "password",
                "passwd",
                "secret",
                "token",
                "apikey",
                "authorization",
                "cookie",
            )
            if (
                _SENSITIVE_KEYS.search(key)
                or compact_key in {"app", "input"}
                or compact_key.endswith(sensitive_suffixes)
            ):
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = sanitize_event_data(child, _depth=_depth + 1)
        return sanitized
    if isinstance(value, list):
        return [sanitize_event_data(child, _depth=_depth + 1) for child in value]
    if isinstance(value, tuple):
        return [sanitize_event_data(child, _depth=_depth + 1) for child in value]
    if isinstance(value, str):
        return _redact_string(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _redact_string(str(value))


def sanitize_event_label(value: str) -> str:
    """Keep stable machine labels only; never persist arbitrary caller prose."""
    normalized = value.strip().casefold()
    return (
        normalized
        if _SAFE_EVENT_LABEL.fullmatch(normalized) and not _TOKEN_LITERAL.search(normalized)
        else "redacted_event_type"
    )


def sanitize_stage_label(value: str) -> str:
    """Keep a bounded stage label without retaining arbitrary caller prose."""
    normalized = value.strip().casefold()
    return (
        normalized
        if _SAFE_EVENT_LABEL.fullmatch(normalized) and not _TOKEN_LITERAL.search(normalized)
        else "redacted_stage"
    )
