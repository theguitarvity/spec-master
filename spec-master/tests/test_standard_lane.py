"""Standard lane: verify:pre (deterministic analyze), TDD RED/GREEN gates with
evidence, and the TDD guard hook (blocks only in hooks_mode=block)."""
import io
import json
import os
import sys
import unittest

import _pathfix  # noqa: F401
import kernel_fixtures as fx
import standard_lane
import tdd_gates
import verify_pre
from kernel import changes, hookd, step

SPEC = """# Spec-lite: add_strings

## Problem
add() rejects numeric strings. [EXPLICIT]

## Acceptance
- [EXPLICIT] AC1 numeric strings are added as numbers (test: tests/test_calc.py)
- [DISCOVERED_FROM_CODEBASE] add() is in `src/calc.py:1` (task: T001)

## Plan
Convert operands with int().

## Tasks
- [ ] T001 write the failing test
- [ ] T002 make it pass
"""
FIXED_TEST = fx.TEST_CALC.replace(
    "        self.assertEqual(add(2, 3), 5)\n",
    "        self.assertEqual(add(2, 3), 5)\n\n    def test_add_strings(self):\n"
    "        self.assertEqual(add('1', '2'), 3)\n",
)
FIXED_CALC = "def add(a, b):\n    return int(a) + int(b)\n"


class VerifyPreTests(unittest.TestCase):
    def setUp(self):
        self.root = fx.make_repo()
        self.dir = "specs/020-add-strings"

    def tearDown(self):
        fx.remove(self.root)

    def run_pre(self, spec):
        fx.write(self.root, f"{self.dir}/spec.md", spec)
        return verify_pre.run(self.root, self.dir)

    def failed(self, result):
        return {c["name"] for c in result["checks"] if not c["ok"]}

    def test_clean_spec_lite_passes(self):
        result = self.run_pre(SPEC)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["tasks"], 2)

    def test_missing_spec_fails_closed(self):
        self.assertEqual(self.failed(verify_pre.run(self.root, self.dir)), {"spec"})

    def test_unresolved_blocks_implement(self):
        self.assertIn("unresolved", self.failed(self.run_pre(SPEC + "\n- [UNRESOLVED] which rounding?\n")))

    def test_ac_without_test_or_task_is_flagged(self):
        spec = SPEC.replace(" (test: tests/test_calc.py)", "")
        self.assertIn("coverage", self.failed(self.run_pre(spec)))

    def test_ac_pointing_at_a_missing_task_is_flagged(self):
        self.assertIn("coverage", self.failed(self.run_pre(SPEC.replace("(task: T001)", "(task: T099)"))))

    def test_more_than_twelve_tasks_or_8kb_is_not_spec_lite(self):
        many = SPEC + "".join(f"- [ ] T{n:03d} more\n" for n in range(3, 15))
        self.assertIn("tasks", self.failed(self.run_pre(many)))
        self.assertIn("size", self.failed(self.run_pre(SPEC + "x" * 9000)))

    def test_discovered_claim_needs_a_real_file_line(self):
        self.assertIn("provenance", self.failed(self.run_pre(SPEC.replace("src/calc.py:1", "src/nope.py:3"))))

    def test_full_cycle_dir_reads_tasks_md_and_has_no_size_cap(self):
        fx.write(self.root, f"{self.dir}/spec.md", SPEC.split("## Tasks")[0] + "x" * 9000)
        fx.write(self.root, f"{self.dir}/tasks.md", "- [ ] T001 a\n- [x] T002 b\n")
        result = verify_pre.run(self.root, self.dir)
        self.assertTrue(result["ok"], result)

    def test_light_analyze_is_the_same_check(self):
        fx.write(self.root, f"{self.dir}/spec.md", SPEC)
        self.assertEqual(verify_pre.light_analyze(self.root, self.dir)["ok"], True)


