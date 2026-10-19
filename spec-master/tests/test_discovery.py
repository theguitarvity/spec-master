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

    # --- H3: manifest-less Python test suites (feature harness-hygiene) ---
    def _suite(self, rel, name="test_a.py", body="import unittest\n"):
        d = os.path.join(self.tmp, rel)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
            fh.write(body)

    def _python_stacks(self):
        return [s for s in discovery.scan(self.tmp)["stacks"] if s["language"] == "python"]

    def test_unittest_suite_in_subpackage_detected_without_manifest(self):
        self._suite("pkg/tests")
        stacks = self._python_stacks()
        self.assertEqual(len(stacks), 1)
        self.assertEqual(stacks[0]["commands"]["test"], "python3 -m unittest discover -s pkg/tests")
        self.assertEqual(stacks[0]["scope"], "pkg/tests")
        self.assertEqual(stacks[0]["detected_from"], "test-suite")
        self.assertTrue(os.path.isdir(stacks[0]["manifest"]))

    def test_pytest_importing_suite_uses_pytest_runner(self):
        self._suite("app/test", name="widget_test.py", body="import os\nimport pytest\n")
        stacks = self._python_stacks()
        self.assertEqual([s["commands"]["test"] for s in stacks], ["python3 -m pytest app/test"])

    def test_pytest_style_suite_without_pytest_import_uses_pytest_runner(self):
        # plain `def test_*` functions are invisible to unittest -> pytest runner
        self._suite("svc/tests", body="def test_a(tmp_path):\n    assert 1\n")
        stacks = self._python_stacks()
        self.assertEqual([s["commands"]["test"] for s in stacks], ["python3 -m pytest svc/tests"])

    def test_suite_whose_conftest_imports_pytest_uses_pytest_runner(self):
        self._suite("svc/tests", body="import unittest\n")
        self._suite("svc/tests", name="conftest.py", body="import pytest\n")
        stacks = self._python_stacks()
        self.assertEqual([s["commands"]["test"] for s in stacks], ["python3 -m pytest svc/tests"])

    def test_path_only_conftest_keeps_unittest_runner(self):
        self._suite("svc/tests", body="import unittest\n\nclass T(unittest.TestCase):\n    pass\n")
        self._suite("svc/tests", name="conftest.py", body="import sys\n")
        stacks = self._python_stacks()
        self.assertEqual([s["commands"]["test"] for s in stacks],
                         ["python3 -m unittest discover -s svc/tests"])

    def test_root_tests_dir_without_manifest_detected(self):
        self._suite("tests")
        stacks = self._python_stacks()
        self.assertEqual([s["scope"] for s in stacks], ["tests"])
        self.assertEqual(stacks[0]["commands"]["test"], "python3 -m unittest discover -s tests")

    def test_hidden_and_vendored_suites_ignored(self):
        for rel in (".hidden/tests", "node_modules/tests", ".venv/tests", "venv/tests"):
            self._suite(rel)
        self.assertEqual(self._python_stacks(), [])

    def test_tests_dir_without_test_modules_ignored(self):
        self._suite("pkg/tests", name="helpers.py")
        self.assertEqual(self._python_stacks(), [])

    def test_manifest_repo_keeps_manifest_detection(self):
        self._suite("pkg/tests")
        with open(os.path.join(self.tmp, "requirements.txt"), "w", encoding="utf-8") as fh:
            fh.write("requests\n")
        os.makedirs(os.path.join(self.tmp, "tests"))
        stacks = self._python_stacks()
        self.assertEqual(len(stacks), 1)
        self.assertEqual(stacks[0]["commands"]["test"], "pytest")
        self.assertNotIn("scope", stacks[0])

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
        self.assertEqual(
            result["speckit_command_paths"]["claude"],
            [".claude/commands/speckit.plan.md", ".claude/commands/speckit.specify.md"],
        )

    def test_opencode_speckit_commands_listed(self):
        cmd_dir = os.path.join(self.tmp, ".opencode", "commands")
        os.makedirs(cmd_dir)
        for name in ("speckit.specify.md", "speckit.plan.md", "other.md"):
            with open(os.path.join(cmd_dir, name), "w", encoding="utf-8") as fh:
                fh.write("")
        result = discovery.scan(self.tmp)
        self.assertEqual(result["speckit_commands"], ["speckit.plan.md", "speckit.specify.md"])
        self.assertEqual(
            result["speckit_command_paths"]["opencode"],
            [".opencode/commands/speckit.plan.md", ".opencode/commands/speckit.specify.md"],
        )


if __name__ == "__main__":
    unittest.main()
