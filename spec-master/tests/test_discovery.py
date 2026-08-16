import json
import os
import shutil
import tempfile
import unittest

import _pathfix  # noqa: F401
import discovery


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_repo_reports_no_stacks_and_no_invented_commands(self):
        result = discovery.scan(self.tmp)
        self.assertEqual(result["stacks"], [])
        self.assertFalse(result["spec_kit_present"])
        self.assertFalse(result["ci_present"])

    def test_node_repo_detects_scripts(self):
        pkg = {
            "name": "demo",
            "scripts": {"test": "jest", "lint": "eslint .", "build": "vite build"},
        }
        with open(os.path.join(self.tmp, "package.json"), "w", encoding="utf-8") as fh:
            json.dump(pkg, fh)
        result = discovery.scan(self.tmp)
        node_stack = next(s for s in result["stacks"] if s["language"] == "node")
        self.assertEqual(node_stack["commands"]["test"], "npm run test")
        self.assertEqual(node_stack["commands"]["lint"], "npm run lint")
        self.assertEqual(node_stack["commands"]["build"], "npm run build")

    def test_node_repo_prefers_pnpm_when_lockfile_present(self):
        pkg = {"scripts": {"test": "jest"}}
        with open(os.path.join(self.tmp, "package.json"), "w", encoding="utf-8") as fh:
            json.dump(pkg, fh)
        with open(os.path.join(self.tmp, "pnpm-lock.yaml"), "w", encoding="utf-8") as fh:
            fh.write("")
        result = discovery.scan(self.tmp)
        node_stack = next(s for s in result["stacks"] if s["language"] == "node")
        self.assertEqual(node_stack["commands"]["test"], "pnpm run test")

    def test_python_repo_detects_pytest_via_tests_dir(self):
        os.makedirs(os.path.join(self.tmp, "tests"))
        with open(os.path.join(self.tmp, "pyproject.toml"), "w", encoding="utf-8") as fh:
            fh.write("[project]\nname='demo'\n")
        result = discovery.scan(self.tmp)
        py_stack = next(s for s in result["stacks"] if s["language"] == "python")
        self.assertEqual(py_stack["commands"]["test"], "pytest")

    def test_go_repo_detected(self):
        with open(os.path.join(self.tmp, "go.mod"), "w", encoding="utf-8") as fh:
            fh.write("module demo\n")
        result = discovery.scan(self.tmp)
        go_stack = next(s for s in result["stacks"] if s["language"] == "go")
        self.assertEqual(go_stack["commands"]["test"], "go test ./...")

    def test_spec_kit_and_constitution_detection(self):
        os.makedirs(os.path.join(self.tmp, ".specify", "memory"))
        with open(
            os.path.join(self.tmp, ".specify", "memory", "constitution.md"), "w", encoding="utf-8"
        ) as fh:
            fh.write("# Constitution\n")
        result = discovery.scan(self.tmp)
        self.assertTrue(result["spec_kit_present"])
        self.assertTrue(result["constitution_present"])

    def test_speckit_commands_listed(self):
        cmd_dir = os.path.join(self.tmp, ".claude", "commands")
        os.makedirs(cmd_dir)
        for name in ("speckit.specify.md", "speckit.plan.md", "other.md"):
            with open(os.path.join(cmd_dir, name), "w", encoding="utf-8") as fh:
                fh.write("")
        result = discovery.scan(self.tmp)
        self.assertEqual(result["speckit_commands"], ["speckit.plan.md", "speckit.specify.md"])


if __name__ == "__main__":
    unittest.main()
