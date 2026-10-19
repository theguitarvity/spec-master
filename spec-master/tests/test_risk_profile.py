import json
import os
import shutil
import tempfile
import unittest

import _pathfix  # noqa: F401
import context_delta
import decision_memory
import hooks
import metrics
import risk_profile
import state as state_mod
import team_model


def _feature(fid="f1", name="Tweak", description="Small tweak", ac=("It works",), **extra):
    feature = {"id": fid, "name": name, "description": description, "acceptance_criteria": list(ac),
               "spec_directory": f"specs/001-{fid}"}
    feature.update(extra)
    return feature


def _tasks_md(tasks):
    lines = ["# Tasks", "", "**Input**: `specs/001-f1/` plan.md, research.md, contracts/api.md", "", "## Phase 1", ""]
    for index, (title, cont) in enumerate(tasks, start=1):
        lines.append(f"- [ ] T{index:03d} {title}")
        for extra in cont:
            lines.append(f"      {extra}")
    return "\n".join(lines) + "\n"


class _Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.state = state_mod.default_state("ctx.md")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def add(self, **kwargs):
        state_mod.upsert_feature(self.state, _feature(**kwargs))
        return kwargs.get("fid", "f1")

    def write_tasks(self, tasks, fid="f1"):
        directory = os.path.join(self.root, "specs", f"001-{fid}")
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, "tasks.md"), "w", encoding="utf-8") as fh:
            fh.write(_tasks_md(tasks))

    def classify(self, fid="f1", stage="intake", **kwargs):
        return risk_profile.classify(self.root, self.state, fid, stage, **kwargs)


