"""Core data models for the Spec Master Knowledge Graph.

GraphNode and GraphEdge are plain dataclasses — no external dependencies.
All fields follow the graph node format in the architecture spec.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GraphNode:
    """A knowledge graph node persisted as a Markdown file with YAML frontmatter."""

    id: str                          # Stable namespaced ID: "component.payment-service"
    type: str                        # Ontology entity type
    name: str                        # Human-readable name
    status: str = "active"           # active | deprecated | stale
    source: str = "UNRESOLVED"       # Provenance enum
    confidence: float = 1.0          # 0.0 – 1.0
    tags: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    first_seen: dict = field(default_factory=dict)   # {commit, phase}
    last_verified: dict = field(default_factory=dict)
    raw_frontmatter: dict = field(default_factory=dict)
    content: str = ""                # Markdown body (below frontmatter)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "status": self.status,
            "source": self.source,
            "confidence": self.confidence,
            "tags": self.tags,
            "aliases": self.aliases,
            "first_seen": self.first_seen,
            "last_verified": self.last_verified,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GraphNode":
        return cls(
            id=data["id"],
            type=data.get("type", "Component"),
            name=data.get("name", data["id"]),
            status=data.get("status", "active"),
            source=data.get("source", "UNRESOLVED"),
            confidence=float(data.get("confidence", 1.0)),
            tags=list(data.get("tags") or []),
            aliases=list(data.get("aliases") or []),
            first_seen=dict(data.get("first_seen") or {}),
            last_verified=dict(data.get("last_verified") or {}),
            raw_frontmatter=data,
            content=data.get("content", ""),
        )


@dataclass
class GraphEdge:
    """A typed, provenance-tracked relationship between two graph nodes."""

    source: str           # Source node ID
    relation: str         # Ontology relation type
    target: str           # Target node ID
    provenance: str = "UNRESOLVED"
    confidence: float = 1.0
    evidence: dict | None = None      # {file, line, description}
    first_seen: dict | None = None
    last_verified: dict | None = None
    valid_from: str | None = None     # commit hash
    valid_to: str | None = None       # commit hash (None = still active)
    status: str = "active"            # active | removed | superseded

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "relation": self.relation,
            "target": self.target,
            "provenance": self.provenance,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "first_seen": self.first_seen,
            "last_verified": self.last_verified,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GraphEdge":
        return cls(
            source=data["source"],
            relation=data["relation"],
            target=data["target"],
            provenance=data.get("provenance", "UNRESOLVED"),
            confidence=float(data.get("confidence", 1.0)),
            evidence=data.get("evidence"),
            first_seen=data.get("first_seen"),
            last_verified=data.get("last_verified"),
            valid_from=data.get("valid_from"),
            valid_to=data.get("valid_to"),
            status=data.get("status", "active"),
        )


@dataclass
class Graph:
    """In-memory graph holding all nodes and edges."""
    nodes: dict[str, GraphNode] = field(default_factory=dict)  # id -> node
    edges: list[GraphEdge] = field(default_factory=list)

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        self.edges.append(edge)

    def get_node(self, node_id: str) -> GraphNode | None:
        return self.nodes.get(node_id)

    def neighbors(self, node_id: str, relations: list[str] | None = None,
                  direction: str = "out") -> list[GraphEdge]:
        """Return edges connected to node_id, filtered by relation types."""
        result = []
        for edge in self.edges:
            if edge.status != "active":
                continue
            if direction in ("out", "both") and edge.source == node_id:
                if relations is None or edge.relation in relations:
                    result.append(edge)
            if direction in ("in", "both") and edge.target == node_id:
                if relations is None or edge.relation in relations:
                    result.append(edge)
        return result

    def stats(self) -> dict:
        from collections import Counter
        node_types = Counter(n.type for n in self.nodes.values())
        edge_rels = Counter(e.relation for e in self.edges)
        total_degree = sum(
            len(self.neighbors(nid, direction="both"))
            for nid in self.nodes
        )
        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "nodes_by_type": dict(node_types),
            "edges_by_relation": dict(edge_rels),
            "average_degree": (total_degree / len(self.nodes)) if self.nodes else 0.0,
            "verified_nodes": sum(1 for n in self.nodes.values() if n.confidence >= 0.9),
            "inferred_nodes": sum(1 for n in self.nodes.values() if 0.5 <= n.confidence < 0.9),
            "unresolved_nodes": sum(1 for n in self.nodes.values() if n.confidence < 0.5),
            "stale_nodes": sum(1 for n in self.nodes.values() if n.status == "stale"),
        }
