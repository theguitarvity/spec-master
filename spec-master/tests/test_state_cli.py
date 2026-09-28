import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

import _pathfix  # noqa: F401
import cli
import state as state_mod


def _run(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(list(argv))
    return code, buf.getvalue()


def _json(*argv):
    code, out = _run(*argv)
    return code, json.loads(out)


def _write(root, relative, text):
    path = os.path.join(root, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class TransitionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.path = os.path.join(self.root, ".spec-master", "state.json")
        _run("state", "init", "--path", self.path, "--context", "ctx.md")
        code, _ = _run("state", "upsert-feature", "--path", self.path, "--feature-json",
                       json.dumps({"id": "f1", "name": "F1", "spec_directory": "specs/001-f1"}))
        self.assertEqual(code, 0)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def transition(self, phase, status, *extra):
        return _json("state", "transition", "--path", self.path, "--feature", "f1",
                     "--phase", phase, "--status", status, "--no-hooks", *extra)

    def test_passed_without_artifact_is_refused_and_state_is_untouched(self):
        code, payload = self.transition("specify", "PASSED")
        self.assertEqual(code, 1)
        self.assertIn("without evidence", payload["error"])
        self.assertFalse(payload["evidence"]["ok"])
        feature = state_mod.find_feature(state_mod.load(self.path), "f1")
        self.assertEqual(feature["phases"]["specify"], "PENDING")
        self.assertNotIn("evidence", feature)

    def test_passed_with_artifact_records_evidence_and_returns_an_ack(self):
        _write(self.root, "specs/001-f1/spec.md", "# Spec\n\nClear.\n")
        code, payload = self.transition("specify", "PASSED")
        self.assertEqual(code, 0)
        self.assertEqual(payload, {"feature": "f1", "phase": "specify", "status": "PASSED",
                                   "previous": "PENDING", "evidence": {"verified": True, "artifacts": 1}})
        feature = state_mod.find_feature(state_mod.load(self.path), "f1")
        self.assertEqual(feature["phases"]["specify"], "PASSED")
        self.assertEqual(feature["evidence"]["specify"]["artifacts"][0]["path"], "specs/001-f1/spec.md")

    def test_order_guard_still_applies_before_evidence(self):
        code, payload = self.transition("plan", "PASSED")
        self.assertEqual(code, 1)
        self.assertIn("before 'clarify'", payload["error"])

    def test_non_passing_statuses_need_no_evidence(self):
        code, payload = self.transition("specify", "RUNNING")
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "RUNNING")
        self.assertNotIn("evidence", payload)

    def test_full_flag_prints_the_feature_record(self):
        code, payload = self.transition("specify", "RUNNING", "--full")
        self.assertEqual(code, 0)
        self.assertEqual(payload["id"], "f1")
        self.assertEqual(payload["phases"]["specify"], "RUNNING")

    def test_import_unverified_needs_a_reason_and_is_marked(self):
        code, payload = self.transition("specify", "PASSED", "--import-unverified")
        self.assertEqual(code, 1)
        self.assertIn("--reason", payload["error"])
        code, payload = self.transition("specify", "PASSED", "--import-unverified", "--reason", "legacy run")
        self.assertEqual(code, 0)
        self.assertEqual(payload["evidence"], {"verified": False, "artifacts": 0})
        code, shown = _json("state", "evidence", "--path", self.path, "--feature", "f1")
        self.assertEqual(shown["phases"], {"specify": "unverified"})

    def test_validate_passed_completes_the_feature(self):
        _write(self.root, "specs/001-f1/spec.md", "# Spec\n")
        _write(self.root, "specs/001-f1/plan.md", "# Plan\n")
        _write(self.root, "specs/001-f1/tasks.md", "- [X] T001 Build it\n")
        for phase in ("specify", "clarify", "plan", "tasks", "analyze", "implement"):
            code, payload = self.transition(phase, "PASSED")
            self.assertEqual(code, 0, payload)
        code, payload = self.transition("validate", "PASSED")
        self.assertEqual(code, 1)
        self.assertIn("traceability", payload["error"])
        code, _ = _run("traceability", "add", "--path", self.path, "--row-json",
                       json.dumps({"requirement": "R1", "source": "EXPLICIT", "feature": "f1", "test": "t"}))
        self.assertEqual(code, 0)
        code, payload = self.transition("validate", "PASSED")
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["feature_status"], "COMPLETED")

    def test_evidence_dry_run(self):
        code, payload = _json("state", "evidence", "--path", self.path, "--feature", "f1", "--phase", "plan")
        self.assertEqual(code, 0)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["phase"], "plan")


class UpsertCliTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.path = os.path.join(self.root, ".spec-master", "state.json")
        _run("state", "init", "--path", self.path, "--context", "ctx.md")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_upsert_refuses_phases_and_imports_with_a_reason(self):
        feature = {"id": "old", "status": "COMPLETED", "delivery": {"mode": "agentic-outside-spec-master"},
                   "phases": {phase: "PASSED" for phase in state_mod.FEATURE_PHASES}}
        code, payload = _json("state", "upsert-feature", "--path", self.path, "--feature-json", json.dumps(feature))
        self.assertEqual(code, 1)
        self.assertIn("only records metadata", payload["error"])
        code, payload = _json("state", "upsert-feature", "--path", self.path, "--feature-json", json.dumps(feature),
                              "--import-unverified", "--reason", "delivered outside the flow")
        self.assertEqual(code, 0)
        self.assertEqual(payload["imported_unverified"]["imported_phases"], list(state_mod.FEATURE_PHASES))
        stored = state_mod.find_feature(state_mod.load(self.path), "old")
        self.assertEqual({entry["verified"] for entry in stored["evidence"].values()}, {False})


class OutputDietTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        cli.PRETTY = False

    def test_budget_file_returns_ids_and_tokens_without_content(self):
        big = os.path.join(self.root, "big.md")
        small = os.path.join(self.root, "small.md")
        _write(self.root, "big.md", "x" * 40000)
        _write(self.root, "small.md", "hello world")
        code, payload = _json("budget", "file", "--files", f"{small},{big}", "--token-budget", "100")
        self.assertEqual(code, 0)
        self.assertEqual(payload["selected_ids"], [small])
        self.assertEqual(payload["omitted_ids"], [big])
        for entry in payload["selected"] + payload["omitted"]:
            self.assertNotIn("content", entry)
        self.assertEqual(payload["omitted"][0]["estimated_tokens"], 10000)
        code, payload = _json("budget", "file", "--files", f"{small},{big}", "--token-budget", "100",
                              "--with-content")
        self.assertEqual(payload["selected"][0]["content"], "hello world")
        self.assertNotIn("content", payload["omitted"][0])  # never echo what was left out

    def test_compact_by_default_and_pretty_on_request(self):
        code, out = _run("budget", "estimate", "abcd")
        self.assertEqual(out.strip(), '{"estimated_tokens":1}')
        code, out = _run("--pretty", "budget", "estimate", "abcd")
        self.assertIn('\n  "estimated_tokens": 1\n', out)


if __name__ == "__main__":
    unittest.main()
