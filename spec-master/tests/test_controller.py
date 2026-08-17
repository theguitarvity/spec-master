import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import _pathfix  # noqa: F401
import controller
import execution_mode
import state as state_mod
from fixtures.fake_agent import FakeAgentStep, fake_subprocess_run


def _write_context(project: Path) -> None:
    (project / "context.md").write_text("# Demo context\n\nBuild a thing.", encoding="utf-8")


def _happy_step(phase: str, variant: str = "a") -> FakeAgentStep:
    writes = {
        "constitution": {".specify/memory/constitution.md": f"# Real Constitution {variant}\n\nPrinciples here."},
        "specify": {
            "specs/001-demo/spec.md": f"# Spec {variant}\n\nUser stories here.",
            ".specify/feature.json": json.dumps({"feature_directory": "specs/001-demo"}),
        },
        "clarify": {"specs/001-demo/spec.md": f"# Spec {variant} clarified\n\nUser stories here, clarified."},
        "plan": {"specs/001-demo/plan.md": f"# Plan {variant}\n\nTechnical approach."},
        "tasks": {"specs/001-demo/tasks.md": f"# Tasks {variant}\n\n- [ ] T001 do the thing"},
        "analyze": {"specs/001-demo/tasks.md": f"# Tasks {variant} re-checked\n\n- [ ] T001 do the thing"},
        "implement": {"specs/001-demo/tasks.md": f"# Tasks {variant} done\n\n- [x] T001 do the thing"},
        "validate": {".spec-master/reports/traceability.md": f"# Traceability {variant}\n\n| req | status |"},
    }[phase]
    return FakeAgentStep(writes=writes)


class ControllerTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        _write_context(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _new_state(self, mode="guarded", max_attempts=2, phase_timeout=30):
        state = state_mod.default_state("context.md")
        execution_mode.init_execution(state, mode, "opencode", "fake-model")
        state["execution"]["max_attempts_per_phase"] = max_attempts
        state["execution"]["phase_timeout_seconds"] = phase_timeout
        state["attempts"] = {}
        return state

    def _run_single_phase(self, state, phase, steps):
        with patch("phase_runner.subprocess.run", side_effect=fake_subprocess_run(steps, self.tmp)):
            return controller._run_phase_with_attempts(state, self.tmp, phase, feature_id=None)


class TestRunPhaseLoop(ControllerTestCase):
    # integration scenario 1 (guarded-mode-spec.md §16): valid constitution.
    def test_valid_constitution_is_promoted_to_passed(self):
        state = self._new_state()
        status = self._run_single_phase(state, "constitution", [_happy_step("constitution")])
        self.assertEqual(status, "PASSED")
        self.assertEqual(state["attempts"]["constitution"][-1]["status"], "PASSED")
        self.assertEqual(state["constitution"]["status"], "VALIDATED")

    # integration scenario 2: agent returns success without changing any artifact.
    def test_exit_zero_without_artifact_change_never_passes(self):
        state = self._new_state()
        step = FakeAgentStep(writes={}, returncode=0)
        status = self._run_single_phase(state, "constitution", [step])
        self.assertEqual(status, "BLOCKED")
        for attempt in state["attempts"]["constitution"]:
            self.assertEqual(attempt["status"], "FAILED")


class TestAttempts(ControllerTestCase):
    # integration scenario 6: first attempt fails, second passes.
    def test_first_attempt_fails_second_passes(self):
        state = self._new_state(max_attempts=2)
        bad = FakeAgentStep(writes={".specify/memory/constitution.md": "# [PROJECT_NAME] Constitution"})
        good = _happy_step("constitution")
        status = self._run_single_phase(state, "constitution", [bad, good])
        self.assertEqual(status, "PASSED")
        attempts = state["attempts"]["constitution"]
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]["status"], "FAILED")
        self.assertEqual(attempts[1]["status"], "PASSED")

    # integration scenario 7: attempts exhausted -> BLOCKED, transcript preserved.
    def test_attempts_exhausted_blocks_and_preserves_transcript(self):
        state = self._new_state(max_attempts=2)
        always_bad = FakeAgentStep(writes={".specify/memory/constitution.md": "# [PROJECT_NAME] Constitution"})
        status = self._run_single_phase(state, "constitution", [always_bad])
        self.assertEqual(status, "BLOCKED")
        self.assertEqual(len(state["attempts"]["constitution"]), 2)
        preserved = list((self.tmp / ".spec-master" / "failed-attempts" / "constitution").glob("*"))
        self.assertTrue(preserved, "failed attempt transcript was not preserved")


