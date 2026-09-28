import tempfile
import unittest
from pathlib import Path

import _pathfix  # noqa: F401
from graph.parser import parse_frontmatter, extract_wikilinks, wikilinks_to_edges, parse_node_file
from graph.model import GraphEdge


class GraphParserTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp_path = Path(tmp.name)

    def test_parse_frontmatter_valid(self):
        text = "---\nid: a\ntype: Component\n---\nHello"
        fm, body = parse_frontmatter(text)
        self.assertEqual(fm["id"], "a")
        self.assertEqual(fm["type"], "Component")
        self.assertEqual(body.strip(), "Hello")

    def test_parse_frontmatter_none(self):
        text = "Hello\nWorld"
        fm, body = parse_frontmatter(text)
        self.assertEqual(fm, {})
        self.assertEqual(body, "Hello\nWorld")

    def test_extract_wikilinks(self):
        text = "Here is [[target]] and [[target2|label]]."
        links = extract_wikilinks(text)
        self.assertEqual(set(links), {"target", "target2"})

    def test_wikilinks_to_edges(self):
        text = "Link to [[b]] and [[c]]."
        edges = wikilinks_to_edges("a", text)
        self.assertEqual(len(edges), 2)
        self.assertEqual(edges[0].source, "a")
        self.assertEqual(edges[0].relation, "RELATED_TO")
        self.assertEqual(edges[0].target, "b")
        self.assertEqual(edges[1].target, "c")

    def test_parse_node_file(self):
        f = self.tmp_path / "a.md"
        f.write_text("---\nid: a\ntype: Component\n---\nBody", encoding="utf-8")

        node = parse_node_file(f)
        self.assertIsNotNone(node)
        self.assertEqual(node.id, "a")
        self.assertEqual(node.type, "Component")
        self.assertEqual(node.content.strip(), "Body")

    def test_parse_node_file_no_id(self):
        f = self.tmp_path / "a.md"
        f.write_text("---\ntype: Component\n---\nBody", encoding="utf-8")

        node = parse_node_file(f)
        self.assertIsNone(node)

    def test_simple_yaml_fallback_reads_inline_json_written_by_store(self):
        from graph.parser import _parse_simple_yaml
        fm = _parse_simple_yaml('id: decision.x\nfirst_seen: {"run": "r1", "at": "2026-09-26"}\ntags: ["a", "b"]\nname: "{curly}"')
        self.assertEqual(fm["first_seen"], {"run": "r1", "at": "2026-09-26"})
        self.assertEqual(fm["tags"], ["a", "b"])
        self.assertEqual(fm["name"], "{curly}")


if __name__ == "__main__":
    unittest.main()
