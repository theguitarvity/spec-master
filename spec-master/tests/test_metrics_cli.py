"""CLI wiring of host telemetry, `metrics record-round --append` and the
baseline runner's confirmation gate (the libraries have their own suites)."""
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

import _pathfix  # noqa: F401
import cli

SESSION = "11111111-2222-3333-4444-555555555555"


def _run(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(list(argv))
    return code, json.loads(buf.getvalue())


def _assistant(clock, msg_id, inp, out):
    return {"type": "assistant", "sessionId": SESSION, "isSidechain": False, "timestamp": f"2026-09-27T{clock}Z",
            "requestId": f"req-{msg_id}", "message": {
                "id": msg_id, "type": "message", "role": "assistant", "model": "test-model",
                "content": [{"type": "text", "text": "never copied"}], "stop_reason": "end_turn",
                "usage": {"input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": 0,
                          "cache_creation_input_tokens": 0}}}


class MetricsCliTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.rounds = os.path.join(self.root, ".spec-master", "metrics", "rounds.json")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def stored(self):
        with open(self.rounds, encoding="utf-8") as fh:
            return json.load(fh)

    def record(self, round_id, *extra):
        return _run("metrics", "record-round", "--round-id", round_id, "--phase", "tasks",
                    "--started-at", "2026-09-27T10:00:00Z", "--ended-at", "2026-09-27T10:05:00Z", *extra)

    def test_record_round_without_append_only_prints_the_v1_row(self):
        code, row = self.record("r1")
        self.assertEqual(code, 0)
        self.assertNotIn("source", row)
        self.assertFalse(os.path.exists(self.rounds))

    def test_append_is_validated_and_unmeasured_rows_say_so(self):
        code, out = self.record("r1", "--source", "manual", "--append", "--path", self.root)
        self.assertEqual((code, out["appended"], out["rounds"]), (0, "r1", 1))
        self.assertEqual(self.stored()[0]["source"], "manual-unverified")
        self.record("r2", "--source", "manual", "--input-tokens", "10", "--append", "--path", self.root)
        self.assertEqual([r["source"] for r in self.stored()], ["manual-unverified", "manual"])

    def test_append_refuses_a_broken_file(self):
        os.makedirs(os.path.dirname(self.rounds))
        with open(self.rounds, "w", encoding="utf-8") as fh:
            json.dump({"not": "a list"}, fh)
        code, out = self.record("r1", "--append", "--path", self.root)
        self.assertEqual(code, 1)
        self.assertIn("not a JSON array", out["error"])

    def test_host_sources_cannot_be_typed_in(self):
        with self.assertRaises(SystemExit):
            with redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
                cli.main(["metrics", "record-round", "--round-id", "r1", "--phase", "tasks", "--started-at",
                          "2026-09-27T10:00:00Z", "--ended-at", "2026-09-27T10:05:00Z", "--source", "host-transcript"])

    def transcript(self, lines):
        path = os.path.join(self.root, f"{SESSION}.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(json.dumps(line) for line in lines) + "\n")
        return path

    def test_ingest_a_transcript_window_and_append(self):
        path = self.transcript([_assistant("10:00:05.000", "msg_A", 10, 500),
                                _assistant("10:20:05.000", "msg_B", 5, 100)])
        code, out = _run("telemetry", "ingest", "--path", self.root, "--transcript", path,
                         "--since", "2026-09-27T10:10:00Z", "--round-id", "r1", "--phase", "plan",
                         "--feature-id", "f1", "--lane", "standard", "--append")
        self.assertEqual(code, 0, out)
        row = self.stored()[0]
        self.assertEqual((row["source"], row["input_tokens"], row["output_tokens"], row["lane"]),
                         ("host-transcript", 5, 100, "standard"))
        self.assertNotIn("never copied", json.dumps(row))

    def test_an_empty_window_is_refused_not_recorded_as_zero(self):
        path = self.transcript([_assistant("10:00:05.000", "msg_A", 10, 500)])
        code, out = _run("telemetry", "ingest", "--path", self.root, "--transcript", path,
                         "--since", "2026-09-27T11:00:00Z", "--round-id", "r1", "--phase", "plan", "--append")
        self.assertEqual(code, 1)
        self.assertIn("no tokens measured", out["error"])
        self.assertFalse(os.path.exists(self.rounds))

    def test_latest_without_any_transcript(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": self.root}):
            code, out = _run("telemetry", "ingest", "--path", self.root, "--latest",
                             "--round-id", "r1", "--phase", "plan")
        self.assertEqual(code, 1)
        self.assertIn("no Claude Code transcript", out["error"])

    def test_ingest_a_headless_result(self):
        result = os.path.join(self.root, "result.json")
        with open(result, "w", encoding="utf-8") as fh:
            json.dump({"type": "result", "subtype": "success", "is_error": False, "duration_ms": 60000,
                       "num_turns": 4, "session_id": SESSION, "total_cost_usd": 0.42, "result": "never copied",
                       "usage": {"input_tokens": 7, "output_tokens": 70},
                       "modelUsage": {"test-model": {"inputTokens": 7, "outputTokens": 70,
                                                     "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0}}},
                      fh)
        code, row = _run("telemetry", "ingest", "--headless-json", result, "--ended-at", "2026-09-27T10:05:00Z",
                         "--round-id", "r1", "--phase", "implement")
        self.assertEqual(code, 0, row)
        self.assertEqual((row["source"], row["cost_usd"], row["started_at"]),
                         ("host-headless", 0.42, "2026-09-27T10:04:00.000Z"))


class BaselineCliTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.cases = os.path.join(self.root, "cases.json")
        with open(self.cases, "w", encoding="utf-8") as fh:
            json.dump([{"id": "bugfix-xs", "repo": self.root, "rev": "HEAD",
                        "prompts": {"specmaster": "/spec-master fix it", "direct": "Fix it"}}], fh)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_plan_executes_nothing(self):
        code, plan = _run("baseline", "plan", "--cases", self.cases, "--runs", "2", "--max-budget-usd", "1.5")
        self.assertEqual((code, plan["total_runs"], plan["worst_case_budget_usd"]), (0, 4, 6.0))

    def test_run_refuses_without_yes(self):
        with mock.patch("subprocess.run") as spawned:
            code, out = _run("baseline", "run", "--cases", self.cases, "--max-budget-usd", "1",
                             "--out", os.path.join(self.root, "out"))
        self.assertEqual(code, 2)
        self.assertIn("spends real money", out["error"])
        self.assertEqual(out["total_runs"], 6)
        spawned.assert_not_called()
        self.assertFalse(os.path.exists(os.path.join(self.root, "out")))


if __name__ == "__main__":
    unittest.main()
