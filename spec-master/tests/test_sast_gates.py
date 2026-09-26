import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import _pathfix  # noqa: F401
import discovery
import phase_runner
import quality_gates
import sast_gates


def _write(root, rel, text=""):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class SastGatesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_evidence_means_no_gate(self):
        _write(self.tmp, "pyproject.toml", "[tool.pytest.ini_options]\n")
        self.assertEqual(sast_gates.detect(self.tmp), [])
        self.assertFalse(any(g.get("category") == "sast" for g in quality_gates.detect(self.tmp)))

    def test_semgrep_config_becomes_blocking_local_gate(self):
        _write(self.tmp, ".semgrep.yml", "rules: []\n")
        gates = sast_gates.detect(self.tmp)
        self.assertEqual(len(gates), 1)
        gate = gates[0]
        self.assertEqual(gate["tool"], "semgrep")
        self.assertTrue(gate["blocking"])
        self.assertEqual(gate["execution"], "local")
        self.assertIn(".semgrep.yml", gate["command"])
        self.assertEqual(gate["evidence"], [".semgrep.yml"])

    def test_codeql_workflow_is_ci_only_gate(self):
        _write(self.tmp, ".github/workflows/codeql.yml",
               "jobs:\n  analyze:\n    steps:\n      - uses: github/codeql-action/init@v3\n")
        gates = sast_gates.detect(self.tmp)
        self.assertEqual([g["tool"] for g in gates], ["codeql"])
        self.assertIsNone(gates[0]["command"])
        self.assertEqual(gates[0]["execution"], "ci")
        self.assertEqual(gates[0]["evidence"], [os.path.join(".github", "workflows", "codeql.yml")])

    def test_semgrep_ci_workflow_without_local_config(self):
        _write(self.tmp, ".github/workflows/sec.yml", "steps:\n  - run: semgrep ci\n")
        gates = sast_gates.detect(self.tmp)
        self.assertEqual(gates[0]["tool"], "semgrep")
        self.assertEqual(gates[0]["execution"], "ci")

    def test_bandit_and_gitleaks_detected(self):
        _write(self.tmp, "pyproject.toml", "[tool.bandit]\nskips = []\n")
        _write(self.tmp, ".gitleaks.toml", "title = 'x'\n")
        by_tool = {g["tool"]: g for g in sast_gates.detect(self.tmp)}
        self.assertIn("bandit", by_tool)
        self.assertEqual(by_tool["gitleaks"]["category"], "secrets")

    def test_pre_commit_hook_not_duplicated_when_config_exists(self):
        _write(self.tmp, ".gitleaks.toml", "")
        _write(self.tmp, ".pre-commit-config.yaml",
               "repos:\n  - repo: x\n    hooks:\n      - id: gitleaks\n      - id: bandit\n")
        tools = [g["tool"] for g in sast_gates.detect(self.tmp)]
        self.assertEqual(tools.count("gitleaks"), 1)
        self.assertIn("bandit", tools)

    def test_package_security_script(self):
        with open(os.path.join(self.tmp, "package.json"), "w", encoding="utf-8") as fh:
            json.dump({"scripts": {"test": "jest", "security": "semgrep scan"}}, fh)
        gates = quality_gates.detect(self.tmp)
        sast = [g for g in gates if g.get("category") == "sast"]
        self.assertEqual(sast[0]["command"], "npm run security")
        self.assertTrue(sast[0]["blocking"])

    def test_discovery_reports_scanners(self):
        _write(self.tmp, ".semgrep.yml", "rules: []\n")
        info = discovery.scan(self.tmp)
        self.assertEqual(info["sast_scanners"][0]["tool"], "semgrep")

    def test_phase_runner_defers_ci_gate_without_running(self):
        _write(self.tmp, ".github/workflows/codeql.yml", "uses: github/codeql-action/analyze@v3\n")
        results = phase_runner._run_quality_gates(Path(self.tmp))
        self.assertEqual(results[0]["result"], "DEFERRED_TO_CI")
        self.assertIsNone(results[0]["exit_code"])
        report = Path(self.tmp, ".spec-master", "reports", "quality-gates.md").read_text()
        self.assertIn("DEFERRED_TO_CI", report)
        self.assertIn("CI:", report)


if __name__ == "__main__":
    unittest.main()
