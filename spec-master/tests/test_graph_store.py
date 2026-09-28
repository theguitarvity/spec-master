import json
import tempfile
import unittest
from pathlib import Path

import _pathfix  # noqa: F401
from graph.events import read_events
from graph.model import GraphNode, GraphEdge
from graph.store import InMemoryGraphStore, FileGraphStore, graph_from_dict


class GraphStoreTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp_path = Path(tmp.name)

    def test_in_memory_store(self):
        store = InMemoryGraphStore()
        node = GraphNode(id="a", type="Component", name="A")
        store.save_node(node)

        edge = GraphEdge(source="a", relation="CALLS", target="b")
        store.save_edge(edge)

        self.assertEqual(store.get_node("a").name, "A")
        self.assertEqual(len(store.all_nodes()), 1)
        self.assertEqual(len(store.all_edges()), 1)

        loaded = store.load()
        self.assertEqual(len(loaded.nodes), 1)

    def test_file_store_save_node(self):
        store = FileGraphStore(project_root=self.tmp_path, knowledge_subdir="knowledge")
        node = GraphNode(id="component.a", type="Component", name="A")
        store.save_node(node)

        p = self.tmp_path / "knowledge/graph/component/component.a.md"
        self.assertTrue(p.exists())
        content = p.read_text(encoding="utf-8")
        self.assertIn("id: component.a", content)

    def test_file_store_load(self):
        store = FileGraphStore(project_root=self.tmp_path, knowledge_subdir="knowledge")
        node = GraphNode(id="component.a", type="Component", name="A", content="Hello [[component.b]]")
        store.save_node(node)

        store2 = FileGraphStore(project_root=self.tmp_path, knowledge_subdir="knowledge")
        g = store2.load()

        self.assertIn("component.a", g.nodes)
        edges = g.edges
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].target, "component.b")
        self.assertEqual(edges[0].relation, "RELATED_TO")

    def test_file_store_save_edge(self):
        store = FileGraphStore(project_root=self.tmp_path, knowledge_subdir="knowledge")
        node1 = GraphNode(id="a", type="Component", name="A")
        node2 = GraphNode(id="b", type="Component", name="B")
        store.save_node(node1)
        store.save_node(node2)

        edge = GraphEdge(source="a", relation="CALLS", target="b")
        store.save_edge(edge)

        manifest_p = self.tmp_path / "knowledge/graph-manifest.json"
        self.assertTrue(manifest_p.exists())
        manifest = json.loads(manifest_p.read_text(encoding="utf-8"))

        self.assertEqual(len(manifest["edges"]), 1)
        self.assertEqual(manifest["edges"][0]["relation"], "CALLS")

    def test_file_store_rebuild_manifest(self):
        store = FileGraphStore(project_root=self.tmp_path, knowledge_subdir="knowledge")
        store.save_node(GraphNode(id="a", type="Component", name="A"))

        stats = store.rebuild_manifest()
        self.assertEqual(stats["total_nodes"], 1)

        manifest_p = self.tmp_path / "knowledge/graph-manifest.json"
        manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
        self.assertEqual(manifest["total_nodes"], 1)

    def test_file_store_snapshot_round_trips_graph(self):
        store = FileGraphStore(project_root=self.tmp_path, knowledge_subdir="knowledge")
        store.save_node(GraphNode(id="a", type="Component", name="A"))
        store.save_node(GraphNode(id="b", type="Component", name="B"))
        store.save_edge(GraphEdge(source="a", relation="DEPENDS_ON", target="b"))

        result = store.snapshot("baseline")
        snapshot = json.loads((self.tmp_path / "knowledge/snapshots/baseline.json").read_text(encoding="utf-8"))
        graph = graph_from_dict(snapshot)

        self.assertEqual(result["total_nodes"], 2)
        self.assertIn("a", graph.nodes)
        self.assertEqual(graph.edges[0].relation, "DEPENDS_ON")


class FileGraphStoreExistingGraphTests(unittest.TestCase):
    """Saving into a store that already holds a graph builds on that graph."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp_path = Path(tmp.name)
        self.manifest_path = self.tmp_path / "knowledge/graph-manifest.json"
        self.events_path = self.tmp_path / "knowledge/graph-events.jsonl"

    def _store(self):
        # A new instance each call, the way every CLI run opens the store afresh.
        return FileGraphStore(project_root=self.tmp_path, knowledge_subdir="knowledge")

    def test_first_save_node_keeps_the_nodes_and_typed_edges_already_stored(self):
        seed = self._store()
        seed.save_node(GraphNode(id="decision.d1", type="Decision", name="D1"))
        seed.save_node(GraphNode(id="agent.architect", type="Agent", name="architect agent"))
        seed.save_node(GraphNode(id="feature.billing", type="Feature", name="Billing"))
        seed.save_edge(GraphEdge(source="decision.d1", relation="DECIDED_BY", target="agent.architect"))
        seed.save_edge(GraphEdge(source="decision.d1", relation="INFLUENCES", target="feature.billing"))

        self._store().save_node(GraphNode(id="artifact.readme", type="Artifact", name="README"))

        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual({n["id"] for n in manifest["nodes"]},
                         {"decision.d1", "agent.architect", "feature.billing", "artifact.readme"})
        self.assertEqual(sorted((e["source"], e["relation"], e["target"]) for e in manifest["edges"]),
                         [("decision.d1", "DECIDED_BY", "agent.architect"),
                          ("decision.d1", "INFLUENCES", "feature.billing")])
        self.assertEqual(len(self._store().load().edges), 2)

    def test_resaving_an_unchanged_node_or_edge_logs_nothing_and_adds_no_duplicate(self):
        store = self._store()
        store.save_node(GraphNode(id="component.a", type="Component", name="A"))
        store.save_node(GraphNode(id="component.b", type="Component", name="B"))
        store.save_edge(GraphEdge(source="component.a", relation="DEPENDS_ON", target="component.b"))
        events = read_events(self.events_path)
        manifest = self.manifest_path.read_text(encoding="utf-8")

        store.save_edge(GraphEdge(source="component.a", relation="DEPENDS_ON", target="component.b"))
        fresh = self._store()
        fresh.save_node(GraphNode(id="component.a", type="Component", name="A"))
        fresh.save_edge(GraphEdge(source="component.a", relation="DEPENDS_ON", target="component.b"))

        self.assertEqual(read_events(self.events_path), events)
        self.assertEqual(self.manifest_path.read_text(encoding="utf-8"), manifest)
        self.assertEqual(len(self._store().load().edges), 1)

    def test_a_changed_node_or_edge_is_updated_in_place_with_one_event_each(self):
        store = self._store()
        store.save_node(GraphNode(id="component.a", type="Component", name="A"))
        store.save_node(GraphNode(id="component.b", type="Component", name="B"))
        store.save_edge(GraphEdge(source="component.a", relation="DEPENDS_ON", target="component.b",
                                  confidence=0.6))
        logged = len(read_events(self.events_path))

        fresh = self._store()
        fresh.save_node(GraphNode(id="component.a", type="Component", name="A", status="deprecated"))
        fresh.save_edge(GraphEdge(source="component.a", relation="DEPENDS_ON", target="component.b",
                                  confidence=0.9))

        self.assertEqual([e["event"] for e in read_events(self.events_path)[logged:]],
                         ["NODE_UPDATED", "EDGE_UPDATED"])
        graph = self._store().load()
        self.assertEqual(graph.nodes["component.a"].status, "deprecated")
        self.assertEqual([(e.relation, e.confidence) for e in graph.edges], [("DEPENDS_ON", 0.9)])


if __name__ == "__main__":
    unittest.main()
