import os
import shutil
import tempfile
import unittest

import _pathfix  # noqa: F401
import evidence


def _write(root, relative, text):
    path = os.path.join(root, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


class EvidenceCheckTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.feature = {"id": "f1", "spec_directory": "specs/001-f1", "phases": {}}

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def failed(self, result):
        return [c["name"] for c in result["checks"] if not c["ok"]]

    def test_missing_spec_directory_fails(self):
        result = evidence.check(self.root, {"id": "f1"}, "specify")
        self.assertFalse(result["ok"])
        self.assertEqual(self.failed(result), ["spec_directory"])

    def test_spec_directory_must_exist_and_stay_inside_the_project(self):
        self.assertFalse(evidence.check(self.root, self.feature, "specify")["ok"])
        escaping = {"id": "f1", "spec_directory": "../elsewhere"}
        self.assertIn("not a safe relative path", evidence.check(self.root, escaping, "specify")["checks"][0]["detail"])

    def test_specify_passes_with_a_clean_spec(self):
        _write(self.root, "specs/001-f1/spec.md", "# Spec\n\nDone.\n")
        result = evidence.check(self.root, self.feature, "specify")
        self.assertTrue(result["ok"])
        self.assertEqual(result["artifacts"][0]["path"], "specs/001-f1/spec.md")
        self.assertEqual(len(result["artifacts"][0]["sha256"]), 64)

    def test_placeholders_and_empty_files_fail(self):
        _write(self.root, "specs/001-f1/spec.md", "# [FEATURE NAME]\n\n[NEEDS CLARIFICATION: scope]\n")
        result = evidence.check(self.root, self.feature, "clarify")
        self.assertFalse(result["ok"])
        self.assertIn("unresolved placeholders", result["checks"][0]["detail"])
        _write(self.root, "specs/001-f1/plan.md", "")
        self.assertIn("missing or empty", evidence.check(self.root, self.feature, "plan")["checks"][0]["detail"])

    def test_other_feature_artifacts_do_not_count(self):
        # The global `specs/*/plan.md` glob was satisfied by any feature.
        _write(self.root, "specs/002-other/plan.md", "# Plan\n")
        os.makedirs(os.path.join(self.root, "specs", "001-f1"))
        self.assertFalse(evidence.check(self.root, self.feature, "plan")["ok"])

    def test_analyze_needs_all_three_artifacts(self):
        for name in ("spec.md", "plan.md"):
            _write(self.root, f"specs/001-f1/{name}", "# ok\n")
        result = evidence.check(self.root, self.feature, "analyze")
        self.assertEqual(self.failed(result), ["artifact:tasks.md"])

    def test_implement_requires_every_task_checked(self):
        _write(self.root, "specs/001-f1/tasks.md",
               "# Tasks\n\n- [X] T001 Write the module\n- [ ] T002 Wire the CLI\n- [ ] T002a Test it\n")
        result = evidence.check(self.root, self.feature, "implement")
        self.assertEqual(self.failed(result), ["tasks_checked"])
        self.assertIn("T002, T002a", result["checks"][-1]["detail"])
        _write(self.root, "specs/001-f1/tasks.md", "# Tasks\n\n- [X] T001 a\n- [x] T002 b\n")
        self.assertTrue(evidence.check(self.root, self.feature, "implement")["ok"])

    def test_validate_needs_traceability_rows(self):
        self.assertFalse(evidence.check(self.root, self.feature, "validate", traceability_rows=[])["ok"])
        rows = [{"requirement": "R1", "feature": "f1"}]
        self.assertTrue(evidence.check(self.root, self.feature, "validate", traceability_rows=rows)["ok"])

    def test_unknown_phase(self):
        with self.assertRaises(evidence.EvidenceError):
            evidence.check(self.root, self.feature, "deploy")


class EvidenceRecordTests(unittest.TestCase):
    def test_record_and_summary(self):
        feature = {"id": "f1", "phases": {"specify": "PASSED", "clarify": "SKIPPED", "plan": "PASSED",
                                          "tasks": "PASSED", "analyze": "PENDING"}}
        ok = {"feature": "f1", "phase": "specify", "ok": True,
              "checks": [{"name": "artifact:spec.md", "ok": True, "detail": "x"}],
              "artifacts": [{"path": "specs/001/spec.md", "sha256": "0" * 64, "bytes": 3}]}
        entry = evidence.record(feature, ok, now="2026-09-28T00:00:00Z")
        self.assertEqual(entry, {"verified": True, "at": "2026-09-28T00:00:00Z",
                                 "checks": ["artifact:spec.md"], "artifacts": ok["artifacts"]})
        evidence.record_unverified(feature, "plan", "delivered before Spec Master", now="2026-09-28T00:00:00Z")
        self.assertEqual(evidence.summary(feature),
                         {"specify": "verified", "plan": "unverified", "tasks": "missing"})

    def test_failed_results_and_blank_reasons_are_refused(self):
        with self.assertRaises(evidence.EvidenceError):
            evidence.record({}, {"phase": "plan", "ok": False, "checks": [], "artifacts": []})
        with self.assertRaises(evidence.EvidenceError):
            evidence.record_unverified({}, "plan", "  ")

    def test_open_tasks(self):
        text = "- [ ] T001 a\n  - [ ] not a task id\n* [ ] T010 b\n- [x] T011 c\n"
        self.assertEqual(evidence.open_tasks(text), ["T001", "T010"])


if __name__ == "__main__":
    unittest.main()
