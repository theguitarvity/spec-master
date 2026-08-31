import pytest
import _pathfix

from knowledge.model import KnowledgeModule

def test_from_file_valid(tmp_path):
    md_content = """---
id: architecture.hexagonal
type: Pattern
name: Hexagonal Architecture
category: architecture
applicable_roles:
  - architect
  - tech-lead
tags:
  - architecture
depth:
  architect: L4
  tech-lead: L3
---

# Hexagonal Architecture

- [[architecture.clean]]
- [[architecture.onion]]
"""
    p = tmp_path / "hexagonal.md"
    p.write_text(md_content)
    
    mod = KnowledgeModule.from_file(p)
    assert mod is not None
    assert mod.id == "architecture.hexagonal"
    assert mod.type == "Pattern"
    assert mod.name == "Hexagonal Architecture"
    assert mod.category == "architecture"
    assert "architect" in mod.applicable_roles
    assert "architecture" in mod.tags
    assert mod.depth["architect"] == "L4"
    assert "architecture.clean" in mod.related
    assert "Hexagonal Architecture" in mod.content

def test_from_file_no_id(tmp_path):
    md_content = """---
type: Pattern
---
"""
    p = tmp_path / "no_id.md"
    p.write_text(md_content)
    assert KnowledgeModule.from_file(p) is None

def test_is_applicable_to():
    mod = KnowledgeModule(id="test", type="Pattern", name="T", category="T", applicable_roles=["architect"])
    assert mod.is_applicable_to("architect") is True
    assert mod.is_applicable_to("backend-dev") is False

def test_is_applicable_to_empty():
    mod = KnowledgeModule(id="test", type="Pattern", name="T", category="T", applicable_roles=[])
    assert mod.is_applicable_to("architect") is True
    assert mod.is_applicable_to("unknown") is True

def test_depth_for_role():
    mod = KnowledgeModule(id="test", type="Pattern", name="T", category="T", depth={"architect": "L4"})
    assert mod.depth_for_role("architect") == "L4"
    assert mod.depth_for_role("tech-lead") == "L0"

def test_to_dict():
    mod = KnowledgeModule(id="test", type="Pattern", name="T", category="T")
    d = mod.to_dict()
    assert d["id"] == "test"
    assert d["type"] == "Pattern"
    assert d["name"] == "T"
    assert d["category"] == "T"
