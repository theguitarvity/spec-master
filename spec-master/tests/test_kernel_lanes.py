import json
import os
import unittest

import _pathfix  # noqa: F401
import kernel_fixtures as fx
from kernel import lanes


class TriageTests(unittest.TestCase):
    def setUp(self):
        self.root = fx.make_repo()

    def tearDown(self):
        fx.remove(self.root)

    def triage(self, intent="Fix the sum", paths=("src/calc.py", "tests/test_calc.py"), **kwargs):
        return lanes.triage(self.root, intent=intent, paths=paths, **kwargs)

    def signals(self, result, bucket):
        return {r["signal"] for r in result["reasons"][bucket]}

    def test_small_tested_change_is_a_patch(self):
        result = self.triage()
        self.assertEqual(result["lane"], "patch")
        self.assertEqual(result["signals"]["files"], 1)
        self.assertEqual(result["signals"]["untested"], [])

    def test_no_declared_paths_is_not_a_patch(self):
        self.assertEqual(self.signals(self.triage(paths=()), "standard"), {"no_paths"})

    def test_size_and_spread_raise_the_lane(self):
        many = [f"src/m{i}.py" for i in range(5)]
        result = self.triage(paths=many)
        self.assertEqual(result["lane"], "standard")
        self.assertIn("files", self.signals(result, "standard"))
        huge = [f"pkg{i}/m.py" for i in range(13)]
        self.assertEqual(self.triage(paths=huge)["lane"], "critical")
        self.assertEqual(self.triage(loc=900)["lane"], "critical")
        self.assertEqual(self.triage(loc=80)["lane"], "standard")

    def test_sensitive_paths_are_critical_and_contract_paths_need_confirmation(self):
        self.assertIn("sensitive:auth", self.signals(self.triage(paths=["src/auth/login.py"]), "critical"))
        self.assertIn("sensitive:schema", self.signals(self.triage(paths=["migrations/0002_add.sql"]), "critical"))
        self.assertIn("sensitive:irreversible", self.signals(self.triage(paths=[".github/workflows/ci.yml"]),
                                                             "critical"))
        self.assertIn("sensitive:public_contract", self.signals(self.triage(paths=["api/openapi.yaml"]), "standard"))

    def test_sensitive_words_become_questions_not_lane_changes(self):
        result = self.triage(intent="Open a pull request after fixing the sum")
        self.assertEqual(result["lane"], "patch")
        self.assertEqual([q["signal"] for q in result["questions"]], ["irreversible"])
        confirmed = self.triage(intent="Open a pull request after fixing the sum", confirmed=["irreversible"])
        self.assertEqual(confirmed["lane"], "critical")
        self.assertEqual(confirmed["questions"], [])
        denied = self.triage(intent="Open a pull request after fixing the sum", denied=["irreversible"])
        self.assertEqual((denied["lane"], denied["questions"]), ("patch", []))

    def test_manifests_untested_code_and_unresolved_items(self):
        self.assertIn("manifest", self.signals(self.triage(paths=["pyproject.toml"]), "standard"))
        self.assertIn("untested", self.signals(self.triage(paths=["src/fresh.py"]), "standard"))
        self.assertEqual(self.triage(paths=["src/fresh.py", "tests/test_fresh.py"])["signals"]["untested"], [])
        self.assertIn("unresolved", self.signals(self.triage(unresolved=1), "standard"))

    def test_override_and_policy_only_raise(self):
        self.assertEqual(self.triage(requested="standard")["lane"], "standard")
        self.assertEqual(self.triage(paths=["src/auth/x.py"], requested="patch")["lane"], "critical")
        fx.write(self.root, ".spec-master/policy.json", json.dumps({"min_lane": "standard",
                                                                    "sensitive_paths": ["src/calc.py"]}))
        result = self.triage()
        self.assertEqual(result["lane"], "critical")
        self.assertEqual({"sensitive:project", "policy"} & (self.signals(result, "critical") |
                                                           self.signals(result, "standard")),
                         {"sensitive:project", "policy"})

    def test_invalid_policy_is_an_error(self):
        for policy in ({"min_lane": "tiny"}, {"audit_started_at": "last monday"}):
            with self.subTest(policy=policy):
                fx.write(self.root, ".spec-master/policy.json", json.dumps(policy))
                with self.assertRaises(ValueError):
                    self.triage()

    def test_escalation_directive(self):
        self.assertIsNone(lanes.escalation("patch", self.triage()))
        directive = lanes.escalation("patch", self.triage(loc=80))
        self.assertEqual((directive["from"], directive["to"]), ("patch", "standard"))


class NoGateTests(unittest.TestCase):
    def test_a_repository_without_an_executable_test_gate_is_critical(self):
        root = fx.make_repo(with_tests=False)
        try:
            result = lanes.triage(root, intent="Fix the sum", paths=["src/calc.py"])
            self.assertEqual(result["lane"], "critical")
            self.assertIn("no_test_gate", {r["signal"] for r in result["reasons"]["critical"]})
        finally:
            fx.remove(root)

    def test_test_stems_skip_vendored_dirs(self):
        root = fx.make_repo()
        try:
            fx.write(root, "node_modules/pkg/test_vendor.py", "")
            self.assertIn("test_calc", lanes.test_stems(root))
            self.assertNotIn("test_vendor", lanes.test_stems(root))
            self.assertTrue(os.path.isdir(os.path.join(root, ".git")))
        finally:
            fx.remove(root)


if __name__ == "__main__":
    unittest.main()
