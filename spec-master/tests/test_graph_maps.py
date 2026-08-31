import pytest
import _pathfix

from graph.model import Graph, GraphNode, GraphEdge
from graph import maps


@pytest.fixture
def sample_graph():
    g = Graph()
    g.add_node(GraphNode(id="service.api", type="Service", name="API Service"))
    g.add_node(GraphNode(id="db.orders", type="Database", name="Orders DB", status="stale"))
    g.add_edge(GraphEdge(source="service.api", relation="DEPENDS_ON", target="db.orders"))
    return g


def test_render_system_map_empty_graph():
    text = maps.render_system_map(Graph())
    assert "System Map" in text
    assert "no nodes" in text


def test_render_system_map_groups_by_type(sample_graph):
    text = maps.render_system_map(sample_graph)
    assert "## Database" in text
    assert "## Service" in text
    assert "API Service" in text
    assert "DEPENDS_ON" in text
    assert "(stale)" in text


def test_render_node_map_unknown_node():
    text = maps.render_node_map(Graph(), "nonexistent")
    assert "not found" in text


def test_render_node_map_shows_neighborhood(sample_graph):
    text = maps.render_node_map(sample_graph, "service.api", depth=1)
    assert "Orders DB" in text
    assert "1 hop away" in text


def test_render_dependency_map_no_edges():
    text = maps.render_dependency_map(Graph())
    assert "no active DEPENDS_ON edges" in text


def test_render_dependency_map_lists_adjacency(sample_graph):
    text = maps.render_dependency_map(sample_graph)
    assert "API Service" in text
    assert "Orders DB" in text
