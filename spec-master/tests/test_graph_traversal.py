import pytest
import _pathfix

from graph.model import Graph, GraphNode, GraphEdge
from graph import traversal


@pytest.fixture
def chain_graph():
    # a -> b -> c -> d, plus an unrelated island node e
    g = Graph()
    for nid in ("a", "b", "c", "d", "e"):
        g.add_node(GraphNode(id=nid, type="Component", name=nid.upper()))
    g.add_edge(GraphEdge(source="a", relation="DEPENDS_ON", target="b"))
    g.add_edge(GraphEdge(source="b", relation="DEPENDS_ON", target="c"))
    g.add_edge(GraphEdge(source="c", relation="DEPENDS_ON", target="d"))
    return g


def test_bfs_outgoing_respects_max_depth(chain_graph):
    reached = traversal.bfs(chain_graph, "a", max_depth=2, direction="out")
    assert reached == {"b": 1, "c": 2}


def test_bfs_unknown_start_returns_empty(chain_graph):
    assert traversal.bfs(chain_graph, "nonexistent") == {}


def test_bfs_island_node_returns_empty(chain_graph):
    assert traversal.bfs(chain_graph, "e", max_depth=3) == {}


def test_descendants_full_closure(chain_graph):
    assert traversal.descendants(chain_graph, "a") == {"b", "c", "d"}


def test_ancestors_full_closure(chain_graph):
    assert traversal.ancestors(chain_graph, "d") == {"a", "b", "c"}


def test_blast_radius_is_incoming_closure(chain_graph):
    # If "c" changes, everything that (transitively) depends on it — a, b —
    # is affected. "d" is not, since d is downstream of c, not upstream.
    affected = traversal.blast_radius(chain_graph, "c", max_depth=5)
    assert set(affected) == {"a", "b"}


def test_blast_radius_bounded_by_depth(chain_graph):
    affected = traversal.blast_radius(chain_graph, "d", max_depth=1)
    assert affected == ["c"]


def test_shortest_path_found(chain_graph):
    path = traversal.shortest_path(chain_graph, "a", "d")
    assert path == ["a", "b", "c", "d"]


def test_shortest_path_same_node(chain_graph):
    assert traversal.shortest_path(chain_graph, "b", "b") == ["b"]


def test_shortest_path_unreachable_within_depth(chain_graph):
    assert traversal.shortest_path(chain_graph, "a", "d", max_depth=1) is None


def test_shortest_path_disconnected_island(chain_graph):
    assert traversal.shortest_path(chain_graph, "a", "e") is None


def test_shortest_path_unknown_node(chain_graph):
    assert traversal.shortest_path(chain_graph, "a", "nonexistent") is None


def test_bfs_handles_cycles_without_infinite_loop():
    g = Graph()
    for nid in ("x", "y", "z"):
        g.add_node(GraphNode(id=nid, type="Component", name=nid))
    g.add_edge(GraphEdge(source="x", relation="RELATED_TO", target="y"))
    g.add_edge(GraphEdge(source="y", relation="RELATED_TO", target="z"))
    g.add_edge(GraphEdge(source="z", relation="RELATED_TO", target="x"))  # cycle
    reached = traversal.bfs(g, "x", max_depth=10, direction="both")
    assert set(reached) == {"y", "z"}
