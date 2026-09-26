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


def _clarify_noop_step(spec_content="# Spec\n\nComplete, no markers.") -> FakeAgentStep:
    structured = json.dumps({
        "phase_result": "no_changes_required",
        "checks": {"needs_clarification_markers": 0, "user_decision_required": False},
    })
    # No write to spec.md at all — this is the point of a no-op.
    return FakeAgentStep(writes={}, stdout=structured)


class TestPaused(ControllerTestCase):
    # §16 test_controller.py item 2: user_decision_required pauses without
    # consuming a new attempt.
    def test_user_decision_required_pauses_without_burning_attempt(self):
        state = self._new_state(mode="guarded", max_attempts=1)
        step = FakeAgentStep(writes={}, stdout=json.dumps({"phase_result": "user_decision_required"}))
        with patch("phase_runner.subprocess.run", side_effect=fake_subprocess_run([step], self.tmp)):
            status = controller._run_phase_with_attempts(state, self.tmp, "clarify", feature_id=None)
        self.assertEqual(status, "PAUSED")
        self.assertEqual(state["status"], "PAUSED")
        attempts = state["attempts"]["clarify"]
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["reason"], "user_decision_required")
        # The attempt budget (max_attempts=1) was NOT consumed by the pause.
        self.assertEqual(controller._consumed_attempts(attempts), 0)


class TestContractRevalidation(ControllerTestCase):
    # §16 test_controller.py items 3-4; Cenário G; acceptance criterion 8.
    def test_resume_revalidates_a_pre_feature_blocked_clarify_attempt(self):
        state = self._new_state(mode="guarded", max_attempts=1)
        # Simulate a real spec.md already complete on disk (as it would be
        # after a successful `specify`), and an old, pre-this-feature
        # attempt record: no contract_version, blocked as missing_artifact,
        # with a transcript that (since this feature didn't exist yet) has
        # no structured phase_result block at all.
        feature_dir = self.tmp / "specs" / "001-demo"
        feature_dir.mkdir(parents=True)
        (feature_dir / "spec.md").write_text("# Spec\n\nComplete, no markers.", encoding="utf-8")
        (self.tmp / ".specify").mkdir(parents=True)
        (self.tmp / ".specify" / "feature.json").write_text(
            json.dumps({"feature_directory": "specs/001-demo"}), encoding="utf-8",
        )
        old_transcript = self.tmp / ".spec-master" / "logs" / "old-clarify.jsonl"
        old_transcript.parent.mkdir(parents=True)
        old_transcript.write_text("looks complete to me, nothing to change", encoding="utf-8")
        context_hash = controller._context_hash(self.tmp, state["context"])
        state["attempts"]["clarify"] = [{
            "number": 1,
            "status": "FAILED",
            "reason": "missing_artifact",
            "transcript": str(old_transcript),
            "forbidden_writes": [],
            "events": [],
            "context_hash": context_hash,
            # deliberately no contract_version key — a pre-feature record.
        }]

        # The old transcript has no structured result, so the cheap
        # revalidation can't apply — expect a fall-through to a real,
        # live attempt, which this time succeeds via the new no-op path.
        with patch("phase_runner.subprocess.run",
                   side_effect=fake_subprocess_run([_clarify_noop_step()], self.tmp)):
            status = controller._run_phase_with_attempts(state, self.tmp, "clarify", feature_id=None)

        self.assertEqual(status, "PASSED")
        attempts = state["attempts"]["clarify"]
        self.assertEqual(len(attempts), 2)
        # The original blocked entry must survive untouched.
        self.assertEqual(attempts[0]["reason"], "missing_artifact")
        self.assertEqual(attempts[0]["status"], "FAILED")
        self.assertEqual(attempts[1]["status"], "PASSED")
        self.assertEqual(attempts[1]["reason"], "valid_noop")

    def test_cheap_revalidation_skips_subprocess_when_old_transcript_has_result(self):
        # A blocked attempt whose transcript *does* have a valid structured
        # result (e.g. blocked for an unrelated reason after this feature
        # shipped) is promoted with zero new subprocess calls.
        state = self._new_state(mode="guarded", max_attempts=1)
        feature_dir = self.tmp / "specs" / "001-demo"
        feature_dir.mkdir(parents=True)
        (feature_dir / "spec.md").write_text("# Spec\n\nComplete, no markers.", encoding="utf-8")
        (self.tmp / ".specify").mkdir(parents=True)
        (self.tmp / ".specify" / "feature.json").write_text(
            json.dumps({"feature_directory": "specs/001-demo"}), encoding="utf-8",
        )
        old_transcript = self.tmp / ".spec-master" / "logs" / "old-clarify.jsonl"
        old_transcript.parent.mkdir(parents=True)
        old_transcript.write_text(json.dumps({
            "phase_result": "no_changes_required",
            "checks": {"needs_clarification_markers": 0, "user_decision_required": False},
        }), encoding="utf-8")
        context_hash = controller._context_hash(self.tmp, state["context"])
        state["attempts"]["clarify"] = [{
            "number": 1,
            "status": "FAILED",
            "reason": "unchanged_artifact",
            "transcript": str(old_transcript),
            "forbidden_writes": [],
            "events": [],
            "context_hash": context_hash,
            "contract_version": 1,
        }]

        with patch("phase_runner.subprocess.run") as mocked_run:
            status = controller._run_phase_with_attempts(state, self.tmp, "clarify", feature_id=None)
            mocked_run.assert_not_called()

        self.assertEqual(status, "PASSED")
        attempts = state["attempts"]["clarify"]
        self.assertEqual(attempts[-1]["source"], "contract_revalidation")


