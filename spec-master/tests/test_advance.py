"""`state advance` (P1): transition + round + traceability + next in one call."""
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

import _pathfix  # noqa: F401
import advance
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


ROUND = {"round_id": "r-x", "started_at": "2026-10-19T10:00:00Z", "ended_at": "2026-10-19T10:05:00Z"}
ROW = {"requirement": "R1", "source": "doc", "feature": "f1", "spec": "s", "plan": "p", "task": "T1",
       "test": "t", "status": "COVERED"}


class NextPhaseTests(unittest.TestCase):
    def test_first_phase_not_done(self):
        feature = {"phases": {p: "PENDING" for p in state_mod.FEATURE_PHASES}}
        self.assertEqual(state_mod.next_phase(feature), "specify")
        feature["phases"]["specify"] = "PASSED"
        feature["phases"]["clarify"] = "SKIPPED"
        self.assertEqual(state_mod.next_phase(feature), "plan")

    def test_none_when_all_done(self):
        feature = {"phases": {p: "PASSED" for p in state_mod.FEATURE_PHASES}}
        self.assertIsNone(state_mod.next_phase(feature))

    def test_failed_phase_is_next(self):
        feature = {"phases": {p: "PENDING" for p in state_mod.FEATURE_PHASES}}
        feature["phases"]["specify"] = "FAILED"
        self.assertEqual(state_mod.next_phase(feature), "specify")


class AdvanceHelpersTests(unittest.TestCase):
    def test_parse_round_requires_object(self):
        with self.assertRaises(ValueError):
            advance.parse_round("[1]")
        with self.assertRaises(ValueError):
            advance.parse_round("{nope")
        self.assertEqual(advance.parse_round(json.dumps(ROUND))["round_id"], "r-x")

    def test_parse_rows_requires_list_of_objects(self):
        with self.assertRaises(ValueError):
            advance.parse_rows('{"a": 1}')
        with self.assertRaises(ValueError):
            advance.parse_rows("[1]")
        self.assertEqual(len(advance.parse_rows(json.dumps([ROW]))), 1)

    def test_next_block_has_hint_and_tier(self):
        feature = {"phases": {p: "PENDING" for p in state_mod.FEATURE_PHASES}, "risk": {"tier": "XS"}}
        feature["phases"]["specify"] = "PASSED"
        block = advance.next_block(feature)
        self.assertEqual(block["phase"], "clarify")
        self.assertIn(block["hint"]["model"], ("fast", "balanced", "deep"))
        self.assertIn(block["hint"]["effort"], ("low", "medium", "high"))
        self.assertIn("skippable", block["clarify"])

    def test_next_block_none_when_done(self):
        feature = {"phases": {p: "PASSED" for p in state_mod.FEATURE_PHASES}}
        self.assertIsNone(advance.next_block(feature))


class AdvanceCliTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.path = os.path.join(self.root, ".spec-master", "state.json")
        _run("state", "init", "--path", self.path, "--context", "ctx.md")
        _run("state", "upsert-feature", "--path", self.path, "--feature-json",
             json.dumps({"id": "f1", "name": "F1", "spec_directory": "specs/001-f1"}))
        self.rounds = os.path.join(self.root, ".spec-master", "metrics", "rounds.json")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _advance(self, phase, status, *extra):
        return _json("state", "advance", "--path", self.path, "--feature", "f1", "--phase", phase,
                     "--status", status, *extra)

    def test_running_gives_ack_and_same_phase_next(self):
        code, out = self._advance("specify", "RUNNING")
        self.assertEqual(code, 0)
        self.assertEqual(out["phase"], "specify")
        self.assertEqual(out["next"]["phase"], "specify")
        self.assertEqual(out["next"]["status"], "RUNNING")

    def test_passed_with_round_and_rows(self):
        _write(self.root, "specs/001-f1/spec.md", "# Spec\n")
        self._advance("specify", "RUNNING")
        code, out = self._advance("specify", "PASSED", "--round-json", json.dumps(ROUND),
                                  "--trace-json", json.dumps([ROW]))
        self.assertEqual(code, 0, out)
        self.assertEqual(out["next"]["phase"], "clarify")
        self.assertEqual(out["round"]["appended"], "r-x")
        self.assertEqual(out["traceability"], 1)
        with open(self.rounds, encoding="utf-8") as fh:
            rows = json.load(fh)
        self.assertEqual(rows[0]["round_id"], "r-x")
        self.assertEqual(rows[0]["phase"], "specify")
        self.assertEqual(rows[0]["feature_id"], "f1")
        s = state_mod.load(self.path)
        import traceability
        self.assertEqual(len(traceability.load_rows(s, self.path, feature="f1")), 1)

    def test_evidence_missing_writes_nothing(self):
        self._advance("specify", "RUNNING")
        code, out = self._advance("specify", "PASSED", "--round-json", json.dumps(ROUND),
                                  "--trace-json", json.dumps([ROW]))
        self.assertEqual(code, 1)
        self.assertIn("evidence", out["error"])
        self.assertFalse(os.path.exists(self.rounds))
        s = state_mod.load(self.path)
        import traceability
        self.assertEqual(traceability.load_rows(s, self.path, feature="f1"), [])
        self.assertEqual(state_mod.find_feature(s, "f1")["phases"]["specify"], "RUNNING")

    def test_invalid_json_fails_before_any_write(self):
        _write(self.root, "specs/001-f1/spec.md", "# Spec\n")
        self._advance("specify", "RUNNING")
        code, out = self._advance("specify", "PASSED", "--round-json", "{bad")
        self.assertEqual(code, 1)
        s = state_mod.load(self.path)
        self.assertEqual(state_mod.find_feature(s, "f1")["phases"]["specify"], "RUNNING")

    def test_invalid_round_fails_before_transition(self):
        _write(self.root, "specs/001-f1/spec.md", "# Spec\n")
        self._advance("specify", "RUNNING")
        bad = {"round_id": "r-bad", "started_at": "2026-10-19T11:00:00Z"}  # no ended_at
        code, out = self._advance("specify", "PASSED", "--round-json", json.dumps(bad))
        self.assertEqual(code, 1)
        s = state_mod.load(self.path)
        self.assertEqual(state_mod.find_feature(s, "f1")["phases"]["specify"], "RUNNING")

    def test_validate_rows_in_same_call_count_as_evidence(self):
        for name in ("spec.md", "plan.md", "tasks.md"):
            _write(self.root, f"specs/001-f1/{name}", "- [x] T001 done\n" if name == "tasks.md" else "# x\n")
        for phase in ("specify", "clarify", "plan", "tasks", "analyze", "implement"):
            self._advance(phase, "RUNNING")
            code, _ = self._advance(phase, "PASSED")
            self.assertEqual(code, 0, phase)
        self._advance("validate", "RUNNING")
        code, out = self._advance("validate", "PASSED", "--trace-json", json.dumps([ROW]))
        self.assertEqual(code, 0, out)
        self.assertIsNone(out["next"])
        self.assertEqual(out["feature_status"], "COMPLETED")


if __name__ == "__main__":
    unittest.main()
