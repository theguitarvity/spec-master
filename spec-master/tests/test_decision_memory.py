import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

import _pathfix  # noqa: F401
import cli
import decision_memory
from graph.model import GraphNode
from graph.store import FileGraphStore


def _run_cli(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(list(argv))
    return code, buf.getvalue()


class DecisionMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_reading_without_graph_creates_nothing(self):
        self.assertEqual(decision_memory.decisions_for_role(self.tmp, "architect"), [])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".spec-master")))

    def test_record_links_agent_and_feature_and_is_idempotent(self):
        FileGraphStore(self.tmp).save_node(GraphNode(id="feature.checkout", type="Feature", name="Checkout"))
        kwargs = dict(kind="architecture_inconsistency", raised_by="backend-dev",
                      decision="Keep repositories behind the domain port", rationale="Consistency",
                      feature="checkout")
        first = decision_memory.record_decision(self.tmp, **kwargs)
        second = decision_memory.record_decision(self.tmp, **kwargs)
        self.assertEqual(first["node"], second["node"])
        self.assertIsNone(first["adr"])
        relations = {(e["relation"], e["target"]) for e in first["edges"]}
        self.assertIn(("DECIDED_BY", "agent.architect"), relations)
        self.assertIn(("INFLUENCES", "feature.checkout"), relations)

        store = FileGraphStore(self.tmp)
        self.assertEqual(store.get_node(first["node"]).type, "Decision")
        self.assertEqual(store.get_node("agent.architect").type, "Agent")
        decided_by = [e for e in store.all_edges() if e.relation == "DECIDED_BY"]
        self.assertEqual(len(decided_by), 1)

        for role in ("architect", "backend-dev", "tech-lead", "scrum-master"):
            self.assertEqual(len(decision_memory.decisions_for_role(self.tmp, role)), 1, role)
        self.assertEqual(decision_memory.decisions_for_role(self.tmp, "qa"), [])
        found = decision_memory.decisions_for_feature(self.tmp, "checkout")[0]
        self.assertEqual(found["decision"], "Keep repositories behind the domain port")
        self.assertEqual(found["decided_by"], "architect")

    def test_adr_written_to_existing_adr_dir_and_reused(self):
        os.makedirs(os.path.join(self.tmp, "docs", "adr"))
        open(os.path.join(self.tmp, "docs", "adr", "0007-old.md"), "w").close()
        kwargs = dict(kind="priority_conflict", raised_by="product-owner",
                      decision="Adopt Stripe: hosted checkout", alternatives=["Adyen", "In-house"],
                      adr_triggers=["new_external_provider", "rejected_alternatives"])
        result = decision_memory.record_decision(self.tmp, **kwargs)
        self.assertEqual(result["decision"]["raised_by"], "po")
        self.assertEqual(result["adr"]["number"], 8)
        path = os.path.join(self.tmp, result["adr"]["path"])
        text = open(path).read()
        self.assertIn("# ADR 0008", text)
        self.assertIn("- Adyen", text)
        again = decision_memory.record_decision(self.tmp, **kwargs)
        self.assertEqual(again["adr"]["path"], result["adr"]["path"])
        self.assertEqual(decision_memory.decisions_for_role(self.tmp, "po")[0]["adr"], result["adr"]["path"])

    def test_route_adr_candidate_falls_back_to_spec_master_dir(self):
        result = decision_memory.record_decision(self.tmp, kind="systemic_violation", raised_by="architect",
                                                 decision="Ban cross-context DB reads")
        self.assertTrue(result["adr"]["path"].startswith(os.path.join(".spec-master", "adr")))
        self.assertIn("route_adr_candidate", result["decision"]["adr_triggers"])

    def test_validation(self):
        with self.assertRaises(ValueError):
            decision_memory.record_decision(self.tmp, kind="design_gap", raised_by="frontend-dev", decision=" ")
        with self.assertRaises(ValueError):
            decision_memory.record_decision(self.tmp, kind="custom", raised_by="qa", decision="x")
        with self.assertRaises(ValueError):
            decision_memory.record_decision(self.tmp, kind="design_gap", raised_by="frontend-dev",
                                            decision="x", adr_triggers=["because"])
        ok = decision_memory.record_decision(self.tmp, kind="custom", raised_by="qa", decision="x",
                                             decided_by="ux")
        self.assertEqual(ok["decision"]["decided_by"], "ui-ux-brand")


class DecisionCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_escalate_then_resolve_records_via_hook(self):
        code, out = _run_cli("team", "escalate", "--path", self.tmp, "--kind", "design_gap",
                             "--raised-by", "frontend-dev", "--feature", "f1")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["route"]["decided_by"], "ui-ux-brand")

        code, out = _run_cli("team", "resolve", "--path", self.tmp, "--kind", "design_gap",
                             "--raised-by", "frontend-dev", "--decision", "Use the empty-state pattern",
                             "--feature", "f1")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertTrue(payload["recorded"]["executed"])
        hook_ids = [f["hook"] for f in payload["hooks"]["fired"]]
        self.assertIn("record-resolved-decision", hook_ids)

        code, out = _run_cli("team", "decisions", "--path", self.tmp, "--role", "ux")
        self.assertEqual(len(json.loads(out)["decisions"]), 1)

        code, out = _run_cli("knowledge", "for-role", "--role", "ui-ux-brand", "--path", self.tmp)
        self.assertEqual(json.loads(out)["decisions"][0]["kind"], "design_gap")

    def test_resolve_records_directly_when_hook_disabled(self):
        os.makedirs(os.path.join(self.tmp, ".spec-master"))
        with open(os.path.join(self.tmp, ".spec-master", "hooks.json"), "w") as fh:
            json.dump({"include_defaults": True, "disabled": ["record-resolved-decision"], "hooks": []}, fh)
        code, out = _run_cli("team", "resolve", "--path", self.tmp, "--kind", "delivery_risk",
                             "--raised-by", "po", "--decision", "Cut scope to MVP")
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["recorded"]["node"].startswith("decision."))

    def test_resolve_error_surfaces(self):
        code, out = _run_cli("team", "resolve", "--path", self.tmp, "--kind", "custom",
                             "--raised-by", "qa", "--decision", "x")
        self.assertEqual(code, 1)
        self.assertIn("decided_by", json.loads(out)["error"])


if __name__ == "__main__":
    unittest.main()
