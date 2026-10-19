from pathlib import Path
import shutil
import tempfile
import unittest

import _pathfix  # noqa: F401
import phase_contracts


class ScopedContractTests(unittest.TestCase):
    """Contracts narrowed to one feature directory (multi-feature projects)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, relative, text="# ok\n"):
        path = self.tmp / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_patterns_are_rewritten_to_the_feature_directory(self):
        self.assertEqual(phase_contracts.phase_artifacts("specify", "specs/002-b"), ("specs/002-b/spec.md",))
        self.assertEqual(phase_contracts.phase_artifacts("specify"), ("specs/*/spec.md", ".specify/feature.json"))
        self.assertEqual(
            phase_contracts.scoped_patterns(phase_contracts.PHASE_ALLOWED_WRITES["specify"], "specs/002-b",
                                            keep_feature_json=True),
            ("specs/002-b/*", ".specify/feature.json"),
        )
        with self.assertRaises(ValueError):
            phase_contracts.scoped_patterns(("specs/*/spec.md",), "../outside")

    def test_another_feature_does_not_satisfy_the_contract(self):
        self.write("specs/001-a/plan.md")
        self.assertEqual(phase_contracts.validate_artifacts(self.tmp, "plan"), [])  # historical global glob
        self.assertEqual(phase_contracts.validate_artifacts(self.tmp, "plan", "specs/002-b"), ["specs/002-b/plan.md"])

    def test_placeholders_of_another_feature_do_not_block(self):
        self.write("specs/001-a/tasks.md", "# [FEATURE NAME]\n")
        self.write("specs/002-b/tasks.md", "- [ ] T001 real task\n")
        self.assertEqual(phase_contracts.placeholder_artifacts(self.tmp, "tasks"), ["specs/001-a/tasks.md"])
        self.assertEqual(phase_contracts.placeholder_artifacts(self.tmp, "tasks", "specs/002-b"), [])

    def test_writes_to_another_feature_are_forbidden_when_scoped(self):
        changed = ["specs/002-b/spec.md", "specs/001-a/spec.md", ".specify/feature.json"]
        self.assertEqual(phase_contracts.forbidden_writes(changed, "specify"), [])
        self.assertEqual(phase_contracts.forbidden_writes(changed, "specify", "specs/002-b"), ["specs/001-a/spec.md"])

    def test_feature_dir_path(self):
        (self.tmp / "specs" / "002-b").mkdir(parents=True)
        self.assertEqual(phase_contracts.feature_dir_path(self.tmp, "specs/002-b"),
                         (self.tmp / "specs" / "002-b").resolve())
        for bad in ("specs/404", "../x"):
            with self.subTest(bad=bad):
                with self.assertRaises(phase_contracts.ActiveFeatureUnresolved):
                    phase_contracts.feature_dir_path(self.tmp, bad)

    def test_noop_predicates_use_the_known_directory_without_feature_json(self):
        self.write("specs/002-b/spec.md", "# Spec\n")
        self.write("specs/002-b/plan.md", "# Plan\n")
        self.write("specs/002-b/tasks.md", "- [ ] T001 x\n")
        self.assertTrue(phase_contracts.clarify_result_ok(self.tmp, {}, "specs/002-b"))
        self.assertTrue(phase_contracts.analyze_result_ok(self.tmp, {}, "specs/002-b"))
        with self.assertRaises(phase_contracts.ActiveFeatureUnresolved):
            phase_contracts.clarify_result_ok(self.tmp, {})  # no .specify/feature.json

    def test_placeholder_markers(self):
        self.assertEqual(phase_contracts.placeholder_markers("# Clean\n[US1] [P] [X]"), [])
        self.assertEqual(phase_contracts.placeholder_markers("[DATE] and NEEDS CLARIFICATION"),
                         ["[DATE]", "NEEDS CLARIFICATION"])


if __name__ == "__main__":
    unittest.main()