class TestModeFlag(ControllerTestCase):
    def test_native_mode_rejected_without_writing_state(self):
        args = controller.build_parser().parse_args([
            "run", "--project", str(self.tmp), "--context", "context.md",
            "--mode", "native", "--model", "fake-model",
        ])
        exit_code = controller.cmd_run(args)
        self.assertEqual(exit_code, 2)
        self.assertFalse((self.tmp / ".spec-master" / "state.json").exists())

    def test_guarded_and_auto_are_accepted(self):
        for mode in ("guarded", "auto"):
            with self.subTest(mode=mode):
                tmp = Path(tempfile.mkdtemp())
                self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
                _write_context(tmp)
                args = controller.build_parser().parse_args([
                    "run", "--project", str(tmp), "--context", "context.md",
                    "--mode", mode, "--model", "fake-model", "--max-attempts", "1",
                ])
                with patch("phase_runner.subprocess.run",
                           side_effect=fake_subprocess_run([_happy_step("constitution")], tmp)):
                    controller.cmd_run(args)
                state = state_mod.load(str(tmp / ".spec-master" / "state.json"))
                self.assertEqual(state["execution"]["requested_mode"], mode)


class TestAutoMigration(ControllerTestCase):
    # integration scenario 3: agent creates src/app.py during constitution.
    def test_early_implementation_migrates_auto_to_guarded(self):
        state = self._new_state(mode="auto", max_attempts=1)
        step = FakeAgentStep(writes={
            ".specify/memory/constitution.md": "# Real Constitution\n\nPrinciples here.",
            "src/app.py": "print('too early')",
        })
        self._run_single_phase(state, "constitution", [step])
        self.assertEqual(state["execution"]["active_mode"], "guarded")
        self.assertEqual(len(state["execution"]["mode_transitions"]), 1)

    # integration scenario 4: agent writes <tool_call> as text.
    def test_simulated_tool_call_migrates_auto_to_guarded(self):
        state = self._new_state(mode="auto", max_attempts=1)
        step = FakeAgentStep(
            writes={".specify/memory/constitution.md": "# Real Constitution\n\nPrinciples here."},
            stdout="<tool_call>{\"name\": \"bash\"}</tool_call>",
        )
        self._run_single_phase(state, "constitution", [step])
        self.assertEqual(state["execution"]["active_mode"], "guarded")

    def test_two_recoverable_events_across_different_phases_migrate(self):
        state = self._new_state(mode="auto", max_attempts=1)
        # constitution.md written at the wrong path -> artifact_wrong_location (recoverable).
        self._run_single_phase(
            state, "constitution",
            [FakeAgentStep(writes={"constitution.md": "# Real Constitution"})],
        )
        self.assertEqual(state["execution"]["active_mode"], "native")
        # specify leaves a placeholder in spec.md -> placeholder_not_removed (recoverable).
        self._run_single_phase(
            state, "specify",
            [FakeAgentStep(writes={
                "specs/001-demo/spec.md": "# [FEATURE NAME]",
                ".specify/feature.json": "{}",
            })],
        )
        self.assertEqual(state["execution"]["active_mode"], "guarded")


class TestNoReversionInController(ControllerTestCase):
    def test_guarded_run_never_touches_migration_state(self):
        state = self._new_state(mode="guarded", max_attempts=1)
        self._run_single_phase(state, "constitution", [_happy_step("constitution")])
        self.assertEqual(state["execution"]["mode_transitions"], [])
        self.assertEqual(state["execution"]["active_mode"], "guarded")


