import tempfile
import unittest
from pathlib import Path

import _pathfix  # noqa: F401
from knowledge.model import KnowledgeModule


class KnowledgeModuleTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp_path = Path(tmp.name)

    def test_from_file_valid(self):
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
        p = self.tmp_path / "hexagonal.md"
        p.write_text(md_content)

        mod = KnowledgeModule.from_file(p)
        self.assertIsNotNone(mod)
        self.assertEqual(mod.id, "architecture.hexagonal")
        self.assertEqual(mod.type, "Pattern")
        self.assertEqual(mod.name, "Hexagonal Architecture")
        self.assertEqual(mod.category, "architecture")
        self.assertIn("architect", mod.applicable_roles)
        self.assertIn("architecture", mod.tags)
        self.assertEqual(mod.depth["architect"], "L4")
        self.assertIn("architecture.clean", mod.related)
        self.assertIn("Hexagonal Architecture", mod.content)

    def test_from_file_no_id(self):
        md_content = """---
type: Pattern
---
"""
        p = self.tmp_path / "no_id.md"
        p.write_text(md_content)
        self.assertIsNone(KnowledgeModule.from_file(p))

    def test_is_applicable_to(self):
        mod = KnowledgeModule(id="test", type="Pattern", name="T", category="T", applicable_roles=["architect"])
        self.assertIs(mod.is_applicable_to("architect"), True)
        self.assertIs(mod.is_applicable_to("backend-dev"), False)

    def test_is_applicable_to_empty(self):
        mod = KnowledgeModule(id="test", type="Pattern", name="T", category="T", applicable_roles=[])
        self.assertIs(mod.is_applicable_to("architect"), True)
        self.assertIs(mod.is_applicable_to("unknown"), True)

    def test_depth_for_role(self):
        mod = KnowledgeModule(id="test", type="Pattern", name="T", category="T", depth={"architect": "L4"})
        self.assertEqual(mod.depth_for_role("architect"), "L4")
        self.assertEqual(mod.depth_for_role("tech-lead"), "L0")

    def test_to_dict(self):
        mod = KnowledgeModule(id="test", type="Pattern", name="T", category="T")
        d = mod.to_dict()
        self.assertEqual(d["id"], "test")
        self.assertEqual(d["type"], "Pattern")
        self.assertEqual(d["name"], "T")
        self.assertEqual(d["category"], "T")


if __name__ == "__main__":
    unittest.main()
