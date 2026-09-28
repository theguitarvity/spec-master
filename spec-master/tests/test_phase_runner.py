import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import _pathfix  # noqa: F401
import phase_runner
from fixtures.fake_agent import FakeAgentStep, fake_subprocess_run


def _init_constitution(project: Path, text: str = "# [PROJECT_NAME] Constitution\n") -> None:
    path = project / ".specify" / "memory" / "constitution.md"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")


def _init_active_feature(project: Path, spec_text: str, plan_text: str = "# Plan\n\nOk.",
                          tasks_text: str = "# Tasks\n\n- [ ] T001 do thing") -> None:
    feature_dir = project / "specs" / "002-demo"
    feature_dir.mkdir(parents=True)
    (feature_dir / "spec.md").write_text(spec_text, encoding="utf-8")
    (feature_dir / "plan.md").write_text(plan_text, encoding="utf-8")
    (feature_dir / "tasks.md").write_text(tasks_text, encoding="utf-8")
    (project / ".specify").mkdir(exist_ok=True)
    (project / ".specify" / "feature.json").write_text(
        json.dumps({"feature_directory": "specs/002-demo"}), encoding="utf-8",
    )


NO_CHANGES_REQUIRED = json.dumps({
    "phase_result": "no_changes_required",
    "checks": {"needs_clarification_markers": 0, "user_decision_required": False},
})
USER_DECISION_REQUIRED = json.dumps({"phase_result": "user_decision_required"})


class PhaseRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, phase, steps, history=()):
        with patch("phase_runner.subprocess.run", side_effect=fake_subprocess_run(steps, self.tmp)):
            return phase_runner.run_phase(
                self.tmp, phase, "opencode", "fake-model", "prompt", timeout_seconds=30,
                history=history,
            )

    # unit test 8 / integration scenario 3 (guarded-mode-spec.md §16):
    # agent creates src/app.py during constitution.
    def test_early_implementation_during_constitution_is_critical(self):
        _init_constitution(self.tmp)
        step = FakeAgentStep(writes={
            ".specify/memory/constitution.md": "# Real Constitution\nPrinciples here.",
            "src/app.py": "print('hi')",
        })
        result = self._run("constitution", [step])
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("early_implementation", result["events"])
        self.assertIn("src/app.py", result["forbidden_writes"])

    def test_out_of_project_symlink_write_is_rejected(self):
        _init_constitution(self.tmp)
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        (self.tmp / "escape.md").symlink_to(outside / "secret.md")
        (outside / "secret.md").write_text("leaked", encoding="utf-8")

        step = FakeAgentStep(writes={
            ".specify/memory/constitution.md": "# Real Constitution\nPrinciples here.",
        })
        # The symlink already exists before the run; simulate the agent
        # "touching" it by rewriting through it during the fake step.
        step.writes["escape.md"] = "still leaked"
        result = self._run("constitution", [step])
        self.assertIn("out_of_project_write", result["events"])
        self.assertEqual(result["status"], "FAILED")

    def test_artifact_wrong_location_detected(self):
        # constitution.md written at the repo root instead of .specify/memory/.
        step = FakeAgentStep(writes={"constitution.md": "# Real Constitution"})
        result = self._run("constitution", [step])
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("artifact_wrong_location", result["events"])

    def test_ordinary_nonzero_exit_is_recoverable_tool_error(self):
        step = FakeAgentStep(returncode=1, stdout="some ordinary tool failure")
        result = self._run("constitution", [step])
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("recoverable_tool_error", result["events"])

    def test_valid_constitution_passes(self):
        step = FakeAgentStep(writes={
            ".specify/memory/constitution.md": "# Real Constitution\n\nPrinciples here.",
        })
        result = self._run("constitution", [step])
        self.assertEqual(result["status"], "PASSED")
        self.assertIsNone(result["reason"])

    def test_unsupported_integration_raises(self):
        with self.assertRaises(phase_runner.UnsupportedIntegrationError):
            phase_runner.run_phase(self.tmp, "constitution", "codex", "m", "p", 30)

    # --- clarify/analyze no-op decisions (§16 test_phase_runner.py) --------

    def test_clarify_noop_passes_on_clean_spec_with_valid_result(self):
        # Cenário A / §16 item 1.
        _init_active_feature(self.tmp, "# Spec\n\nComplete, no markers.")
        step = FakeAgentStep(writes={}, stdout=NO_CHANGES_REQUIRED)
        result = self._run("clarify", [step])
        self.assertEqual(result["status"], "PASSED")
        self.assertEqual(result["reason"], "valid_noop")
        self.assertEqual(result["outcome"], "no_changes_required")
        self.assertEqual(result["active_artifacts"], ["specs/002-demo/spec.md"])

    def test_clarify_noop_fails_without_structured_result(self):
        # §16 item 2.
        _init_active_feature(self.tmp, "# Spec\n\nComplete, no markers.")
        step = FakeAgentStep(writes={}, stdout="looks fine to me, no changes needed")
        result = self._run("clarify", [step])
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["reason"], "phase_result_missing")

    def test_clarify_noop_rejected_when_spec_still_has_marker(self):
        # Cenário B / §16 item 3.
        _init_active_feature(self.tmp, "# Spec\n\nFR-001: [NEEDS CLARIFICATION: how?]")
        step = FakeAgentStep(writes={}, stdout=NO_CHANGES_REQUIRED)
        result = self._run("clarify", [step])
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["reason"], "phase_result_invalid")

    def test_forbidden_write_beats_noop_claim(self):
        # Cenário D / §16 item 4.
        _init_active_feature(self.tmp, "# Spec\n\nComplete, no markers.")
        step = FakeAgentStep(
            writes={"coverage_analysis.md": "stray file"},
            stdout=NO_CHANGES_REQUIRED,
        )
        result = self._run("clarify", [step])
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["reason"], "forbidden_write")

    def test_timeout_beats_noop_claim(self):
        # §16 item 5 — spec.md §14 non-goal "considerar timeout como no-op válido".
        _init_active_feature(self.tmp, "# Spec\n\nComplete, no markers.")

        def _raise_timeout(*args, **kwargs):
            import subprocess
            raise subprocess.TimeoutExpired(cmd="opencode", timeout=30, output=NO_CHANGES_REQUIRED)

        with patch("phase_runner.subprocess.run", side_effect=_raise_timeout):
            result = phase_runner.run_phase(
                self.tmp, "clarify", "opencode", "fake-model", "prompt", timeout_seconds=30,
            )
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["reason"], "timeout")

    def test_analyze_noop_passes_when_clean(self):
        # Cenário E / §16 item 6.
        _init_active_feature(self.tmp, "# Spec\n\nComplete.")
        step = FakeAgentStep(writes={}, stdout=NO_CHANGES_REQUIRED)
        result = self._run("analyze", [step])
        self.assertEqual(result["status"], "PASSED")
        self.assertEqual(result["reason"], "valid_noop")

    def test_producer_phase_noop_still_fails_without_history(self):
        # §16 item 7 — even when a valid tasks.md already exists on disk
        # (e.g. left over from manual setup), an empty attempt `history`
        # means "no prior attempt to trust" and the no-op path never
        # applies — this is what makes it impossible to no-op-pass on a
        # phase's very first real attempt (spec.md §9).
        _init_active_feature(self.tmp, "# Spec\n\nComplete.")
        step = FakeAgentStep(writes={}, stdout=NO_CHANGES_REQUIRED)
        result = self._run("tasks", [step], history=())
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["reason"], "unchanged_artifact")

    def test_user_decision_required_beats_a_real_file_change(self):
        # analyze finding C1 — priority-order regression test.
        _init_active_feature(self.tmp, "# Spec\n\nComplete, no markers.")
        step = FakeAgentStep(
            writes={"specs/002-demo/spec.md": "# Spec\n\nUpdated."},
            stdout=USER_DECISION_REQUIRED,
        )
        result = self._run("clarify", [step])
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["reason"], "user_decision_required")

    # --- producer-phase retry trust (§9, research.md item 2) ----------------

    def test_producer_phase_noop_passes_with_clean_history(self):
        # An earlier (not-yet-promoted) attempt already produced a valid
        # tasks.md; this attempt makes no further change.
        _init_active_feature(self.tmp, "# Spec\n\nComplete.")
        clean_prior_attempt = {"forbidden_writes": [], "events": []}
        step = FakeAgentStep(writes={}, stdout="")
        result = self._run("tasks", [step], history=[clean_prior_attempt])
        self.assertEqual(result["status"], "PASSED")
        self.assertEqual(result["reason"], "valid_noop")
        self.assertEqual(result["outcome"], "no_changes_required")

    def test_producer_phase_noop_blocked_by_tainted_history(self):
        _init_active_feature(self.tmp, "# Spec\n\nComplete.")
        tainted_prior_attempt = {"forbidden_writes": ["src/app.py"], "events": ["early_implementation"]}
        step = FakeAgentStep(writes={}, stdout="")
        result = self._run("tasks", [step], history=[tainted_prior_attempt])
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["reason"], "unchanged_artifact")


