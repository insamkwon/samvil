"""Evidence Validator (v2.5.0, Manifesto v3 P1 Evidence-based Assertions).

Validates that cited evidence (file:line) actually exists in the project,
and that referenced code is not a stub/mock (delegates to semantic_checker).
"""

from __future__ import annotations

import re
from pathlib import Path


EVIDENCE_PATTERN = re.compile(r"^(.+?):(\d+)(?:-(\d+))?(?:\s+\((.+)\))?$")


def parse_evidence(evidence_str: str) -> dict | None:
    """Parse a file:line or file:line-line evidence string.

    Examples:
        'src/auth.ts:15'
        'src/auth.ts:15-20'
        'src/auth.ts:15 (zod emailSchema)'

    Returns:
        Dict with file, line_start, line_end, note — or None if malformed.
    """
    match = EVIDENCE_PATTERN.match(evidence_str.strip())
    if not match:
        return None
    file_path, start, end, note = match.groups()
    return {
        "file": file_path.strip(),
        "line_start": int(start),
        "line_end": int(end) if end else int(start),
        "note": note.strip() if note else "",
    }


def validate_file_exists(evidence: dict, project_root: str) -> dict:
    """Check that the cited file exists in the project.

    Returns:
        Dict with exists, abs_path, error.
    """
    root = Path(project_root)
    file_path = evidence.get("file", "")
    if not file_path:
        return {"exists": False, "error": "No file path in evidence"}

    abs_path = root / file_path
    return {
        "exists": abs_path.exists() and abs_path.is_file(),
        "abs_path": str(abs_path),
        "error": "" if abs_path.exists() else f"File not found: {abs_path}",
    }


def validate_line_range(evidence: dict, project_root: str) -> dict:
    """Check that the cited lines are within file bounds.

    Returns:
        Dict with valid, total_lines, error.
    """
    check = validate_file_exists(evidence, project_root)
    if not check["exists"]:
        return {"valid": False, "error": check["error"]}

    abs_path = Path(check["abs_path"])
    try:
        with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
            total_lines = sum(1 for _ in f)
    except OSError as e:
        return {"valid": False, "error": f"Read failed: {e}"}

    line_start = evidence.get("line_start", 0)
    line_end = evidence.get("line_end", line_start)

    if line_start < 1 or line_end > total_lines:
        return {
            "valid": False,
            "total_lines": total_lines,
            "error": f"Lines {line_start}-{line_end} out of range (file has {total_lines} lines)",
        }

    return {"valid": True, "total_lines": total_lines}


def read_evidence_snippet(evidence: dict, project_root: str, context: int = 2) -> str:
    """Read the cited lines + context for semantic verification.

    Args:
        context: extra lines before/after to include.

    Returns:
        Code snippet (empty if file/range invalid).
    """
    validation = validate_line_range(evidence, project_root)
    if not validation["valid"]:
        return ""

    abs_path = Path(project_root) / evidence["file"]
    try:
        with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        return ""

    start = max(0, evidence["line_start"] - 1 - context)
    end = min(len(lines), evidence["line_end"] + context)
    return "".join(lines[start:end])


def validate_evidence_list(evidences: list[str], project_root: str) -> dict:
    """Validate a list of evidence strings. Returns aggregate result."""
    results = []
    all_valid = True
    for e_str in evidences:
        parsed = parse_evidence(e_str)
        if not parsed:
            results.append({
                "evidence": e_str,
                "valid": False,
                "error": "Malformed — expected 'file:line' or 'file:line-line'",
            })
            all_valid = False
            continue

        check = validate_line_range(parsed, project_root)
        results.append({
            "evidence": e_str,
            "valid": check["valid"],
            "parsed": parsed,
            "error": check.get("error", ""),
        })
        if not check["valid"]:
            all_valid = False

    return {
        "all_valid": all_valid,
        "results": results,
        "total": len(evidences),
        "valid_count": sum(1 for r in results if r["valid"]),
    }
