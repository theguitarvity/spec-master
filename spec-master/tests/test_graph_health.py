import tempfile
import unittest
from pathlib import Path

import _pathfix  # noqa: F401
from graph.model import Graph, GraphNode, GraphEdge
from graph import health as graph_health


class GraphHealthTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp_path = Path(tmp.name)

    def test_compute_health_perfect_graph_scores_100(self):
        g = Graph()
        g.add_node(GraphNode(id="a", type="Component", name="A"))
        g.add_node(GraphNode(id="b", type="Component", name="B"))
        g.add_edge(GraphEdge(source="a", relation="DEPENDS_ON", target="b", provenance="EXPLICIT"))

        report = graph_health.compute_health(g)
        self.assertEqual(report["score"], 100)
        self.assertEqual(report["grade"], "A")
        self.assertIs(report["validation"]["valid"], True)

    def test_compute_health_deducts_for_broken_wikilinks(self):
        g = Graph()
        g.add_node(GraphNode(id="a", type="Component", name="A"))
        g.add_edge(GraphEdge(source="a", relation="DEPENDS_ON", target="missing"))

        report = graph_health.compute_health(g)
        self.assertLess(report["score"], 100)
        self.assertIn("broken_wikilinks", report["deductions"])

    def test_compute_health_deducts_for_stale_nodes(self):
        old_ts = {"timestamp": "2000-01-01T00:00:00+00:00"}
        g = Graph()
        g.add_node(GraphNode(id="a", type="Component", name="A", last_verified=old_ts))

        report = graph_health.compute_health(g, max_age_days=30)
        self.assertLess(report["score"], 100)
        self.assertIn("stale_nodes", report["deductions"])
        self.assertEqual(report["temporal_drift"]["stale_nodes"], ["a"])

    def test_compute_health_score_never_negative(self):
        g = Graph()
        for i in range(50):
            g.add_node(GraphNode(id=f"n{i}", type="Component", name=f"N{i}"))
            g.add_edge(GraphEdge(source=f"n{i}", relation="DEPENDS_ON", target="missing"))

        report = graph_health.compute_health(g)
        self.assertGreaterEqual(report["score"], 0)

    def test_compute_health_empty_graph(self):
        report = graph_health.compute_health(Graph())
        self.assertEqual(report["score"], 100)
        self.assertEqual(report["total_nodes"], 0)

    def test_render_health_report_contains_score_and_grade(self):
        g = Graph()
        g.add_node(GraphNode(id="a", type="Component", name="A"))
        g.add_node(GraphNode(id="b", type="Component", name="B"))
        g.add_edge(GraphEdge(source="a", relation="DEPENDS_ON", target="b", provenance="EXPLICIT"))
        report = graph_health.compute_health(g)
        md = graph_health.render_health_report(report)
        self.assertIn("Score:", md)
        self.assertIn("100/100", md)
        self.assertIn("grade A", md)

    def test_render_health_report_lists_issues_when_present(self):
        g = Graph()
        g.add_node(GraphNode(id="a", type="Component", name="A"))
        g.add_edge(GraphEdge(source="a", relation="DEPENDS_ON", target="missing"))
        report = graph_health.compute_health(g)
        md = graph_health.render_health_report(report)
        self.assertIn("broken wikilinks", md)

    def test_record_stale_nodes_writes_events(self):
        old_ts = {"timestamp": "2000-01-01T00:00:00+00:00"}
        g = Graph()
        g.add_node(GraphNode(id="a", type="Component", name="A", last_verified=old_ts))

        events_path = self.tmp_path / "events.jsonl"
        stale = graph_health.record_stale_nodes(g, str(events_path), max_age_days=30)
        self.assertEqual(stale, ["a"])

        from graph.events import read_events
        events = read_events(events_path)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "STALE_NODE_DETECTED")
        self.assertEqual(events[0]["node_id"], "a")


if __name__ == "__main__":
    unittest.main()