class TestFullWorkflowWithNoops(ControllerTestCase):
    # §16 test_controller.py item 5.
    def test_workflow_completes_with_clarify_and_analyze_noops(self):
        steps = [
            _happy_step("constitution"),
            _happy_step("specify"),
            _clarify_noop_step(),
            _happy_step("plan"),
            _happy_step("tasks"),
            FakeAgentStep(writes={}, stdout=json.dumps({
                "phase_result": "no_changes_required",
                "checks": {"critical_findings": 0, "high_findings": 0, "spec_drift": False,
                           "user_decision_required": False},
            })),
            _happy_step("implement"),
            _happy_step("validate"),
        ]
        args = controller.build_parser().parse_args([
            "run", "--project", str(self.tmp), "--context", "context.md",
            "--mode", "guarded", "--model", "fake-model", "--max-attempts", "1",
        ])
        with patch("phase_runner.subprocess.run", side_effect=fake_subprocess_run(steps, self.tmp)):
            with patch("sys.stdout"):
                exit_code = controller.cmd_run(args)

        self.assertEqual(exit_code, 0)
        state = state_mod.load(str(self.tmp / ".spec-master" / "state.json"))
        self.assertEqual(state["status"], "COMPLETED")
        self.assertEqual(state["attempts"]["clarify"][-1]["reason"], "valid_noop")
        self.assertEqual(state["attempts"]["analyze"][-1]["reason"], "valid_noop")


class TestOutcomesInReport(ControllerTestCase):
    # spec.md §18 criterion 9 — analyze finding H1 fix.
    def test_report_distinguishes_artifact_updated_from_no_changes_required(self):
        steps = [
            _happy_step("constitution"),
            _happy_step("specify"),
            _clarify_noop_step(),
            _happy_step("plan"),
            _happy_step("tasks"),
            _happy_step("analyze"),
            _happy_step("implement"),
            _happy_step("validate"),
        ]
        args = controller.build_parser().parse_args([
            "run", "--project", str(self.tmp), "--context", "context.md",
            "--mode", "guarded", "--model", "fake-model", "--max-attempts", "1",
        ])
        with patch("phase_runner.subprocess.run", side_effect=fake_subprocess_run(steps, self.tmp)):
            with patch("builtins.print") as mocked_print:
                controller.cmd_run(args)
        final_payload = json.loads(mocked_print.call_args.args[0])
        self.assertEqual(final_payload["outcomes"]["specify"], "artifact_updated")
        self.assertEqual(final_payload["outcomes"]["clarify"], "no_changes_required")


