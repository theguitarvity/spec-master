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


if __name__ == "__main__":
    unittest.main()
