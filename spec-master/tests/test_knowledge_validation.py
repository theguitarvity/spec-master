import tempfile
import unittest
from pathlib import Path

import _pathfix  # noqa: F401
from knowledge.validation import validate_manifest
from knowledge.manifest import KnowledgeManifest


class KnowledgeValidationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp_path = Path(tmp.name)

    def test_validate_manifest_clean(self):
        (self.tmp_path / "mod1.md").write_text("---\nid: mod1\ntype: Pattern\napplicable_roles:\n  - architect\ndepth:\n  architect: L3\n---\n")
        manifest = KnowledgeManifest(knowledge_root=self.tmp_path)
        res = validate_manifest(manifest)
        self.assertIs(res["valid"], True)
        self.assertEqual(len(res["issues"]), 0)

    def test_validate_manifest_invalid_type(self):
        (self.tmp_path / "mod1.md").write_text("---\nid: mod1\ntype: InvalidType\n---\n")
        manifest = KnowledgeManifest(knowledge_root=self.tmp_path)
        res = validate_manifest(manifest)
        self.assertIs(res["valid"], False)
        self.assertTrue(any("unknown type" in i["issue"] for i in res["issues"]))

    def test_validate_manifest_invalid_depth(self):
        (self.tmp_path / "mod1.md").write_text("---\nid: mod1\ntype: Pattern\ndepth:\n  architect: L9\n---\n")
        manifest = KnowledgeManifest(knowledge_root=self.tmp_path)
        res = validate_manifest(manifest)
        self.assertIs(res["valid"], False)
        self.assertTrue(any("invalid depth" in i["issue"] for i in res["issues"]))

    def test_validate_manifest_unknown_role_in_depth(self):
        (self.tmp_path / "mod1.md").write_text("---\nid: mod1\ntype: Pattern\ndepth:\n  unknown: L3\n---\n")
        manifest = KnowledgeManifest(knowledge_root=self.tmp_path)
        res = validate_manifest(manifest)
        self.assertIs(res["valid"], False)
        self.assertTrue(any("unknown role" in i["issue"] for i in res["issues"]))

    def test_validate_manifest_unknown_applicable_role(self):
        (self.tmp_path / "mod1.md").write_text("---\nid: mod1\ntype: Pattern\napplicable_roles:\n  - unknown_role\n---\n")
        manifest = KnowledgeManifest(knowledge_root=self.tmp_path)
        res = validate_manifest(manifest)
        self.assertIs(res["valid"], False)
        self.assertTrue(any("unknown applicable_role" in i["issue"] for i in res["issues"]))


if __name__ == "__main__":
    unittest.main()
