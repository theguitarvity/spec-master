import unittest

import _pathfix  # noqa: F401
from graph.model import GraphNode, GraphEdge, Graph
from graph.validation import (
    find_orphan_nodes, find_broken_links, find_duplicate_aliases,
    find_unknown_entity_types, find_unknown_relation_types,
    find_invalid_provenance, find_low_confidence_edges,
    validate_graph
)


class GraphValidationTests(unittest.TestCase):
    def test_find_orphan_nodes(self):
        g = Graph()
        g.add_node(GraphNode(id="a", type="Component", name="A"))
        g.add_node(GraphNode(id="b", type="Component", name="B"))
        g.add_edge(GraphEdge(source="b", relation="CALLS", target="c"))

        orphans = find_orphan_nodes(g)
        self.assertIn("a", orphans)
        self.assertNotIn("b", orphans)
        self.assertNotIn("c", orphans)

    def test_find_broken_links(self):
        g = Graph()
        g.add_node(GraphNode(id="a", type="Component", name="A"))
        g.add_edge(GraphEdge(source="a", relation="CALLS", target="b"))

        broken = find_broken_links(g)
        self.assertEqual(len(broken), 1)
        self.assertEqual(broken[0]["missing_ids"], ["b"])

    def test_find_duplicate_aliases(self):
        g = Graph()
        g.add_node(GraphNode(id="a", type="Component", name="A", aliases=["shared"]))
        g.add_node(GraphNode(id="b", type="Component", name="B", aliases=["shared"]))

        dupes = find_duplicate_aliases(g)
        self.assertEqual(len(dupes), 1)
        self.assertEqual(dupes[0]["alias"], "shared")
        self.assertEqual(set(dupes[0]["nodes"]), {"a", "b"})

    def test_find_unknown_entity_types(self):
        g = Graph()
        g.add_node(GraphNode(id="a", type="InvalidType", name="A"))

        unknowns = find_unknown_entity_types(g)
        self.assertEqual(len(unknowns), 1)
        self.assertEqual(unknowns[0]["type"], "InvalidType")

    def test_find_unknown_relation_types(self):
        g = Graph()
        g.add_node(GraphNode(id="a", type="Component", name="A"))
        g.add_edge(GraphEdge(source="a", relation="INVALID_REL", target="b"))

        unknowns = find_unknown_relation_types(g)
        self.assertEqual(len(unknowns), 1)
        self.assertEqual(unknowns[0]["relation"], "INVALID_REL")

    def test_find_invalid_provenance(self):
        g = Graph()
        g.add_node(GraphNode(id="a", type="Component", name="A", source="BAD_PROV"))

        issues = find_invalid_provenance(g)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["provenance"], "BAD_PROV")

    def test_find_low_confidence_edges(self):
        g = Graph()
        g.add_edge(GraphEdge(source="a", relation="CALLS", target="b", confidence=0.2))

        low = find_low_confidence_edges(g, 0.5)
        self.assertEqual(len(low), 1)
        self.assertEqual(low[0]["confidence"], 0.2)

    def test_validate_graph(self):
        g = Graph()
        g.add_node(GraphNode(id="a", type="Component", name="A", source="EXPLICIT"))
        g.add_node(GraphNode(id="b", type="Component", name="B", source="EXPLICIT"))
        g.add_edge(GraphEdge(source="a", relation="CALLS", target="b", provenance="EXPLICIT", confidence=1.0))

        report = validate_graph(g)
        self.assertIs(report["valid"], True)
        self.assertEqual(report["total_issues"], 0)


if __name__ == "__main__":
    unittest.main()