class DeclaredQualityGateExecutionTests(unittest.TestCase):
    """`.spec-master/gates.json` cwd and timeout_seconds are honored when gates run."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _declare(self, gates):
        path = self.tmp / ".spec-master" / "gates.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(gates), encoding="utf-8")

    def test_declared_gate_runs_in_its_cwd(self):
        (self.tmp / "backend").mkdir()
        check = "import os, sys; sys.exit(0 if os.path.basename(os.getcwd()) == 'backend' else 3)"
        self._declare([
            {"name": "in backend", "command": [sys.executable, "-c", check], "cwd": "backend"},
            {"name": "at root", "command": [sys.executable, "-c", check]},
        ])
        results = phase_runner._run_quality_gates(self.tmp)
        self.assertEqual([(r["name"], r["result"], r["exit_code"]) for r in results],
                         [("in backend", "PASSED", 0), ("at root", "FAILED", 3)])

    def test_declared_gate_timeout_fails_the_gate(self):
        self._declare([{"name": "slow", "command": [sys.executable, "-c", "import time; time.sleep(3)"],
                        "timeout_seconds": 1}])
        [result] = phase_runner._run_quality_gates(self.tmp)
        self.assertEqual(result["result"], "FAILED")
        self.assertIsNone(result["exit_code"])
        self.assertTrue(result["timed_out"])
        self.assertTrue(result["blocking"])
        report = (self.tmp / ".spec-master" / "reports" / "quality-gates.md").read_text(encoding="utf-8")
        self.assertIn("**slow**", report)
        self.assertIn("FAILED", report)


if __name__ == "__main__":
    unittest.main()
