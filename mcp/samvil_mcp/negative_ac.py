"""Negative / edge AC coverage — close the spec↔intent gap (A1).

The #1 reason a SAMVIL output "passes QA but I keep fixing it" is that
the AC tree captures only the happy path. The interview extracts
"사용자가 X를 추가할 수 있다" and stops — so QA verifies adding works,
the app ships, and the moment you submit an empty form / a 5,000-char
title / reload mid-action, it breaks and you fix it by hand.

This module does NOT auto-write ACs (Korean NLP guessing is unreliable).
Instead it detects what KIND of behavior each happy-path AC describes and
returns the edge categories the feature MUST address — a forced checklist
the seed stage fills with concrete ACs (or explicitly marks N/A with a
reason). Structure from MCP, specifics from the LLM — SAMVIL's pattern.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Behaviour patterns → required edge categories. Keyword match is KO + EN,
# case-insensitive, substring. A single AC can match multiple patterns.
_PATTERNS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "create",
        r"추가|입력|작성|생성|등록|제출|올리|add|create|submit|insert|new\b|post\b",
        ("empty_input", "too_long", "duplicate"),
    ),
    (
        "persist",
        r"저장|유지|기억|보존|persist|save|store|localstorage|남아|지속",
        ("survives_reload",),
    ),
    (
        "list",
        r"표시|목록|보여|리스트|렌더|나열|조회|display|list|show|render|render|grid",
        ("empty_state",),
    ),
    (
        "delete",
        r"삭제|제거|지우|비우|delete|remove|clear|destroy",
        ("confirm_or_undo",),
    ),
    (
        "numeric",
        r"증가|감소|숫자|카운트|수량|점수|개수|금액|number|count|increment|decrement|score|amount|quantity",
        ("boundary_min", "boundary_max"),
    ),
    (
        "toggle",
        r"완료|토글|체크|상태\s*변경|on/off|toggle|complete|check|status|switch",
        ("round_trip",),
    ),
    (
        "search_filter",
        r"검색|필터|정렬|찾기|search|filter|sort|query",
        ("no_match",),
    ),
)

# Per-category: human rationale + a fill-in template the LLM concretizes.
_EDGE_SPECS: dict[str, dict[str, str]] = {
    "empty_input": {
        "rationale": "빈 값/공백만 입력했을 때의 동작이 정의되지 않음",
        "template": "빈 값 또는 공백만으로 <행위>를 시도하면 거부되고 안내가 표시된다",
    },
    "too_long": {
        "rationale": "비정상적으로 긴 입력에서 레이아웃/저장이 깨질 수 있음",
        "template": "매우 긴 입력(예: 1000자)에서도 <대상>이 깨지지 않고 처리된다",
    },
    "duplicate": {
        "rationale": "중복 입력 허용/거부 정책이 미정의",
        "template": "이미 존재하는 <대상>과 중복될 때 정책(허용/거부/병합)이 일관되게 동작한다",
    },
    "survives_reload": {
        "rationale": "새로고침 후 데이터 유지가 검증되지 않으면 '됐다 안 됐다' 함",
        "template": "<대상>을 변경한 뒤 새로고침해도 값이 그대로 유지된다",
    },
    "empty_state": {
        "rationale": "데이터가 0개일 때 빈 화면/깨진 UI가 흔한 결함",
        "template": "<대상>이 하나도 없을 때 빈 상태 안내가 표시된다(빈 화면 아님)",
    },
    "confirm_or_undo": {
        "rationale": "되돌릴 수 없는 삭제는 실수 데이터 손실로 이어짐",
        "template": "<대상> 삭제 시 확인 또는 취소(undo) 경로가 있다",
    },
    "boundary_min": {
        "rationale": "하한(0/음수)에서의 동작이 미정의면 음수/언더플로 버그",
        "template": "<값>이 하한(예: 0)에 도달했을 때 동작이 정의대로다(음수 허용 여부 명시)",
    },
    "boundary_max": {
        "rationale": "상한/대량에서 성능·오버플로 결함",
        "template": "<값>이 매우 클 때도 정확하고 깨지지 않는다",
    },
    "round_trip": {
        "rationale": "토글을 다시 눌러 원상복귀하는 경로가 자주 누락됨",
        "template": "<상태>를 변경한 뒤 다시 변경하면 원래 상태로 정확히 돌아온다",
    },
    "no_match": {
        "rationale": "검색/필터 결과 0건일 때의 표시가 미정의",
        "template": "검색/필터 결과가 0건일 때 '결과 없음'이 명확히 표시된다",
    },
}


@dataclass
class NegativeChecklist:
    feature_name: str
    detected_patterns: list[str] = field(default_factory=list)
    required_edges: list[dict[str, str]] = field(default_factory=list)
    happy_ac_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_name": self.feature_name,
            "detected_patterns": self.detected_patterns,
            "happy_ac_count": self.happy_ac_count,
            "required_edges": self.required_edges,
            "coverage_note": (
                f"{len(self.required_edges)} edge categories must each become a "
                "concrete negative AC (kind='negative') OR be marked N/A with a "
                "one-line reason. Do not ship happy-path-only ACs."
            ),
        }


def _ac_text(ac: Any) -> str:
    if isinstance(ac, str):
        return ac
    if isinstance(ac, dict):
        return str(ac.get("description") or ac.get("text") or ac.get("criterion") or "")
    return ""


def negative_ac_checklist(
    feature_name: str, happy_acs: list[Any]
) -> NegativeChecklist:
    """Detect behaviour patterns across a feature's happy-path ACs and
    return the edge categories it must cover. Deduplicated, ordered."""
    blob = " ".join(_ac_text(ac) for ac in happy_acs).lower()
    result = NegativeChecklist(feature_name=feature_name, happy_ac_count=len(happy_acs))

    seen_edges: set[str] = set()
    for name, pattern, edges in _PATTERNS:
        if re.search(pattern, blob):
            result.detected_patterns.append(name)
            for edge in edges:
                if edge in seen_edges:
                    continue
                seen_edges.add(edge)
                spec = _EDGE_SPECS[edge]
                result.required_edges.append(
                    {
                        "category": edge,
                        "rationale": spec["rationale"],
                        "ac_template": spec["template"],
                    }
                )

    # A feature that matched nothing still deserves the universal edge:
    # what happens on first load / no data.
    if not result.required_edges:
        spec = _EDGE_SPECS["empty_state"]
        result.required_edges.append(
            {
                "category": "empty_state",
                "rationale": spec["rationale"],
                "ac_template": spec["template"],
            }
        )
    return result
