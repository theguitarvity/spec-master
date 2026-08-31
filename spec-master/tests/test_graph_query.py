import pytest
import _pathfix

from graph.model import Graph, GraphNode, GraphEdge
from graph import query


@pytest.fixture
def sample_graph():
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


def test_find_by_type(sample_graph):
    services = query.find_by_type(sample_graph, "Service")
    assert {n.id for n in services} == {"service.api", "service.worker"}


def test_find_by_tag(sample_graph):
    tagged = query.find_by_tag(sample_graph, "payments")
    assert {n.id for n in tagged} == {"service.api", "service.worker"}


def test_find_by_status(sample_graph):
    stale = query.find_by_status(sample_graph, "stale")
    assert {n.id for n in stale} == {"db.orders"}


def test_find_by_relation(sample_graph):
    depends = query.find_by_relation(sample_graph, "DEPENDS_ON")
    assert len(depends) == 2
    assert all(e.relation == "DEPENDS_ON" for e in depends)


def test_find_matching_custom_predicate(sample_graph):
    result = query.find_matching(sample_graph, lambda n: n.confidence >= 1.0 and n.status == "active")
    assert {n.id for n in result} == {"service.api", "service.worker"}


def test_search_matches_id_name_tag_alias(sample_graph):
    assert {n.id for n in query.search(sample_graph, "orders")} == {"db.orders"}
    assert {n.id for n in query.search(sample_graph, "worker")} == {"service.worker"}
    assert {n.id for n in query.search(sample_graph, "payments")} == {"service.api", "service.worker"}


def test_search_empty_query_returns_nothing(sample_graph):
    assert query.search(sample_graph, "") == []


def test_edges_between(sample_graph):
    edges = query.edges_between(sample_graph, "service.api", "service.worker")
    assert len(edges) == 1
    assert edges[0].relation == "CALLS"


def test_edges_between_no_connection(sample_graph):
    assert query.edges_between(sample_graph, "service.worker", "component.legacy") == []


def test_nodes_by_confidence(sample_graph):
    sample_graph.nodes["db.orders"].confidence = 0.4
    low = query.nodes_by_confidence(sample_graph, max_confidence=0.5)
    assert {n.id for n in low} == {"db.orders"}