class StandardFlowTests(unittest.TestCase):
    def setUp(self):
        self.root = fx.make_repo()
        self.intent = "add() must accept numeric strings"

    def tearDown(self):
        fx.remove(self.root)

    def begin(self, **kw):
        return standard_lane.begin(self.root, intent=self.intent, paths=["src/calc.py", "tests/test_calc.py"], **kw)

    def spec(self, change):
        fx.write(self.root, change["spec"], SPEC)

    def test_begin_allocates_a_spec_dir_and_opens_a_standard_change(self):
        started = self.begin()
        self.assertEqual((started["status"], started["lane"], started["step"]), ("RUNNING", "standard", "spec"))
        self.assertRegex(started["spec_dir"], r"^specs/\d{3}-")
        record = changes.active(self.root)
        self.assertIn(started["spec"], record["envelope"])
        self.assertIn("verify-pre", started["card"])
        self.assertEqual(step.next_step(self.root)["change"], started["change"])

    def test_critical_signals_go_to_the_full_cycle(self):
        result = standard_lane.begin(self.root, intent="x", paths=["src/auth/login.py", "tests/test_calc.py"])
        self.assertEqual((result["status"], result["lane"]), ("FULL_CYCLE", "critical"))

    def test_verify_pre_failure_keeps_the_spec_step(self):
        started = self.begin()
        fx.write(self.root, started["spec"], SPEC + "\n- [UNRESOLVED] ?\n")
        result = standard_lane.verify_pre_step(self.root)
        self.assertEqual((result["status"], result["step"]), ("RUNNING", "spec"))
        self.assertFalse(result["ok"])

    def test_red_requires_a_failing_run_with_a_test_change(self):
        started = self.begin()
        self.spec(started)
        self.assertTrue(standard_lane.verify_pre_step(self.root)["ok"])
        self.assertEqual(changes.active(self.root)["step"], "implement")
        refused = standard_lane.tdd_run(self.root, "red")          # no test written yet
        self.assertFalse(refused["ok"])
        fx.write(self.root, "tests/test_calc.py", FIXED_TEST)
        red = standard_lane.tdd_run(self.root, "red")
        self.assertTrue(red["ok"], red)
        self.assertEqual(red["run"]["result"], "FAILED")
        self.assertTrue(red["run"]["tests"])                      # digests of the tests behind the RED

    def test_red_that_passes_is_rejected(self):
        started = self.begin()
        self.spec(started)
        standard_lane.verify_pre_step(self.root)
        fx.write(self.root, "tests/test_calc.py", fx.TEST_CALC + "\n# touched\n")
        red = standard_lane.tdd_run(self.root, "red")
        self.assertFalse(red["ok"])
        self.assertIn("must fail", red["detail"])

    def test_green_needs_a_red_first(self):
        started = self.begin()
        self.spec(started)
        standard_lane.verify_pre_step(self.root)
        self.assertFalse(standard_lane.tdd_run(self.root, "green")["ok"])

    def test_end_to_end_passes_only_with_red_then_green_evidence(self):
        started = self.begin()
        self.spec(started)
        standard_lane.verify_pre_step(self.root)
        fx.write(self.root, "tests/test_calc.py", FIXED_TEST)
        # production code changed but no RED recorded: fail-closed
        fx.write(self.root, "src/calc.py", FIXED_CALC)
        early = step.end(self.root)
        self.assertEqual(early["status"], "RUNNING")
        self.assertIn("tdd", {f["name"] for f in early["failed"]})
        # honest order: revert, RED, then GREEN
        fx.write(self.root, "src/calc.py", fx.CALC)
        self.assertTrue(standard_lane.tdd_run(self.root, "red")["ok"])
        fx.write(self.root, "src/calc.py", FIXED_CALC)
        self.assertTrue(standard_lane.tdd_run(self.root, "green")["ok"])
        fx.write(self.root, started["spec"], SPEC.replace("[ ]", "[x]"))
        result = step.end(self.root)
        self.assertEqual(result["status"], "PASSED", result)
        record = changes.load(self.root, started["change"])
        self.assertEqual([r["phase"] for r in record["tdd"]["runs"]], ["red", "green"])
        self.assertTrue(record["evidence"]["verified"])

    def test_open_tasks_block_the_end(self):
        started = self.begin()
        self.spec(started)
        standard_lane.verify_pre_step(self.root)
        fx.write(self.root, "tests/test_calc.py", FIXED_TEST)
        standard_lane.tdd_run(self.root, "red")
        fx.write(self.root, "src/calc.py", FIXED_CALC)
        standard_lane.tdd_run(self.root, "green")
        result = step.end(self.root)
        self.assertIn("tasks", {f["name"] for f in result["failed"]})

    def test_growing_into_a_critical_path_escalates(self):
        started = self.begin()
        self.spec(started)
        standard_lane.verify_pre_step(self.root)
        fx.write(self.root, "src/auth/login.py", "x = 1\n")
        result = step.end(self.root)
        self.assertEqual(result["status"], "ESCALATED")
        self.assertEqual(result["lane"], "critical")


class TddGuardTests(unittest.TestCase):
    def setUp(self):
        self.root = fx.make_repo()
        self.started = standard_lane.begin(self.root, intent="add() must accept numeric strings",
                                           paths=["src/calc.py", "tests/test_calc.py"])
        fx.write(self.root, self.started["spec"], SPEC)

    def tearDown(self):
        fx.remove(self.root)

    def hook(self, path):
        out = io.StringIO()
        stdout, sys.stdout = sys.stdout, out
        try:
            code = hookd.main(["pre-tool-use"], stdin=io.StringIO(json.dumps(
                {"cwd": self.root, "tool_name": "Write", "tool_input": {"file_path": path, "content": "x"}})))
        finally:
            sys.stdout = stdout
        text = out.getvalue().strip()
        return code, (json.loads(text) if text else None)

    def test_guard_unit(self):
        record = changes.active(self.root)
        self.assertIsNotNone(tdd_gates.guard(record, "src/calc.py"))
        self.assertIsNone(tdd_gates.guard(record, "tests/test_calc.py"))
        self.assertIsNone(tdd_gates.guard(record, self.started["spec"]))
        record["step"] = "implement"
        self.assertIsNotNone(tdd_gates.guard(record, "src/calc.py"))       # no RED yet
        record["tdd"] = {"runs": [{"phase": "red", "result": "FAILED"}]}
        self.assertIsNone(tdd_gates.guard(record, "src/calc.py"))

    def test_audit_mode_logs_but_does_not_block(self):
        code, out = self.hook(os.path.join(self.root, "src/calc.py"))
        self.assertEqual((code, out), (0, None))
        with open(os.path.join(self.root, hookd.DECISIONS_RELPATH), encoding="utf-8") as fh:
            last = [json.loads(line) for line in fh][-1]
        self.assertEqual((last["decision"], last["enforced"]), ("deny", False))
        self.assertIn("verify-pre", last["reason"])

    def test_block_mode_denies_production_writes_until_red(self):
        fx.write(self.root, ".spec-master/policy.json", json.dumps({"hooks_mode": "block"}))
        code, out = self.hook(os.path.join(self.root, "src/calc.py"))
        self.assertNotEqual((code, out), (0, None))
        self.assertEqual(self.hook(os.path.join(self.root, "tests/test_calc.py")), (0, None))


if __name__ == "__main__":
    unittest.main()
