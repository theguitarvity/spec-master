import json
import os
import unittest

import _pathfix  # noqa: F401
import kernel_fixtures as fx
from kernel import changes, step

FIXED_TEST = fx.TEST_CALC.replace(
    "        self.assertEqual(add(2, 3), 5)\n",
    "        self.assertEqual(add(2, 3), 5)\n\n    def test_add_strings(self):\n"
    "        self.assertEqual(add('1', '2'), 3)\n",
)
FIXED_CALC = "def add(a, b):\n    return int(a) + int(b)\n"


class PatchLaneTests(unittest.TestCase):
    """The patch lane end to end, in a throwaway git repository with a real
    unittest gate (declared in .spec-master/gates.json)."""

    def setUp(self):
        self.root = fx.make_repo()
        self.intent = "add() must accept numeric strings"

    def tearDown(self):
        fx.remove(self.root)

    def begin(self, paths=("src/calc.py", "tests/test_calc.py"), **kwargs):
        return step.begin(self.root, intent=self.intent, paths=list(paths), **kwargs)

    def write_note(self, change_id, checks=None):
        checks = checks or ["[EXPLICIT] numeric strings are added as numbers (test: tests/test_calc.py)"]
        fx.write(self.root, changes.note_relpath(change_id),
                 fx.note(change_id, self.intent, checks, ["src/calc.py", "tests/test_calc.py"]))

    def implement(self):
        fx.write(self.root, "src/calc.py", FIXED_CALC)
        fx.write(self.root, "tests/test_calc.py", FIXED_TEST)

    def test_happy_path_passes_only_with_evidence(self):
        started = self.begin()
        self.assertEqual(started["status"], "RUNNING")
        self.assertIn("Declared files: src/calc.py, tests/test_calc.py", started["card"])
        self.assertEqual(step.next_step(self.root)["change"], started["change"])
        self.implement()
        result = step.end(self.root)
        self.assertEqual(result["status"], "RUNNING")  # no change note yet
        self.assertIn("note", {f["name"] for f in result["failed"]})
        self.write_note(started["change"])
        result = step.end(self.root)
        self.assertEqual(result["status"], "PASSED", result)
        self.assertEqual(result["files"], ["src/calc.py", "tests/test_calc.py"])
        record = changes.load(self.root, started["change"])
        self.assertTrue(record["evidence"]["verified"])
        self.assertEqual(record["evidence"]["gates"][0]["result"], "PASSED")
        self.assertIsNone(changes.active_id(self.root))
        self.assertEqual(step.next_step(self.root)["step"], "triage")
        with open(os.path.join(changes.changes_dir(self.root), "log.jsonl"), encoding="utf-8") as fh:
            self.assertEqual(json.loads(fh.readline())["status"], "PASSED")

    def test_failing_gate_keeps_the_change_running(self):
        started = self.begin()
        fx.write(self.root, "tests/test_calc.py", FIXED_TEST)  # test without the fix
        self.write_note(started["change"])
        result = step.end(self.root)
        self.assertEqual(result["status"], "RUNNING")
        self.assertEqual([f["name"] for f in result["failed"]], ["gates"])
        self.assertEqual(result["gates"][0]["result"], "FAILED")

    def test_writing_outside_the_envelope_fails_the_scope_check(self):
        started = self.begin()
        self.implement()
        fx.write(self.root, "src/extra.py", "X = 1\n")
        self.write_note(started["change"])
        result = step.end(self.root, run_gates=False)
        self.assertIn("scope", [f["name"] for f in result["failed"]])

    def test_a_diff_that_outgrows_the_lane_escalates(self):
        started = self.begin()
        fx.write(self.root, "src/calc.py", FIXED_CALC + "".join(f"\n\ndef f{i}():\n    return {i}\n" for i in range(30)))
        self.write_note(started["change"])
        result = step.end(self.root, run_gates=False)
        self.assertEqual(result["status"], "ESCALATED")
        self.assertEqual(result["lane"], "standard")
        self.assertIn("/spec-master <context file>", result["card"])
        self.assertEqual(changes.load(self.root, started["change"])["status"], "ESCALATED")
        self.assertIsNone(changes.active_id(self.root))

    def test_provenance_claims_must_cite_real_lines(self):
        started = self.begin()
        self.implement()
        self.write_note(started["change"], [
            "[EXPLICIT] numeric strings are added (test: tests/test_calc.py)",
            "[DISCOVERED_FROM_CODEBASE] add lives at `src/calc.py:99` (test: tests/test_calc.py)",
        ])
        result = step.end(self.root, run_gates=False)
        self.assertIn("provenance", [f["name"] for f in result["failed"]])
        self.write_note(started["change"], [
            "[EXPLICIT] numeric strings are added (test: tests/test_calc.py)",
            "[DISCOVERED_FROM_CODEBASE] add lives at `src/calc.py:1` (test: tests/test_calc.py)",
        ])
        self.assertEqual(step.end(self.root)["status"], "PASSED")

    def test_note_rules(self):
        started = self.begin()
        self.implement()
        fx.write(self.root, changes.note_relpath(started["change"]),
                 "Intent: something\n- [INFERRED] a guess without a test\nUNRESOLVED: scope\n")
        failed = {f["name"] for f in step.end(self.root, run_gates=False)["failed"]}
        self.assertTrue({"intent", "acceptance", "unresolved"} <= failed)

    def test_questions_and_other_lanes_do_not_open_a_change(self):
        asked = step.begin(self.root, intent="Fix the sum and open a pull request", paths=["src/calc.py"])
        self.assertEqual(asked["status"], "QUESTIONS")
        full = self.begin(paths=["src/auth/login.py", "tests/test_calc.py"])
        self.assertEqual((full["status"], full["lane"]), ("FULL_CYCLE", "critical"))
        self.assertIsNone(changes.active_id(self.root))

    def test_one_running_change_at_a_time_pause_and_resume(self):
        started = self.begin()
        with self.assertRaises(changes.ChangeError):
            self.begin()
        step.pause(self.root, reason="lunch")
        self.assertEqual(changes.load(self.root, started["change"])["status"], "PAUSED")
        resumed = step.resume(self.root, change_id=started["change"])
        self.assertEqual(resumed["status"], "RUNNING")

    def test_widen_adds_files_or_escalates(self):
        started = self.begin()
        self.assertEqual(step.widen(self.root, paths=["src/__init__.py"])["status"], "RUNNING")
        self.assertIn("src/__init__.py", changes.load(self.root, started["change"])["envelope"])
        escalated = step.widen(self.root, paths=["src/auth/token.py"])
        self.assertEqual((escalated["status"], escalated["lane"]), ("ESCALATED", "critical"))

    def test_pre_existing_dirty_files_are_not_part_of_the_change(self):
        fx.write(self.root, "src/scratch.py", "WIP = True\n")  # the user's uncommitted work
        started = self.begin()
        self.implement()
        self.write_note(started["change"])
        result = step.end(self.root)
        self.assertEqual(result["status"], "PASSED", result)
        self.assertNotIn("src/scratch.py", result["files"])


