import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

import _pathfix  # noqa: F401
import cli
import hooks
import state as state_mod
import team_model


def _run_cli(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(list(argv))
    return code, buf.getvalue()


def _raised(text="", paths=()):
    fired = hooks.evaluate(hooks.DEFAULT_HOOKS, {"type": "feature.intake",
                                                 "payload": {"text": text, "paths": list(paths)}})
    return {f["action"]["category"]: f["action"]["floor"] for f in fired if f["action"]["type"] == "raise_tier"}


class EscalationRouteTests(unittest.TestCase):
    def test_route_follows_playbook_chain(self):
        route = team_model.escalation_route("architecture_inconsistency", "backend-dev")
        self.assertEqual(route["chain"], ["architect", "tech-lead", "scrum-master"])
        self.assertEqual(route["decided_by"], "architect")
        self.assertEqual(route["package_owner"], "tech-lead")
        self.assertTrue(route["raiser_expected"])

    def test_raiser_is_removed_from_its_own_chain(self):
        route = team_model.escalation_route("unowned_blocker", "tech-lead")
        self.assertEqual(route["chain"], ["scrum-master"])
        self.assertFalse(route["raiser_expected"])

    def test_systemic_violation_is_adr_candidate(self):
        self.assertTrue(team_model.escalation_route("systemic_violation", "architect")["adr_candidate"])

    def test_unknown_kind_or_role_raises(self):
        with self.assertRaises(ValueError):
            team_model.escalation_route("nope", "qa")
        with self.assertRaises(ValueError):
            team_model.escalation_route("design_gap", "ghost")

    def test_every_route_hop_is_a_known_role(self):
        role_ids = {r["id"] for r in team_model.AGENT_ROLES}
        for kind, route in team_model.ESCALATION_ROUTES.items():
            for hop in route["chain"]:
                self.assertIn(hop, role_ids, kind)


class HookEvaluationTests(unittest.TestCase):
    def test_defaults_are_valid(self):
        self.assertEqual(hooks.validate_hooks(hooks.DEFAULT_HOOKS), [])

    def test_blocking_gate_failure_repairs_and_security_escalates(self):
        event = {"type": "gate.result", "payload": {"gate": "sast (semgrep)", "category": "sast",
                                                    "result": "FAILED", "blocking": True}}
        fired = {f["hook"]: f["action"] for f in hooks.evaluate(hooks.DEFAULT_HOOKS, event)}
        self.assertEqual(fired["repair-on-blocking-gate-failure"]["gate"], "sast (semgrep)")
        self.assertEqual(fired["escalate-security-gate-failure"]["kind"], "security_finding")

    def test_passing_or_deferred_gate_fires_nothing(self):
        for result in ("PASSED", "DEFERRED_TO_CI"):
            event = {"type": "gate.result", "payload": {"category": "sast", "result": result, "blocking": True}}
            self.assertEqual(hooks.evaluate(hooks.DEFAULT_HOOKS, event), [])

    def test_operators(self):
        payload = {"a": {"b": 3}, "tags": ["X", "y"], "s": "Hello"}
        self.assertTrue(hooks.matches({"a.b": {"gte": 3, "lt": 4}}, payload))
        self.assertTrue(hooks.matches({"tags": {"contains": "x"}}, payload))
        self.assertTrue(hooks.matches({"s": {"matches": "^hel"}}, payload))
        self.assertTrue(hooks.matches({"missing": {"exists": False}}, payload))
        self.assertTrue(hooks.matches({"s": "Hello"}, payload))
        self.assertFalse(hooks.matches({"a.b": {"in": [1, 2]}}, payload))
        self.assertTrue(hooks.matches({"any": [{"s": "nope"}, {"a.b": 3}]}, payload))
        self.assertFalse(hooks.matches({"s": {"gt": 1}}, payload))

    def test_validate_reports_bad_hooks(self):
        errors = hooks.validate_hooks([
            {"id": "x", "on": ["nope"], "when": {"f": {"matches": "("}}, "action": {"type": "explode"}},
            {"id": "x", "on": ["gate.result"], "action": {"type": "raise_tier", "floor": "HUGE"}},
        ])
        joined = " | ".join(errors)
        for needle in ("unknown event", "invalid regex", "action.type", "duplicate id", "floor"):
            self.assertIn(needle, joined)


class SensitivityTests(unittest.TestCase):
    def test_portuguese_and_english_categories(self):
        self.assertEqual(_raised("Login com senha e OAuth"), {"auth": "L"})
        self.assertEqual(_raised("Checkout via Pix e cartão de crédito")["payment"], "L")
        self.assertEqual(_raised("Nova migração de modelo de dados"), {"schema": "M"})
        self.assertEqual(_raised("Integração com provedor externo de e-mail"), {"external_provider": "M"})
        self.assertEqual(_raised("Expose a public API endpoint")["public_contract"], "M")

    def test_secrets_ignores_plain_tokens(self):
        self.assertEqual(_raised("Count LLM tokens and design tokens per round"), {})
        self.assertEqual(_raised("Rotate the refresh token and API key")["secrets"], "L")

    def test_paths_trigger_sensitivity(self):
        raised = _raised(paths=["src/billing/invoice.py", "db/migrations/0001.sql", ".env.local"])
        self.assertEqual(raised, {"payment": "L", "schema": "M", "secrets": "L"})

    def test_author_is_not_auth(self):
        self.assertEqual(_raised("Show the author of each post"), {})


class HookEmitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_emit_logs_firings_and_resolves_escalation_route(self):
        result = hooks.emit(self.tmp, "escalation.raised", {"kind": "design_gap", "raised_by": "frontend-dev"})
        directive = result["directives"][0]
        self.assertEqual(directive["type"], "escalate")
        self.assertEqual(directive["route"]["decided_by"], "ui-ux-brand")
        firings = hooks.read_firings(self.tmp)
        self.assertEqual(firings[0]["event"]["type"], "escalation.raised")

    def test_bad_escalation_payload_becomes_directive_error(self):
        result = hooks.emit(self.tmp, "escalation.raised", {"kind": "nope", "raised_by": "qa"})
        self.assertIn("unknown escalation kind", result["directives"][0]["error"])

    def test_nothing_fired_means_no_log(self):
        hooks.emit(self.tmp, "analyze.findings", {"count": 0})
        self.assertFalse(os.path.exists(os.path.join(self.tmp, hooks.FIRINGS_RELPATH)))

    def test_project_config_overrides_and_disables(self):
        hooks.init_config(self.tmp)
        with self.assertRaises(ValueError):
            hooks.init_config(self.tmp)
        config = hooks.default_config()
        config["disabled"] = ["dashboard-refresh"]
        config["hooks"] = [{"id": "block-on-critical", "on": ["analyze.findings"],
                            "when": {"critical": {"gt": 0}}, "action": {"type": "block", "reason": "critical"}}]
        with open(hooks.config_path(self.tmp), "w") as fh:
            json.dump(config, fh)
        ids = {h["id"] for h in hooks.load_hooks(self.tmp)}
        self.assertIn("block-on-critical", ids)
        self.assertNotIn("dashboard-refresh", ids)
        result = hooks.emit(self.tmp, "analyze.findings", {"count": 2, "critical": 1, "feature": "f1"})
        types = sorted(d["type"] for d in result["directives"])
        self.assertEqual(types, ["block", "repair"])
        self.assertEqual(result["directives"][0]["feature"], "f1")

    def test_internal_actions_can_be_suppressed(self):
        result = hooks.emit(self.tmp, "workflow.status", {"status": "RUNNING"}, execute_internal=False)
        self.assertEqual(result["fired"][0]["result"]["reason"], "internal actions disabled")

    def test_safe_emit_swallows_invalid_config(self):
        os.makedirs(os.path.join(self.tmp, ".spec-master"))
        with open(hooks.config_path(self.tmp), "w") as fh:
            fh.write("{broken")
        self.assertIsNone(hooks.safe_emit(self.tmp, "workflow.status", {}))

    def test_project_root_for_state(self):
        self.assertEqual(hooks.project_root_for_state("/p/.spec-master/state.json"), "/p")
        self.assertEqual(hooks.project_root_for_state("/p/other/state.json"), "/p/other")


class HookCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmp, ".spec-master", "state.json")
        state_mod.init(self.state_path, context="ctx.md")
        s = state_mod.load(self.state_path)
        state_mod.upsert_feature(s, {"id": "f1", "name": "F1"})
        state_mod.save(self.state_path, s)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_state_transition_blocked_returns_escalation_directive(self):
        code, out = _run_cli("state", "transition", "--path", self.state_path,
                             "--feature", "f1", "--phase", "specify", "--status", "BLOCKED")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["hook_directives"][0]["kind"], "unowned_blocker")
        firings = hooks.read_firings(self.tmp, event_type="phase.transition")
        self.assertEqual(firings[-1]["event"]["payload"]["previous"], "PENDING")

    def test_state_transition_no_hooks(self):
        _run_cli("state", "transition", "--path", self.state_path, "--feature", "f1",
                 "--phase", "specify", "--status", "RUNNING", "--no-hooks")
        self.assertEqual(hooks.read_firings(self.tmp), [])

    def test_hooks_cli_emit_list_validate_firings(self):
        code, out = _run_cli("hooks", "emit", "--path", self.tmp, "--event", "gate.result",
                             "--payload-json", json.dumps({"result": "FAILED", "blocking": True, "gate": "tests"}))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["directives"][0]["type"], "repair")
        code, out = _run_cli("hooks", "list", "--path", self.tmp)
        self.assertIn("sensitivity-auth", {h["id"] for h in json.loads(out)["hooks"]})
        code, out = _run_cli("hooks", "validate", "--path", self.tmp)
        self.assertTrue(json.loads(out)["valid"])
        code, out = _run_cli("hooks", "firings", "--path", self.tmp, "--limit", "1")
        self.assertEqual(len(json.loads(out)["firings"]), 1)


if __name__ == "__main__":
    unittest.main()
