import os
from pathlib import Path
import shutil
import tempfile
import unittest

import _pathfix  # noqa: F401
import opencode_runner


class OpenCodeRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fake_tool_markup_is_rejected(self):
        self.assertEqual(opencode_runner.validate_transcript("<function=bash>"), ["<function="])
        self.assertEqual(opencode_runner.validate_transcript("normal response"), [])

    def test_specify_requires_both_artifacts(self):
        (self.tmp / "specs" / "001-demo").mkdir(parents=True)
        (self.tmp / "specs" / "001-demo" / "spec.md").write_text("ok", encoding="utf-8")
        self.assertEqual(
            opencode_runner.validate_artifacts(self.tmp, "specify"),
            [".specify/feature.json"],
        )

    def test_nonempty_artifacts_pass(self):
        (self.tmp / ".specify" / "memory").mkdir(parents=True)
        (self.tmp / ".specify" / "memory" / "constitution.md").write_text("ok", encoding="utf-8")
        self.assertEqual(opencode_runner.validate_artifacts(self.tmp, "constitution"), [])

    def test_constitution_rejects_implementation_writes(self):
        changed = [".specify/memory/constitution.md", "src/app.py", "requirements.txt"]
        self.assertEqual(
            opencode_runner.forbidden_writes(changed, "constitution"),
            ["requirements.txt", "src/app.py"],
        )

    def test_constitution_placeholder_is_rejected(self):
        path = self.tmp / ".specify" / "memory" / "constitution.md"
        path.parent.mkdir(parents=True)
        path.write_text("# [PROJECT_NAME] Constitution", encoding="utf-8")
        self.assertEqual(
            opencode_runner.placeholder_artifacts(self.tmp, "constitution"),
            [".specify/memory/constitution.md"],
        )

    # validate phase entry added for the guarded-mode-controller feature
    # (specs/001-guarded-mode-controller/) — confirms the phase_contracts.py
    # extraction kept `validate` reachable through opencode_runner too.
    def test_validate_is_a_known_phase(self):
        self.assertIn("validate", opencode_runner.PHASE_ARTIFACTS)
        args = opencode_runner.build_parser().parse_args(
            ["--project", str(self.tmp), "--phase", "validate",
             "--prompt-file", str(self.tmp / "p.txt")],
        )
        self.assertEqual(args.phase, "validate")

    def test_validate_requires_traceability_and_quality_gates_reports(self):
        self.assertEqual(
            opencode_runner.validate_artifacts(self.tmp, "validate"),
            [".spec-master/reports/traceability.md", ".spec-master/reports/quality-gates.md"],
        )
        reports = self.tmp / ".spec-master" / "reports"
        reports.mkdir(parents=True)
        (reports / "traceability.md").write_text("ok", encoding="utf-8")
        (reports / "quality-gates.md").write_text("ok", encoding="utf-8")
        self.assertEqual(opencode_runner.validate_artifacts(self.tmp, "validate"), [])


if __name__ == "__main__":
    unittest.main()
