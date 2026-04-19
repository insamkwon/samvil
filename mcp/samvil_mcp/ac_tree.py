"""AC Tree — recursive acceptance criteria structure (v2.5.0, Ouroboros #06).

Backward-compatible with flat AC arrays. String ACs auto-convert to leaf nodes.
Supports up to MAX_DEPTH=3 recursive decomposition.

Schema:
  - Leaf node: {id, description, children: []}
  - Branch node: {id, description, children: [ACNode, ...]}

Status aggregation:
  - Leaf: status is set directly (pending/in_progress/pass/fail/blocked)
  - Branch: status = aggregate of children
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal, Optional

Status = Literal["pending", "in_progress", "pass", "fail", "blocked", "skipped"]
MAX_DEPTH = 3


@dataclass
class ACNode:
    """A node in the AC tree."""
    id: str
    description: str
    parent_id: Optional[str] = None
    children: list["ACNode"] = field(default_factory=list)
    status: Status = "pending"
    evidence: list[str] = field(default_factory=list)
    depth: int = 0

    @property
    def is_leaf(self) -> bool:
        return len(self.children) == 0

    @property
    def is_branch(self) -> bool:
        return len(self.children) > 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "parent_id": self.parent_id,
            "children": [c.to_dict() for c in self.children],
            "status": self.status,
            "evidence": list(self.evidence),
            "depth": self.depth,
        }

    @classmethod
    def from_dict(cls, data: dict, parent_id: str | None = None, depth: int = 0) -> "ACNode":
        if depth > MAX_DEPTH:
            raise ValueError(
                f"AC tree depth {depth} exceeds MAX_DEPTH={MAX_DEPTH} "
                f"(node id={data.get('id', '?')!r}). Flatten or split into "
                f"a separate feature."
            )
        node = cls(
            id=data.get("id", ""),
            description=data.get("description", ""),
            parent_id=parent_id,
            status=data.get("status", "pending"),
            evidence=list(data.get("evidence", [])),
            depth=depth,
        )
        for child_data in data.get("children", []):
            child = cls.from_dict(child_data, parent_id=node.id, depth=depth + 1)
            node.children.append(child)
        return node


def load_ac_from_schema(ac_data) -> ACNode:
    """Load AC from either flat string or ACNode dict. Backward-compat.

    Examples:
        "User can sign up" → ACNode(description="User can sign up", children=[])
        {"id": "AC-1", "description": "...", "children": [...]}
    """
    if isinstance(ac_data, str):
        # Flat string — auto-wrap as leaf
        return ACNode(id="", description=ac_data, children=[], depth=0)
    if isinstance(ac_data, dict):
        return ACNode.from_dict(ac_data, depth=0)
    raise ValueError(f"Unsupported AC format: {type(ac_data)}")


def aggregate_status(node: ACNode) -> Status:
    """Compute aggregate status for a branch node based on children."""
    if node.is_leaf:
        return node.status

    child_statuses = [aggregate_status(c) for c in node.children]

    if all(s == "pass" for s in child_statuses):
        return "pass"
    if any(s == "fail" for s in child_statuses):
        return "fail"
    if any(s == "in_progress" for s in child_statuses):
        return "in_progress"
    if any(s == "blocked" for s in child_statuses):
        return "blocked"
    return "pending"


def walk(node: ACNode):
    """Generator yielding all nodes (pre-order)."""
    yield node
    for child in node.children:
        yield from walk(child)


def leaves(node: ACNode) -> list[ACNode]:
    """Get all leaf nodes."""
    return [n for n in walk(node) if n.is_leaf]


def count_nodes(node: ACNode) -> dict:
    """Return counts of total/leaf/branch nodes."""
    total = sum(1 for _ in walk(node))
    leaf_count = sum(1 for _ in walk(node) if _.is_leaf)
    return {
        "total": total,
        "leaves": leaf_count,
        "branches": total - leaf_count,
        "max_depth": max((n.depth for n in walk(node)), default=0),
    }


def render_tree_ascii(node: ACNode, indent: int = 0) -> str:
    """Render tree as ASCII HUD."""
    status_icon = {
        "pass": "✓",
        "fail": "✗",
        "in_progress": "⟳",
        "pending": "⏸",
        "blocked": "🛡",
        "skipped": "⏭",
    }

    lines = []
    actual_status = aggregate_status(node) if node.is_branch else node.status
    icon = status_icon.get(actual_status, "?")
    prefix = "  " * indent + ("├── " if indent > 0 else "")
    lines.append(f"{prefix}{icon} {node.id or ''} {node.description}".rstrip())

    for child in node.children:
        lines.append(render_tree_ascii(child, indent + 1))

    return "\n".join(lines)


def assign_ids(root: ACNode, prefix: str = "AC") -> None:
    """Auto-assign hierarchical IDs (AC-1, AC-1.1, AC-1.1.1, ...)."""
    counters: dict[int, int] = {}

    def _assign(n: ACNode, parent_id: str, depth: int):
        counters.setdefault(depth, 0)
        counters[depth] += 1
        if parent_id:
            n.id = f"{parent_id}.{counters[depth]}"
        else:
            n.id = f"{prefix}-{counters[depth]}"

        # reset deeper counters for this branch
        for c in n.children:
            counters_copy_for_children = {k: v for k, v in counters.items() if k <= depth}
            counters.clear()
            counters.update(counters_copy_for_children)
            _assign(c, n.id, depth + 1)

    # Actually simpler approach for a single tree:
    def _simple_assign(n: ACNode, id_str: str):
        n.id = id_str
        for idx, c in enumerate(n.children, start=1):
            _simple_assign(c, f"{id_str}.{idx}")

    # Use simple assign for single-root trees
    if not root.id:
        root.id = f"{prefix}-1"
    for idx, c in enumerate(root.children, start=1):
        _simple_assign(c, f"{root.id}.{idx}")


def simple_decompose_suggestion(ac_description: str) -> list[str]:
    """Simple heuristic decomposition — for scaffolding.

    Real decomposition requires LLM. This is a placeholder for test/demo.
    """
    # Very basic: if description has " and " or commas, split
    lower = ac_description.lower()
    if " and " in lower:
        parts = [p.strip() for p in ac_description.split(" and ")]
        if len(parts) > 1 and all(len(p) > 5 for p in parts):
            return parts
    if "," in ac_description and ac_description.count(",") >= 2:
        parts = [p.strip() for p in ac_description.split(",")]
        if all(len(p) > 5 for p in parts):
            return parts
    return []  # No suggestion — needs LLM


def is_branch_complete(node: ACNode) -> bool:
    """All leaves under this branch have terminal status."""
    if node.is_leaf:
        return node.status in ("pass", "skipped")
    return all(is_branch_complete(c) for c in node.children)


def all_done(node: ACNode) -> bool:
    """All leaves are in a terminal state (pass/fail/skipped)."""
    return all(
        n.status in ("pass", "fail", "skipped")
        for n in walk(node)
        if n.is_leaf
    )


def next_buildable_leaves(
    node: ACNode,
    completed: set[str],
    max_parallel: int = 2,
) -> list[ACNode]:
    """Get next ACs that can be built in parallel.

    Respects tree order and max_parallel limit.
    Skips already-completed / terminal leaves and any leaf whose ancestor
    chain (parent, grandparent, …) contains a `blocked` node.
    """
    buildable = []
    for leaf_node in leaves(node):
        if leaf_node.id in completed:
            continue
        if leaf_node.status in ("pass", "fail", "skipped"):
            continue
        if _has_blocked_ancestor(node, leaf_node):
            continue
        buildable.append(leaf_node)
        if len(buildable) >= max_parallel:
            break
    return buildable


def _has_blocked_ancestor(root: ACNode, leaf: ACNode) -> bool:
    """Walk parent chain from leaf up to root; return True if any is blocked."""
    current_parent_id = leaf.parent_id
    while current_parent_id:
        ancestor = _find_by_id(root, current_parent_id)
        if ancestor is None:
            return False
        if ancestor.status == "blocked":
            return True
        current_parent_id = ancestor.parent_id
    return False


def _find_by_id(root: ACNode, node_id: str) -> Optional["ACNode"]:
    """Find a node by ID in the tree."""
    for n in walk(root):
        if n.id == node_id:
            return n
    return None


def tree_progress(node: ACNode) -> dict:
    """Compute progress stats for the tree."""
    all_leaves = leaves(node)
    total = len(all_leaves)
    done = sum(1 for l in all_leaves if l.status in ("pass", "fail", "skipped"))
    passed = sum(1 for l in all_leaves if l.status == "pass")
    failed = sum(1 for l in all_leaves if l.status == "fail")
    return {
        "total_leaves": total,
        "completed": done,
        "passed": passed,
        "failed": failed,
        "pending": total - done,
        "progress_pct": round(done / total * 100, 1) if total > 0 else 0,
    }
