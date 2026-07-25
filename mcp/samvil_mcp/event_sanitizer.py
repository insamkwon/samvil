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
_AUTHORIZATION_HEADER = re.compile(
    r"(?P<label>['\"]?\bAuthorization\b['\"]?\s*[:=]\s*)"
    r"(?P<quote>['\"]?)[^\r\n]*(?P=quote)",
    re.IGNORECASE,
)
_COOKIE_HEADER = re.compile(
    r"(?P<label>['\"]?\b(?:Set-Cookie|Cookie)\b['\"]?\s*[:=]\s*)"
    r"(?P<quote>['\"]?)[^\r\n]*(?P=quote)",
    re.IGNORECASE,
)
_CREDENTIAL_KEY = (
    r"\b(?:(?:[a-z0-9]+[_-])*(?:api[_-]?key|access[_-]?token|"
    r"auth[_-]?token|client[_-]?secret|secret[_-]?access[_-]?key|"
    r"service[_-]?role[_-]?key|private[_-]?key|secret[_-]?key|"
    r"restricted[_-]?key|secret|token|password|passwd)|database[_-]?url)\b"
)
_QUOTED_CREDENTIAL = re.compile(
    rf"(?P<key_quote>['\"]?)(?P<key>{_CREDENTIAL_KEY})(?P=key_quote)"
    r"(?P<separator>\s*[:=]\s*)(?P<value_quote>['\"])"
    r"(?:\\.|(?!(?P=value_quote))[\s\S])*(?P=value_quote)",
    re.IGNORECASE,
)
_CREDENTIAL = re.compile(
    rf"(?P<key_quote>['\"]?)(?P<key>{_CREDENTIAL_KEY})"
    r"(?P=key_quote)(?P<separator>\s*[:=]\s*)"
    r"(?P<value>[^'\"\s,;}]+)",
    re.IGNORECASE,
)
_TOKEN_LITERAL = re.compile(
    r"\b(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9_]{8,}|"
    r"rk_(?:live|test)_[A-Za-z0-9_]{8,}|sk-[A-Za-z0-9_-]{8,})\b",
    re.IGNORECASE,
)
_MAX_STRING_LENGTH = 4096
_MAX_DEPTH = 8
_SAFE_EVENT_LABEL = re.compile(r"^[a-z][a-z0-9_:-]{0,63}$")


def _redact_string(value: str) -> str:
    redacted = _EMAIL.sub("[REDACTED_EMAIL]", value)
    redacted = _AUTHORIZATION_HEADER.sub(_redact_header_match, redacted)
    redacted = _BEARER.sub("[REDACTED_TOKEN]", redacted)
    redacted = _QUOTED_CREDENTIAL.sub(_redact_credential_match, redacted)
    redacted = _CREDENTIAL.sub(_redact_credential_match, redacted)
    redacted = _COOKIE_HEADER.sub(_redact_header_match, redacted)
    redacted = _TOKEN_LITERAL.sub("[REDACTED_TOKEN]", redacted)
    if len(redacted) > _MAX_STRING_LENGTH:
        return redacted[:_MAX_STRING_LENGTH] + "...[TRUNCATED]"
    return redacted


def _redact_header_match(match: re.Match[str]) -> str:
    quote = match.group("quote")
    return f"{match.group('label')}{quote}[REDACTED]{quote}"


def _redact_credential_match(match: re.Match[str]) -> str:
    value_quote = match.groupdict().get("value_quote") or ""
    return (
        f"{match.group('key_quote')}{match.group('key')}"
        f"{match.group('key_quote')}{match.group('separator')}"
        f"{value_quote}[REDACTED]{value_quote}"
    )


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
                "restrictedkey",
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