class ScopeAndSensitivityTests(_Base):
    def test_tiny_feature_is_xs(self):
        self.add(name="Fix typo", description="Fix a typo in the footer text")
        result = self.classify()
        self.assertEqual(result["scope"]["tier"], "XS")
        self.assertEqual(result["sensitivity"], [])
        self.assertEqual(result["tier"], "XS")
        self.assertEqual(result["profile"]["clarify"], "skippable")
        self.assertEqual(result["work_packages"], [])

    def test_auth_text_with_tiny_scope_is_L(self):
        self.add(name="Login redirect", description="Fix the login redirect after the OAuth callback")
        result = self.classify()
        self.assertEqual(result["scope"]["tier"], "XS")
        self.assertEqual(result["sensitivity"], [{"category": "auth", "floor": "L", "hook": "sensitivity-auth"}])
        self.assertEqual(result["computed_tier"], "L")
        self.assertEqual(result["tier"], "L")
        self.assertTrue(result["profile"]["adr_check"])
        self.assertEqual(len(result["work_packages"]), len(risk_profile.WORK_PACKAGE_TEMPLATE))

    def test_portuguese_text(self):
        self.add(name="Ajuste no checkout", description="Aceitar pagamento via Pix e cartão de crédito",
                 ac=["Pix aceito"])
        self.assertEqual(self.classify()["tier"], "L")
        self.add(fid="f2", name="Modelo", description="Nova migração de modelo de dados")
        result = self.classify("f2")
        self.assertEqual([s["category"] for s in result["sensitivity"]], ["schema"])
        self.assertEqual(result["tier"], "M")
        self.assertFalse(result["profile"]["adr_check"])  # schema alone is not an ADR trigger

    def test_scope_grows_with_acceptance_criteria_and_words(self):
        self.add(ac=[f"criterion {i}" for i in range(6)], description=" ".join(["word"] * 150))
        result = self.classify()
        self.assertEqual(result["scope"]["tier"], "M")
        self.assertEqual(result["scope"]["source"], "estimate")
        signals = {b["signal"] for b in result["scope"]["binding"]}
        self.assertEqual(signals, {"acceptance_criteria", "description_words"})
        self.assertTrue(all(b["exceeds"] == "S" for b in result["scope"]["binding"]))

    def test_intake_path_hints_count_files_and_layers(self):
        self.add(description="Touch the header", paths=["web/components/Header.tsx"])
        result = self.classify(paths=["api/routes/header.py", "server/services/header.py"])
        self.assertEqual(result["scope"]["signals"]["files"], 3)
        self.assertEqual(result["scope"]["layers"], ["ui", "api", "domain"])
        self.assertEqual(result["scope"]["tier"], "M")  # 3 layers > S limit of 2

    def test_paths_at_pre_implement_raise_sensitivity_and_escalate(self):
        self.add(name="Rounding fix", description="Round the displayed total to two decimals")
        intake = self.classify()
        self.assertEqual(intake["tier"], "XS")
        risk_profile.save_classification(self.state, "f1", intake)
        self.write_tasks([("Round the total in", ["`src/billing/invoice.py`"]),
                          ("Test it in `tests/test_invoice.py`", [])])
        result = self.classify(stage="pre_implement")
        self.assertEqual(result["scope"]["source"], "tasks.md")
        self.assertIn("src/billing/invoice.py", result["scope"]["paths"])
        self.assertEqual(result["sensitivity"][0]["category"], "payment")
        self.assertEqual(result["tier"], "L")
        self.assertTrue(result["escalated"])
        self.assertEqual(result["baseline"], {"tier": "XS", "source": "stored"})
        obligations = {a["obligation"] for a in result["added_obligations"]}
        self.assertTrue({"clarify", "analyze", "work_packages", "adr_check", "review"} <= obligations)
        self.assertEqual(result["rerun_phases"], ["clarify", "analyze"])

    def test_pre_implement_without_stored_intake_computes_baseline(self):
        self.add(description="Rotate the refresh token")
        self.write_tasks([("Do it", [])])
        result = self.classify(stage="pre_implement")
        self.assertEqual(result["baseline"]["source"], "computed")
        self.assertFalse(result["escalated"])

    def test_tasks_md_drives_scope(self):
        self.add(description="Big refactor")
        tasks = []
        for i in range(20):
            tasks.append((f"Update module {i} in", [f"`server/services/mod{i % 8}.py` and `web/pages/p{i % 3}.tsx`"]))
        tasks.append(("Document in research.md and contracts/api.md and `docs/guide.md`", []))
        self.write_tasks(tasks)
        result = self.classify(stage="pre_implement")
        scope = result["scope"]
        self.assertEqual(scope["source"], "tasks.md")
        self.assertEqual(scope["signals"]["tasks"], 21)
        # 8 services + 3 pages; docs/guide.md is not counted (docs and tests are
        # part of the work, not of its risk — the same rule `layers` applies).
        self.assertEqual(scope["signals"]["files"], 11)
        self.assertEqual(scope["signals"]["layers"], 2)   # domain + ui (docs not counted)
        self.assertNotIn("research.md", scope["paths"])
        self.assertNotIn("contracts/api.md", scope["paths"])
        self.assertFalse(any(p.startswith("specs/") for p in scope["paths"]))
        self.assertEqual(scope["tier"], "M")

    def test_missing_tasks_md_falls_back_with_warning(self):
        self.add()
        result = self.classify(stage="pre_implement")
        self.assertEqual(result["scope"]["source"], "estimate")
        self.assertIn("tasks.md not found", result["warnings"][0])

    def test_sensitivity_comes_from_declarative_hooks(self):
        self.add(description="Fix the login page")
        config = hooks.default_config()
        config["disabled"] = ["sensitivity-auth"]
        config["hooks"] = [{"id": "mainframe-is-xl", "on": ["feature.intake", "feature.pre_implement"],
                            "when": {"text": {"matches": "(?i)mainframe"}},
                            "action": {"type": "raise_tier", "category": "legacy", "floor": "XL"}}]
        os.makedirs(os.path.join(self.root, ".spec-master"), exist_ok=True)
        with open(hooks.config_path(self.root), "w") as fh:
            json.dump(config, fh)
        self.assertEqual(self.classify()["sensitivity"], [])
        self.add(fid="f2", description="Sync with the mainframe")
        result = self.classify("f2")
        self.assertEqual(result["sensitivity"], [{"category": "legacy", "floor": "XL", "hook": "mainframe-is-xl"}])
        self.assertEqual(result["tier"], "XL")

    def test_emit_event_logs_sensitivity_firings(self):
        self.add(description="Store the API key in the vault")
        result = risk_profile.emit_event(self.root, self.state, "f1", "intake")
        self.assertEqual(result["directives"][0]["type"], "raise_tier")
        firings = hooks.read_firings(self.root, event_type="feature.intake")
        self.assertEqual([f["hook"] for f in firings[-1]["fired"]], ["sensitivity-secrets"])
        self.assertEqual(firings[-1]["event"]["payload"]["feature"], "f1")

    def test_unknown_stage_and_feature(self):
        self.add()
        with self.assertRaises(ValueError):
            self.classify(stage="deploy")
        with self.assertRaises(state_mod.StateError):
            self.classify(fid="ghost")


