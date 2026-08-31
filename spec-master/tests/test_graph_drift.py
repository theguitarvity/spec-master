import pytest
import _pathfix

from graph.model import Graph, GraphNode, GraphEdge
from graph import drift


def _node(id_, **kwargs):
    return GraphNode(id=id_, type=kwargs.pop("type", "Component"),
                      name=kwargs.pop("name", id_), **kwargs)


def test_diff_graphs_detects_added_and_removed_nodes():
    old = Graph()
    old.add_node(_node("a"))
    old.add_node(_node("b"))
    new = Graph()
    new.add_node(_node("a"))
    new.add_node(_node("c"))

    diff = drift.diff_graphs(old, new)
    assert diff["added_nodes"] == ["c"]
    assert diff["removed_nodes"] == ["b"]


def test_diff_graphs_detects_changed_status():
    old = Graph()
    old.add_node(_node("a", status="active"))
    new = Graph()
    new.add_node(_node("a", status="deprecated"))

    diff = drift.diff_graphs(old, new)
    assert diff["changed_nodes"] == [{
        "id": "a", "old_status": "active", "new_status": "deprecated",
        "old_type": "Component", "new_type": "Component",
    }]


def test_diff_graphs_detects_added_and_removed_edges():
    old = Graph()
    old.add_node(_node("a"))
    old.add_node(_node("b"))
    old.add_edge(GraphEdge(source="a", relation="DEPENDS_ON", target="b"))
    new = Graph()
    new.add_node(_node("a"))
    new.add_node(_node("b"))
    new.add_edge(GraphEdge(source="a", relation="CALLS", target="b"))

    diff = drift.diff_graphs(old, new)
    assert diff["removed_edges"] == [{"source": "a", "relation": "DEPENDS_ON", "target": "b"}]
    assert diff["added_edges"] == [{"source": "a", "relation": "CALLS", "target": "b"}]


def test_detect_structural_drift_flags_high_provenance_removal():
    old = Graph()
    old.add_node(_node("a"))
    old.add_node(_node("b"))
    old.add_edge(GraphEdge(source="a", relation="DEPENDS_ON", target="b", provenance="EXPLICIT"))
    new = Graph()
    new.add_node(_node("a"))
    new.add_node(_node("b"))

    report = drift.detect_structural_drift(old, new)
    assert report["has_drift"] is True
    assert len(report["drifted_removed_edges"]) == 1


def test_detect_structural_drift_ignores_low_provenance_removal():
    old = Graph()
    old.add_node(_node("a"))
    old.add_node(_node("b"))
    old.add_edge(GraphEdge(source="a", relation="DEPENDS_ON", target="b", provenance="UNRESOLVED"))
    new = Graph()
    new.add_node(_node("a"))
    new.add_node(_node("b"))

    report = drift.detect_structural_drift(old, new)
    assert report["has_drift"] is False


def test_detect_structural_drift_flags_removed_explicit_node():
    old = Graph()
    old.add_node(_node("a", source="EXPLICIT"))
    new = Graph()

    report = drift.detect_structural_drift(old, new)
    assert report["has_drift"] is True
    assert report["drifted_removed_nodes"] == ["a"]


def test_detect_structural_drift_writes_event(tmp_path):
    old = Graph()
    old.add_node(_node("a", source="EXPLICIT"))
    new = Graph()

    events_path = tmp_path / "events.jsonl"
    drift.detect_structural_drift(old, new, events_path=str(events_path))

    from graph.events import read_events
    events = read_events(events_path)
    assert len(events) == 1
    assert events[0]["event"] == "ARCHITECTURE_DRIFT_DETECTED"


def test_detect_temporal_drift_flags_stale_and_unverified():
    from graph import temporal

    old_ts = {"timestamp": "2000-01-01T00:00:00+00:00"}
    g = Graph()
    g.add_node(_node("stale", last_verified=old_ts))
    g.add_node(_node("fresh", last_verified=temporal.make_last_verified()))
    g.add_node(_node("never_verified"))

    report = drift.detect_temporal_drift(g, max_age_days=30)
    assert report["stale_nodes"] == ["stale"]
    assert report["unverified_nodes"] == ["never_verified"]
    assert "fresh" not in report["stale_nodes"]
