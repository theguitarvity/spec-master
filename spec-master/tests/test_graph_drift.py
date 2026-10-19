import tempfile
import unittest
from pathlib import Path

import _pathfix  # noqa: F401
from graph.model import Graph, GraphNode, GraphEdge
from graph import drift


def _node(id_, **kwargs):
    return GraphNode(id=id_, type=kwargs.pop("type", "Component"),
                     name=kwargs.pop("name", id_), **kwargs)


class GraphDriftTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp_path = Path(tmp.name)

    def test_diff_graphs_detects_added_and_removed_nodes(self):
        old = Graph()
        old.add_node(_node("a"))
        old.add_node(_node("b"))
        new = Graph()
        new.add_node(_node("a"))
        new.add_node(_node("c"))

        diff = drift.diff_graphs(old, new)
        self.assertEqual(diff["added_nodes"], ["c"])
        self.assertEqual(diff["removed_nodes"], ["b"])

    def test_diff_graphs_detects_changed_status(self):
        old = Graph()
        old.add_node(_node("a", status="active"))
        new = Graph()
        new.add_node(_node("a", status="deprecated"))

        diff = drift.diff_graphs(old, new)
        self.assertEqual(diff["changed_nodes"], [{
            "id": "a", "old_status": "active", "new_status": "deprecated",
            "old_type": "Component", "new_type": "Component",
        }])

    def test_diff_graphs_detects_added_and_removed_edges(self):
        old = Graph()
        old.add_node(_node("a"))
        old.add_node(_node("b"))
        old.add_edge(GraphEdge(source="a", relation="DEPENDS_ON", target="b"))
        new = Graph()
        new.add_node(_node("a"))
        new.add_node(_node("b"))
        new.add_edge(GraphEdge(source="a", relation="CALLS", target="b"))

        diff = drift.diff_graphs(old, new)
        self.assertEqual(diff["removed_edges"], [{"source": "a", "relation": "DEPENDS_ON", "target": "b"}])
        self.assertEqual(diff["added_edges"], [{"source": "a", "relation": "CALLS", "target": "b"}])

    def test_detect_structural_drift_flags_high_provenance_removal(self):
        old = Graph()
        old.add_node(_node("a"))
        old.add_node(_node("b"))
        old.add_edge(GraphEdge(source="a", relation="DEPENDS_ON", target="b", provenance="EXPLICIT"))
        new = Graph()
        new.add_node(_node("a"))
        new.add_node(_node("b"))

        report = drift.detect_structural_drift(old, new)
        self.assertIs(report["has_drift"], True)
        self.assertEqual(len(report["drifted_removed_edges"]), 1)

    def test_detect_structural_drift_ignores_low_provenance_removal(self):
        old = Graph()
        old.add_node(_node("a"))
        old.add_node(_node("b"))
        old.add_edge(GraphEdge(source="a", relation="DEPENDS_ON", target="b", provenance="UNRESOLVED"))
        new = Graph()
        new.add_node(_node("a"))
        new.add_node(_node("b"))

        report = drift.detect_structural_drift(old, new)
        self.assertIs(report["has_drift"], False)

    def test_detect_structural_drift_flags_removed_explicit_node(self):
        old = Graph()
        old.add_node(_node("a", source="EXPLICIT"))
        new = Graph()

        report = drift.detect_structural_drift(old, new)
        self.assertIs(report["has_drift"], True)
        self.assertEqual(report["drifted_removed_nodes"], ["a"])

    def test_detect_structural_drift_writes_event(self):
        old = Graph()
        old.add_node(_node("a", source="EXPLICIT"))
        new = Graph()

        events_path = self.tmp_path / "events.jsonl"
        drift.detect_structural_drift(old, new, events_path=str(events_path))

        from graph.events import read_events
        events = read_events(events_path)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "ARCHITECTURE_DRIFT_DETECTED")

    def test_detect_temporal_drift_flags_stale_and_unverified(self):
        from graph import temporal

        old_ts = {"timestamp": "2000-01-01T00:00:00+00:00"}
        g = Graph()
        g.add_node(_node("stale", last_verified=old_ts))
        g.add_node(_node("fresh", last_verified=temporal.make_last_verified()))
        g.add_node(_node("never_verified"))

        report = drift.detect_temporal_drift(g, max_age_days=30)
        self.assertEqual(report["stale_nodes"], ["stale"])
        self.assertEqual(report["unverified_nodes"], ["never_verified"])
        self.assertNotIn("fresh", report["stale_nodes"])


if __name__ == "__main__":
    unittest.main()
