import pytest
import _pathfix

from graph.model import Graph, GraphNode, GraphEdge
from graph.traversal import blast_radius


@pytest.fixture
def service_graph():
    """A small service dependency graph:

    web -> api -> auth-lib
    worker -> api
    api -> db
    reporting -> db  (independent consumer of db, not of api)
    """
    g = Graph()
    for nid in ("web", "api", "auth-lib", "worker", "db", "reporting"):
        g.add_node(GraphNode(id=nid, type="Service", name=nid))
    g.add_edge(GraphEdge(source="web", relation="DEPENDS_ON", target="api"))
    g.add_edge(GraphEdge(source="api", relation="DEPENDS_ON", target="auth-lib"))
    g.add_edge(GraphEdge(source="worker", relation="DEPENDS_ON", target="api"))
    g.add_edge(GraphEdge(source="api", relation="DEPENDS_ON", target="db"))
    g.add_edge(GraphEdge(source="reporting", relation="DEPENDS_ON", target="db"))
    return g


def test_blast_radius_of_leaf_dependency_reaches_all_transitive_consumers(service_graph):
    # If auth-lib changes, both api and everything that depends on api
    # (web, worker) are affected.
    affected = blast_radius(service_graph, "auth-lib", max_depth=5)
    assert set(affected) == {"api", "web", "worker"}


def test_blast_radius_of_shared_dependency_covers_all_consumers(service_graph):
    # If db changes, api (and its dependents) AND reporting are affected —
    # two independent branches converging on the same node.
    affected = blast_radius(service_graph, "db", max_depth=5)
    assert set(affected) == {"api", "web", "worker", "reporting"}


def test_blast_radius_of_leaf_consumer_is_empty(service_graph):
    # Nothing depends on web — changing it affects no one else.
    assert blast_radius(service_graph, "web", max_depth=5) == []


def test_blast_radius_depth_limits_impact_analysis_scope(service_graph):
    # Only direct consumers of api within 1 hop: web and worker, not
    # anything further upstream (there is none here, but depth=1 should
    # still exclude nothing transitively deeper than 1 hop by construction).
    affected = blast_radius(service_graph, "api", max_depth=1)
    assert set(affected) == {"web", "worker"}


def test_blast_radius_ordered_by_distance_then_id(service_graph):
    affected = blast_radius(service_graph, "auth-lib", max_depth=5)
    # api is 1 hop from auth-lib; web and worker are 2 hops.
    assert affected[0] == "api"
    assert affected[1:] == ["web", "worker"]


def test_blast_radius_unknown_node_returns_empty(service_graph):
    assert blast_radius(service_graph, "does-not-exist") == []
