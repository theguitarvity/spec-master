import os
import shutil
import tempfile
import unittest

import _pathfix  # noqa: F401
import fingerprint


class FingerprintTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name, content):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path

    def test_hash_stable_for_same_content(self):
        p1 = self._write("app-features.md", "hello world")
        h1 = fingerprint.compute_file_hash(p1)
        h2 = fingerprint.compute_file_hash(p1)
        self.assertEqual(h1, h2)

    def test_hash_changes_with_content(self):
        p = self._write("app-features.md", "v1")
        h1 = fingerprint.compute_file_hash(p)
        self._write("app-features.md", "v2")
        h2 = fingerprint.compute_file_hash(p)
        self.assertNotEqual(h1, h2)

    def test_compare_detects_no_change(self):
        p = self._write("app-features.md", "v1")
        snapshot = fingerprint.compute([p])
        result = fingerprint.compare(snapshot, snapshot)
        self.assertEqual(result["changed"], [])
        self.assertEqual(result["stale_phases"], [])

    def test_compare_propagates_staleness_for_app_features(self):
        p = self._write("app-features.md", "v1")
        before = fingerprint.compute([p])
        self._write("app-features.md", "v2")
        after = fingerprint.compute([p])
        result = fingerprint.compare(before, after)
        self.assertEqual(result["changed"], ["app-features.md"])
        self.assertEqual(
            result["stale_phases"], ["specify", "clarify", "plan", "tasks", "analyze"]
        )

    def test_tech_stack_change_does_not_stale_specify(self):
        p = self._write("tech-stack.md", "v1")
        before = fingerprint.compute([p])
        self._write("tech-stack.md", "v2")
        after = fingerprint.compute([p])
        result = fingerprint.compare(before, after)
        self.assertNotIn("specify", result["stale_phases"])
        self.assertIn("plan", result["stale_phases"])

    def test_implement_never_auto_staled(self):
        p = self._write("app-features.md", "v1")
        before = fingerprint.compute([p])
        self._write("app-features.md", "v2")
        after = fingerprint.compute([p])
        result = fingerprint.compare(before, after)
        self.assertNotIn("implement", result["stale_phases"])


if __name__ == "__main__":
    unittest.main()
