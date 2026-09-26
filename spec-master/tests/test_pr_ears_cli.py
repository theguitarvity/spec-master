import _pathfix  # noqa: F401

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import cli
import state as state_mod

PHASES_DONE = {p: "PASSED" for p in state_mod.FEATURE_PHASES}


def _run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(argv)
    return code, json.loads(buf.getvalue())


class PrCliTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.state_path = os.path.join(self.root, ".spec-master", "state.json")
        state = state_mod.default_state("ctx.md", workflow="git-flow")
        state_mod.upsert_feature(state, {
            "id": "checkout", "name": "Checkout", "description": "Pay for the cart.",
            "acceptance_criteria": ["When the user pays, the system shall issue a receipt"],
            "branch": "feature/checkout", "spec_directory": "specs/002-checkout", "phases": dict(PHASES_DONE),
        })
        state["traceability"] = [{"requirement": "FR-010: receipt", "feature": "checkout", "status": "VALIDATED"}]
        state_mod.save(self.state_path, state)
        git = Path(self.root) / ".git"
        (git / "refs" / "heads").mkdir(parents=True)
        (git / "refs" / "heads" / "develop").write_text("0" * 40, encoding="utf-8")
        (git / "config").write_text('[remote "origin"]\n\turl = https://github.com/acme/shop.git\n',
                                     encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_plan_requires_confirmation_then_returns_directive(self):
        code, result = _run(["pr", "plan", "--path", self.root, "--feature", "checkout"])
        self.assertEqual(code, 0)
        self.assertEqual(result["action"], "confirm_required")
        body = Path(result["body_path"]).read_text(encoding="utf-8")
        self.assertIn("FR-010: receipt", body)
        self.assertIn("- [x] When the user pays, the system shall issue a receipt", body)

        code, result = _run(["pr", "plan", "--path", self.root, "--feature", "checkout", "--confirm", "--draft"])
        self.assertEqual(code, 0)
        self.assertEqual(result["action"], "open_pr")
        self.assertEqual(result["provider"], "github")
        self.assertEqual(result["directive"]["argv"], [
            "gh", "pr", "create", "--base", "develop", "--head", "feature/checkout",
            "--title", "Checkout", "--body-file", result["body_path"], "--draft",
        ])

    def test_plan_overrides_and_explicit_state(self):
        custom_state = os.path.join(self.root, "elsewhere.json")
        shutil.copy(self.state_path, custom_state)
        code, result = _run(["pr", "plan", "--path", self.root, "--feature", "checkout", "--state", custom_state,
                             "--confirm", "--base", "main", "--remote-url", "git@gitlab.com:acme/shop.git"])
        self.assertEqual(code, 0)
        self.assertEqual(result["provider"], "gitlab")
        argv = result["directive"]["argv"]
        self.assertEqual(argv[argv.index("--target-branch") + 1], "main")

    def test_trunk_noop(self):
        state = state_mod.load(self.state_path)
        state_mod.set_workflow(state, "trunk")
        state_mod.save(self.state_path, state)
        code, result = _run(["pr", "plan", "--path", self.root, "--feature", "checkout", "--confirm"])
        self.assertEqual((code, result["action"]), (0, "noop"))

    def test_errors_are_json(self):
        code, result = _run(["pr", "plan", "--path", self.root, "--feature", "missing"])
        self.assertEqual(code, 1)
        self.assertIn("unknown feature id", result["error"])
        code, result = _run(["pr", "plan", "--path", os.path.join(self.root, "nope"), "--feature", "checkout"])
        self.assertEqual(code, 1)
        self.assertIn("state file not found", result["error"])


class EarsCliTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.state_path = os.path.join(self.root, ".spec-master", "state.json")
        state = state_mod.default_state("ctx.md")
        state_mod.upsert_feature(state, {"id": "a", "name": "A", "acceptance_criteria": [
            "When a job fails, the scheduler shall retry it", "Jobs finish quickly"]})
        state_mod.upsert_feature(state, {"id": "b", "name": "B", "acceptance_criteria": [
            "O sistema deve registrar auditoria"]})
        state_mod.save(self.state_path, state)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_text_mode_advisory_and_strict(self):
        argv = ["ears", "check", "--text", "The API shall return JSON", "--text", "Pages load fast"]
        code, result = _run(argv)
        self.assertEqual(code, 0)
        self.assertTrue(result["valid"])
        self.assertEqual((result["total"], result["ears"]), (2, 1))
        code, result = _run(argv + ["--strict"])
        self.assertEqual(code, 1)
        self.assertFalse(result["valid"])
        self.assertEqual(result["items"][1]["hints"][0]["code"], "no_modal")
        code, result = _run(["ears", "check", "--strict", "--text", "Quando o pedido for pago, o sistema deve "
                                                                     "enviar o recibo."])
        self.assertEqual((code, result["valid"], result["items"][0]["pattern"]), (0, True, "event"))

    def test_state_mode_from_project_dir_and_file(self):
        code, result = _run(["ears", "check", "--path", self.root])
        self.assertEqual(code, 0)
        self.assertEqual(result["state"], self.state_path)
        self.assertEqual([f["id"] for f in result["features"]], ["a", "b"])
        self.assertEqual(result["non_ears"], 1)

        code, result = _run(["ears", "check", "--path", self.state_path, "--strict"])
        self.assertEqual(code, 1)
        self.assertFalse(result["valid"])

        code, result = _run(["ears", "check", "--path", self.state_path, "--feature", "b", "--strict"])
        self.assertEqual((code, result["valid"]), (0, True))

    def test_state_mode_errors(self):
        code, result = _run(["ears", "check", "--path", self.root, "--feature", "zzz"])
        self.assertEqual(code, 1)
        self.assertIn("unknown feature id", result["error"])
        code, result = _run(["ears", "check", "--path", os.path.join(self.root, "missing.json")])
        self.assertEqual(code, 1)
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
