"""Security Hardening — SSRF, Path Traversal, Input Validation (v2.6.0, #09).

Defense-in-depth layers:
  1. sanitize_filename — strip path traversal / limit length
  2. validate_path_within — prevent directory escape
  3. validate_url_safe — block SSRF vectors (for future use)
  4. detect_dangerous — pattern-based injection detection

Escape hatch: SAMVIL_ALLOW_LOCAL_TRANSPORT=1 (dev only).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse

SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_\-.]")


def sanitize_filename(name: str, max_len: int = 64) -> str:
    """Strip path traversal chars, limit length."""
    safe = SAFE_NAME_RE.sub("", name)
    safe = safe.replace("..", "_")
    return safe[:max_len] or "unnamed"


def validate_path_within(
    path: str | Path,
    allowed_root: str | Path,
) -> tuple[bool, str]:
    """Ensure resolved path stays within allowed_root."""
    try:
        resolved = Path(path).resolve()
        root = Path(allowed_root).resolve()
        if not resolved.is_relative_to(root):
            return (False, f"Path escapes root: {resolved}")
        return (True, "")
    except (OSError, ValueError) as e:
        return (False, str(e))


def validate_url_safe(url: str) -> tuple[bool, str]:
    """Block SSRF vectors (for future Tavily/MCP Bridge)."""
    import ipaddress

    try:
        parsed = urlparse(url)
    except Exception as e:
        return (False, f"Malformed URL: {e}")

    if parsed.scheme.lower() not in {"http", "https"}:
        return (False, f"Unsafe scheme: {parsed.scheme}")

    if parsed.username or parsed.password:
        return (False, "Userinfo forbidden")

    hostname = parsed.hostname or ""
    if not hostname:
        return (False, "Empty hostname")

    if hostname == "localhost":
        if not os.environ.get("SAMVIL_ALLOW_LOCAL_TRANSPORT"):
            return (False, "localhost blocked (set SAMVIL_ALLOW_LOCAL_TRANSPORT=1 for dev)")

    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_loopback:
            return (False, f"Loopback IP: {ip}")
        if ip.is_link_local:
            return (False, f"Link-local IP: {ip}")
        if ip.is_private:
            return (False, f"Private IP: {ip}")
        if ip.is_reserved:
            return (False, f"Reserved IP: {ip}")
    except ValueError:
        pass  # DNS name — OK

    return (True, "")


DANGEROUS_PATTERNS = [
    "__import__", "subprocess", "os.popen", "os.system",
    "eval(", "exec(", "compile(",
    "../", "..\\",
]


def detect_dangerous(s: str) -> list[str]:
    """Return list of detected dangerous patterns."""
    return [p for p in DANGEROUS_PATTERNS if p in s]