class TestResume(ControllerTestCase):
    def _full_run_args(self, tmp, max_attempts=2, phase_timeout=30):
        return controller.build_parser().parse_args([
            "run", "--project", str(tmp), "--context", "context.md",
            "--mode", "guarded", "--model", "fake-model",
            "--max-attempts", str(max_attempts), "--phase-timeout", str(phase_timeout),
        ])

    def test_resume_skips_passed_phase_with_matching_fingerprint(self):
        steps = [_happy_step(phase) for phase in controller.PHASES]
        with patch("phase_runner.subprocess.run", side_effect=fake_subprocess_run(steps, self.tmp)):
            controller.cmd_run(self._full_run_args(self.tmp))

        state = state_mod.load(str(self.tmp / ".spec-master" / "state.json"))
        self.assertEqual(state["attempts"]["constitution"][-1]["status"], "PASSED")

        resume_args = controller.build_parser().parse_args(["resume", "--project", str(self.tmp)])
        with patch("phase_runner.subprocess.run",
                   side_effect=fake_subprocess_run([_happy_step("constitution", "b")], self.tmp)) as mocked:
            controller.cmd_resume(resume_args)
            # If constitution had been re-attempted, this fake step would have
            # been consumed; instead resume must have skipped straight past it.
            self.assertEqual(mocked.call_count, 0)

    def test_stale_lock_is_reclaimed(self):
        lock_dir = self.tmp / ".spec-master"
        lock_dir.mkdir(parents=True)
        (lock_dir / "run.lock").write_text(
            json.dumps({"phase": "constitution", "pid": 1, "started_at": "2000-01-01T00:00:00Z"}),
            encoding="utf-8",
        )
        args = self._full_run_args(self.tmp, max_attempts=1)
        with patch("phase_runner.subprocess.run",
                   side_effect=fake_subprocess_run([_happy_step("constitution")], self.tmp)):
            exit_code = controller.cmd_run(args)
        self.assertNotEqual(exit_code, 2)
        self.assertFalse((lock_dir / "run.lock").exists())

    def test_fresh_lock_rejects_run(self):
        lock_dir = self.tmp / ".spec-master"
        lock_dir.mkdir(parents=True)
        (lock_dir / "run.lock").write_text(
            json.dumps({"phase": "constitution", "pid": 1, "started_at": controller._now_iso()}),
            encoding="utf-8",
        )
        args = self._full_run_args(self.tmp, phase_timeout=600)
        exit_code = controller.cmd_run(args)
        self.assertEqual(exit_code, 2)


class TestFullWorkflow(ControllerTestCase):
    # integration scenario 8 / acceptance criterion 6: all eight phases in
    # separate sessions, reaching COMPLETED.
    def test_full_workflow_reaches_completed_with_one_retry(self):
        bad_specify = FakeAgentStep(writes={"specs/001-demo/spec.md": "# [NEEDS CLARIFICATION]"})
        steps = [
            _happy_step("constitution"),
            bad_specify,
            _happy_step("specify"),
            _happy_step("clarify"),
            _happy_step("plan"),
            _happy_step("tasks"),
            _happy_step("analyze"),
            _happy_step("implement"),
            _happy_step("validate"),
        ]
        args = controller.build_parser().parse_args([
            "run", "--project", str(self.tmp), "--context", "context.md",
            "--mode", "guarded", "--model", "fake-model", "--max-attempts", "2",
        ])
        with patch("phase_runner.subprocess.run", side_effect=fake_subprocess_run(steps, self.tmp)):
            with patch("sys.stdout"):
                exit_code = controller.cmd_run(args)

        self.assertEqual(exit_code, 0)
        state = state_mod.load(str(self.tmp / ".spec-master" / "state.json"))
        self.assertEqual(state["status"], "COMPLETED")
        for phase in controller.PHASES:
            self.assertEqual(state["attempts"][phase][-1]["status"], "PASSED")
        specify_attempts = state["attempts"]["specify"]
        self.assertEqual(len(specify_attempts), 2)
        self.assertEqual(specify_attempts[0]["status"], "FAILED")
        self.assertEqual(specify_attempts[1]["status"], "PASSED")
        self.assertIn("quality_gates", state["attempts"]["validate"][-1])

    def test_report_quality_gates_field_present(self):
        steps = [_happy_step(phase) for phase in controller.PHASES]
        args = controller.build_parser().parse_args([
            "run", "--project", str(self.tmp), "--context", "context.md",
            "--mode", "guarded", "--model", "fake-model", "--max-attempts", "1",
        ])
        with patch("phase_runner.subprocess.run", side_effect=fake_subprocess_run(steps, self.tmp)):
            with patch("builtins.print") as mocked_print:
                controller.cmd_run(args)
        printed = "\n".join(str(call.args[0]) if call.args else "" for call in mocked_print.call_args_list)
        self.assertIn("quality_gates", printed)


class TestStatus(ControllerTestCase):
    def test_status_with_no_state_file_returns_empty_payload(self):
        args = controller.build_parser().parse_args(["status", "--project", str(self.tmp)])
        with patch("builtins.print") as mocked_print:
            exit_code = controller.cmd_status(args)
        self.assertEqual(exit_code, 0)
        printed = json.loads(mocked_print.call_args.args[0])
        self.assertEqual(printed, {"execution": None, "phases": {}, "attempts_summary": {}, "blocked_phase": None})


if __name__ == "__main__":
    unittest.main()
