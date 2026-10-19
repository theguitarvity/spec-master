import _pathfix  # noqa: F401

import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import ledger
import statusline
from test_telemetry import SESSION, _main_session_lines, _write_jsonl


class StatuslineTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, ".spec-master"))
        self.transcript = _write_jsonl(os.path.join(self.root, "t.jsonl"), _main_session_lines())
        state = {"features": [{"id": "feat-a", "phases": {"specify": "PASSED", "implement": "RUNNING"},
                               "risk": {"tier": "M"}}]}
        with open(os.path.join(self.root, ".spec-master", "state.json"), "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        os.makedirs(os.path.join(self.root, ".spec-master", "metrics"))
        with open(os.path.join(self.root, ".spec-master", "metrics", "prices.json"), "w", encoding="utf-8") as fh:
            json.dump({"claude-test-model": {"input": 1, "output": 1, "cache_read": 1, "cache_write": 1}}, fh)

    def payload(self, **extra):
        return {"session_id": SESSION, "transcript_path": self.transcript,
                "workspace": {"current_dir": self.root}, **extra}

    def test_line_has_feature_phase_tier_tokens_cost_cache_and_context(self):
        line = statusline.render(self.payload(context_window={"used_percentage": 41.6}))
        self.assertTrue(line.startswith("feat-a implement M"), line)
        for needle in ("tok", "~$", "cache ", "ctx 42%"):
            self.assertIn(needle, line)

    def test_incremental_ingest_fills_the_ledger_once(self):
        statusline.render(self.payload())
        first = len(ledger.read(self.root))
        statusline.render(self.payload())
        self.assertGreater(first, 0)
        self.assertEqual(len(ledger.read(self.root)), first)

    def test_unknown_parts_are_omitted(self):
        line = statusline.render({"workspace": {"current_dir": self.root}})
        self.assertEqual(line, "feat-a implement M")

    def test_malformed_input_prints_nothing_and_exits_zero(self):
        for raw in ("not json", "[]", ""):
            out = io.StringIO()
            with mock.patch("sys.stdin", io.StringIO(raw)), mock.patch("sys.stdout", out):
                self.assertEqual(statusline.main(), 0)
            self.assertEqual(out.getvalue().strip(), "")

    def test_outside_a_project_only_context_is_shown(self):
        outside = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, outside, True)
        self.assertEqual(statusline.render({"workspace": {"current_dir": outside},
                                            "context_window": {"used_percentage": 10}}), "ctx 10%")


if __name__ == "__main__":
    unittest.main()
