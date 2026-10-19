import unittest

import _pathfix  # noqa: F401
from graph.model import Graph, GraphNode, GraphEdge
from graph import traversal


def _chain_graph():
    # a -> b -> c -> d, plus an unrelated island node e
    g = Graph()
    for nid in ("a", "b", "c", "d", "e"):
        g.add_node(GraphNode(id=nid, type="Component", name=nid.upper()))
    g.add_edge(GraphEdge(source="a", relation="DEPENDS_ON", target="b"))
    g.add_edge(GraphEdge(source="b", relation="DEPENDS_ON", target="c"))
    g.add_edge(GraphEdge(source="c", relation="DEPENDS_ON", target="d"))
    return g


class GraphTraversalTests(unittest.TestCase):
    def setUp(self):
        self.chain_graph = _chain_graph()

    def test_bfs_outgoing_respects_max_depth(self):
        reached = traversal.bfs(self.chain_graph, "a", max_depth=2, direction="out")
        self.assertEqual(reached, {"b": 1, "c": 2})

    def test_bfs_unknown_start_returns_empty(self):
        self.assertEqual(traversal.bfs(self.chain_graph, "nonexistent"), {})

    def test_bfs_island_node_returns_empty(self):
        self.assertEqual(traversal.bfs(self.chain_graph, "e", max_depth=3), {})

    def test_descendants_full_closure(self):
        self.assertEqual(traversal.descendants(self.chain_graph, "a"), {"b", "c", "d"})

    def test_ancestors_full_closure(self):
        self.assertEqual(traversal.ancestors(self.chain_graph, "d"), {"a", "b", "c"})

    def test_blast_radius_is_incoming_closure(self):
        # If "c" changes, everything that (transitively) depends on it — a, b —
        # is affected. "d" is not, since d is downstream of c, not upstream.
        affected = traversal.blast_radius(self.chain_graph, "c", max_depth=5)
        self.assertEqual(set(affected), {"a", "b"})

    def test_blast_radius_bounded_by_depth(self):
        affected = traversal.blast_radius(self.chain_graph, "d", max_depth=1)
        self.assertEqual(affected, ["c"])

    def test_shortest_path_found(self):
        path = traversal.shortest_path(self.chain_graph, "a", "d")
        self.assertEqual(path, ["a", "b", "c", "d"])

    def test_shortest_path_same_node(self):
        self.assertEqual(traversal.shortest_path(self.chain_graph, "b", "b"), ["b"])

    def test_shortest_path_unreachable_within_depth(self):
        self.assertIsNone(traversal.shortest_path(self.chain_graph, "a", "d", max_depth=1))

    def test_shortest_path_disconnected_island(self):
        self.assertIsNone(traversal.shortest_path(self.chain_graph, "a", "e"))

    def test_shortest_path_unknown_node(self):
        self.assertIsNone(traversal.shortest_path(self.chain_graph, "a", "nonexistent"))

    def test_bfs_handles_cycles_without_infinite_loop(self):
        g = Graph()
        for nid in ("x", "y", "z"):
            g.add_node(GraphNode(id=nid, type="Component", name=nid))
        g.add_edge(GraphEdge(source="x", relation="RELATED_TO", target="y"))
        g.add_edge(GraphEdge(source="y", relation="RELATED_TO", target="z"))
        g.add_edge(GraphEdge(source="z", relation="RELATED_TO", target="x"))  # cycle
        reached = traversal.bfs(g, "x", max_depth=10, direction="both")
        self.assertEqual(set(reached), {"y", "z"})


if __name__ == "__main__":
    unittest.main()
