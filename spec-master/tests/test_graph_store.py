import pytest
import json
import _pathfix
from graph.model import GraphNode, GraphEdge
from graph.store import InMemoryGraphStore, FileGraphStore

def test_in_memory_store():
    store = InMemoryGraphStore()
    node = GraphNode(id="a", type="Component", name="A")
    store.save_node(node)
    
    edge = GraphEdge(source="a", relation="CALLS", target="b")
    store.save_edge(edge)
    
    assert store.get_node("a").name == "A"
    assert len(store.all_nodes()) == 1
    assert len(store.all_edges()) == 1
    
    loaded = store.load()
    assert len(loaded.nodes) == 1

def test_file_store_save_node(tmp_path):
    store = FileGraphStore(project_root=tmp_path, knowledge_subdir="knowledge")
    node = GraphNode(id="component.a", type="Component", name="A")
    store.save_node(node)
    
    p = tmp_path / "knowledge/graph/component/component.a.md"
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    assert "id: component.a" in content

def test_file_store_load(tmp_path):
    store = FileGraphStore(project_root=tmp_path, knowledge_subdir="knowledge")
    node = GraphNode(id="component.a", type="Component", name="A", content="Hello [[component.b]]")
    store.save_node(node)
    
    store2 = FileGraphStore(project_root=tmp_path, knowledge_subdir="knowledge")
    g = store2.load()
    
    assert "component.a" in g.nodes
    edges = g.edges
    assert len(edges) == 1
    assert edges[0].target == "component.b"
    assert edges[0].relation == "RELATED_TO"

def test_file_store_save_edge(tmp_path):
    store = FileGraphStore(project_root=tmp_path, knowledge_subdir="knowledge")
    node1 = GraphNode(id="a", type="Component", name="A")
    node2 = GraphNode(id="b", type="Component", name="B")
    store.save_node(node1)
    store.save_node(node2)
    
    edge = GraphEdge(source="a", relation="CALLS", target="b")
    store.save_edge(edge)
    
    manifest_p = tmp_path / "knowledge/graph-manifest.json"
    assert manifest_p.exists()
    manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
    
    assert len(manifest["edges"]) == 1
    assert manifest["edges"][0]["relation"] == "CALLS"

def test_file_store_rebuild_manifest(tmp_path):
    store = FileGraphStore(project_root=tmp_path, knowledge_subdir="knowledge")
    store.save_node(GraphNode(id="a", type="Component", name="A"))
    
    stats = store.rebuild_manifest()
    assert stats["total_nodes"] == 1
    
    manifest_p = tmp_path / "knowledge/graph-manifest.json"
    manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
    assert manifest["total_nodes"] == 1
