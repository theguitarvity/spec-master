import pytest
import _pathfix

from knowledge.validation import validate_manifest
from knowledge.manifest import KnowledgeManifest

def test_validate_manifest_clean(tmp_path):
    (tmp_path / "mod1.md").write_text("---\nid: mod1\ntype: Pattern\napplicable_roles:\n  - architect\ndepth:\n  architect: L3\n---\n")
    manifest = KnowledgeManifest(knowledge_root=tmp_path)
    res = validate_manifest(manifest)
    assert res["valid"] is True
    assert len(res["issues"]) == 0

def test_validate_manifest_invalid_type(tmp_path):
    (tmp_path / "mod1.md").write_text("---\nid: mod1\ntype: InvalidType\n---\n")
    manifest = KnowledgeManifest(knowledge_root=tmp_path)
    res = validate_manifest(manifest)
    assert res["valid"] is False
    assert any("unknown type" in i["issue"] for i in res["issues"])

def test_validate_manifest_invalid_depth(tmp_path):
    (tmp_path / "mod1.md").write_text("---\nid: mod1\ntype: Pattern\ndepth:\n  architect: L9\n---\n")
    manifest = KnowledgeManifest(knowledge_root=tmp_path)
    res = validate_manifest(manifest)
    assert res["valid"] is False
    assert any("invalid depth" in i["issue"] for i in res["issues"])

def test_validate_manifest_unknown_role_in_depth(tmp_path):
    (tmp_path / "mod1.md").write_text("---\nid: mod1\ntype: Pattern\ndepth:\n  unknown: L3\n---\n")
    manifest = KnowledgeManifest(knowledge_root=tmp_path)
    res = validate_manifest(manifest)
    assert res["valid"] is False
    assert any("unknown role" in i["issue"] for i in res["issues"])

def test_validate_manifest_unknown_applicable_role(tmp_path):
    (tmp_path / "mod1.md").write_text("---\nid: mod1\ntype: Pattern\napplicable_roles:\n  - unknown_role\n---\n")
    manifest = KnowledgeManifest(knowledge_root=tmp_path)
    res = validate_manifest(manifest)
    assert res["valid"] is False
    assert any("unknown applicable_role" in i["issue"] for i in res["issues"])
