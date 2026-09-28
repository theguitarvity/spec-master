import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import _pathfix  # noqa: F401
import controller
import execution_mode
import state as state_mod
from fixtures.fake_agent import FakeAgentStep, fake_subprocess_run


class PerFeatureAttemptTests(unittest.TestCase):
    """Attempts are recorded per feature and phase (a second feature never
    inherits the first one's PASSED)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "context.md").write_text("# ctx\n", encoding="utf-8")
        self.state = state_mod.default_state("context.md")
        execution_mode.init_execution(self.state, "guarded", "opencode", "fake-model")
        self.state["execution"]["max_attempts_per_phase"] = 2
        self.state["execution"]["phase_timeout_seconds"] = 30
        self.state["attempts"] = {}
        for fid, directory in (("a", "specs/001-a"), ("b", "specs/002-b")):
            state_mod.upsert_feature(self.state, {"id": fid, "spec_directory": directory})
        state_mod.save(str(self.tmp / ".spec-master" / "state.json"), self.state)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def specify(self, feature_id, directory):
        step = FakeAgentStep(writes={
            f"{directory}/spec.md": f"# Spec {feature_id}\n",
            ".specify/feature.json": json.dumps({"feature_directory": directory}),
        })
        with patch("phase_runner.subprocess.run", side_effect=fake_subprocess_run([step], self.tmp)):
            with patch("builtins.print"):
                return controller._run_phase_with_attempts(self.state, self.tmp, "specify", feature_id)

    def test_attempt_keys(self):
        self.assertEqual(controller._attempt_key(None, "specify"), "specify")
        self.assertEqual(controller._attempt_key("a", "constitution"), "constitution")
        self.assertEqual(controller._attempt_key("a", "specify"), "a/specify")

    def test_second_feature_runs_its_own_specify(self):
        self.assertEqual(self.specify("a", "specs/001-a"), "PASSED")
        self.assertEqual(self.specify("b", "specs/002-b"), "PASSED")
        self.assertEqual(len(self.state["attempts"]["a/specify"]), 1)
        self.assertEqual(len(self.state["attempts"]["b/specify"]), 1)
        self.assertNotIn("specify", self.state["attempts"])
        self.assertEqual(controller._phase_status(self.state, "specify", "b"), "PASSED")
        self.assertEqual(controller._phase_status(self.state, "plan", "b"), "PENDING")
        self.assertEqual(state_mod.find_feature(self.state, "b")["phases"]["specify"], "PASSED")

    def test_scoped_contract_rejects_writing_into_another_feature(self):
        step = FakeAgentStep(writes={"specs/001-a/spec.md": "# Spec written in the wrong feature\n"})
        with patch("phase_runner.subprocess.run", side_effect=fake_subprocess_run([step, step], self.tmp)):
            with patch("builtins.print"):
                status = controller._run_phase_with_attempts(self.state, self.tmp, "specify", "b")
        self.assertEqual(status, "BLOCKED")
        # The first attempt wrote into feature a's directory; the retry rewrote
        # the same bytes (no change) and still produced nothing in specs/002-b.
        reasons = [attempt["reason"] for attempt in self.state["attempts"]["b/specify"]]
        self.assertEqual(reasons, ["forbidden_write", "missing_artifact"])

    def test_legacy_attempts_are_adopted_only_by_a_single_feature_state(self):
        legacy = [{"number": 1, "status": "PASSED", "context_hash": "x"}]
        single = {"features": [{"id": "only"}], "attempts": {"plan": list(legacy)}}
        self.assertEqual(controller._attempts_for(single, "only", "plan"), legacy)
        shared = {"features": [{"id": "a"}, {"id": "b"}], "attempts": {"plan": list(legacy)}}
        self.assertEqual(controller._attempts_for(shared, "a", "plan"), [])

    def test_specify_prompt_names_the_allocated_directory(self):
        prompt = controller._render_prompt("specify", 1, None, ("specs/002-b/*",), ("specs/002-b/spec.md",),
                                           "specs/002-b")
        self.assertIn("--number 2 --short-name b", prompt)
        self.assertNotIn("--number", controller._render_prompt("plan", 1, None, (), (), "specs/002-b"))

    def test_discovered_directory_is_recorded_after_specify(self):
        state_mod.upsert_feature(self.state, {"id": "c"})
        (self.tmp / "specs" / "003-c").mkdir(parents=True)
        (self.tmp / ".specify").mkdir(exist_ok=True)
        (self.tmp / ".specify" / "feature.json").write_text(json.dumps({"feature_directory": "specs/003-c"}))
        controller._record_discovered_feature_dir(self.state, self.tmp, "c")
        self.assertEqual(state_mod.find_feature(self.state, "c")["spec_directory"], "specs/003-c")


if __name__ == "__main__":
    unittest.main()
