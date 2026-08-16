import json
import os
import shutil
import tempfile
import unittest

import _pathfix  # noqa: F401
import quality_gates


class QualityGatesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_python_repo_never_returns_npm_test(self):
        with open(os.path.join(self.tmp, "pyproject.toml"), "w", encoding="utf-8") as fh:
            fh.write("[tool.pytest.ini_options]\n")
        gates = quality_gates.detect(self.tmp)
        commands = [g["command"] for g in gates]
        self.assertTrue(any("pytest" in c for c in commands))
        self.assertFalse(any("npm" in c for c in commands))

    def test_node_repo_never_returns_pytest(self):
        pkg = {"scripts": {"test": "jest", "build": "tsc"}}
        with open(os.path.join(self.tmp, "package.json"), "w", encoding="utf-8") as fh:
            json.dump(pkg, fh)
        gates = quality_gates.detect(self.tmp)
        commands = [g["command"] for g in gates]
        self.assertTrue(any("npm run test" in c for c in commands))
        self.assertFalse(any("pytest" in c for c in commands))

    def test_empty_repo_returns_no_gates(self):
        self.assertEqual(quality_gates.detect(self.tmp), [])

    def test_build_and_test_gates_marked_blocking(self):
        pkg = {"scripts": {"test": "jest", "build": "tsc", "lint": "eslint ."}}
        with open(os.path.join(self.tmp, "package.json"), "w", encoding="utf-8") as fh:
            json.dump(pkg, fh)
        gates = {g["name"].split(" ")[0]: g for g in quality_gates.detect(self.tmp)}
        self.assertTrue(gates["build"]["blocking"])
        self.assertTrue(gates["test"]["blocking"])
        self.assertFalse(gates["lint"]["blocking"])


if __name__ == "__main__":
    unittest.main()
