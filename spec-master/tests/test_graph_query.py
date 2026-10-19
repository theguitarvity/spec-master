import unittest

import _pathfix  # noqa: F401
from graph.model import Graph, GraphNode, GraphEdge
from graph import query


def _sample_graph():
    g = Graph()
    g.add_node(GraphNode(id="service.api", type="Service", name="API Service",
                         tags=["payments", "core"], status="active"))
    g.add_node(GraphNode(id="service.worker", type="Service", name="Worker Service",
                         tags=["payments"], status="active"))
    g.add_node(GraphNode(id="db.orders", type="Database", name="Orders DB",
                         tags=["storage"], status="stale", aliases=["orders-db"]))
    g.add_node(GraphNode(id="component.legacy", type="Component", name="Legacy Widget",
                         status="deprecated"))
    g.add_edge(GraphEdge(source="service.api", relation="DEPENDS_ON", target="db.orders"))
    g.add_edge(GraphEdge(source="service.worker", relation="DEPENDS_ON", target="db.orders"))
    g.add_edge(GraphEdge(source="service.api", relation="CALLS", target="service.worker"))
    return g


class GraphQueryTests(unittest.TestCase):
    def setUp(self):
        self.sample_graph = _sample_graph()

    def test_find_by_type(self):
        services = query.find_by_type(self.sample_graph, "Service")
        self.assertEqual({n.id for n in services}, {"service.api", "service.worker"})

    def test_find_by_tag(self):
        tagged = query.find_by_tag(self.sample_graph, "payments")
        self.assertEqual({n.id for n in tagged}, {"service.api", "service.worker"})

    def test_find_by_status(self):
        stale = query.find_by_status(self.sample_graph, "stale")
        self.assertEqual({n.id for n in stale}, {"db.orders"})

    def test_find_by_relation(self):
        depends = query.find_by_relation(self.sample_graph, "DEPENDS_ON")
        self.assertEqual(len(depends), 2)
        self.assertTrue(all(e.relation == "DEPENDS_ON" for e in depends))

    def test_find_matching_custom_predicate(self):
        result = query.find_matching(self.sample_graph, lambda n: n.confidence >= 1.0 and n.status == "active")
        self.assertEqual({n.id for n in result}, {"service.api", "service.worker"})

    def test_search_matches_id_name_tag_alias(self):
        self.assertEqual({n.id for n in query.search(self.sample_graph, "orders")}, {"db.orders"})
        self.assertEqual({n.id for n in query.search(self.sample_graph, "worker")}, {"service.worker"})
        self.assertEqual({n.id for n in query.search(self.sample_graph, "payments")}, {"service.api", "service.worker"})

    def test_search_empty_query_returns_nothing(self):
        self.assertEqual(query.search(self.sample_graph, ""), [])

    def test_edges_between(self):
        edges = query.edges_between(self.sample_graph, "service.api", "service.worker")
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].relation, "CALLS")

    def test_edges_between_no_connection(self):
        self.assertEqual(query.edges_between(self.sample_graph, "service.worker", "component.legacy"), [])

    def test_nodes_by_confidence(self):
        self.sample_graph.nodes["db.orders"].confidence = 0.4
        low = query.nodes_by_confidence(self.sample_graph, max_confidence=0.5)
        self.assertEqual({n.id for n in low}, {"db.orders"})


if __name__ == "__main__":
    unittest.main()
