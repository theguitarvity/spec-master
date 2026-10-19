import _pathfix  # noqa: F401

import json
import os
import shutil
import tempfile
import unittest

import events


class EventsTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, ".spec-master"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def lines(self):
        with open(events.events_path(self.root), encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def test_append_writes_common_fields(self):
        events.append(self.root, "phase.started", feature_id="f1", phase="plan", status="RUNNING", ts="2026-10-19T10:00:00Z")
        (line,) = self.lines()
        self.assertEqual(line, {"schema": "spec-master.event/v1", "ts": "2026-10-19T10:00:00Z", "type": "phase.started",
                                "session_id": None, "feature_id": "f1", "phase": "plan", "status": "RUNNING"})

    def test_append_is_a_noop_outside_a_spec_master_project(self):
        bare = tempfile.mkdtemp()
        try:
            self.assertFalse(events.append(bare, "phase.started"))
            self.assertFalse(os.path.exists(events.events_path(bare)))
        finally:
            shutil.rmtree(bare, ignore_errors=True)

    def test_read_skips_corrupt_lines(self):
        events.append(self.root, "hook.fired", hook_id="h", event="e")
        with open(events.events_path(self.root), "a", encoding="utf-8") as fh:
            fh.write("{not json\n[1]\n")
        self.assertEqual([e["type"] for e in events.read(self.root)], ["hook.fired"])

    def test_read_missing_file_is_empty(self):
        self.assertEqual(events.read(self.root), [])

    def test_on_phase_maps_status_to_started_or_finished(self):
        events.on_phase(self.root, "f1", "plan", "RUNNING")
        events.on_phase(self.root, "f1", "plan", "PASSED")
        events.on_phase(self.root, "f1", "plan", "PENDING")  # a reset is neither
        got = [(e["type"], e["status"]) for e in self.lines()]
        self.assertEqual(got, [("phase.started", "RUNNING"), ("phase.finished", "PASSED")])

    def test_on_agent_records_start_and_finish_with_active_phase(self):
        events.on_phase(self.root, "f1", "implement", "RUNNING")
        events.on_agent(self.root, "start", {"session_id": "s1", "agent_id": "a1", "agent_type": "Explore",
                                             "transcript_path": "/t/main.jsonl"})
        events.on_agent(self.root, "stop", {"session_id": "s1", "agent_id": "a1", "agent_type": "Explore",
                                            "agent_transcript_path": "/t/agent-a1.jsonl"})
        started, finished = self.lines()[1:]
        self.assertEqual((started["type"], started["agent_id"], started["agent_type"]), ("agent.started", "a1", "Explore"))
        self.assertEqual((started["feature_id"], started["phase"], started["session_id"]), ("f1", "implement", "s1"))
        self.assertIsNone(started["worktree"])
        self.assertEqual(finished["type"], "agent.finished")
        self.assertEqual(finished["transcript_path"], "/t/agent-a1.jsonl")

    def test_on_agent_ignores_payload_without_agent_id(self):
        self.assertFalse(events.on_agent(self.root, "start", {"session_id": "s1"}))
        self.assertEqual(events.read(self.root), [])

    def test_active_window_picks_latest_open_phase(self):
        evs = [
            {"type": "phase.started", "ts": "2026-10-19T10:00:00Z", "feature_id": "f1", "phase": "plan", "session_id": None},
            {"type": "phase.finished", "ts": "2026-10-19T10:05:00Z", "feature_id": "f1", "phase": "plan", "session_id": None},
            {"type": "phase.started", "ts": "2026-10-19T10:06:00Z", "feature_id": "f1", "phase": "tasks", "session_id": None},
        ]
        self.assertEqual(events.active_window(evs, "s1", "2026-10-19T10:01:00Z"), ("f1", "plan"))
        self.assertEqual(events.active_window(evs, "s1", "2026-10-19T10:05:30Z"), (None, None))
        self.assertEqual(events.active_window(evs, "s1", "2026-10-19T10:07:00Z"), ("f1", "tasks"))
        self.assertEqual(events.active_window(evs, "s1", "2026-10-19T09:00:00Z"), (None, None))

    def test_active_window_respects_session_ids(self):
        evs = [{"type": "phase.started", "ts": "2026-10-19T10:00:00Z", "feature_id": "f1", "phase": "plan",
                "session_id": "other"}]
        self.assertEqual(events.active_window(evs, "s1", "2026-10-19T10:01:00Z"), (None, None))
        self.assertEqual(events.active_window(evs, "other", "2026-10-19T10:01:00Z"), ("f1", "plan"))


if __name__ == "__main__":
    unittest.main()
