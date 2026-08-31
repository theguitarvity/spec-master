import pytest
import _pathfix
from graph.model import GraphNode, GraphEdge, Graph
from graph.validation import (
    find_orphan_nodes, find_broken_links, find_duplicate_aliases,
    find_unknown_entity_types, find_unknown_relation_types,
    find_invalid_provenance, find_low_confidence_edges,
    validate_graph
)

def test_find_orphan_nodes():
    g = Graph()
    g.add_node(GraphNode(id="a", type="Component", name="A"))
    g.add_node(GraphNode(id="b", type="Component", name="B"))
    g.add_edge(GraphEdge(source="b", relation="CALLS", target="c"))
    
    orphans = find_orphan_nodes(g)
    assert "a" in orphans
    assert "b" not in orphans
    assert "c" not in orphans

def test_find_broken_links():
    g = Graph()
    g.add_node(GraphNode(id="a", type="Component", name="A"))
    g.add_edge(GraphEdge(source="a", relation="CALLS", target="b"))
    
    broken = find_broken_links(g)
    assert len(broken) == 1
    assert broken[0]["missing_ids"] == ["b"]

def test_find_duplicate_aliases():
    g = Graph()
    g.add_node(GraphNode(id="a", type="Component", name="A", aliases=["shared"]))
    g.add_node(GraphNode(id="b", type="Component", name="B", aliases=["shared"]))
    
    dupes = find_duplicate_aliases(g)
    assert len(dupes) == 1
    assert dupes[0]["alias"] == "shared"
    assert set(dupes[0]["nodes"]) == {"a", "b"}

def test_find_unknown_entity_types():
    g = Graph()
    g.add_node(GraphNode(id="a", type="InvalidType", name="A"))
    
    unknowns = find_unknown_entity_types(g)
    assert len(unknowns) == 1
    assert unknowns[0]["type"] == "InvalidType"

def test_find_unknown_relation_types():
    g = Graph()
    g.add_node(GraphNode(id="a", type="Component", name="A"))
    g.add_edge(GraphEdge(source="a", relation="INVALID_REL", target="b"))
    
    unknowns = find_unknown_relation_types(g)
    assert len(unknowns) == 1
    assert unknowns[0]["relation"] == "INVALID_REL"

def test_find_invalid_provenance():
    g = Graph()
    g.add_node(GraphNode(id="a", type="Component", name="A", source="BAD_PROV"))
    
    issues = find_invalid_provenance(g)
    assert len(issues) == 1
    assert issues[0]["provenance"] == "BAD_PROV"

def test_find_low_confidence_edges():
    g = Graph()
    g.add_edge(GraphEdge(source="a", relation="CALLS", target="b", confidence=0.2))
    
    low = find_low_confidence_edges(g, 0.5)
    assert len(low) == 1
    assert low[0]["confidence"] == 0.2

def test_validate_graph():
    g = Graph()
    g.add_node(GraphNode(id="a", type="Component", name="A", source="EXPLICIT"))
    g.add_node(GraphNode(id="b", type="Component", name="B", source="EXPLICIT"))
    g.add_edge(GraphEdge(source="a", relation="CALLS", target="b", provenance="EXPLICIT", confidence=1.0))
    
    report = validate_graph(g)
    assert report["valid"] is True
    assert report["total_issues"] == 0
