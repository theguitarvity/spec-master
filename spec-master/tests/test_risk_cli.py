import datetime as dt
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

import _pathfix  # noqa: F401
import calibration
import cli
import metrics
import risk_profile
import state as state_mod


def _run_cli(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(list(argv))
    return code, json.loads(buf.getvalue())


def _feature(fid, name, description, ac=("It works",)):
    return {"id": fid, "name": name, "description": description, "acceptance_criteria": list(ac),
            "spec_directory": f"specs/001-{fid}"}


class _CliBase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.state_path = os.path.join(self.root, ".spec-master", "state.json")
        state = state_mod.default_state("ctx.md")
        state_mod.upsert_feature(state, _feature("tiny", "Fix typo", "Fix a typo in the footer text"))
        state_mod.upsert_feature(state, _feature("login", "Login redirect",
                                                 "Fix the login redirect after the OAuth callback"))
        state_mod.save(self.state_path, state)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def feature(self, fid):
        return state_mod.find_feature(state_mod.load(self.state_path), fid)


class RiskClassifyCliTests(_CliBase):
    def test_classify_without_save_writes_nothing(self):
        code, out = _run_cli("risk", "classify", "--path", self.root, "--feature", "login")
        self.assertEqual(code, 0)
        self.assertEqual((out["tier"], out["stage"]), ("L", "intake"))
        self.assertEqual([s["category"] for s in out["sensitivity"]], ["auth"])
        self.assertNotIn("hook_directives", out)
        self.assertNotIn("risk", self.feature("login"))
        self.assertFalse(os.path.exists(os.path.join(self.root, ".spec-master", "hooks", "firings.jsonl")))

    def test_classify_save_persists_risk_and_logs_firings(self):
        code, out = _run_cli("risk", "classify", "--path", self.root, "--feature", "login", "--save")
        self.assertEqual(code, 0)
        risk = self.feature("login")["risk"]
        self.assertEqual((risk["tier"], risk["computed_tier"], risk["scope_tier"]), ("L", "L", "XS"))
        self.assertEqual(risk["sensitivity"], ["auth"])
        self.assertEqual(out["saved_risk"]["tier"], "L")
        self.assertEqual(out["hook_directives"][0]["type"], "raise_tier")
        with open(os.path.join(self.root, ".spec-master", "hooks", "firings.jsonl"), encoding="utf-8") as fh:
            firings = [json.loads(line) for line in fh if line.strip()]
        self.assertEqual(firings[-1]["event"]["type"], "feature.intake")
        self.assertIn("sensitivity-auth", [f["hook"] for f in firings[-1]["fired"]])

    def test_paths_hint_and_explicit_state(self):
        other = os.path.join(self.root, "elsewhere.json")
        shutil.copy(self.state_path, other)
        code, out = _run_cli("risk", "classify", "--path", self.root, "--feature", "tiny", "--state", other,
                             "--paths", "src/payments/charge.py, src/payments/refund.py", "--save")
        self.assertEqual(code, 0)
        self.assertIn("payment", [s["category"] for s in out["sensitivity"]])
        self.assertIn("src/payments/charge.py", out["scope"]["paths"])
        self.assertEqual(state_mod.find_feature(state_mod.load(other), "tiny")["risk"]["tier"], "L")
        self.assertNotIn("risk", self.feature("tiny"))

    def test_pre_implement_stage_reports_baseline(self):
        _run_cli("risk", "classify", "--path", self.root, "--feature", "tiny", "--save")
        code, out = _run_cli("risk", "classify", "--path", self.root, "--feature", "tiny",
                             "--stage", "pre_implement", "--paths", "src/auth/session.py")
        self.assertEqual(code, 0)
        self.assertEqual(out["baseline"], {"tier": "XS", "source": "stored"})
        self.assertTrue(out["escalated"])
        self.assertIn("analyze", out["rerun_phases"])

    def test_unknown_feature_is_an_error(self):
        code, out = _run_cli("risk", "classify", "--path", self.root, "--feature", "nope")
        self.assertEqual(code, 1)
        self.assertIn("error", out)


class RiskOverrideCliTests(_CliBase):
    def test_override_up_is_saved_and_logged(self):
        code, out = _run_cli("risk", "override", "--path", self.root, "--feature", "tiny", "--tier", "m",
                             "--reason", "touches billing reports", "--by", "tech-lead")
        self.assertEqual(code, 0)
        self.assertTrue(out["raised"])
        risk = self.feature("tiny")["risk"]
        self.assertEqual((risk["tier"], risk["computed_tier"]), ("M", "XS"))
        self.assertEqual((risk["override"]["tier"], risk["override"]["by"]), ("M", "tech-lead"))
        log = risk_profile.read_overrides(self.root)
        self.assertEqual((log[-1]["forced_tier"], log[-1]["accepted"]), ("M", True))

    def test_override_down_is_rejected_but_logged(self):
        _run_cli("risk", "classify", "--path", self.root, "--feature", "login", "--save")
        code, out = _run_cli("risk", "override", "--path", self.root, "--feature", "login", "--tier", "S",
                             "--reason", "it is just a redirect")
        self.assertEqual(code, 1)
        self.assertIn("error", out)
        self.assertEqual(self.feature("login")["risk"]["tier"], "L")
        self.assertIsNone(self.feature("login")["risk"]["override"])
        self.assertEqual(risk_profile.read_overrides(self.root)[-1]["accepted"], False)

    def test_override_requires_non_blank_reason(self):
        code, out = _run_cli("risk", "override", "--path", self.root, "--feature", "tiny", "--tier", "L",
                             "--reason", "   ")
        self.assertEqual(code, 1)
        self.assertIn("error", out)
        self.assertEqual(risk_profile.read_overrides(self.root), [])


class RiskInfoCliTests(_CliBase):
    def test_profiles_include_effective_thresholds(self):
        os.makedirs(os.path.dirname(risk_profile.thresholds_path(self.root)), exist_ok=True)
        with open(risk_profile.thresholds_path(self.root), "w", encoding="utf-8") as fh:
            json.dump({"tiers": {"XS": {"tasks": 4}}}, fh)
        code, out = _run_cli("risk", "profiles", "--path", self.root)
        self.assertEqual(code, 0)
        self.assertEqual(out["tiers"], list(risk_profile.TIER_ORDER))
        self.assertEqual(out["profiles"]["XS"]["clarify"], "skippable")
        self.assertTrue(out["profiles"]["L"]["work_packages"])
        self.assertEqual(out["thresholds"]["XS"]["tasks"], 4)
        self.assertEqual(out["thresholds"]["S"], risk_profile.DEFAULT_THRESHOLDS["S"])

    def test_work_packages_only_for_large_tiers(self):
        code, out = _run_cli("risk", "work-packages", "--feature", "f9", "--tier", "l")
        self.assertEqual(code, 0)
        self.assertEqual(out["tier"], "L")
        self.assertEqual([p["id"] for p in out["packages"]][:2], ["f9-wp-contract", "f9-wp-data-model"])
        self.assertEqual(out["packages"][1]["depends_on"], ["f9-wp-contract"])
        _, small = _run_cli("risk", "work-packages", "--feature", "f9", "--tier", "S")
        self.assertEqual(small["packages"], [])


def _rows(fid, tier, count, day):
    rows = []
    base = dt.datetime(2026, 3, day, tzinfo=dt.timezone.utc)
    for index in range(count):
        stamp = (base + dt.timedelta(minutes=index * 30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        last = index == count - 1
        rows.append(metrics.record_round(round_id=f"{fid}-r{index}", phase="validate" if last else "plan",
                                         started_at=stamp, ended_at=stamp, feature_id=fid, tier=tier,
                                         features_completed=1 if last else 0))
    return rows


class MetricsCliTests(_CliBase):
    def test_record_round_with_feature_and_tier(self):
        code, row = _run_cli("metrics", "record-round", "--round-id", "r1", "--phase", "plan",
                             "--started-at", "2026-03-01T10:00:00Z", "--ended-at", "2026-03-01T10:30:00Z",
                             "--feature-id", "tiny", "--tier", "s")
        self.assertEqual(code, 0)
        self.assertEqual((row["feature_id"], row["tier"]), ("tiny", "S"))
        _, plain = _run_cli("metrics", "record-round", "--round-id", "r2", "--phase", "plan",
                            "--started-at", "2026-03-01T10:00:00Z", "--ended-at", "2026-03-01T10:30:00Z")
        self.assertNotIn("feature_id", plain)
        self.assertNotIn("tier", plain)

    def test_calibrate_reports_drift_and_apply_writes_thresholds(self):
        rounds_file = os.path.join(self.root, "rounds.json")
        with open(rounds_file, "w", encoding="utf-8") as fh:
            json.dump(_rows("a", "XS", 8, 1) + _rows("b", "XS", 9, 2) + _rows("c", "XS", 8, 3), fh)
        code, dry = _run_cli("metrics", "calibrate", "--path", self.root, "--rounds", rounds_file)
        self.assertEqual(code, 0)
        self.assertEqual(dry["drift"][0]["message"], "XS está custando como S há 3 features seguidas")
        self.assertNotIn("apply", dry)
        self.assertFalse(os.path.exists(risk_profile.thresholds_path(self.root)))

        code, applied = _run_cli("metrics", "calibrate", "--path", self.root, "--rounds", rounds_file, "--apply")
        self.assertEqual(code, 0)
        self.assertTrue(applied["apply"]["applied"])
        self.assertLess(risk_profile.load_thresholds(self.root)["XS"]["tasks"],
                        risk_profile.DEFAULT_THRESHOLDS["XS"]["tasks"])
        self.assertEqual(len(calibration.read_log(self.root)), 1)

        _, again = _run_cli("metrics", "calibrate", "--path", self.root, "--rounds", rounds_file)
        self.assertEqual(again["drift"], [])

    def test_calibrate_defaults_to_project_rounds_and_tolerates_missing_state(self):
        rounds_dir = os.path.join(self.root, ".spec-master", "metrics")
        os.makedirs(rounds_dir, exist_ok=True)
        with open(os.path.join(rounds_dir, "rounds.json"), "w", encoding="utf-8") as fh:
            json.dump(_rows("a", "S", 3, 1), fh)
        code, out = _run_cli("metrics", "calibrate", "--path", self.root, "--window", "2",
                             "--state", os.path.join(self.root, "missing.json"))
        self.assertEqual(code, 0)
        self.assertEqual((out["window"], out["rounds_used"]), (2, 3))
        self.assertEqual(out["drift"], [])

    def test_calibrate_rejects_invalid_window(self):
        code, out = _run_cli("metrics", "calibrate", "--path", self.root, "--window", "0")
        self.assertEqual(code, 1)
        self.assertIn("error", out)


if __name__ == "__main__":
    unittest.main()
