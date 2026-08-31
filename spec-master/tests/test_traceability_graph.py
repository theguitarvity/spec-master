import pytest
import _pathfix

from graph.model import Graph, GraphNode, GraphEdge
import traceability


@pytest.fixture
def traced_graph():
    g = Graph()
    g.add_node(GraphNode(id="req.checkout", type="Requirement",
                          name="User can check out", source="EXPLICIT"))
    g.add_node(GraphNode(id="feature.checkout", type="Feature", name="Checkout Flow"))
    g.add_node(GraphNode(id="task.checkout-api", type="Task", name="Build checkout API"))
    g.add_node(GraphNode(id="test.checkout-e2e", type="Test", name="checkout_e2e_test"))
    g.add_edge(GraphEdge(source="req.checkout", relation="SATISFIES", target="feature.checkout"))
    g.add_edge(GraphEdge(source="task.checkout-api", relation="IMPLEMENTS", target="req.checkout"))
    g.add_edge(GraphEdge(source="req.checkout", relation="TESTED_BY", target="test.checkout-e2e"))
    return g


def test_existing_add_row_and_render_still_work():
    # Additive change must not break the original, already-tested API.
    state = {}
    traceability.add_row(state, {"requirement": "R1", "status": "traced"})
    text = traceability.render(state)
    assert "R1" in text
    assert "traced" in text


def test_row_from_requirement_node(traced_graph):
    row = traceability.row_from_requirement_node(traced_graph, "req.checkout")
    assert row["requirement"] == "User can check out"
    assert row["source"] == "EXPLICIT"
    assert row["feature"] == "Checkout Flow"
    assert row["task"] == "Build checkout API"
    assert row["test"] == "checkout_e2e_test"
    assert row["status"] == "traced"


def test_row_from_requirement_node_untraced_without_tests():
    g = Graph()
    g.add_node(GraphNode(id="req.x", type="Requirement", name="Some requirement"))
    row = traceability.row_from_requirement_node(g, "req.x")
    assert row["test"] == ""
    assert row["status"] == "untraced"


def test_row_from_requirement_node_unknown_id_returns_empty():
    assert traceability.row_from_requirement_node(Graph(), "nonexistent") == {}


def test_rows_from_graph_only_includes_requirement_nodes(traced_graph):
    rows = traceability.rows_from_graph(traced_graph)
    assert len(rows) == 1
    assert rows[0]["requirement"] == "User can check out"


def test_rows_from_graph_empty_graph():
    assert traceability.rows_from_graph(Graph()) == []


def test_sync_from_graph_adds_new_rows(traced_graph):
    state = {}
    added = traceability.sync_from_graph(state, traced_graph)
    assert len(added) == 1
    assert len(state["traceability"]) == 1
    assert state["traceability"][0]["requirement"] == "User can check out"


def test_sync_from_graph_is_idempotent(traced_graph):
    state = {}
    traceability.sync_from_graph(state, traced_graph)
    added_second_time = traceability.sync_from_graph(state, traced_graph)
    assert added_second_time == []
    assert len(state["traceability"]) == 1


def test_sync_from_graph_preserves_manually_added_rows(traced_graph):
    state = {}
    traceability.add_row(state, {"requirement": "Manually tracked requirement"})
    traceability.sync_from_graph(state, traced_graph)
    requirements = {row["requirement"] for row in state["traceability"]}
    assert "Manually tracked requirement" in requirements
    assert "User can check out" in requirements
    assert len(state["traceability"]) == 2


def test_sync_from_graph_result_renders_correctly(traced_graph):
    state = {}
    traceability.sync_from_graph(state, traced_graph)
    text = traceability.render(state)
    assert "User can check out" in text
    assert "Checkout Flow" in text
    assert "checkout_e2e_test" in text