class TestCompatibilityWithFeature1Only(ControllerTestCase):
    # NPV-012 — analyze finding M1.
    def test_loading_a_pre_feature_completed_state_does_not_crash(self):
        state = self._new_state(mode="guarded", max_attempts=2)
        state["status"] = "COMPLETED"
        old_style_attempt = {
            "number": 1,
            "status": "PASSED",
            "reason": None,
            "events": [],
            "transcript": str(self.tmp / "nonexistent.jsonl"),
            "changed_paths": [".specify/memory/constitution.md"],
            "forbidden_writes": [],
            "quality_gates": None,
            "started_at": "2026-08-01T00:00:00Z",
            "finished_at": "2026-08-01T00:00:05Z",
            "context_hash": "deadbeef",
            # no contract_version/policy/outcome/active_artifacts/structured_result/source
        }
        state["attempts"] = {"constitution": [old_style_attempt]}
        state_mod.save(str(self.tmp / ".spec-master" / "state.json"), state)

        args = controller.build_parser().parse_args(["status", "--project", str(self.tmp)])
        with patch("builtins.print") as mocked_print:
            exit_code = controller.cmd_status(args)
        self.assertEqual(exit_code, 0)
        payload = json.loads(mocked_print.call_args.args[0])
        self.assertEqual(payload["phases"]["constitution"], "PASSED")

        self.assertIsNone(
            controller._try_contract_revalidation(self.tmp, "constitution", [old_style_attempt], "deadbeef")
        )


class TestRiskProfileSkip(ControllerTestCase):
    # roadmap item 15: an XS/S feature's clarify is skippable in guarded mode too.
    def _drive(self, tier, steps):
        state = self._new_state()
        state_mod.upsert_feature(state, {"id": "001-demo", "name": "Demo", "risk": {"tier": tier}})
        state_mod.save(str(self.tmp / ".spec-master" / "state.json"), state)
        with patch("phase_runner.subprocess.run", side_effect=fake_subprocess_run(steps, self.tmp)):
            with patch("builtins.print") as mocked_print:
                exit_code = controller._drive_workflow(state, self.tmp, "001-demo")
        return exit_code, state, json.loads(mocked_print.call_args.args[0])

    def test_skippable_tier_records_clarify_skipped_without_running_it(self):
        steps = [_happy_step(phase) for phase in controller.PHASES if phase != "clarify"]
        exit_code, state, report = self._drive("XS", steps)
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["workflow_status"], "COMPLETED")
        self.assertEqual(report["phases"]["clarify"], "SKIPPED")
        self.assertNotIn("clarify", state["attempts"])
        phases = state_mod.find_feature(state, "001-demo")["phases"]
        self.assertEqual(phases["clarify"], "SKIPPED")
        self.assertEqual(phases["plan"], "PASSED")
        self.assertEqual(phases["validate"], "PASSED")

    def test_required_tier_still_runs_clarify(self):
        steps = [_happy_step(phase) for phase in controller.PHASES]
        exit_code, state, report = self._drive("M", steps)
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["phases"]["clarify"], "PASSED")
        self.assertEqual(state_mod.find_feature(state, "001-demo")["phases"]["clarify"], "PASSED")

    def test_feature_without_risk_tier_runs_clarify(self):
        self.assertFalse(controller._skip_by_risk_profile(
            {"features": [{"id": "x", "phases": {"specify": "PASSED", "clarify": "PENDING"}}]}, "x", "clarify"))
        self.assertFalse(controller._skip_by_risk_profile(
            {"features": [{"id": "x", "risk": {"tier": "XS"}, "phases": {"specify": "PASSED"}}]}, "x", "plan"))


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
