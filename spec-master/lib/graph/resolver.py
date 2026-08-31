"""Entity resolver for the Spec Master Knowledge Graph.

Prevents duplicate nodes by maintaining a canonical ID + aliases registry.
Before creating a new node, agents must call resolve() to check if an
alias already maps to an existing canonical ID.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .model import Graph


def _normalize(name: str) -> str:
    """Lowercase, strip, collapse whitespace and punctuation for comparison."""
    name = name.lower().strip()
    name = re.sub(r"[-_\s]+", "-", name)
    name = re.sub(r"[^a-z0-9-]", "", name)
    return name


class EntityResolver:
    """Resolves entity names to canonical node IDs."""

    def __init__(self, graph: "Graph") -> None:
        self._graph = graph
        self._alias_index: dict[str, str] = {}  # normalized alias -> canonical id
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self._alias_index.clear()
        for node_id, node in self._graph.nodes.items():
            self._alias_index[_normalize(node_id)] = node_id
            self._alias_index[_normalize(node.name)] = node_id
            for alias in node.aliases:
                self._alias_index[_normalize(alias)] = node_id

    def resolve(self, name: str) -> str | None:
        """Return the canonical node ID for a given name/alias, or None."""
        return self._alias_index.get(_normalize(name))

    def register_node(self, node) -> None:
        """Register a node after it's added to the graph."""
        self._alias_index[_normalize(node.id)] = node.id
        self._alias_index[_normalize(node.name)] = node.id
        for alias in node.aliases:
            self._alias_index[_normalize(alias)] = node.id

    def all_aliases(self) -> dict[str, str]:
        """Return the full alias -> canonical_id map (for debugging)."""
        return dict(self._alias_index)
