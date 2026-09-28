import tempfile
import unittest
from pathlib import Path

import _pathfix  # noqa: F401
from knowledge.manifest import KnowledgeManifest
from knowledge.model import KnowledgeModule


class KnowledgeManifestTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp_path = Path(tmp.name)

    def test_manifest_empty_dir(self):
        manifest = KnowledgeManifest(knowledge_root=self.tmp_path)
        self.assertEqual(len(manifest.all_modules()), 0)

    def test_manifest_loads_modules(self):
        (self.tmp_path / "mod1.md").write_text("---\nid: mod1\ntype: Pattern\ncategory: test\napplicable_roles:\n  - role1\ntags:\n  - tag1\n---\nbody")
        (self.tmp_path / "mod2.md").write_text("---\nid: mod2\ntype: Principle\ncategory: other\napplicable_roles:\n  - role2\ntags:\n  - tag2\n---\nbody")

        manifest = KnowledgeManifest(knowledge_root=self.tmp_path)
        modules = manifest.all_modules()
        self.assertEqual(len(modules), 2)
        self.assertEqual(manifest.get("mod1").type, "Pattern")

        self.assertEqual(len(manifest.by_role("role1")), 1)
        self.assertEqual(len(manifest.by_tag("tag1")), 1)
        self.assertEqual(len(manifest.by_category("other")), 1)
        self.assertEqual(len(manifest.by_ids(["mod1", "mod2"])), 2)

        search_res = manifest.search("mod1")
        self.assertEqual(len(search_res), 1)

        stats = manifest.stats()
        self.assertEqual(stats["total_modules"], 2)
        self.assertEqual(stats["by_category"]["test"], 1)
        self.assertEqual(stats["by_type"]["Principle"], 1)

    def test_manifest_skips_maps(self):
        maps_dir = self.tmp_path / "maps"
        maps_dir.mkdir()
        (maps_dir / "map.md").write_text("---\nid: map1\n---\n")
        (self.tmp_path / "mod.md").write_text("---\nid: mod1\n---\n")

        manifest = KnowledgeManifest(knowledge_root=self.tmp_path)
        self.assertEqual(len(manifest.all_modules()), 1)


if __name__ == "__main__":
    unittest.main()
