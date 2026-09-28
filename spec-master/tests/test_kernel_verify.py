import subprocess
import unittest

import _pathfix  # noqa: F401
import kernel_fixtures as fx
from kernel import changes, step, verify

CHANGE = "c1"


class NoteCheckTests(unittest.TestCase):
    def setUp(self):
        self.root = fx.make_repo()

    def tearDown(self):
        fx.remove(self.root)

    def failed(self, note):
        return {c["name"]: c["detail"] for c in verify.note_checks(self.root, CHANGE, note) if not c["ok"]}

    def test_missing_and_oversized_notes(self):
        self.assertIn("missing", self.failed(None)["note"])
        huge = "Intent: x [EXPLICIT]\n- [EXPLICIT] y (test: tests/test_calc.py)\n" + "z" * verify.NOTE_HARD_LIMIT
        self.assertIn("a change note is a few lines", self.failed(huge)["note"])

    def test_a_good_note(self):
        note = ("Intent: add() accepts numeric strings [EXPLICIT]\n"
                "- [EXPLICIT] '1' + '2' is 3 (test: tests/test_calc.py::CalcTests.test_add)\n"
                "- [DISCOVERED_FROM_CODEBASE] add is defined at `src/calc.py:1` (test: tests/test_calc.py)\n")
        self.assertEqual(self.failed(note), {})

    def test_every_rule(self):
        self.assertIn("intent", self.failed("Intent: guessed [INFERRED]\n- [EXPLICIT] y (test: tests/test_calc.py)\n"))
        self.assertIn("acceptance", self.failed("Intent: x [EXPLICIT]\n"))
        self.assertIn("without an existing test",
                      self.failed("Intent: x [EXPLICIT]\n- [EXPLICIT] no test named\n")["acceptance"])
        self.assertIn("tests/test_nope.py (not found)",
                      self.failed("Intent: x [EXPLICIT]\n- [EXPLICIT] y (test: tests/test_nope.py)\n")["acceptance"])
        self.assertIn("unresolved", self.failed("Intent: x [EXPLICIT]\n- [EXPLICIT] y (test: tests/test_calc.py)\n"
                                                "UNRESOLVED: rounding mode\n"))
        claims = {
            "no file:line": "- [DISCOVERED_FROM_CODEBASE] it is somewhere (test: tests/test_calc.py)",
            "does not exist": "- [DISCOVERED_FROM_CODEBASE] see `src/nope.py:3` (test: tests/test_calc.py)",
            "past the end": "- [DISCOVERED_FROM_CODEBASE] see `src/calc.py:40` (test: tests/test_calc.py)",
        }
        for expected, line in claims.items():
            with self.subTest(expected=expected):
                self.assertIn(expected, self.failed("Intent: x [EXPLICIT]\n" + line + "\n")["provenance"])


def completed(code, out=""):
    return subprocess.CompletedProcess([], code, stdout=out, stderr="")


class GateTests(unittest.TestCase):
    def test_results_timeouts_and_missing_tools(self):
        seen = {}

        def runner(argv, **kwargs):
            seen.update(argv=argv, **kwargs)
            return completed(0, "ok")
        result = verify.run_gate("/proj", {"name": "unit", "command": "make test", "cwd": "web", "timeout_seconds": 5},
                                 runner=runner)
        self.assertEqual((result["result"], result["exit_code"]), ("PASSED", 0))
        self.assertEqual((seen["argv"], seen["cwd"], seen["timeout"]), (["make", "test"], "/proj/web", 5))
        self.assertEqual(verify.run_gate("/proj", {"name": "u", "command": ["x"]}, runner=lambda a, **k: completed(2))
                         ["result"], "FAILED")

        def slow(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        self.assertIn("timed out after 900s", verify.run_gate("/proj", {"name": "u", "command": "x"}, runner=slow)
                      ["output_tail"])

        def missing(argv, **kwargs):
            raise FileNotFoundError("no such tool")
        self.assertEqual(verify.run_gate("/proj", {"name": "u", "command": "x"}, runner=missing)["result"], "FAILED")

    def test_regression_check_needs_its_inputs(self):
        checks = verify.regression_check("/proj", {"bugfix": {"test": "tests/t.py"}, "base": {}})
        self.assertFalse(checks[0]["ok"])
        self.assertIn("--regression-test", checks[0]["detail"])


class PostTests(unittest.TestCase):
    def setUp(self):
        self.root = fx.make_repo()

    def tearDown(self):
        fx.remove(self.root)

    def test_skipping_the_gates_never_passes(self):
        started = step.begin(self.root, intent="add() accepts strings", paths=["src/calc.py", "tests/test_calc.py"])
        fx.write(self.root, "src/calc.py", "def add(a, b):\n    return int(a) + int(b)\n")
        fx.write(self.root, changes.note_relpath(started["change"]),
                 fx.note(started["change"], "add() accepts strings",
                         ["[EXPLICIT] '1' + '2' is 3 (test: tests/test_calc.py)"], ["src/calc.py"]))
        record = changes.load(self.root, started["change"])
        skipped = verify.post(self.root, record, run_gates=False)
        self.assertFalse(skipped["ok"])
        self.assertEqual([c["name"] for c in skipped["checks"] if not c["ok"]], ["gates"])
        self.assertEqual(step.end(self.root, run_gates=False)["status"], "RUNNING")
        self.assertTrue(verify.post(self.root, record)["ok"])

    def test_nothing_changed_is_not_done(self):
        step.begin(self.root, intent="x", paths=["src/calc.py", "tests/test_calc.py"])
        record = changes.active(self.root)
        self.assertIn("diff", [c["name"] for c in verify.post(self.root, record, run_gates=False)["checks"]
                               if not c["ok"]])


if __name__ == "__main__":
    unittest.main()
