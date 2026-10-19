import unittest

import _pathfix  # noqa: F401
from graph.model import Graph, GraphNode, GraphEdge
from graph import maps


def _sample_graph():
    g = Graph()
    g.add_node(GraphNode(id="service.api", type="Service", name="API Service"))
    g.add_node(GraphNode(id="db.orders", type="Database", name="Orders DB", status="stale"))
    g.add_edge(GraphEdge(source="service.api", relation="DEPENDS_ON", target="db.orders"))
    return g


class GraphMapsTests(unittest.TestCase):
    def setUp(self):
        self.sample_graph = _sample_graph()

    def test_render_system_map_empty_graph(self):
        text = maps.render_system_map(Graph())
        self.assertIn("System Map", text)
        self.assertIn("no nodes", text)

    def test_render_system_map_groups_by_type(self):
        text = maps.render_system_map(self.sample_graph)
        self.assertIn("## Database", text)
        self.assertIn("## Service", text)
        self.assertIn("API Service", text)
        self.assertIn("DEPENDS_ON", text)
        self.assertIn("(stale)", text)

    def test_render_node_map_unknown_node(self):
        text = maps.render_node_map(Graph(), "nonexistent")
        self.assertIn("not found", text)

    def test_render_node_map_shows_neighborhood(self):
        text = maps.render_node_map(self.sample_graph, "service.api", depth=1)
        self.assertIn("Orders DB", text)
        self.assertIn("1 hop away", text)

    def test_render_dependency_map_no_edges(self):
        text = maps.render_dependency_map(Graph())
        self.assertIn("no active DEPENDS_ON edges", text)

    def test_render_dependency_map_lists_adjacency(self):
        text = maps.render_dependency_map(self.sample_graph)
        self.assertIn("API Service", text)
        self.assertIn("Orders DB", text)


if __name__ == "__main__":
    unittest.main()
