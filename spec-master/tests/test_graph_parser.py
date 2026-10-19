import unittest
import shutil
import tempfile
from pathlib import Path
import _pathfix
from graph.parser import parse_frontmatter, extract_wikilinks, wikilinks_to_edges, parse_node_file
from graph.model import GraphEdge


class GraphParserTests(unittest.TestCase):
    def _tmp_path(self):
        path = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        return path

    def test_parse_frontmatter_valid(self):
        text = "---\nid: a\ntype: Component\n---\nHello"
        fm, body = parse_frontmatter(text)
        assert fm["id"] == "a"
        assert fm["type"] == "Component"
        assert body.strip() == "Hello"

    def test_parse_frontmatter_none(self):
        text = "Hello\nWorld"
        fm, body = parse_frontmatter(text)
        assert fm == {}
        assert body == "Hello\nWorld"

    def test_extract_wikilinks(self):
        text = "Here is [[target]] and [[target2|label]]."
        links = extract_wikilinks(text)
        assert set(links) == {"target", "target2"}

    def test_wikilinks_to_edges(self):
        text = "Link to [[b]] and [[c]]."
        edges = wikilinks_to_edges("a", text)
        assert len(edges) == 2
        assert edges[0].source == "a"
        assert edges[0].relation == "RELATED_TO"
        assert edges[0].target == "b"
        assert edges[1].target == "c"

    def test_parse_node_file(self):
        tmp_path = self._tmp_path()
        f = tmp_path / "a.md"
        f.write_text("---\nid: a\ntype: Component\n---\nBody", encoding="utf-8")

        node = parse_node_file(f)
        assert node is not None
        assert node.id == "a"
        assert node.type == "Component"
        assert node.content.strip() == "Body"

    def test_parse_node_file_no_id(self):
        tmp_path = self._tmp_path()
        f = tmp_path / "a.md"
        f.write_text("---\ntype: Component\n---\nBody", encoding="utf-8")

        node = parse_node_file(f)
        assert node is None

    def test_simple_yaml_fallback_reads_inline_json_written_by_store(self):
        from graph.parser import _parse_simple_yaml
        fm = _parse_simple_yaml('id: decision.x\nfirst_seen: {"run": "r1", "at": "2026-09-26"}\ntags: ["a", "b"]\nname: "{curly}"')
        assert fm["first_seen"] == {"run": "r1", "at": "2026-09-26"}
        assert fm["tags"] == ["a", "b"]
        assert fm["name"] == "{curly}"


if __name__ == "__main__":
    unittest.main()
