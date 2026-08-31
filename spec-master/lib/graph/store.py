"""Graph storage abstractions for the Spec Master Knowledge Graph.

GraphStore: abstract interface
FileGraphStore: primary implementation — stores nodes as .md files,
                maintains graph-manifest.json, appends to graph-events.jsonl
InMemoryGraphStore: for testing and ephemeral usage

No external graph database required. Git is the source of truth.
"""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

from .model import Graph, GraphNode, GraphEdge
from .parser import parse_node_file, wikilinks_to_edges
from .resolver import EntityResolver
from .events import append_event, NODE_CREATED, NODE_UPDATED, EDGE_CREATED


class GraphStore(ABC):
    """Abstract interface for graph persistence."""

    @abstractmethod
    def load(self) -> Graph:
        ...

    @abstractmethod
    def save_node(self, node: GraphNode) -> None:
        ...

    @abstractmethod
    def save_edge(self, edge: GraphEdge) -> None:
        ...

    @abstractmethod
    def get_node(self, node_id: str) -> GraphNode | None:
        ...

    @abstractmethod
    def all_nodes(self) -> list[GraphNode]:
        ...

    @abstractmethod
    def all_edges(self) -> list[GraphEdge]:
        ...


class InMemoryGraphStore(GraphStore):
    """In-memory graph store for testing and ephemeral usage."""

    def __init__(self) -> None:
        self._graph = Graph()

    def load(self) -> Graph:
        return self._graph

    def save_node(self, node: GraphNode) -> None:
        self._graph.add_node(node)

    def save_edge(self, edge: GraphEdge) -> None:
        self._graph.add_edge(edge)

    def get_node(self, node_id: str) -> GraphNode | None:
        return self._graph.get_node(node_id)

    def all_nodes(self) -> list[GraphNode]:
        return list(self._graph.nodes.values())

    def all_edges(self) -> list[GraphEdge]:
        return list(self._graph.edges)


