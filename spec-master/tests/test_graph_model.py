import pytest
import _pathfix
from graph.model import GraphNode, GraphEdge, Graph

def test_graphnode_roundtrip():
    node = GraphNode(id="component.test", type="Component", name="Test Component")
    d = node.to_dict()
    assert d["id"] == "component.test"
    assert d["type"] == "Component"
    assert d["name"] == "Test Component"
    
    node2 = GraphNode.from_dict(d)
    assert node2.id == "component.test"
    assert node2.type == "Component"
    assert node2.name == "Test Component"

def test_graphedge_roundtrip():
    edge = GraphEdge(source="component.a", relation="DEPENDS_ON", target="component.b")
    d = edge.to_dict()
    assert d["source"] == "component.a"
    assert d["relation"] == "DEPENDS_ON"
    assert d["target"] == "component.b"
    
    edge2 = GraphEdge.from_dict(d)
    assert edge2.source == "component.a"
    assert edge2.relation == "DEPENDS_ON"
    assert edge2.target == "component.b"

def test_graph_add_get_node():
    g = Graph()
    node = GraphNode(id="a", type="Component", name="A")
    g.add_node(node)
    
    fetched = g.get_node("a")
    assert fetched is not None
    assert fetched.name == "A"
    assert g.get_node("b") is None

def test_graph_neighbors():
    g = Graph()
    g.add_node(GraphNode(id="a", type="Component", name="A"))
    g.add_node(GraphNode(id="b", type="Component", name="B"))
    g.add_node(GraphNode(id="c", type="Component", name="C"))
    
    g.add_edge(GraphEdge(source="a", relation="CALLS", target="b"))
    g.add_edge(GraphEdge(source="b", relation="CALLS", target="c"))
    g.add_edge(GraphEdge(source="c", relation="DEPENDS_ON", target="a"))
    
    # test directions
    out_a = g.neighbors("a", direction="out")
    assert len(out_a) == 1
    assert out_a[0].target == "b"
    
    in_a = g.neighbors("a", direction="in")
    assert len(in_a) == 1
    assert in_a[0].source == "c"
    
    both_a = g.neighbors("a", direction="both")
    assert len(both_a) == 2
    
    # test relation filter
    filtered = g.neighbors("b", relations=["DEPENDS_ON"], direction="both")
    assert len(filtered) == 0

def test_graph_stats():
    g = Graph()
    g.add_node(GraphNode(id="a", type="Component", name="A"))
    g.add_node(GraphNode(id="b", type="Service", name="B"))
    g.add_edge(GraphEdge(source="a", relation="CALLS", target="b"))
    
    stats = g.stats()
    assert stats["total_nodes"] == 2
    assert stats["total_edges"] == 1
    assert stats["nodes_by_type"]["Component"] == 1
    assert stats["nodes_by_type"]["Service"] == 1