class PathExtractionTests(unittest.TestCase):
    def test_extracts_paths_and_skips_prose_urls_and_speckit_artifacts(self):
        text = ("Edit src/auth/login.ts and ./api/routes/ (see https://x.io/a/b.py), US1/US2 and/or "
                ".env.local, db/migrations/0001.sql. Read plan.md, specs/001-x/spec.md, contracts/cli.md.")
        self.assertEqual(risk_profile.extract_paths(text),
                         ["src/auth/login.ts", "api/routes/", ".env.local", "db/migrations/0001.sql"])

    def test_task_blocks_join_continuation_lines(self):
        text = "- [ ] T001 Do a thing in\n      `lib/x.py`\n\n  stray indented prose\n- [x] T002 Done\n"
        self.assertEqual(risk_profile.task_blocks(text), ["- [ ] T001 Do a thing in `lib/x.py`", "- [x] T002 Done"])

    def test_path_layers(self):
        self.assertEqual(risk_profile.path_layer("app/db/migrations/0001.sql"), "data")
        self.assertEqual(risk_profile.path_layer("frontend/src/App.tsx"), "ui")
        self.assertEqual(risk_profile.path_layer(".claude/skills/x/SKILL.md"), "config")
        self.assertEqual(risk_profile.path_layer("widgets/thing.py"), "dir:widgets")
        self.assertIsNone(risk_profile.path_layer("README.md"))


class ThresholdTests(_Base):
    def _write(self, data):
        os.makedirs(os.path.join(self.root, ".spec-master", "risk"), exist_ok=True)
        with open(risk_profile.thresholds_path(self.root), "w") as fh:
            json.dump(data, fh)

    def test_defaults_are_valid_and_monotonic(self):
        self.assertEqual(risk_profile.validate_thresholds(risk_profile.DEFAULT_THRESHOLDS), [])
        self.assertEqual(risk_profile.load_thresholds(self.root), risk_profile.DEFAULT_THRESHOLDS)

    def test_thresholds_file_is_merged(self):
        self.add(ac=["a", "b", "c", "d"])
        self.assertEqual(self.classify()["scope"]["tier"], "S")
        self._write({"tiers": {"XS": {"acceptance_criteria": 4}}})
        loaded = risk_profile.load_thresholds(self.root)
        self.assertEqual(loaded["XS"]["acceptance_criteria"], 4)
        self.assertEqual(loaded["XS"]["tasks"], risk_profile.DEFAULT_THRESHOLDS["XS"]["tasks"])
        self.assertEqual(self.classify()["scope"]["tier"], "XS")
        self._write({"XS": {"acceptance_criteria": 3}})  # bare tier map also accepted
        self.assertEqual(risk_profile.load_thresholds(self.root)["XS"]["acceptance_criteria"], 3)

    def test_invalid_thresholds_are_rejected(self):
        for bad in ({"XS": {"tasks": 50}}, {"XS": {"vibes": 1}}, {"XL": {"tasks": 1}}, {"S": {"files": 0}},
                    {"M": {"files": True}}):
            self._write(bad)
            with self.assertRaises(ValueError, msg=bad):
                risk_profile.load_thresholds(self.root)
        with open(risk_profile.thresholds_path(self.root), "w") as fh:
            fh.write("{nope")
        with self.assertRaises(ValueError):
            risk_profile.load_thresholds(self.root)


