import pytest
import _pathfix

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


@pytest.fixture
def sample_graph():
    g = Graph()
    g.add_node(GraphNode(id="service.api", type="Service", name="API Service", tags=["payments"]))
    g.add_node(GraphNode(id="db.orders", type="Database", name="Orders DB", tags=["storage"]))
    g.add_node(GraphNode(id="service.worker", type="Service", name="Worker", tags=["payments"]))
    g.add_edge(GraphEdge(source="service.api", relation="DEPENDS_ON", target="db.orders"))
    return g


def test_build_agent_context_with_focus_node(sample_graph, tmp_path):
    manifest = _knowledge_manifest(tmp_path)
    ctx = build_agent_context("architect", sample_graph, manifest,
                               focus_node_id="service.api", node_depth=1)
    node_ids = {n["id"] for n in ctx["graph_nodes"]}
    assert "service.api" in node_ids
    assert "db.orders" in node_ids
    assert ctx["role"] == "architect"
    assert ctx["focus_node_id"] == "service.api"


def test_build_agent_context_includes_knowledge_modules(sample_graph, tmp_path):
    manifest = _knowledge_manifest(tmp_path)
    ctx = build_agent_context("architect", sample_graph, manifest)
    module_ids = {m["id"] for m in ctx["knowledge_modules"]}
    assert "principle.a" in module_ids
    assert "principle.b" not in module_ids  # not applicable to architect


def test_build_agent_context_keyword_search_without_focus_node(sample_graph, tmp_path):
    manifest = _knowledge_manifest(tmp_path)
    ctx = build_agent_context("architect", sample_graph, manifest, keywords=["payments"])
    node_ids = {n["id"] for n in ctx["graph_nodes"]}
    assert node_ids == {"service.api", "service.worker"}


def test_build_agent_context_respects_node_budget(sample_graph, tmp_path):
    manifest = _knowledge_manifest(tmp_path)
    ctx = build_agent_context("architect", sample_graph, manifest,
                               focus_node_id="service.api", node_depth=2, node_budget=1)
    assert len(ctx["graph_nodes"]) == 1
    assert ctx["budget"]["node_budget"] == 1


def test_build_agent_context_respects_module_budget(sample_graph, tmp_path):
    manifest = _knowledge_manifest(tmp_path)
    ctx = build_agent_context("architect", sample_graph, manifest, module_budget=0)
    assert ctx["knowledge_modules"] == []
    assert ctx["budget"]["module_budget"] == 0


def test_build_agent_context_empty_graph_and_manifest_is_valid(tmp_path):
    empty_graph = Graph()
    manifest = KnowledgeManifest(knowledge_root=tmp_path)
    ctx = build_agent_context("architect", empty_graph, manifest)
    assert ctx["graph_nodes"] == []
    assert ctx["knowledge_modules"] == []
    assert ctx["budget"]["node_count"] == 0
