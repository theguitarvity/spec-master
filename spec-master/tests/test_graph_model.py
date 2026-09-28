import unittest

import _pathfix  # noqa: F401
from graph.model import GraphNode, GraphEdge, Graph


class GraphModelTests(unittest.TestCase):
    def test_graphnode_roundtrip(self):
        node = GraphNode(id="component.test", type="Component", name="Test Component")
        d = node.to_dict()
        self.assertEqual(d["id"], "component.test")
        self.assertEqual(d["type"], "Component")
        self.assertEqual(d["name"], "Test Component")

        node2 = GraphNode.from_dict(d)
        self.assertEqual(node2.id, "component.test")
        self.assertEqual(node2.type, "Component")
        self.assertEqual(node2.name, "Test Component")

    def test_graphedge_roundtrip(self):
        edge = GraphEdge(source="component.a", relation="DEPENDS_ON", target="component.b")
        d = edge.to_dict()
        self.assertEqual(d["source"], "component.a")
        self.assertEqual(d["relation"], "DEPENDS_ON")
        self.assertEqual(d["target"], "component.b")

        edge2 = GraphEdge.from_dict(d)
        self.assertEqual(edge2.source, "component.a")
        self.assertEqual(edge2.relation, "DEPENDS_ON")
        self.assertEqual(edge2.target, "component.b")

    def test_graph_add_get_node(self):
        g = Graph()
        node = GraphNode(id="a", type="Component", name="A")
        g.add_node(node)

        fetched = g.get_node("a")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "A")
        self.assertIsNone(g.get_node("b"))

    def test_graph_neighbors(self):
        g = Graph()
        g.add_node(GraphNode(id="a", type="Component", name="A"))
        g.add_node(GraphNode(id="b", type="Component", name="B"))
        g.add_node(GraphNode(id="c", type="Component", name="C"))

        g.add_edge(GraphEdge(source="a", relation="CALLS", target="b"))
        g.add_edge(GraphEdge(source="b", relation="CALLS", target="c"))
        g.add_edge(GraphEdge(source="c", relation="DEPENDS_ON", target="a"))

        # test directions
        out_a = g.neighbors("a", direction="out")
        self.assertEqual(len(out_a), 1)
        self.assertEqual(out_a[0].target, "b")

        in_a = g.neighbors("a", direction="in")
        self.assertEqual(len(in_a), 1)
        self.assertEqual(in_a[0].source, "c")

        both_a = g.neighbors("a", direction="both")
        self.assertEqual(len(both_a), 2)

        # test relation filter
        filtered = g.neighbors("b", relations=["DEPENDS_ON"], direction="both")
        self.assertEqual(len(filtered), 0)

    def test_graph_stats(self):
        g = Graph()
        g.add_node(GraphNode(id="a", type="Component", name="A"))
        g.add_node(GraphNode(id="b", type="Service", name="B"))
        g.add_edge(GraphEdge(source="a", relation="CALLS", target="b"))

        stats = g.stats()
        self.assertEqual(stats["total_nodes"], 2)
        self.assertEqual(stats["total_edges"], 1)
        self.assertEqual(stats["nodes_by_type"]["Component"], 1)
        self.assertEqual(stats["nodes_by_type"]["Service"], 1)


if __name__ == "__main__":
    unittest.main()
