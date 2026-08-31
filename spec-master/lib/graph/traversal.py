"""Graph traversal utilities: reachability, blast radius, shortest path.

Pure BFS over Graph.neighbors() — no external graph library. Depth is always
bounded (max_depth) since an unbounded traversal over a graph that may
contain cycles (RELATED_TO wikilinks in particular are frequently mutual)
would otherwise never terminate on its own.
"""
from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .model import Graph

DEFAULT_MAX_DEPTH = 3


def bfs(graph: "Graph", start_id: str, max_depth: int = DEFAULT_MAX_DEPTH,
        relations: "list[str] | None" = None, direction: str = "out") -> dict[str, int]:
    """Breadth-first reachability from start_id, bounded to max_depth hops.

    Returns {node_id: hop_distance}, not including start_id itself.
    """
    if start_id not in graph.nodes:
        return {}

    visited: dict[str, int] = {}
    queue: deque[tuple[str, int]] = deque([(start_id, 0)])
    seen = {start_id}

    while queue:
        node_id, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for edge in graph.neighbors(node_id, relations=relations, direction=direction):
            neighbor_id = edge.target if edge.source == node_id else edge.source
            if neighbor_id in seen:
                continue
            seen.add(neighbor_id)
            visited[neighbor_id] = depth + 1
            queue.append((neighbor_id, depth + 1))

    return visited


def descendants(graph: "Graph", start_id: str,
                 relations: "list[str] | None" = None,
                 max_depth: "int | None" = None) -> set[str]:
    """Nodes reachable by following outgoing edges from start_id."""
    depth = max_depth if max_depth is not None else len(graph.nodes) or 1
    return set(bfs(graph, start_id, max_depth=depth, relations=relations, direction="out"))


def ancestors(graph: "Graph", start_id: str,
              relations: "list[str] | None" = None,
              max_depth: "int | None" = None) -> set[str]:
    """Nodes that can reach start_id by following outgoing edges (i.e. reverse)."""
    depth = max_depth if max_depth is not None else len(graph.nodes) or 1
    return set(bfs(graph, start_id, max_depth=depth, relations=relations, direction="in"))


def blast_radius(graph: "Graph", start_id: str, max_depth: int = DEFAULT_MAX_DEPTH,
                  relations: "list[str] | None" = None) -> list[str]:
    """What would be affected if start_id changed: everything that (transitively)
    depends on it — i.e. nodes reachable by following edges *into* start_id.

    Bounded to max_depth hops so a large graph returns a focused, budgeted set
    rather than the whole transitive closure.
    """
    affected = bfs(graph, start_id, max_depth=max_depth, relations=relations, direction="in")
    return sorted(affected, key=lambda nid: (affected[nid], nid))


def shortest_path(graph: "Graph", source_id: str, target_id: str,
                   max_depth: int = 10,
                   relations: "list[str] | None" = None) -> "list[str] | None":
    """BFS shortest path (list of node ids, source..target inclusive), or None."""
    if source_id not in graph.nodes or target_id not in graph.nodes:
        return None
    if source_id == target_id:
        return [source_id]

    parents: dict[str, str] = {}
    seen = {source_id}
    queue: deque[tuple[str, int]] = deque([(source_id, 0)])

    while queue:
        node_id, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for edge in graph.neighbors(node_id, relations=relations, direction="both"):
            neighbor_id = edge.target if edge.source == node_id else edge.source
            if neighbor_id in seen:
                continue
            seen.add(neighbor_id)
            parents[neighbor_id] = node_id
            if neighbor_id == target_id:
                path = [target_id]
                cur = target_id
                while cur != source_id:
                    cur = parents[cur]
                    path.append(cur)
                path.reverse()
                return path
            queue.append((neighbor_id, depth + 1))

    return None
