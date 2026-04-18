"""AC Dependency Planning (v3.0.0, T2).

Structured + LLM-hybrid DAG builder for acceptance criteria.
- Structured pass uses metadata fields on ACs:
    - depends_on: list[str]  (explicit IDs)
    - prerequisites: list[str]  (implicit text match, optional)
    - shared_runtime_resources: list[str]  (serial constraints)
- LLM pass is performed by the skill layer; this module merges its JSON
  output with the structured pass and runs Kahn's topological sort.

Usage (MCP):
    structured = analyze_structured(acs)
    merged = merge_llm(structured, llm_deps)
    levels = compute_execution_levels(merged)
    plan = build_plan(merged, levels)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class ACDepNode:
    """Dependency analysis view of an AC."""
    id: str
    description: str
    depends_on: list[str] = field(default_factory=list)
    shared_resources: list[str] = field(default_factory=list)
    requires_serial_stage: bool = False
    serialization_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "depends_on": list(self.depends_on),
            "shared_resources": list(self.shared_resources),
            "requires_serial_stage": self.requires_serial_stage,
            "serialization_reasons": list(self.serialization_reasons),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ACDepNode":
        return cls(
            id=d["id"],
            description=d.get("description", ""),
            depends_on=list(d.get("depends_on", [])),
            shared_resources=list(d.get("shared_resources", [])),
            requires_serial_stage=bool(d.get("requires_serial_stage", False)),
            serialization_reasons=list(d.get("serialization_reasons", [])),
        )


def analyze_structured(acs: list[dict]) -> list[ACDepNode]:
    """Build ACDepNodes from raw AC dicts.

    Recognizes these optional fields on each AC:
      - id (required — falls back to AC-<idx>)
      - description
      - depends_on: list[str]
      - prerequisites: list[str]  (alias, merged into depends_on)
      - shared_runtime_resources: list[str]
      - serial_only: bool
    """
    nodes: list[ACDepNode] = []
    seen_ids: set[str] = set()
    for idx, ac in enumerate(acs, start=1):
        ac_id = ac.get("id") or f"AC-{idx}"
        if ac_id in seen_ids:
            raise ValueError(f"Duplicate AC id: {ac_id}")
        seen_ids.add(ac_id)

        deps_raw: list[str] = []
        deps_raw.extend(ac.get("depends_on", []) or [])
        deps_raw.extend(ac.get("prerequisites", []) or [])
        deps = []
        for d in deps_raw:
            if d and d not in deps and d != ac_id:
                deps.append(d)

        reasons: list[str] = []
        if ac.get("serial_only"):
            reasons.append("explicit serial_only=true")

        shared = list(ac.get("shared_runtime_resources", []) or [])

        nodes.append(
            ACDepNode(
                id=ac_id,
                description=ac.get("description", ""),
                depends_on=deps,
                shared_resources=shared,
                requires_serial_stage=bool(ac.get("serial_only", False)),
                serialization_reasons=reasons,
            )
        )
    return nodes


def merge_llm(
    structured: list[ACDepNode],
    llm_deps: list[dict],
    mode: str = "augment",
) -> list[ACDepNode]:
    """Merge LLM-inferred dependencies into the structured node set.

    llm_deps schema (per entry):
      {"ac_id": "<id>", "depends_on": ["<id>", ...], "reason": "..."}

    Args:
        structured: nodes from `analyze_structured`.
        llm_deps: LLM output.
        mode:
          - "augment" (default) — keep structured deps, add LLM-inferred ones.
          - "replace" — for any AC mentioned in llm_deps, discard its
            structured deps and use the LLM list only. ACs not mentioned
            keep their structured deps.

    Self-references and unknown IDs are always discarded regardless of mode.
    """
    if mode not in ("augment", "replace"):
        raise ValueError(f"merge_llm mode must be 'augment' or 'replace', got {mode!r}")

    by_id = {n.id: n for n in structured}
    known_ids = set(by_id)

    for entry in llm_deps:
        ac_id = entry.get("ac_id")
        if not ac_id or ac_id not in by_id:
            continue
        target = by_id[ac_id]
        if mode == "replace":
            target.depends_on = []
        for dep in entry.get("depends_on", []) or []:
            if not dep or dep == ac_id or dep not in known_ids:
                continue
            if dep not in target.depends_on:
                target.depends_on.append(dep)
    return structured


def _detect_cycle(nodes: list[ACDepNode]) -> list[str]:
    """Return the IDs involved in a cycle (first one found), or []."""
    graph = {n.id: list(n.depends_on) for n in nodes}
    color = {k: 0 for k in graph}  # 0=white 1=gray 2=black
    parent: dict[str, str | None] = {k: None for k in graph}
    cycle: list[str] = []

    def dfs(u: str) -> bool:
        color[u] = 1
        for v in graph.get(u, []):
            if v not in color:
                continue
            if color[v] == 1:
                # cycle found — rebuild path
                cur: str | None = u
                path = [v]
                while cur is not None and cur != v:
                    path.append(cur)
                    cur = parent.get(cur)
                if cur == v:
                    path.append(v)
                cycle[:] = list(reversed(path))
                return True
            if color[v] == 0:
                parent[v] = u
                if dfs(v):
                    return True
        color[u] = 2
        return False

    for start in list(graph):
        if color[start] == 0 and dfs(start):
            return cycle
    return []


def compute_execution_levels(nodes: list[ACDepNode]) -> list[list[str]]:
    """Kahn's algorithm: return levels where each level is a set of AC IDs
    that can be built in parallel.

    Raises ValueError if a cycle is detected.
    Serial-only nodes always form a single-item level.
    """
    cycle = _detect_cycle(nodes)
    if cycle:
        raise ValueError(f"Cycle detected among ACs: {' → '.join(cycle)}")

    by_id = {n.id: n for n in nodes}
    in_degree = {n.id: len([d for d in n.depends_on if d in by_id]) for n in nodes}
    remaining = set(by_id)
    levels: list[list[str]] = []

    while remaining:
        current_parallel: list[str] = []
        current_serial: list[str] = []
        for node_id in list(remaining):
            if in_degree[node_id] == 0:
                if by_id[node_id].requires_serial_stage:
                    current_serial.append(node_id)
                else:
                    current_parallel.append(node_id)
        if not current_parallel and not current_serial:
            break  # shouldn't happen since we ruled out cycles

        # Serial nodes split into single-node levels so they never parallelize
        if current_parallel:
            levels.append(sorted(current_parallel))
            for node_id in current_parallel:
                remaining.discard(node_id)
                _decrement_in_degree(nodes, by_id, in_degree, node_id)
        # one serial node at a time, after the parallel batch
        for node_id in sorted(current_serial):
            levels.append([node_id])
            remaining.discard(node_id)
            _decrement_in_degree(nodes, by_id, in_degree, node_id)

    return levels


def _decrement_in_degree(
    nodes: list[ACDepNode],
    by_id: dict[str, ACDepNode],
    in_degree: dict[str, int],
    resolved_id: str,
) -> None:
    for other in nodes:
        if resolved_id in other.depends_on:
            in_degree[other.id] = max(0, in_degree[other.id] - 1)


def build_plan(nodes: list[ACDepNode], levels: list[list[str]]) -> dict:
    """Return an execution plan dict (serializable)."""
    return {
        "nodes": [n.to_dict() for n in nodes],
        "execution_levels": levels,
        "is_parallelizable": any(len(l) > 1 for l in levels),
        "total_levels": len(levels),
        "total_acs": len(nodes),
    }
