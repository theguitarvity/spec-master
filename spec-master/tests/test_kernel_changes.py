import json
import os
import shutil
import subprocess
import tempfile
import unittest

import _pathfix  # noqa: F401
import kernel_fixtures as fx
from kernel import changes


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.root = fx.make_repo()

    def tearDown(self):
        fx.remove(self.root)

    def test_ids_are_dated_sequenced_and_safe(self):
        first = changes.new_id(self.root, "Fix the SUM of strings!", today="2026-09-28T10:00:00Z")
        self.assertEqual(first, "c20260928-001-fix-the-sum-of-strings")
        changes.save(self.root, {"id": first, "status": "RUNNING"})
        self.assertTrue(changes.new_id(self.root, "again", today="2026-09-28").startswith("c20260928-002-"))
        self.assertEqual(changes.slug("!!!"), "change")
        for bad in ("../escape", "a/b", "", None):
            with self.subTest(bad=bad):
                with self.assertRaises(changes.ChangeError):
                    changes.record_path(self.root, bad)

    def test_save_load_active_and_log(self):
        changes.save(self.root, {"id": "c1", "status": "RUNNING"})
        self.assertEqual(changes.load(self.root, "c1")["status"], "RUNNING")
        self.assertIn("updated_at", changes.load(self.root, "c1"))
        with self.assertRaises(changes.ChangeError):
            changes.load(self.root, "c2")
        self.assertIsNone(changes.active(self.root))
        changes.set_active(self.root, "c1")
        self.assertEqual(changes.active(self.root)["id"], "c1")
        changes.set_active(self.root, None)
        self.assertIsNone(changes.active_id(self.root))
        changes.set_active(self.root, None)  # clearing twice is fine
        changes.append_log(self.root, {"id": "c1", "status": "PASSED"})
        with open(os.path.join(changes.changes_dir(self.root), changes.LOG), encoding="utf-8") as fh:
            self.assertEqual(json.loads(fh.read())["id"], "c1")
        self.assertEqual(changes.note_relpath("c1"), ".spec-master/changes/c1.md")


class GitBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.root = fx.make_repo()

    def tearDown(self):
        fx.remove(self.root)

    def base(self):
        dirty = {p: changes.file_digest(self.root, p) for p in changes.dirty_paths(self.root)}
        return {"commit": changes.head(self.root), "dirty": dirty}

    def test_changed_since_ignores_junk_and_untouched_pre_existing_work(self):
        fx.write(self.root, "notes/wip.txt", "the user's own work\n")
        fx.write(self.root, "notes/edited.txt", "draft\n")
        base = self.base()
        fx.write(self.root, "src/calc.py", fx.CALC + "\n# changed\n")
        fx.write(self.root, "notes/edited.txt", "draft, edited during the change\n")
        fx.write(self.root, "src/__pycache__/calc.cpython-312.pyc", "junk")
        fx.write(self.root, "src/new.py", "X = 1\n")
        self.assertEqual(changes.changed_since(self.root, base), ["notes/edited.txt", "src/calc.py", "src/new.py"])

    def test_diff_loc_counts_tracked_and_untracked_lines(self):
        base = self.base()
        fx.write(self.root, "src/calc.py", fx.CALC + "\n\ndef sub(a, b):\n    return a - b\n")
        fx.write(self.root, "src/new.py", "A = 1\nB = 2\nC = 3\n")
        self.assertEqual(changes.diff_loc(self.root, base, ["src/calc.py"]), 4)
        self.assertEqual(changes.diff_loc(self.root, base, ["src/calc.py", "src/new.py"]), 7)
        self.assertEqual(changes.diff_loc(self.root, base, []), 0)

    def test_repository_probes(self):
        self.assertTrue(changes.is_git_repo(self.root))
        self.assertEqual(len(changes.head(self.root)), 40)
        outside = tempfile.mkdtemp()
        try:
            self.assertFalse(changes.is_git_repo(outside))
            self.assertIsNone(changes.head(outside))
            self.assertEqual(changes.dirty_paths(outside), [])
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_porcelain_renames_report_only_the_destination(self):
        def runner(argv, **kwargs):
            out = "R  new/name.py\0old/name.py\0 M src/calc.py\0?? tests/test_new.py\0"
            return subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")
        self.assertEqual(changes.dirty_paths(self.root, runner=runner),
                         ["new/name.py", "src/calc.py", "tests/test_new.py"])

    def test_git_failures_never_raise(self):
        def runner(argv, **kwargs):
            raise OSError("git not installed")
        self.assertEqual(changes.git(self.root, "status", runner=runner), (1, "git not installed"))
        self.assertFalse(changes.is_git_repo(self.root, runner=runner))


class JunkTests(unittest.TestCase):
    def test_build_and_cache_artifacts(self):
        for path in ("src/__pycache__/a.cpython-312.pyc", "a.pyc", "node_modules/x/index.js",
                     "pkg.egg-info/PKG-INFO", ".pytest_cache/v/cache"):
            with self.subTest(path=path):
                self.assertTrue(changes.is_junk(path))
        for path in ("src/calc.py", "docs/node_modules.md", "src/pycache.py"):
            with self.subTest(path=path):
                self.assertFalse(changes.is_junk(path))


if __name__ == "__main__":
    unittest.main()
