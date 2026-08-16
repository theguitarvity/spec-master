import os
import shutil
import tempfile
import unittest

import _pathfix  # noqa: F401
import state as state_mod


class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "state.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_init_creates_default_state(self):
        s = state_mod.init(self.path, context="CLAUDE.md")
        self.assertEqual(s["status"], "INITIALIZED")
        self.assertEqual(s["context"], "CLAUDE.md")
        self.assertTrue(os.path.exists(self.path))

    def test_init_is_idempotent(self):
        state_mod.init(self.path, context="CLAUDE.md")
        state_mod.transition_workflow_status(state_mod.load(self.path), "DISCOVERING")
        s1 = state_mod.load(self.path)
        s2 = state_mod.init(self.path, context="CLAUDE.md")
        self.assertEqual(s1, s2)

    def test_workflow_status_forward_transition_allowed(self):
        s = state_mod.init(self.path, context="CLAUDE.md")
        state_mod.transition_workflow_status(s, "DISCOVERING")
        state_mod.transition_workflow_status(s, "CONTEXT_NORMALIZED")
        self.assertEqual(s["status"], "CONTEXT_NORMALIZED")

    def test_workflow_status_backward_transition_rejected(self):
        s = state_mod.init(self.path, context="CLAUDE.md")
        state_mod.transition_workflow_status(s, "CONTEXT_NORMALIZED")
        with self.assertRaises(state_mod.InvalidTransitionError):
            state_mod.transition_workflow_status(s, "DISCOVERING")

    def test_blocked_and_resume_allowed(self):
        s = state_mod.init(self.path, context="CLAUDE.md")
        state_mod.transition_workflow_status(s, "PLANNING")
        state_mod.transition_workflow_status(s, "BLOCKED")
        # resuming forward from BLOCKED must be allowed explicitly
        state_mod.transition_workflow_status(s, "PLANNING")
        self.assertEqual(s["status"], "PLANNING")

    def test_feature_phase_requires_previous_phase_passed(self):
        s = state_mod.init(self.path, context="CLAUDE.md")
        state_mod.upsert_feature(s, {"id": "f1", "name": "Feature 1"})
        with self.assertRaises(state_mod.InvalidTransitionError):
            state_mod.transition_phase(s, "f1", "plan", "PASSED")

    def test_feature_phase_sequence_passes(self):
        s = state_mod.init(self.path, context="CLAUDE.md")
        state_mod.upsert_feature(s, {"id": "f1", "name": "Feature 1"})
        state_mod.transition_phase(s, "f1", "specify", "PASSED")
        state_mod.transition_phase(s, "f1", "clarify", "PASSED")
        feature = state_mod.transition_phase(s, "f1", "plan", "RUNNING")
        self.assertEqual(feature["phases"]["plan"], "RUNNING")

    def test_analyze_cycle_caps_at_three(self):
        s = state_mod.init(self.path, context="CLAUDE.md")
        state_mod.upsert_feature(s, {"id": "f1", "name": "Feature 1"})
        for _ in range(state_mod.MAX_ANALYZE_REPAIR_CYCLES):
            result = state_mod.analyze_cycle(s, "f1", "increment")
        self.assertTrue(result["exhausted"])
        with self.assertRaises(state_mod.StateError):
            state_mod.analyze_cycle(s, "f1", "increment")

    def test_persistence_round_trip(self):
        s = state_mod.init(self.path, context="CLAUDE.md")
        state_mod.upsert_feature(s, {"id": "f1", "name": "Feature 1"})
        state_mod.save(self.path, s)
        reloaded = state_mod.load(self.path)
        self.assertEqual(reloaded["features"][0]["id"], "f1")


if __name__ == "__main__":
    unittest.main()
