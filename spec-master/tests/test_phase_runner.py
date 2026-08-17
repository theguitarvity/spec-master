from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import _pathfix  # noqa: F401
import phase_runner
from fixtures.fake_agent import FakeAgentStep, fake_subprocess_run


def _init_constitution(project: Path, text: str = "# [PROJECT_NAME] Constitution\n") -> None:
    path = project / ".specify" / "memory" / "constitution.md"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")


class PhaseRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, phase, steps):
        with patch("phase_runner.subprocess.run", side_effect=fake_subprocess_run(steps, self.tmp)):
            return phase_runner.run_phase(
                self.tmp, phase, "opencode", "fake-model", "prompt", timeout_seconds=30,
            )

    # unit test 8 / integration scenario 3 (guarded-mode-spec.md §16):
    # agent creates src/app.py during constitution.
    def test_early_implementation_during_constitution_is_critical(self):
        _init_constitution(self.tmp)
        step = FakeAgentStep(writes={
            ".specify/memory/constitution.md": "# Real Constitution\nPrinciples here.",
            "src/app.py": "print('hi')",
        })
        result = self._run("constitution", [step])
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("early_implementation", result["events"])
        self.assertIn("src/app.py", result["forbidden_writes"])

    def test_out_of_project_symlink_write_is_rejected(self):
        _init_constitution(self.tmp)
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        (self.tmp / "escape.md").symlink_to(outside / "secret.md")
        (outside / "secret.md").write_text("leaked", encoding="utf-8")

        step = FakeAgentStep(writes={
            ".specify/memory/constitution.md": "# Real Constitution\nPrinciples here.",
        })
        # The symlink already exists before the run; simulate the agent
        # "touching" it by rewriting through it during the fake step.
        step.writes["escape.md"] = "still leaked"
        result = self._run("constitution", [step])
        self.assertIn("out_of_project_write", result["events"])
        self.assertEqual(result["status"], "FAILED")

    def test_artifact_wrong_location_detected(self):
        # constitution.md written at the repo root instead of .specify/memory/.
        step = FakeAgentStep(writes={"constitution.md": "# Real Constitution"})
        result = self._run("constitution", [step])
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("artifact_wrong_location", result["events"])

    def test_ordinary_nonzero_exit_is_recoverable_tool_error(self):
        step = FakeAgentStep(returncode=1, stdout="some ordinary tool failure")
        result = self._run("constitution", [step])
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("recoverable_tool_error", result["events"])

    def test_valid_constitution_passes(self):
        step = FakeAgentStep(writes={
            ".specify/memory/constitution.md": "# Real Constitution\n\nPrinciples here.",
        })
        result = self._run("constitution", [step])
        self.assertEqual(result["status"], "PASSED")
        self.assertIsNone(result["reason"])

    def test_unsupported_integration_raises(self):
        with self.assertRaises(phase_runner.UnsupportedIntegrationError):
            phase_runner.run_phase(self.tmp, "constitution", "codex", "m", "p", 30)


if __name__ == "__main__":
    unittest.main()
