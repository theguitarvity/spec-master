import json
import os
import tempfile
import unittest

import _pathfix  # noqa: F401
import dispatch_scope
from kernel import hookd, policy


def _marker(root, owned, read_only=False):
    os.makedirs(os.path.join(root, ".spec-master"), exist_ok=True)
    with open(os.path.join(root, ".spec-master", "worktree.json"), "w", encoding="utf-8") as fh:
        json.dump({"agent_key": "F:T1:sm-implement", "role": "sm-review" if read_only else "sm-implement",
                   "owned_paths": owned, "read_only": read_only}, fh)


class GuardTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def test_no_marker_means_no_opinion(self):
        self.assertIsNone(dispatch_scope.guard(self.root, "src/a.py"))

    def test_owned_path_is_allowed_and_foreign_path_denied(self):
        _marker(self.root, ["src/a.py", "lib/*.py", "pkg/"])
        self.assertIsNone(dispatch_scope.guard(self.root, "src/a.py"))
        self.assertIsNone(dispatch_scope.guard(self.root, os.path.join(self.root, "lib/x.py")))
        self.assertIsNone(dispatch_scope.guard(self.root, "pkg/deep/y.py"))
        verdict = dispatch_scope.guard(self.root, "src/b.py")
        self.assertEqual(verdict["decision"], policy.DENY)
        self.assertIn("owned_paths", verdict["reason"])

    def test_tests_and_harness_files_are_always_writable(self):
        _marker(self.root, ["src/a.py"])
        self.assertIsNone(dispatch_scope.guard(self.root, "tests/test_a.py"))
        self.assertIsNone(dispatch_scope.guard(self.root, ".spec-master/dispatch/x.json"))

    def test_read_only_reviewer_cannot_write_anywhere(self):
        _marker(self.root, ["src/a.py"], read_only=True)
        verdict = dispatch_scope.guard(self.root, "src/a.py")
        self.assertEqual(verdict["decision"], policy.DENY)
        self.assertIn("read-only", verdict["reason"])

    def test_corrupt_marker_is_ignored(self):
        os.makedirs(os.path.join(self.root, ".spec-master"))
        with open(os.path.join(self.root, ".spec-master", "worktree.json"), "w") as fh:
            fh.write("{nope")
        self.assertIsNone(dispatch_scope.guard(self.root, "src/b.py"))


class HookdIntegrationTests(unittest.TestCase):
    def test_pre_tool_use_applies_the_worktree_scope(self):
        with tempfile.TemporaryDirectory() as root:
            _marker(root, ["src/a.py"])
            payload = {"tool_name": "Write", "tool_input": {"file_path": "src/b.py"}}
            self.assertEqual(hookd.pre_tool_use(root, payload, True)["decision"], policy.DENY)
            payload["tool_input"]["file_path"] = "src/a.py"
            self.assertNotEqual(hookd.pre_tool_use(root, payload, True)["decision"], policy.DENY)

    def test_without_marker_hookd_is_unchanged(self):
        with tempfile.TemporaryDirectory() as root:
            payload = {"tool_name": "Write", "tool_input": {"file_path": "src/b.py"}}
            self.assertNotIn("worktree scope", hookd.pre_tool_use(root, payload, True).get("reason", ""))


if __name__ == "__main__":
    unittest.main()
