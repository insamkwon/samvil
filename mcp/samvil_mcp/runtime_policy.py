"""Shared policy for subprocess-backed stage verification."""

from __future__ import annotations


RUNTIME_RECEIPT_REQUIRED_GATES = frozenset(
    {
        "build_to_qa",
        "qa_to_evolve",
        "qa_to_deploy",
    }
)


def gate_requires_runtime_receipt(gate_name: str) -> bool:
    """Return whether a native gate must have a current subprocess receipt."""
    return gate_name in RUNTIME_RECEIPT_REQUIRED_GATES


__all__ = ["RUNTIME_RECEIPT_REQUIRED_GATES", "gate_requires_runtime_receipt"]
