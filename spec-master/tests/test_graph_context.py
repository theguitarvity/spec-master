import tempfile
import unittest
from pathlib import Path

import _pathfix  # noqa: F401
from graph.model import Graph, GraphNode, GraphEdge
from graph.context import build_agent_context
from knowledge.manifest import KnowledgeManifest


def _knowledge_manifest(tmp_path):
    (tmp_path / "a.md").write_text(
        "---\nid: principle.a\ntype: Principle\ncategory: architecture\n"
        "applicable_roles:\n  - architect\ntags:\n  - scaling\n---\n"
        "content about scaling"
    )
    (tmp_path / "b.md").write_text(
        "---\nid: principle.b\ntype: Principle\ncategory: foundations\n"
        "applicable_roles:\n  - backend-dev\ntags:\n  - testing\n---\n"
        "content about testing"
    )
    return KnowledgeManifest(knowledge_root=tmp_path)


def _sample_graph():
    g = Graph()
    g.add_node(GraphNode(id="service.api", type="Service", name="API Service", tags=["payments"]))
    g.add_node(GraphNode(id="db.orders", type="Database", name="Orders DB", tags=["storage"]))
    g.add_node(GraphNode(id="service.worker", type="Service", name="Worker", tags=["payments"]))
    g.add_edge(GraphEdge(source="service.api", relation="DEPENDS_ON", target="db.orders"))
    return g


class AgentContextTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp_path = Path(tmp.name)
        self.sample_graph = _sample_graph()

    def test_build_agent_context_with_focus_node(self):
        manifest = _knowledge_manifest(self.tmp_path)
        ctx = build_agent_context("architect", self.sample_graph, manifest,
                                  focus_node_id="service.api", node_depth=1)
        node_ids = {n["id"] for n in ctx["graph_nodes"]}
        self.assertIn("service.api", node_ids)
        self.assertIn("db.orders", node_ids)
        self.assertEqual(ctx["role"], "architect")
        self.assertEqual(ctx["focus_node_id"], "service.api")

    def test_build_agent_context_includes_knowledge_modules(self):
        manifest = _knowledge_manifest(self.tmp_path)
        ctx = build_agent_context("architect", self.sample_graph, manifest)
        module_ids = {m["id"] for m in ctx["knowledge_modules"]}
        self.assertIn("principle.a", module_ids)
        self.assertNotIn("principle.b", module_ids)  # not applicable to architect

    def test_build_agent_context_keyword_search_without_focus_node(self):
        manifest = _knowledge_manifest(self.tmp_path)
        ctx = build_agent_context("architect", self.sample_graph, manifest, keywords=["payments"])
        node_ids = {n["id"] for n in ctx["graph_nodes"]}
        self.assertEqual(node_ids, {"service.api", "service.worker"})

    def test_build_agent_context_respects_node_budget(self):
        manifest = _knowledge_manifest(self.tmp_path)
        ctx = build_agent_context("architect", self.sample_graph, manifest,
                                  focus_node_id="service.api", node_depth=2, node_budget=1)
        self.assertEqual(len(ctx["graph_nodes"]), 1)
        self.assertEqual(ctx["budget"]["node_budget"], 1)

    def test_build_agent_context_respects_module_budget(self):
        manifest = _knowledge_manifest(self.tmp_path)
        ctx = build_agent_context("architect", self.sample_graph, manifest, module_budget=0)
        self.assertEqual(ctx["knowledge_modules"], [])
        self.assertEqual(ctx["budget"]["module_budget"], 0)

    def test_build_agent_context_empty_graph_and_manifest_is_valid(self):
        empty_graph = Graph()
        manifest = KnowledgeManifest(knowledge_root=self.tmp_path)
        ctx = build_agent_context("architect", empty_graph, manifest)
        self.assertEqual(ctx["graph_nodes"], [])
        self.assertEqual(ctx["knowledge_modules"], [])
        self.assertEqual(ctx["budget"]["node_count"], 0)


if __name__ == "__main__":
    unittest.main()
