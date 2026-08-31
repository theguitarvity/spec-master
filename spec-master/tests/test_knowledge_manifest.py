import pytest
import _pathfix

from knowledge.manifest import KnowledgeManifest
from knowledge.model import KnowledgeModule

def test_manifest_empty_dir(tmp_path):
    manifest = KnowledgeManifest(knowledge_root=tmp_path)
    assert len(manifest.all_modules()) == 0

def test_manifest_loads_modules(tmp_path):
    (tmp_path / "mod1.md").write_text("---\nid: mod1\ntype: Pattern\ncategory: test\napplicable_roles:\n  - role1\ntags:\n  - tag1\n---\nbody")
    (tmp_path / "mod2.md").write_text("---\nid: mod2\ntype: Principle\ncategory: other\napplicable_roles:\n  - role2\ntags:\n  - tag2\n---\nbody")
    
    manifest = KnowledgeManifest(knowledge_root=tmp_path)
    modules = manifest.all_modules()
    assert len(modules) == 2
    assert manifest.get("mod1").type == "Pattern"
    
    assert len(manifest.by_role("role1")) == 1
    assert len(manifest.by_tag("tag1")) == 1
    assert len(manifest.by_category("other")) == 1
    assert len(manifest.by_ids(["mod1", "mod2"])) == 2
    
    search_res = manifest.search("mod1")
    assert len(search_res) == 1
    
    stats = manifest.stats()
    assert stats["total_modules"] == 2
    assert stats["by_category"]["test"] == 1
    assert stats["by_type"]["Principle"] == 1

def test_manifest_skips_maps(tmp_path):
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    (maps_dir / "map.md").write_text("---\nid: map1\n---\n")
    (tmp_path / "mod.md").write_text("---\nid: mod1\n---\n")
    
    manifest = KnowledgeManifest(knowledge_root=tmp_path)
    assert len(manifest.all_modules()) == 1
