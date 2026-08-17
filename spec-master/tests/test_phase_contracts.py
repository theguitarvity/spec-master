import json
from pathlib import Path
import shutil
import tempfile
import unittest

import _pathfix  # noqa: F401
import phase_contracts


class PhaseContractsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- allowlist rejection (guarded-mode-spec.md §16 unit test 5) -------

    def test_write_outside_allowlist_is_forbidden(self):
        changed = [".specify/memory/constitution.md", "src/app.py"]
        self.assertEqual(
            phase_contracts.forbidden_writes(changed, "constitution"),
            ["src/app.py"],
        )

    def test_protected_paths_always_forbidden_even_under_broad_allowlist(self):
        # "implement" allows "*", but PROTECTED_PATHS must still win.
        changed = ["src/app.py", ".spec-master/state.json", ".git/HEAD"]
        self.assertEqual(
            phase_contracts.forbidden_writes(changed, "implement"),
            [".git/HEAD", ".spec-master/state.json"],
        )

    # --- placeholder detection (unit test 6) -------------------------------

    def test_known_constitution_placeholders_are_detected(self):
        path = self.tmp / ".specify" / "memory" / "constitution.md"
        path.parent.mkdir(parents=True)
        path.write_text("## [SECTION_2_NAME]\n[GOVERNANCE_RULES]", encoding="utf-8")
        self.assertEqual(
            phase_contracts.placeholder_artifacts(self.tmp, "constitution"),
            [".specify/memory/constitution.md"],
        )

    def test_filled_artifact_has_no_placeholder(self):
        path = self.tmp / ".specify" / "memory" / "constitution.md"
        path.parent.mkdir(parents=True)
        path.write_text("# Real Constitution\n\nNo brackets here.", encoding="utf-8")
        self.assertEqual(phase_contracts.placeholder_artifacts(self.tmp, "constitution"), [])

    def test_task_story_labels_are_not_false_positive_placeholders(self):
        # [US1]/[P]/[X] are real Spec Kit tasks.md syntax, not unfilled
        # template markers — a generic "any [BRACKETED] text" regex would
        # wrongly flag a correctly-completed tasks.md (caught during
        # implementation of this feature's own controller.py tests).
        path = self.tmp / "specs" / "001-demo" / "tasks.md"
        path.parent.mkdir(parents=True)
        path.write_text(
            "- [ ] T001 [P] [US1] Create model in src/models/user.py\n"
            "- [x] T002 [US2] Wire endpoint\n",
            encoding="utf-8",
        )
        self.assertEqual(phase_contracts.placeholder_artifacts(self.tmp, "tasks"), [])

    # --- simulated tool-call detection (unit test 7) -----------------------

    def test_fake_tool_markers_detected(self):
        self.assertEqual(
            phase_contracts.validate_transcript("before <tool_call>ls</tool_call> after"),
            ["<tool_call>", "</tool_call>"],
        )
        self.assertEqual(phase_contracts.validate_transcript("plain text response"), [])

    # --- snapshot ignoring caches (unit test 13) ----------------------------

    def test_snapshot_ignores_caches_and_own_state(self):
        (self.tmp / "__pycache__").mkdir()
        (self.tmp / "__pycache__" / "mod.pyc").write_bytes(b"x")
        (self.tmp / ".venv" / "lib").mkdir(parents=True)
        (self.tmp / ".venv" / "lib" / "site.py").write_text("x", encoding="utf-8")
        (self.tmp / "node_modules" / "pkg").mkdir(parents=True)
        (self.tmp / "node_modules" / "pkg" / "index.js").write_text("x", encoding="utf-8")
        (self.tmp / ".spec-master").mkdir()
        (self.tmp / ".spec-master" / "state.json").write_text("{}", encoding="utf-8")
        (self.tmp / ".spec-master" / "failed-attempts").mkdir()
        (self.tmp / ".spec-master" / "failed-attempts" / "x.jsonl").write_text("x", encoding="utf-8")
        (self.tmp / "src").mkdir()
        (self.tmp / "src" / "real.py").write_text("real", encoding="utf-8")

        result = phase_contracts.snapshot(self.tmp)

        self.assertEqual(list(result), ["src/real.py"])

    def test_snapshot_ignores_own_logs_and_git(self):
        (self.tmp / ".git").mkdir()
        (self.tmp / ".git" / "HEAD").write_text("ref: refs/heads/main", encoding="utf-8")
        (self.tmp / ".spec-master" / "logs").mkdir(parents=True)
        (self.tmp / ".spec-master" / "logs" / "x.jsonl").write_text("x", encoding="utf-8")

        self.assertEqual(phase_contracts.snapshot(self.tmp), {})

    # --- PHASE_POLICY (§16 test_phase_contracts.py item 1) ------------------

    def test_phase_policy_classifies_every_phase(self):
        self.assertEqual(phase_contracts.PHASE_POLICY["constitution"], "produce-or-update")
        self.assertEqual(phase_contracts.PHASE_POLICY["specify"], "produce-or-update")
        self.assertEqual(phase_contracts.PHASE_POLICY["clarify"], "inspect-or-update")
        self.assertEqual(phase_contracts.PHASE_POLICY["plan"], "produce-or-update")
        self.assertEqual(phase_contracts.PHASE_POLICY["tasks"], "produce-or-update")
        self.assertEqual(phase_contracts.PHASE_POLICY["analyze"], "inspect-or-update")
        self.assertEqual(phase_contracts.PHASE_POLICY["implement"], "execute")
        self.assertEqual(phase_contracts.PHASE_POLICY["validate"], "produce-or-update")

    # --- resolve_active_feature_dir (§16 items 2-3) -------------------------

    def _write_feature_json(self, feature_directory) -> None:
        (self.tmp / ".specify").mkdir(parents=True, exist_ok=True)
        (self.tmp / ".specify" / "feature.json").write_text(
            json.dumps({"feature_directory": feature_directory}), encoding="utf-8",
        )

    def test_resolves_valid_feature_json(self):
        (self.tmp / "specs" / "002-demo").mkdir(parents=True)
        self._write_feature_json("specs/002-demo")
        resolved = phase_contracts.resolve_active_feature_dir(self.tmp)
        self.assertEqual(resolved, (self.tmp / "specs" / "002-demo").resolve())

    def test_missing_feature_json_raises(self):
        with self.assertRaises(phase_contracts.ActiveFeatureUnresolved):
            phase_contracts.resolve_active_feature_dir(self.tmp)

    def test_dotdot_feature_directory_rejected(self):
        self._write_feature_json("../escape")
        with self.assertRaises(phase_contracts.ActiveFeatureUnresolved):
            phase_contracts.resolve_active_feature_dir(self.tmp)

    def test_absolute_feature_directory_rejected(self):
        self._write_feature_json("/etc/passwd")
        with self.assertRaises(phase_contracts.ActiveFeatureUnresolved):
            phase_contracts.resolve_active_feature_dir(self.tmp)

    def test_symlink_escaping_feature_directory_rejected(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        (self.tmp / "specs").mkdir()
        (self.tmp / "specs" / "002-demo").symlink_to(outside, target_is_directory=True)
        self._write_feature_json("specs/002-demo")
        with self.assertRaises(phase_contracts.ActiveFeatureUnresolved):
            phase_contracts.resolve_active_feature_dir(self.tmp)

    def test_invalid_json_feature_file_rejected(self):
        (self.tmp / ".specify").mkdir(parents=True)
        (self.tmp / ".specify" / "feature.json").write_text("not json", encoding="utf-8")
        with self.assertRaises(phase_contracts.ActiveFeatureUnresolved):
            phase_contracts.resolve_active_feature_dir(self.tmp)

    # --- clarify_result_ok / analyze_result_ok (§16 items 5-6) -------------

    def test_clean_spec_is_clarify_eligible(self):
        (self.tmp / "specs" / "002-demo").mkdir(parents=True)
        (self.tmp / "specs" / "002-demo" / "spec.md").write_text(
            "# Spec\n\nComplete, no markers.", encoding="utf-8",
        )
        self._write_feature_json("specs/002-demo")
        self.assertTrue(phase_contracts.clarify_result_ok(self.tmp, {}))

    def test_spec_with_needs_clarification_marker_not_eligible(self):
        (self.tmp / "specs" / "002-demo").mkdir(parents=True)
        (self.tmp / "specs" / "002-demo" / "spec.md").write_text(
            "# Spec\n\nFR-001: system MUST [NEEDS CLARIFICATION: how?]", encoding="utf-8",
        )
        self._write_feature_json("specs/002-demo")
        self.assertFalse(phase_contracts.clarify_result_ok(self.tmp, {}))

    def test_clean_spec_plan_tasks_trio_is_analyze_eligible(self):
        feature = self.tmp / "specs" / "002-demo"
        feature.mkdir(parents=True)
        (feature / "spec.md").write_text("# Spec\n\nComplete.", encoding="utf-8")
        (feature / "plan.md").write_text("# Plan\n\nComplete.", encoding="utf-8")
        (feature / "tasks.md").write_text("# Tasks\n\n- [ ] T001 do thing", encoding="utf-8")
        self._write_feature_json("specs/002-demo")
        self.assertTrue(phase_contracts.analyze_result_ok(self.tmp, {}))

    def test_missing_plan_makes_analyze_ineligible(self):
        feature = self.tmp / "specs" / "002-demo"
        feature.mkdir(parents=True)
        (feature / "spec.md").write_text("# Spec\n\nComplete.", encoding="utf-8")
        (feature / "tasks.md").write_text("# Tasks\n\n- [ ] T001 do thing", encoding="utf-8")
        self._write_feature_json("specs/002-demo")
        self.assertFalse(phase_contracts.analyze_result_ok(self.tmp, {}))


if __name__ == "__main__":
    unittest.main()
