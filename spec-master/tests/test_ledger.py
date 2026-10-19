import _pathfix  # noqa: F401

import json
import os
import shutil
import tempfile
import unittest

import events
import ledger
import telemetry
from test_telemetry import (MODEL, SECRET, SESSION, _assistant, _main_session_lines, _subagent_lines, _usage,
                            _write_jsonl)


class _LedgerCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, ".spec-master"))
        self.tmp = tempfile.mkdtemp()
        self.main = _write_jsonl(os.path.join(self.tmp, f"{SESSION}.jsonl"), _main_session_lines())
        self.agent = _write_jsonl(os.path.join(self.tmp, SESSION, "subagents", "agent-abc.jsonl"), _subagent_lines(
            "abc", [("10:00:08.000", "msg_X", _usage(4, 3, 5000, 400)), ("10:00:09.000", "msg_Y", _usage(2, 5, 6000, 0))]))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ingest(self, *paths):
        return ledger.ingest(self.root, transcripts=list(paths) or [self.main, self.agent])

    def lines(self):
        return ledger.read(self.root)


class IngestTests(_LedgerCase):
    def test_one_line_per_response_with_contract_fields(self):
        result = self.ingest()
        lines = self.lines()
        self.assertEqual(result["appended"], len(lines))
        self.assertEqual(sorted(l["request_id"] for l in lines),
                         sorted(f"req-{k}" for k in ["msg_A", "msg_B", "msg_C", "msg_D", "msg_S1", "msg_X", "msg_Y"]))
        line = next(l for l in lines if l["request_id"] == "req-msg_A")
        self.assertEqual(line["schema"], "spec-master.tokens/v1")
        self.assertEqual(line["source"], "host-transcript")
        self.assertEqual((line["session_id"], line["model"]), (SESSION, MODEL))
        self.assertEqual((line["input_tokens"], line["output_tokens"], line["cache_read_input_tokens"],
                          line["cache_creation_input_tokens"]), (10, 500, 1000, 200))
        self.assertTrue(line["output_tokens_complete"])
        self.assertIsNone(line["agent_id"])
        self.assertEqual(line["ts"], "2026-09-27T10:00:05.000Z")
        self.assertEqual(set(line), {"schema", "ts", "source", "session_id", "request_id", "agent_id", "agent_type",
                                     "feature_id", "phase", "model", "input_tokens", "output_tokens",
                                     "cache_read_input_tokens", "cache_creation_input_tokens",
                                     "output_tokens_complete", "cost_usd", "cost_basis"})

    def test_sidechain_lines_are_lower_bounds_with_agent_id(self):
        self.ingest()
        sub = [l for l in self.lines() if l["agent_id"] == "abc"]
        self.assertEqual(len(sub), 2)
        self.assertTrue(all(not l["output_tokens_complete"] for l in sub))

    def test_second_ingest_appends_nothing(self):
        self.ingest()
        before = len(self.lines())
        self.assertEqual(self.ingest()["appended"], 0)
        self.assertEqual(len(self.lines()), before)

    def test_growing_transcript_appends_only_new_responses(self):
        self.ingest()
        before = len(self.lines())
        with open(self.main, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(_assistant("12:00:00.000", "msg_N", _usage(1, 2, 3, 4), stop="end_turn")) + "\n")
        self.assertEqual(self.ingest()["appended"], 1)
        self.assertEqual(len(self.lines()), before + 1)

    def test_lost_offsets_do_not_duplicate_the_ledger(self):
        self.ingest()
        os.unlink(ledger.offsets_path(self.root))
        self.assertEqual(self.ingest()["appended"], 0)

    def test_truncated_transcript_is_reread_without_duplicates(self):
        self.ingest()
        before = len(self.lines())
        _write_jsonl(self.main, _main_session_lines()[:6])  # rotated: shorter than the saved offset
        self.assertEqual(self.ingest()["appended"], 0)
        self.assertEqual(len(self.lines()), before)

    def test_total_matches_the_aggregate_reader(self):
        self.ingest()
        usage = telemetry.read_transcript_usage([self.main, self.agent])
        totals = ledger.summary(self.root)["totals"]
        self.assertEqual(totals["input_tokens"], usage["input_tokens"])
        self.assertEqual(totals["output_tokens"], usage["output_tokens"])
        self.assertEqual(totals["cache_read_input_tokens"], usage["cache_read_input_tokens"])
        self.assertEqual(totals["cache_creation_input_tokens"], usage["cache_creation_input_tokens"])

    def test_unknown_format_degrades_to_nothing_with_a_note(self):
        junk = _write_jsonl(os.path.join(self.tmp, "junk.jsonl"), ['{"foo": 1}', "not json", '{"type": "assistant"}'])
        result = ledger.ingest(self.root, transcripts=[junk])
        self.assertEqual(result["appended"], 0)
        self.assertTrue(any("no usage" in note for note in result["notes"]))
        self.assertEqual(self.lines(), [])

    def test_missing_transcript_is_a_note_not_a_crash(self):
        result = ledger.ingest(self.root, transcripts=[os.path.join(self.tmp, "gone.jsonl")])
        self.assertEqual(result["appended"], 0)
        self.assertTrue(result["notes"])

    def test_no_message_content_reaches_the_ledger(self):
        self.ingest()
        with open(ledger.ledger_path(self.root), encoding="utf-8") as fh:
            self.assertNotIn(SECRET, fh.read())

    def test_transcripts_are_discovered_from_the_project_and_events(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        project = os.path.join(home, ".claude", "projects", telemetry.project_dir_name(os.path.realpath(self.root)))
        _write_jsonl(os.path.join(project, f"{SESSION}.jsonl"), _main_session_lines())
        result = ledger.ingest(self.root, home=home, env={})
        self.assertGreater(result["appended"], 0)
        events.append(self.root, "agent.finished", agent_id="abc", transcript_path=self.agent)
        self.assertEqual(ledger.ingest(self.root, home=home, env={})["appended"], 2)


class AttributionTests(_LedgerCase):
    def write_events(self, rows):
        for row in rows:
            events.append(self.root, row.pop("type"), **row)

    def test_phase_window_and_agent_type_are_attributed(self):
        self.write_events([
            {"type": "phase.started", "ts": "2026-09-27T09:59:00Z", "feature_id": "f1", "phase": "implement"},
            {"type": "agent.started", "ts": "2026-09-27T10:00:07Z", "agent_id": "abc", "agent_type": "Explore"},
            {"type": "phase.finished", "ts": "2026-09-27T10:20:00Z", "feature_id": "f1", "phase": "implement",
             "status": "PASSED"},
        ])
        self.ingest()
        by_req = {l["request_id"]: l for l in self.lines()}
        self.assertEqual((by_req["req-msg_A"]["feature_id"], by_req["req-msg_A"]["phase"]), ("f1", "implement"))
        self.assertEqual(by_req["req-msg_X"]["agent_type"], "Explore")
        self.assertEqual(by_req["req-msg_X"]["feature_id"], "f1")
        # 10:30 is after the window closed: not attributable, so null, never invented
        self.assertEqual((by_req["req-msg_C"]["feature_id"], by_req["req-msg_C"]["phase"]), (None, None))

    def test_without_events_everything_is_null(self):
        self.ingest()
        self.assertTrue(all(l["feature_id"] is None and l["phase"] is None for l in self.lines()))


class CostTests(unittest.TestCase):
    def test_known_model_is_estimated_from_the_price_table(self):
        cost, basis = ledger.estimate_cost("claude-sonnet-4-5", {"input_tokens": 1_000_000, "output_tokens": 1_000_000,
                                                                   "cache_read_input_tokens": 1_000_000,
                                                                   "cache_creation_input_tokens": 1_000_000})
        self.assertEqual(basis, "estimated")
        self.assertAlmostEqual(cost, 3.0 + 15.0 + 0.30 + 3.75)

    def test_unknown_model_has_no_cost(self):
        self.assertEqual(ledger.estimate_cost("some-other-model", {"input_tokens": 5}), (None, None))
        self.assertEqual(ledger.estimate_cost(None, {"input_tokens": 5}), (None, None))

    def test_price_override_file_wins(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        os.makedirs(os.path.join(root, ".spec-master", "metrics"))
        with open(os.path.join(root, ".spec-master", "metrics", "prices.json"), "w") as fh:
            json.dump({"my-model": {"input": 10, "output": 20, "cache_read": 1, "cache_write": 12}}, fh)
        cost, basis = ledger.estimate_cost("my-model-v2", {"input_tokens": 1_000_000}, prices=ledger.load_prices(root))
        self.assertEqual((cost, basis), (10.0, "estimated"))


class SummaryTests(_LedgerCase):
    def test_empty_ledger_gives_zero_totals(self):
        summary = ledger.summary(self.root)
        self.assertEqual(summary["schema"], "spec-master.tokens-summary/v1")
        self.assertEqual(summary["totals"]["total_tokens"], 0)
        self.assertEqual(summary["totals"]["cache_hit_ratio"], 0.0)
        self.assertEqual(summary["burn_rate_tokens_per_min"], 0.0)
        self.assertEqual(summary["window"], {"first_ts": None, "last_ts": None})
        self.assertEqual(summary["by_feature"], {})

    def test_groupings_and_ratios(self):
        events.append(self.root, "phase.started", ts="2026-09-27T09:59:00Z", feature_id="f1", phase="plan")
        events.append(self.root, "agent.started", ts="2026-09-27T10:00:07Z", agent_id="abc", agent_type="Explore")
        self.ingest()
        summary = ledger.summary(self.root)
        totals = summary["totals"]
        self.assertEqual(totals["total_tokens"], totals["input_tokens"] + totals["output_tokens"])
        denominator = (totals["input_tokens"] + totals["cache_read_input_tokens"] + totals["cache_creation_input_tokens"])
        self.assertAlmostEqual(totals["cache_hit_ratio"], totals["cache_read_input_tokens"] / denominator)
        self.assertIn("f1", summary["by_feature"])
        self.assertIn("f1:plan", summary["by_phase"])
        self.assertEqual(summary["by_agent"]["abc"]["agent_type"], "Explore")
        self.assertEqual(summary["by_agent"]["abc"]["input_tokens"], 6)
        self.assertEqual(list(summary["by_model"]), [MODEL])
        self.assertEqual(summary["window"]["first_ts"], "2026-09-27T10:00:05.000Z")
        self.assertGreater(summary["burn_rate_tokens_per_min"], 0)

    def test_recent_burn_rate_counts_only_the_last_hour(self):
        self.ingest()
        summary = ledger.summary(self.root)
        self.assertEqual(summary["recent_window_minutes"], 60)
        newest = events.parse_ts(summary["window"]["last_ts"])
        recent = sum(line["input_tokens"] + line["output_tokens"] for line in self.lines()
                     if (newest - events.parse_ts(line["ts"])).total_seconds() <= 3600)
        self.assertEqual(summary["recent_burn_rate_tokens_per_min"], round(recent / 60, 3))
        self.assertEqual(ledger.summary(self.root, session_id="nope")["recent_burn_rate_tokens_per_min"], 0.0)

    def test_since_filters_by_ts(self):
        self.ingest()
        later = ledger.summary(self.root, since="2026-09-27T11:00:00Z")
        self.assertEqual(later["window"]["first_ts"], "2026-09-27T11:00:10.000Z")
        self.assertLess(later["totals"]["total_tokens"], ledger.summary(self.root)["totals"]["total_tokens"])

    def test_session_filter(self):
        self.ingest()
        self.assertEqual(ledger.summary(self.root, session_id="nope")["totals"]["total_tokens"], 0)
        self.assertGreater(ledger.summary(self.root, session_id=SESSION)["totals"]["total_tokens"], 0)

    def test_unknown_model_leaves_cost_null_and_known_sums(self):
        unknown = _write_jsonl(os.path.join(self.tmp, "u.jsonl"), [
            _assistant("13:00:00.000", "msg_U", _usage(1, 1, 1, 1), stop="end_turn", model="mystery-1")])
        ledger.ingest(self.root, transcripts=[unknown])
        summary = ledger.summary(self.root)
        self.assertIsNone(summary["by_model"]["mystery-1"]["cost_usd"])
        self.assertIsNone(summary["totals"]["cost_usd"])

    def test_corrupt_ledger_lines_are_skipped(self):
        self.ingest()
        with open(ledger.ledger_path(self.root), "a", encoding="utf-8") as fh:
            fh.write("{broken\n")
        self.assertGreater(ledger.summary(self.root)["totals"]["total_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
