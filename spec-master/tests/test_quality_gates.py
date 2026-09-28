import contextlib
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

import _pathfix  # noqa: F401
import quality_gates

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

UNITTEST_MODULE = (
    "import unittest\n\n\n"
    "class SmokeTests(unittest.TestCase):\n"
    "    def test_ok(self):\n"
    "        self.assertTrue(True)\n"
)
PYTEST_MODULE = "def test_ok():\n    assert True\n"


def _write(root, rel, text=""):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _declare(root, payload):
    _write(root, ".spec-master/gates.json", json.dumps(payload))


def _run_gate(root, gate):
    """Run a detected `python3 ...` gate with this interpreter, from `root`."""
    argv = shlex.split(gate["command"])
    return subprocess.run([sys.executable, *argv[1:]], cwd=root, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)


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

    def test_detected_gates_carry_source_category_and_no_limits(self):
        pkg = {"scripts": {"test": "jest", "build": "tsc", "lint": "eslint ."}}
        with open(os.path.join(self.tmp, "package.json"), "w", encoding="utf-8") as fh:
            json.dump(pkg, fh)
        for gate in quality_gates.detect(self.tmp):
            self.assertEqual(gate["source"], "detected")
            self.assertIsNone(gate["timeout_seconds"])
            self.assertIsNone(gate["cwd"])
            self.assertEqual(gate["category"], gate["name"].split(" ")[0])


class DeclaredGatesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_declared_gates_are_normalized_with_defaults(self):
        _declare(self.tmp, [
            {"name": "unit", "command": "make test"},
            {"name": "lint", "command": ["ruff", "check", "src dir"], "blocking": False,
             "category": "lint", "timeout_seconds": 120, "cwd": "./backend/"},
            {"name": " e2e ", "command": "make e2e", "blocking": None, "category": None,
             "timeout_seconds": None, "cwd": None},
        ])
        self.assertEqual(quality_gates.detect(self.tmp), [
            {"name": "unit", "command": "make test", "blocking": True, "category": "test",
             "source": "declared", "timeout_seconds": None, "cwd": None},
            {"name": "lint", "command": "ruff check 'src dir'", "blocking": False, "category": "lint",
             "source": "declared", "timeout_seconds": 120, "cwd": "backend"},
            {"name": "e2e", "command": "make e2e", "blocking": True, "category": "test",
             "source": "declared", "timeout_seconds": None, "cwd": None},
        ])

    def test_argv_command_is_shell_quoted_without_loss(self):
        argv = ["python3", "-c", "print('a b')", "$HOME", "x;rm -rf y", ""]
        _declare(self.tmp, [{"name": "argv", "command": argv}])
        [gate] = quality_gates.load_declared(self.tmp)
        self.assertEqual(shlex.split(gate["command"]), argv)

    def test_declared_gate_overrides_detected_gate_with_the_same_name(self):
        pkg = {"scripts": {"test": "jest", "build": "tsc", "lint": "eslint ."}}
        _write(self.tmp, "package.json", json.dumps(pkg))
        _declare(self.tmp, [
            {"name": "e2e", "command": "npm run e2e", "blocking": False},
            {"name": "test (node)", "command": "npm run test:ci", "timeout_seconds": 600},
        ])
        gates = quality_gates.detect(self.tmp)
        self.assertEqual([g["name"] for g in gates], ["build (node)", "lint (node)", "test (node)", "e2e"])
        by_name = {g["name"]: g for g in gates}
        self.assertEqual(by_name["test (node)"]["source"], "declared")
        self.assertEqual(by_name["test (node)"]["command"], "npm run test:ci")
        self.assertEqual(by_name["test (node)"]["timeout_seconds"], 600)
        self.assertEqual(by_name["build (node)"]["source"], "detected")
        self.assertEqual(by_name["e2e"]["source"], "declared")

    def test_empty_declaration_keeps_detection(self):
        _write(self.tmp, "go.mod", "module demo\n")
        detected = quality_gates.detect(self.tmp)
        _declare(self.tmp, [])
        self.assertEqual(quality_gates.detect(self.tmp), detected)
        self.assertEqual(quality_gates.load_declared(self.tmp), [])

    def test_validate_declared_accepts_a_valid_payload(self):
        self.assertEqual(quality_gates.validate_declared([
            {"name": "unit", "command": ["python3", "-m", "unittest"], "blocking": True,
             "category": "test", "timeout_seconds": 1, "cwd": "."},
        ]), [])

    def test_validate_declared_reports_each_problem(self):
        cases = [
            ({"name": "x", "command": "y"}, "gates must be a JSON array"),
            (["make test"], "gates[0]: must be an object, got string"),
            ([{"command": "make"}], "gates[0].name: required non-empty string"),
            ([{"name": "  ", "command": "make"}], "gates[0].name: required non-empty string"),
            ([{"name": "a", "command": "x"}, {"name": "a", "command": "y"}],
             "gates[1].name: 'a' is already declared by gates[0]"),
            ([{"name": "a"}], "gates[0].command: required"),
            ([{"name": "a", "command": " "}], "gates[0].command: must not be empty"),
            ([{"name": "a", "command": []}], "gates[0].command: argv list must not be empty"),
            ([{"name": "a", "command": ["make", 1]}], "gates[0].command[1]: argv items must be strings"),
            ([{"name": "a", "command": ["", "x"]}], "gates[0].command[0]: program must not be empty"),
            ([{"name": "a", "command": 42}], "gates[0].command: must be a string or a list of strings"),
            ([{"name": "a", "command": "x", "blocking": "yes"}], "gates[0].blocking: must be true or false"),
            ([{"name": "a", "command": "x", "category": ""}], "gates[0].category: must be a non-empty string"),
            ([{"name": "a", "command": "x", "comand": "y"}], "gates[0]: unknown key(s) comand"),
        ]
        for timeout in (0, -5, "30", True, 1.5):
            cases.append(([{"name": "a", "command": "x", "timeout_seconds": timeout}],
                          "gates[0].timeout_seconds: must be an integer > 0"))
        for payload, expected in cases:
            with self.subTest(payload=payload):
                errors = quality_gates.validate_declared(payload)
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_unsafe_cwd_is_rejected(self):
        for cwd in ("/tmp", "../outside", "a/../../b", "..\\up", "C:\\work", "\\\\server\\share", "", 3):
            with self.subTest(cwd=cwd):
                errors = quality_gates.validate_declared([{"name": "a", "command": "x", "cwd": cwd}])
                self.assertTrue(errors and all(e.startswith("gates[0].cwd:") for e in errors), errors)

    def test_cwd_symlink_escaping_the_repository_is_rejected(self):
        outside = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        try:
            os.symlink(outside, os.path.join(self.tmp, "link"))
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        _declare(self.tmp, [{"name": "a", "command": "x", "cwd": "link"}])
        with self.assertRaises(quality_gates.DeclaredGatesError) as ctx:
            quality_gates.load_declared(self.tmp)
        self.assertIn("gates[0].cwd: resolves outside the repository", ctx.exception.errors[0])

    def test_invalid_file_fails_detection_listing_every_error(self):
        _write(self.tmp, "go.mod", "module demo\n")
        _declare(self.tmp, [{"name": "a"}, {"name": "b", "command": "x", "cwd": "/etc"}])
        with self.assertRaises(quality_gates.DeclaredGatesError) as ctx:
            quality_gates.detect(self.tmp)
        self.assertIsInstance(ctx.exception, ValueError)
        self.assertEqual(len(ctx.exception.errors), 2)
        self.assertIn(".spec-master/gates.json is invalid", str(ctx.exception))

    def test_malformed_json_reports_its_position(self):
        _write(self.tmp, ".spec-master/gates.json", '[{"name": "a",\n')
        with self.assertRaises(quality_gates.DeclaredGatesError) as ctx:
            quality_gates.load_declared(self.tmp)
        self.assertRegex(ctx.exception.errors[0], r"^invalid JSON: .* \(line 2, column \d+\)$")

    def test_cli_reports_an_invalid_file_as_a_json_error(self):
        import cli

        _declare(self.tmp, {"name": "not a list"})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["gates", "detect", "--path", self.tmp])
        self.assertEqual(code, 1)
        self.assertIn(".spec-master/gates.json is invalid", json.loads(out.getvalue())["error"])


class UnittestSuiteDetectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_suite_importing_unittest_becomes_a_blocking_test_gate(self):
        _write(self.tmp, "tests/test_a.py", UNITTEST_MODULE)
        _write(self.tmp, "tests/test_b.py", PYTEST_MODULE)
        self.assertEqual(quality_gates.detect(self.tmp), [{
            "name": "test (unittest: tests)",
            "command": "python3 -m unittest discover -s tests",
            "blocking": True, "category": "test", "source": "detected",
            "timeout_seconds": None, "cwd": None,
            "tool": "unittest", "execution": "local", "evidence": ["tests/test_a.py"],
        }])

    def test_command_runs_a_suite_that_imports_sibling_helpers(self):
        # Mirrors spec-master/tests: a package directory whose modules import a
        # sibling helper (`_pathfix`) as a top-level module.
        _write(self.tmp, "tool-x/tests/__init__.py")
        _write(self.tmp, "tool-x/tests/_helper.py", "VALUE = 1\n")
        _write(self.tmp, "tool-x/tests/test_a.py",
               "import unittest\n\nimport _helper\n\n\n"
               "class T(unittest.TestCase):\n"
               "    def test_value(self):\n"
               "        self.assertEqual(_helper.VALUE, 1)\n")
        [gate] = quality_gates.detect_unittest_suites(self.tmp)
        self.assertEqual(gate["command"], "python3 -m unittest discover -s tool-x/tests")
        completed = _run_gate(self.tmp, gate)
        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertIn("Ran 1 test", completed.stdout)

    def test_suite_with_relative_imports_gets_a_top_level_dir(self):
        _write(self.tmp, "tests/__init__.py")
        _write(self.tmp, "tests/helpers.py", "VALUE = 2\n")
        _write(self.tmp, "tests/test_a.py",
               "import unittest\n\nfrom . import helpers\n\n\n"
               "class T(unittest.TestCase):\n"
               "    def test_value(self):\n"
               "        self.assertEqual(helpers.VALUE, 2)\n")
        [gate] = quality_gates.detect_unittest_suites(self.tmp)
        self.assertEqual(gate["command"], "python3 -m unittest discover -s tests -t .")
        completed = _run_gate(self.tmp, gate)
        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertIn("Ran 1 test", completed.stdout)

    def test_subclassing_testcase_is_evidence(self):
        for source in (
            "from unittest import TestCase\n\n\nclass T(TestCase):\n    pass\n",
            "from unittest import IsolatedAsyncioTestCase as Base\n\n\nclass T(Base):\n    pass\n",
            "import unittest.mock\n\n\nclass T(unittest.TestCase):\n    pass\n",
        ):
            with self.subTest(source=source.splitlines()[0]):
                root = tempfile.mkdtemp()
                self.addCleanup(shutil.rmtree, root, ignore_errors=True)
                _write(root, "tests/test_a.py", source)
                self.assertEqual(len(quality_gates.detect_unittest_suites(root)), 1)

    def test_tests_without_unittest_evidence_are_not_a_gate(self):
        _write(self.tmp, "tests/test_a.py", "import pytest\n\n\n" + PYTEST_MODULE)
        _write(self.tmp, "tests/test_b.py", "from unittest import mock\n\n\n" + PYTEST_MODULE)
        _write(self.tmp, "tests/test_c.py", "import unittest.mock\n\n\n" + PYTEST_MODULE)
        _write(self.tmp, "tests/test_d.py", '"""import unittest"""\n# import unittest\n' + PYTEST_MODULE)
        _write(self.tmp, "tests/test_e.py", "import unittest\nthis is not python(\n")
        _write(self.tmp, "tests/helper.py", UNITTEST_MODULE)  # not a test_*.py file
        self.assertEqual(quality_gates.detect(self.tmp), [])

    def test_python_manifest_disables_the_unittest_heuristic(self):
        _write(self.tmp, "pyproject.toml", "[project]\nname = 'demo'\n")
        _write(self.tmp, "tests/test_a.py", UNITTEST_MODULE)
        gates = quality_gates.detect(self.tmp)
        self.assertEqual([g["name"] for g in gates], ["test (python)"])
        self.assertEqual(gates[0]["command"], "pytest")

    def test_scan_depth_is_bounded(self):
        _write(self.tmp, "a/b/c/test_x.py", UNITTEST_MODULE)
        _write(self.tmp, "e/f/g/h/test_y.py", UNITTEST_MODULE)
        gates = quality_gates.detect_unittest_suites(self.tmp)
        self.assertEqual([g["name"] for g in gates], ["test (unittest: a/b/c)"])

    def test_vendored_virtualenv_and_cache_dirs_are_skipped(self):
        for rel in ("node_modules/pkg/test_x.py", ".venv/lib/test_x.py", "venv/test_x.py",
                    "__pycache__/test_x.py", ".spec-master/test_x.py", ".git/test_x.py",
                    "env/test_x.py"):
            _write(self.tmp, rel, UNITTEST_MODULE)
        _write(self.tmp, "env/pyvenv.cfg", "home = /usr/bin\n")  # a virtualenv under any name
        self.assertEqual(quality_gates.detect_unittest_suites(self.tmp), [])
        _write(self.tmp, "src/test_x.py", UNITTEST_MODULE)
        self.assertEqual([g["name"] for g in quality_gates.detect_unittest_suites(self.tmp)],
                         ["test (unittest: src)"])

    def test_nested_package_suite_is_covered_by_its_parent(self):
        _write(self.tmp, "tests/test_a.py", UNITTEST_MODULE)
        _write(self.tmp, "tests/unit/__init__.py")
        _write(self.tmp, "tests/unit/test_b.py", UNITTEST_MODULE)
        _write(self.tmp, "tests/data/test_c.py", UNITTEST_MODULE)  # not a package: not discovered from tests
        gates = quality_gates.detect_unittest_suites(self.tmp)
        self.assertEqual([g["command"] for g in gates], [
            "python3 -m unittest discover -s tests",
            "python3 -m unittest discover -s tests/data",
        ])

    def test_this_repository_suite_is_detected(self):
        if not os.path.isfile(os.path.join(REPO_ROOT, "spec-master", "tests", "_pathfix.py")):
            self.skipTest("not running inside the spec-master repository")
        commands = [g["command"] for g in quality_gates.detect_unittest_suites(REPO_ROOT)]
        self.assertIn("python3 -m unittest discover -s spec-master/tests", commands)


if __name__ == "__main__":
    unittest.main()
