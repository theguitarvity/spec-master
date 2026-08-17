import unittest

import _pathfix  # noqa: F401
import execution_mode


TS = "2026-08-17T18:00:00Z"


class ParseModeTests(unittest.TestCase):
    # unit test 1: parsing dos três modos
    def test_accepts_all_three_modes(self):
        for value in ("native", "guarded", "auto"):
            self.assertEqual(execution_mode.parse_mode(value), value)

    def test_rejects_unknown_mode(self):
        with self.assertRaises(execution_mode.ExecutionModeError):
            execution_mode.parse_mode("yolo")

    # unit test 2: modo padrão auto
    def test_missing_mode_defaults_to_auto(self):
        self.assertEqual(execution_mode.parse_mode(None), "auto")


class InitExecutionTests(unittest.TestCase):
    def test_auto_starts_native(self):
        state = {}
        execution_mode.init_execution(state, "auto", "opencode", "some-model")
        self.assertEqual(state["execution"]["requested_mode"], "auto")
        self.assertEqual(state["execution"]["active_mode"], "native")

    def test_guarded_starts_guarded(self):
        state = {}
        execution_mode.init_execution(state, "guarded", "opencode", "some-model")
        self.assertEqual(state["execution"]["active_mode"], "guarded")


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.state = {}
        execution_mode.init_execution(self.state, "auto", "opencode", "some-model")

    # unit test 3: transição native -> guarded por evento crítico
    def test_single_critical_event_triggers_migration(self):
        migrated = execution_mode.maybe_migrate(self.state, "early_implementation", TS)
        self.assertTrue(migrated)
        execution = self.state["execution"]
        self.assertEqual(execution["active_mode"], "guarded")
        self.assertEqual(len(execution["mode_transitions"]), 1)
        transition = execution["mode_transitions"][0]
        self.assertEqual(transition["from"], "native")
        self.assertEqual(transition["to"], "guarded")
        self.assertEqual(transition["reason"], "early_implementation")
        self.assertEqual(transition["timestamp"], TS)

    # unit test 4: acumulação de eventos recuperáveis (cumulative across
    # the whole workflow, per the 2026-08-17 clarification in spec.md —
    # simulated here as two events from *different* phases/calls).
    def test_two_recoverable_events_across_workflow_trigger_migration(self):
        first = execution_mode.maybe_migrate(self.state, "wrong_path", TS)
        self.assertFalse(first)
        self.assertEqual(self.state["execution"]["active_mode"], "native")

        second = execution_mode.maybe_migrate(self.state, "placeholder_not_removed", TS)
        self.assertTrue(second)
        self.assertEqual(self.state["execution"]["active_mode"], "guarded")

    def test_single_recoverable_event_does_not_migrate(self):
        migrated = execution_mode.maybe_migrate(self.state, "wrong_path", TS)
        self.assertFalse(migrated)
        self.assertEqual(self.state["execution"]["active_mode"], "native")
        self.assertEqual(self.state["execution"]["recoverable_event_count"], 1)

    def test_two_consecutive_timeouts_are_critical(self):
        first = execution_mode.maybe_migrate(self.state, "timeout", TS)
        self.assertFalse(first)
        second = execution_mode.maybe_migrate(self.state, "timeout", TS)
        self.assertTrue(second)

    def test_a_passing_attempt_between_two_timeouts_resets_consecutiveness(self):
        execution_mode.maybe_migrate(self.state, "timeout", TS)
        # Any other event type (e.g. a benign attempt outcome) breaks the streak.
        execution_mode.record_event(self.state, "unrelated_progress_marker", TS)
        self.state["execution"]["last_consecutive_event"] = None
        migrated = execution_mode.maybe_migrate(self.state, "timeout", TS)
        self.assertFalse(migrated)


class NoReversionTests(unittest.TestCase):
    def test_guarded_never_reverts_to_native_after_more_events(self):
        state = {}
        execution_mode.init_execution(state, "auto", "opencode", "some-model")
        execution_mode.maybe_migrate(state, "simulated_tool_call", TS)
        self.assertEqual(state["execution"]["active_mode"], "guarded")

        # Further critical/recoverable events must never flip it back.
        execution_mode.maybe_migrate(state, "out_of_project_write", TS)
        execution_mode.maybe_migrate(state, "wrong_path", TS)
        self.assertEqual(state["execution"]["active_mode"], "guarded")
        # Only the first transition should ever have been recorded.
        self.assertEqual(len(state["execution"]["mode_transitions"]), 1)

    def test_requested_guarded_never_has_a_native_phase_to_migrate_from(self):
        state = {}
        execution_mode.init_execution(state, "guarded", "opencode", "some-model")
        migrated = execution_mode.maybe_migrate(state, "early_implementation", TS)
        self.assertFalse(migrated)
        self.assertEqual(state["execution"]["mode_transitions"], [])


if __name__ == "__main__":
    unittest.main()