class ProfileTests(unittest.TestCase):
    def test_ceremony_rules(self):
        for tier in risk_profile.TIER_ORDER:
            profile = risk_profile.CEREMONY_PROFILES[tier]
            small = tier in ("XS", "S")
            self.assertEqual(profile["clarify"], "skippable" if small else "required", tier)
            self.assertEqual(profile["analyze"], "light" if small else "deep", tier)
            self.assertEqual(profile["work_packages"], tier in ("L", "XL"), tier)
            self.assertEqual(profile["adr_check"], tier in ("L", "XL"), tier)
            skippable = [p for p, v in profile["phases"].items() if v != "required"]
            self.assertEqual(skippable, ["clarify"] if small else [], tier)
            self.assertEqual(set(profile["phases"]), set(state_mod.FEATURE_PHASES))

    def test_sensitive_categories_force_adr_check(self):
        self.assertTrue(risk_profile.profile_for("XS", ["payment"])["adr_check"])
        self.assertIn("payment", risk_profile.profile_for("M", ["payment", "schema"])["adr_reason"])
        self.assertFalse(risk_profile.profile_for("M", ["schema", "public_contract"])["adr_check"])
        with self.assertRaises(ValueError):
            risk_profile.profile_for("XXL")

    def test_work_packages_chain(self):
        self.assertEqual(risk_profile.work_packages("f1", "M"), [])
        packages = risk_profile.work_packages("f1", "l")
        self.assertEqual([p["id"] for p in packages],
                         ["f1-wp-contract", "f1-wp-data-model", "f1-wp-backend", "f1-wp-frontend", "f1-wp-e2e",
                          "f1-wp-docs"])
        self.assertEqual([p["owner_agent"] for p in packages],
                         ["architect", "backend-dev", "backend-dev", "frontend-dev", "qa", "tech-lead"])
        self.assertEqual(packages[0]["depends_on"], [])
        for previous, package in zip(packages, packages[1:]):
            self.assertEqual(package["depends_on"], [previous["id"]])
        roles = {r["id"] for r in team_model.AGENT_ROLES}
        for package in packages:
            self.assertIn(package["owner_agent"], roles)
            self.assertIn(package["reviewer_agent"], roles)
            self.assertNotEqual(package["owner_agent"], package["reviewer_agent"])


class OverrideTests(_Base):
    def test_override_up_is_accepted_and_logged(self):
        self.add()
        risk_profile.save_classification(self.state, "f1", self.classify())
        result = risk_profile.override(self.root, self.state, "f1", "l", "touches legacy billing", by="po")
        self.assertTrue(result["raised"])
        self.assertEqual(result["risk"]["tier"], "L")
        self.assertEqual(result["risk"]["override"]["tier"], "L")
        self.assertEqual(result["risk"]["override"]["computed_tier"], "XS")
        self.assertEqual(len(result["work_packages"]), 6)
        log = risk_profile.read_overrides(self.root)
        self.assertEqual(len(log), 1)
        self.assertEqual({k: log[0][k] for k in ("feature", "computed_tier", "forced_tier", "by", "accepted")},
                         {"feature": "f1", "computed_tier": "XS", "forced_tier": "L", "by": "po", "accepted": True})
        again = self.classify()
        self.assertEqual((again["computed_tier"], again["tier"]), ("XS", "L"))
        risk_profile.save_classification(self.state, "f1", again)
        self.assertEqual(self.state["features"][0]["risk"]["override"]["tier"], "L")  # preserved

    def test_override_down_is_rejected_and_logged(self):
        self.add(description="Fix the login flow")
        risk_profile.save_classification(self.state, "f1", self.classify())
        with self.assertRaises(ValueError):
            risk_profile.override(self.root, self.state, "f1", "S", "feels small")
        self.assertEqual(self.state["features"][0]["risk"]["tier"], "L")
        self.assertIsNone(self.state["features"][0]["risk"]["override"])
        log = risk_profile.read_overrides(self.root)
        self.assertEqual(len(log), 1)
        self.assertFalse(log[0]["accepted"])
        self.assertEqual(log[0]["forced_tier"], "S")

    def test_override_needs_reason_and_classifies_unclassified_feature(self):
        self.add()
        with self.assertRaises(ValueError):
            risk_profile.override(self.root, self.state, "f1", "M", "  ")
        self.assertEqual(risk_profile.read_overrides(self.root), [])
        result = risk_profile.override(self.root, self.state, "f1", "M", "gut feeling")
        self.assertEqual(result["risk"]["history"][0]["stage"], "intake")
        self.assertEqual(result["risk"]["history"][-1]["stage"], "override")


