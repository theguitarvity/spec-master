import unittest

import _pathfix  # noqa: F401
from graph.model import Graph, GraphNode, GraphEdge
import traceability


def _traced_graph():
    g = Graph()
    g.add_node(GraphNode(id="req.checkout", type="Requirement",
                         name="User can check out", source="EXPLICIT"))
    g.add_node(GraphNode(id="feature.checkout", type="Feature", name="Checkout Flow"))
    g.add_node(GraphNode(id="task.checkout-api", type="Task", name="Build checkout API"))
    g.add_node(GraphNode(id="test.checkout-e2e", type="Test", name="checkout_e2e_test"))
    g.add_edge(GraphEdge(source="req.checkout", relation="SATISFIES", target="feature.checkout"))
    g.add_edge(GraphEdge(source="task.checkout-api", relation="IMPLEMENTS", target="req.checkout"))
    g.add_edge(GraphEdge(source="req.checkout", relation="TESTED_BY", target="test.checkout-e2e"))
    return g


class TraceabilityGraphTests(unittest.TestCase):
    def setUp(self):
        self.traced_graph = _traced_graph()

    def test_existing_add_row_and_render_still_work(self):
        # Additive change must not break the original, already-tested API.
        state = {}
        traceability.add_row(state, {"requirement": "R1", "status": "traced"})
        text = traceability.render(state)
        self.assertIn("R1", text)
        self.assertIn("traced", text)

    def test_row_from_requirement_node(self):
        row = traceability.row_from_requirement_node(self.traced_graph, "req.checkout")
        self.assertEqual(row["requirement"], "User can check out")
        self.assertEqual(row["source"], "EXPLICIT")
        self.assertEqual(row["feature"], "Checkout Flow")
        self.assertEqual(row["task"], "Build checkout API")
        self.assertEqual(row["test"], "checkout_e2e_test")
        self.assertEqual(row["status"], "traced")

    def test_row_from_requirement_node_untraced_without_tests(self):
        g = Graph()
        g.add_node(GraphNode(id="req.x", type="Requirement", name="Some requirement"))
        row = traceability.row_from_requirement_node(g, "req.x")
        self.assertEqual(row["test"], "")
        self.assertEqual(row["status"], "untraced")

    def test_row_from_requirement_node_unknown_id_returns_empty(self):
        self.assertEqual(traceability.row_from_requirement_node(Graph(), "nonexistent"), {})

    def test_rows_from_graph_only_includes_requirement_nodes(self):
        rows = traceability.rows_from_graph(self.traced_graph)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["requirement"], "User can check out")

    def test_rows_from_graph_empty_graph(self):
        self.assertEqual(traceability.rows_from_graph(Graph()), [])

    def test_sync_from_graph_adds_new_rows(self):
        state = {}
        added = traceability.sync_from_graph(state, self.traced_graph)
        self.assertEqual(len(added), 1)
        self.assertEqual(len(state["traceability"]), 1)
        self.assertEqual(state["traceability"][0]["requirement"], "User can check out")

    def test_sync_from_graph_is_idempotent(self):
        state = {}
        traceability.sync_from_graph(state, self.traced_graph)
        added_second_time = traceability.sync_from_graph(state, self.traced_graph)
        self.assertEqual(added_second_time, [])
        self.assertEqual(len(state["traceability"]), 1)

    def test_sync_from_graph_preserves_manually_added_rows(self):
        state = {}
        traceability.add_row(state, {"requirement": "Manually tracked requirement"})
        traceability.sync_from_graph(state, self.traced_graph)
        requirements = {row["requirement"] for row in state["traceability"]}
        self.assertIn("Manually tracked requirement", requirements)
        self.assertIn("User can check out", requirements)
        self.assertEqual(len(state["traceability"]), 2)

    def test_sync_from_graph_result_renders_correctly(self):
        state = {}
        traceability.sync_from_graph(state, self.traced_graph)
        text = traceability.render(state)
        self.assertIn("User can check out", text)
        self.assertIn("Checkout Flow", text)
        self.assertIn("checkout_e2e_test", text)


if __name__ == "__main__":
    unittest.main()