class BugfixTests(unittest.TestCase):
    def setUp(self):
        self.root = fx.make_repo()

    def tearDown(self):
        fx.remove(self.root)

    def run_bugfix(self, calc_after):
        intent = "add('1', '2') returns '12' instead of 3"
        started = step.begin(self.root, intent=intent, paths=["src/calc.py", "tests/test_calc.py"], kind="bugfix",
                             regression_test="tests/test_calc.py",
                             test_command="python3 -m unittest tests.test_calc")
        self.assertEqual(started["status"], "RUNNING")
        self.assertIn("must fail on the base commit", started["card"])
        fx.write(self.root, "tests/test_calc.py", FIXED_TEST)
        fx.write(self.root, "src/calc.py", calc_after)
        fx.write(self.root, changes.note_relpath(started["change"]),
                 fx.note(started["change"], intent, ["[EXPLICIT] '1' + '2' is 3 (test: tests/test_calc.py)"],
                         ["src/calc.py", "tests/test_calc.py"]))
        return step.end(self.root)

    def test_regression_test_fails_before_and_passes_after(self):
        result = self.run_bugfix(FIXED_CALC)
        self.assertEqual(result["status"], "PASSED", result)

    def test_a_test_that_passes_on_the_base_is_not_a_regression_test(self):
        result = self.run_bugfix(fx.CALC)  # "fix" that changes nothing: the new test fails on both sides
        self.assertEqual(result["status"], "RUNNING")
        self.assertIn("regression", [f["name"] for f in result["failed"]])

    def test_bugfix_needs_its_test_and_command(self):
        with self.assertRaises(changes.ChangeError):
            step.begin(self.root, intent="x", paths=["src/calc.py"], kind="bugfix")


if __name__ == "__main__":
    unittest.main()