class SaveClassificationTests(_Base):
    def test_risk_shape(self):
        self.add(description="Add a public API endpoint")
        risk = risk_profile.save_classification(self.state, "f1", self.classify())
        self.assertEqual(set(risk), {"tier", "computed_tier", "stage", "scope_tier", "sensitivity", "override",
                                     "escalated", "classified_at", "history"})
        self.assertEqual((risk["tier"], risk["stage"], risk["scope_tier"]), ("M", "intake", "XS"))
        self.assertEqual(risk["sensitivity"], ["public_contract"])
        self.assertEqual(risk["history"][0]["stage"], "intake")

    def test_deescalation_is_reported(self):
        self.add(ac=[f"c{i}" for i in range(10)])
        risk_profile.save_classification(self.state, "f1", self.classify())
        self.write_tasks([("Change `lib/x.py`", [])])
        result = self.classify(stage="pre_implement")
        self.assertEqual(result["tier"], "XS")
        self.assertTrue(result.get("deescalated"))
        risk = risk_profile.save_classification(self.state, "f1", result)
        self.assertEqual([h["stage"] for h in risk["history"]], ["intake", "pre_implement"])


class IntakeContextTests(_Base):
    def test_context_without_snapshot_or_decisions(self):
        self.add()
        context = self.classify()["context"]
        self.assertFalse(context["delta"]["baseline"])
        self.assertEqual(context["decisions"], [])

    def test_context_uses_delta_and_decision_memory(self):
        self.add()
        context_delta.save_snapshot(self.root, context_delta.snapshot(self.root, self.state))
        decision_memory.record_decision(self.root, kind="design_gap", raised_by="frontend-dev",
                                        decision="Use tabs for the settings page", feature="f1")
        context = self.classify()["context"]
        self.assertTrue(context["delta"]["baseline"])
        self.assertEqual(len(context["decisions"]), 1)
        self.assertEqual(context["decisions"][0]["decided_by"], "ui-ux-brand")
        self.assertNotIn("context", self.classify(include_context=False))


class StateSkippedTransitionTests(unittest.TestCase):
    def setUp(self):
        self.state = state_mod.default_state("ctx.md")
        state_mod.upsert_feature(self.state, {"id": "f1"})

    def test_skipped_clarify_satisfies_plan(self):
        self.assertEqual(state_mod.SKIPPABLE_PHASES, ("clarify",))
        state_mod.transition_phase(self.state, "f1", "specify", "PASSED")
        state_mod.transition_phase(self.state, "f1", "clarify", "SKIPPED")
        state_mod.transition_phase(self.state, "f1", "plan", "RUNNING")
        state_mod.transition_phase(self.state, "f1", "plan", "PASSED")
        self.assertEqual(self.state["features"][0]["phases"]["clarify"], "SKIPPED")

    def test_only_skippable_phases_can_be_skipped(self):
        state_mod.transition_phase(self.state, "f1", "specify", "PASSED")
        state_mod.transition_phase(self.state, "f1", "clarify", "PASSED")
        for phase in ("specify", "plan", "analyze", "validate"):
            with self.assertRaises(state_mod.InvalidTransitionError):
                state_mod.transition_phase(self.state, "f1", phase, "SKIPPED")

    def test_skip_still_needs_previous_phase_and_pending_blocks(self):
        with self.assertRaises(state_mod.InvalidTransitionError):
            state_mod.transition_phase(self.state, "f1", "clarify", "SKIPPED")
        state_mod.transition_phase(self.state, "f1", "specify", "PASSED")
        with self.assertRaises(state_mod.InvalidTransitionError):
            state_mod.transition_phase(self.state, "f1", "plan", "RUNNING")


class MetricsTierFieldsTests(unittest.TestCase):
    ARGS = dict(round_id="r1", phase="plan", started_at="2026-01-01T00:00:00Z", ended_at="2026-01-01T00:10:00Z")

    def test_row_unchanged_without_new_fields(self):
        row = metrics.record_round(**self.ARGS)
        self.assertNotIn("feature_id", row)
        self.assertNotIn("tier", row)
        self.assertEqual(list(row)[-1], "features_per_hour")

    def test_feature_and_tier_are_recorded(self):
        row = metrics.record_round(**self.ARGS, notes="n", feature_id="f1", tier="s")
        self.assertEqual((row["feature_id"], row["tier"]), ("f1", "S"))
        self.assertEqual(list(row)[-3:], ["notes", "feature_id", "tier"])
        with self.assertRaises(ValueError):
            metrics.record_round(**self.ARGS, tier="huge")


if __name__ == "__main__":
    unittest.main()