class FileGraphStore(GraphStore):
    """File-based graph store.

    Layout:
        <knowledge_root>/graph/<category>/<node-id>.md   — node files
        <knowledge_root>/graph-manifest.json              — fast index
        <knowledge_root>/graph-events.jsonl               — mutation log

    The knowledge_root defaults to .spec-master/knowledge/ relative to
    the project root passed at construction time.
    """

    def __init__(self, project_root: str = ".",
                 knowledge_subdir: str = ".spec-master/knowledge") -> None:
        self._root = Path(project_root).resolve()
        self._knowledge_dir = self._root / knowledge_subdir
        self._graph_dir = self._knowledge_dir / "graph"
        self._manifest_path = self._knowledge_dir / "graph-manifest.json"
        self._events_path = self._knowledge_dir / "graph-events.jsonl"
        self._graph_dir.mkdir(parents=True, exist_ok=True)
        self._graph: Graph | None = None

    def _category_dir(self, node_id: str) -> Path:
        """Derive subdirectory from node type prefix (before first dot)."""
        parts = node_id.split(".")
        category = parts[0] if len(parts) > 1 else "misc"
        return self._graph_dir / category

    def _node_path(self, node_id: str) -> Path:
        return self._category_dir(node_id) / f"{node_id}.md"

    def _node_to_markdown(self, node: GraphNode) -> str:
        """Serialize a GraphNode to Markdown with YAML frontmatter."""
        lines = ["---"]
        lines.append(f"id: {node.id}")
        lines.append(f"type: {node.type}")
        lines.append(f"name: {node.name}")
        lines.append(f"status: {node.status}")
        lines.append(f"source: {node.source}")
        lines.append(f"confidence: {node.confidence}")
        if node.tags:
            lines.append("tags:")
            for t in node.tags:
                lines.append(f"  - {t}")
        if node.aliases:
            lines.append("aliases:")
            for a in node.aliases:
                lines.append(f"  - {a}")
        if node.first_seen:
            lines.append(f"first_seen: {json.dumps(node.first_seen)}")
        if node.last_verified:
            lines.append(f"last_verified: {json.dumps(node.last_verified)}")
        lines.append("---")
        lines.append("")
        if node.content:
            lines.append(node.content)
        return "\n".join(lines)

    def _edges_to_manifest_entry(self, node: GraphNode,
                                  edges: list[GraphEdge]) -> dict:
        return {
            "id": node.id,
            "type": node.type,
            "name": node.name,
            "status": node.status,
            "confidence": node.confidence,
            "tags": node.tags,
            "aliases": node.aliases,
            "edge_count": len(edges),
        }

    def load(self) -> Graph:
        """Load all node files and reconstruct the graph."""
        if self._graph is not None:
            return self._graph

        graph = Graph()
        if not self._graph_dir.exists():
            self._graph = graph
            return graph

        # Walk all .md files under graph dir
        for md_file in sorted(self._graph_dir.rglob("*.md")):
            node = parse_node_file(md_file)
            if node:
                graph.add_node(node)

        # Extract edges from wikilinks in node content
        for node in list(graph.nodes.values()):
            for edge in wikilinks_to_edges(node.id, node.content):
                graph.add_edge(edge)

        # Load edges from manifest if it contains explicit typed edges
        if self._manifest_path.exists():
            try:
                manifest = json.loads(self._manifest_path.read_text(encoding="utf-8"))
                for edge_dict in manifest.get("edges", []):
                    graph.add_edge(GraphEdge.from_dict(edge_dict))
            except (json.JSONDecodeError, KeyError):
                pass

        self._graph = graph
        return graph

    def save_node(self, node: GraphNode) -> None:
        """Persist a node as a Markdown file and update the manifest."""
        path = self._node_path(node.id)
        path.parent.mkdir(parents=True, exist_ok=True)

        is_new = not path.exists()
        path.write_text(self._node_to_markdown(node), encoding="utf-8")

        # Update in-memory graph
        if self._graph is None:
            self._graph = Graph()
        self._graph.add_node(node)

        self._update_manifest()
        event_type = NODE_CREATED if is_new else NODE_UPDATED
        append_event(self._events_path, event_type, {"node_id": node.id,
                                                      "type": node.type})

    def save_edge(self, edge: GraphEdge) -> None:
        """Persist a typed edge in the manifest."""
        if self._graph is None:
            self._graph = self.load()
        self._graph.add_edge(edge)
        self._update_manifest()
        append_event(self._events_path, EDGE_CREATED, {
            "source": edge.source,
            "relation": edge.relation,
            "target": edge.target,
        })

    def get_node(self, node_id: str) -> GraphNode | None:
        graph = self.load()
        return graph.get_node(node_id)

    def all_nodes(self) -> list[GraphNode]:
        return list(self.load().nodes.values())

    def all_edges(self) -> list[GraphEdge]:
        return list(self.load().edges)

    def _update_manifest(self) -> None:
        """Rebuild and write the graph-manifest.json index."""
        graph = self._graph or Graph()
        manifest = {
            "schema_version": "1.0",
            "total_nodes": len(graph.nodes),
            "total_edges": len(graph.edges),
            "nodes": [
                {
                    "id": n.id, "type": n.type, "name": n.name,
                    "status": n.status, "confidence": n.confidence,
                    "tags": n.tags, "aliases": n.aliases,
                }
                for n in graph.nodes.values()
            ],
            "edges": [
                e.to_dict() for e in graph.edges
                if e.relation != "RELATED_TO"  # wikilinks stored in md files
            ],
            "types": sorted({n.type for n in graph.nodes.values()}),
            "aliases": {
                alias: n.id
                for n in graph.nodes.values()
                for alias in n.aliases
            },
            "tags": sorted({t for n in graph.nodes.values() for t in n.tags}),
        }
        self._manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def rebuild_manifest(self) -> dict:
        """Force rebuild the manifest by re-scanning all node files."""
        self._graph = None  # force reload
        graph = self.load()
        self._update_manifest()
        return graph.stats()
