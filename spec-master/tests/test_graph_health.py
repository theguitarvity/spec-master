import pytest
import _pathfix

from graph.model import Graph, GraphNode, GraphEdge
from graph import health as graph_health


def test_compute_health_perfect_graph_scores_100():
    g = Graph()
    g.add_node(GraphNode(id="a", type="Component", name="A"))
    g.add_node(GraphNode(id="b", type="Component", name="B"))
    g.add_edge(GraphEdge(source="a", relation="DEPENDS_ON", target="b", provenance="EXPLICIT"))

    report = graph_health.compute_health(g)
    assert report["score"] == 100
    assert report["grade"] == "A"
    assert report["validation"]["valid"] is True


def test_compute_health_deducts_for_broken_wikilinks():
    g = Graph()
    g.add_node(GraphNode(id="a", type="Component", name="A"))
    g.add_edge(GraphEdge(source="a", relation="DEPENDS_ON", target="missing"))

    report = graph_health.compute_health(g)
    assert report["score"] < 100
    assert "broken_wikilinks" in report["deductions"]


def test_compute_health_deducts_for_stale_nodes():
    old_ts = {"timestamp": "2000-01-01T00:00:00+00:00"}
    g = Graph()
    g.add_node(GraphNode(id="a", type="Component", name="A", last_verified=old_ts))

    report = graph_health.compute_health(g, max_age_days=30)
    assert report["score"] < 100
    assert "stale_nodes" in report["deductions"]
    assert report["temporal_drift"]["stale_nodes"] == ["a"]


def test_compute_health_score_never_negative():
    g = Graph()
    for i in range(50):
        g.add_node(GraphNode(id=f"n{i}", type="Component", name=f"N{i}"))
        g.add_edge(GraphEdge(source=f"n{i}", relation="DEPENDS_ON", target="missing"))

    report = graph_health.compute_health(g)
    assert report["score"] >= 0


def test_compute_health_empty_graph():
    report = graph_health.compute_health(Graph())
    assert report["score"] == 100
    assert report["total_nodes"] == 0


def test_render_health_report_contains_score_and_grade():
    g = Graph()
    g.add_node(GraphNode(id="a", type="Component", name="A"))
    g.add_node(GraphNode(id="b", type="Component", name="B"))
    g.add_edge(GraphEdge(source="a", relation="DEPENDS_ON", target="b", provenance="EXPLICIT"))
    report = graph_health.compute_health(g)
    md = graph_health.render_health_report(report)
    assert "Score:" in md
    assert "100/100" in md
    assert "grade A" in md


def test_render_health_report_lists_issues_when_present():
    g = Graph()
    g.add_node(GraphNode(id="a", type="Component", name="A"))
    g.add_edge(GraphEdge(source="a", relation="DEPENDS_ON", target="missing"))
    report = graph_health.compute_health(g)
    md = graph_health.render_health_report(report)
    assert "broken wikilinks" in md


def test_record_stale_nodes_writes_events(tmp_path):
    old_ts = {"timestamp": "2000-01-01T00:00:00+00:00"}
    g = Graph()
    g.add_node(GraphNode(id="a", type="Component", name="A", last_verified=old_ts))

    events_path = tmp_path / "events.jsonl"
    stale = graph_health.record_stale_nodes(g, str(events_path), max_age_days=30)
    assert stale == ["a"]

    from graph.events import read_events
    events = read_events(events_path)
    assert len(events) == 1
    assert events[0]["event"] == "STALE_NODE_DETECTED"
    assert events[0]["node_id"] == "a"
