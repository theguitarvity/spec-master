from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import _pathfix  # noqa: F401
import adapters_gen  # noqa: E402


class AdapterGenerationTests(unittest.TestCase):
    def test_agy_generates_antigravity_custom_agent_not_codex_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            written = adapters_gen.generate(root, "spec-master", ["agy"], home=None)

            expected = root / ".agents" / "agents" / "spec-master" / "agent.md"
            codex_skill = root / ".agents" / "skills" / "spec-master" / "SKILL.md"
            self.assertEqual(written, [expected])
            self.assertTrue(expected.exists())
            self.assertFalse(codex_skill.exists())
            content = expected.read_text(encoding="utf-8")
            self.assertIn("Antigravity", content)
            self.assertIn("/agents", content)


if __name__ == "__main__":
    unittest.main()
