import pytest
import _pathfix
from graph.parser import parse_frontmatter, extract_wikilinks, wikilinks_to_edges, parse_node_file
from graph.model import GraphEdge

def test_parse_frontmatter_valid():
    text = "---\nid: a\ntype: Component\n---\nHello"
    fm, body = parse_frontmatter(text)
    assert fm["id"] == "a"
    assert fm["type"] == "Component"
    assert body.strip() == "Hello"

def test_parse_frontmatter_none():
    text = "Hello\nWorld"
    fm, body = parse_frontmatter(text)
    assert fm == {}
    assert body == "Hello\nWorld"

def test_extract_wikilinks():
    text = "Here is [[target]] and [[target2|label]]."
    links = extract_wikilinks(text)
    assert set(links) == {"target", "target2"}

def test_wikilinks_to_edges():
    text = "Link to [[b]] and [[c]]."
    edges = wikilinks_to_edges("a", text)
    assert len(edges) == 2
    assert edges[0].source == "a"
    assert edges[0].relation == "RELATED_TO"
    assert edges[0].target == "b"
    assert edges[1].target == "c"

def test_parse_node_file(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("---\nid: a\ntype: Component\n---\nBody", encoding="utf-8")
    
    node = parse_node_file(f)
    assert node is not None
    assert node.id == "a"
    assert node.type == "Component"
    assert node.content.strip() == "Body"

def test_parse_node_file_no_id(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("---\ntype: Component\n---\nBody", encoding="utf-8")
    
    node = parse_node_file(f)
    assert node is None
