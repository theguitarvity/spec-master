import datetime as dt
import json
import os
import shutil
import tempfile
import unittest

import _pathfix  # noqa: F401
import calibration
import metrics
import risk_profile


def _rounds(fid, tier, count, day, tokens=0, seconds_per_round=0, completed=True):
    rows = []
    base = dt.datetime(2026, 3, day, tzinfo=dt.timezone.utc)
    for index in range(count):
        started = base + dt.timedelta(minutes=index * 30)
        start = started.strftime("%Y-%m-%dT%H:%M:%SZ")
        end = (started + dt.timedelta(seconds=seconds_per_round)).strftime("%Y-%m-%dT%H:%M:%SZ")
        last = index == count - 1
        rows.append(metrics.record_round(
            round_id=f"{fid}-r{index}", phase="validate" if last and completed else "plan",
            started_at=start, ended_at=end, input_tokens=tokens, feature_id=fid, tier=tier,
            features_completed=1 if last and completed else 0))
    return rows


def _override(fid, computed, forced, day, accepted=True):
    return {"feature": fid, "computed_tier": computed, "previous_tier": computed, "forced_tier": forced,
            "reason": "r", "by": "user", "stage": "intake", "at": f"2026-03-{day:02d}T23:00:00Z",
            "accepted": accepted}


class CalibrateTests(unittest.TestCase):
    def test_drift_after_three_consecutive_underestimated_features(self):
        rows = _rounds("a", "XS", 8, 1) + _rounds("b", "XS", 9, 2) + _rounds("c", "XS", 8, 3)
        result = calibration.calibrate(rows)
        self.assertEqual(len(result["drift"]), 1)
        drift = result["drift"][0]
        self.assertEqual(drift["message"], "XS está custando como S há 3 features seguidas")
        self.assertEqual((drift["tier"], drift["direction"], drift["features"]), ("XS", "under", ["a", "b", "c"]))
        rec = result["recommendations"][0]
        self.assertEqual((rec["target_tier"], rec["factor"]), ("XS", calibration.TIGHTEN_FACTOR))
        self.assertLess(rec["new_thresholds"]["tasks"], rec["previous_thresholds"]["tasks"])
        self.assertEqual(result["tiers"]["XS"]["under"], 3)

    def test_two_features_are_not_drift(self):
        rows = _rounds("a", "XS", 8, 1) + _rounds("b", "XS", 9, 2)
        result = calibration.calibrate(rows)
        self.assertEqual(result["drift"], [])
        self.assertEqual(result["proposed_thresholds"], result["thresholds"])

    def test_alternating_directions_are_not_drift(self):
        rows = (_rounds("a", "XS", 8, 1) + _rounds("b", "XS", 3, 2) + _rounds("c", "XS", 8, 3)
                + _rounds("d", "XS", 3, 4) + _rounds("e", "XS", 8, 5))
        result = calibration.calibrate(rows)
        self.assertEqual(result["drift"], [])
        self.assertEqual((result["tiers"]["XS"]["under"], result["tiers"]["XS"]["ok"]), (3, 2))

    def test_only_the_last_window_counts(self):
        rows = (_rounds("a", "XS", 3, 1) + _rounds("b", "XS", 8, 2) + _rounds("c", "XS", 8, 3)
                + _rounds("d", "XS", 8, 4))
        self.assertEqual(calibration.calibrate(rows)["drift"][0]["features"], ["b", "c", "d"])
        self.assertEqual(calibration.calibrate(rows, window=4)["drift"], [])

    def test_overestimated_tier_loosens_the_tier_below(self):
        rows = _rounds("a", "M", 2, 1) + _rounds("b", "M", 3, 2) + _rounds("c", "M", 2, 3)
        result = calibration.calibrate(rows)
        drift = result["drift"][0]
        self.assertEqual(drift["direction"], "over")
        self.assertEqual(drift["message"], "M está custando como XS há 3 features seguidas")
        rec = result["recommendations"][0]
        self.assertEqual((rec["target_tier"], rec["factor"]), ("S", calibration.LOOSEN_FACTOR))
        self.assertGreater(rec["new_thresholds"]["tasks"], rec["previous_thresholds"]["tasks"])

    def test_over_is_ok_when_tier_came_from_sensitivity(self):
        rows = _rounds("a", "L", 2, 1) + _rounds("b", "L", 2, 2) + _rounds("c", "L", 2, 3)
        risk = {fid: {"tier": "L", "scope_tier": "XS"} for fid in "abc"}
        result = calibration.calibrate(rows, risk=risk)
        self.assertEqual(result["drift"], [])
        self.assertIn("sensitivity", result["features"][0]["note"])
        self.assertEqual(calibration.calibrate(rows)["drift"][0]["direction"], "over")

    def test_override_counts_as_underestimate_of_computed_tier(self):
        rows = _rounds("a", "S", 10, 1) + _rounds("b", "S", 10, 2)
        overrides = [_override("c", "S", "L", 3)]
        result = calibration.calibrate(rows, overrides=overrides)
        drift = result["drift"][0]
        self.assertEqual((drift["tier"], drift["direction"], drift["features"]), ("S", "under", ["a", "b", "c"]))
        self.assertEqual(drift["costs_like"], "M")
        self.assertEqual(result["tiers"]["S"]["overrides"], 1)

    def test_three_overrides_alone_make_drift_and_rejected_ones_are_ignored(self):
        overrides = [_override(fid, "XS", "M", day) for day, fid in enumerate("abc", start=1)]
        result = calibration.calibrate([], overrides=overrides)
        self.assertEqual(result["drift"][0]["message"], "XS está custando como M há 3 features seguidas")
        overrides[-1]["accepted"] = False
        self.assertEqual(calibration.calibrate([], overrides=overrides)["drift"], [])

    def test_pending_features_do_not_count(self):
        rows = (_rounds("a", "XS", 8, 1) + _rounds("b", "XS", 8, 2) + _rounds("c", "XS", 8, 3, completed=False))
        result = calibration.calibrate(rows)
        self.assertEqual(result["drift"], [])
        self.assertEqual(result["tiers"]["XS"]["pending"], 1)

    def test_unattributed_rounds_are_ignored_and_reported(self):
        plain = metrics.record_round(round_id="x", phase="plan", started_at="2026-03-01T00:00:00Z",
                                     ended_at="2026-03-01T00:00:00Z")
        result = calibration.calibrate([plain, dict(plain, feature_id="f", tier="HUGE")])
        self.assertEqual(result["ignored_rounds"], 2)
        self.assertIn("2 round(s) sem feature_id/tier", result["notes"][0])
        self.assertEqual(result["drift"], [])

    def test_zero_token_rounds_fall_back_to_duration_then_round_count(self):
        rows = (_rounds("tok", "S", 2, 1, tokens=500_000)            # tokens > S budget -> under
                + _rounds("dur", "S", 2, 2, seconds_per_round=3000)  # 6000s > 5400s -> under
                + _rounds("cnt", "S", 10, 3))                        # 10 rounds > 9 -> under
        result = calibration.calibrate(rows)
        bases = {f["feature"]: f["basis"] for f in result["features"]}
        self.assertEqual(bases, {"tok": "total_tokens", "dur": "duration_seconds", "cnt": "rounds"})
        self.assertEqual(result["basis_counts"], {"total_tokens": 1, "duration_seconds": 1, "rounds": 1})
        joined = " ".join(result["notes"])
        self.assertIn("duração", joined)
        self.assertIn("nº de rounds", joined)
        self.assertEqual(result["drift"][0]["tier"], "S")

    def test_real_style_rounds_without_attribution(self):
        rows = [{"round_id": "r1", "phase": "specify", "started_at": "2026-09-26T12:21:55Z",
                 "ended_at": "2026-09-26T12:21:55.1+00:00", "total_tokens": 0, "duration_seconds": 0.0}]
        result = calibration.calibrate(rows)
        self.assertEqual(result["ignored_rounds"], 1)
        self.assertEqual(result["features"], [])

    def test_since_skips_consumed_observations(self):
        rows = _rounds("a", "XS", 8, 1) + _rounds("b", "XS", 8, 2) + _rounds("c", "XS", 8, 3)
        until = calibration.calibrate(rows)["drift"][0]["until"]
        self.assertEqual(calibration.calibrate(rows, since={"XS": until})["drift"], [])

    def test_invalid_window(self):
        for window in (0, -1, 1.5, True):
            with self.assertRaises(ValueError):
                calibration.calibrate([], window=window)

    def test_inputs_are_not_mutated(self):
        thresholds = json.loads(json.dumps(risk_profile.DEFAULT_THRESHOLDS))
        rows = _rounds("a", "XS", 8, 1) + _rounds("b", "XS", 8, 2) + _rounds("c", "XS", 8, 3)
        calibration.calibrate(rows, thresholds=thresholds)
        self.assertEqual(thresholds, risk_profile.DEFAULT_THRESHOLDS)


def _drifting_xs_rows():
    """Three XS features that each took 8 zero-token rounds: drifts on the round-count fallback."""
    return _rounds("a", "XS", 8, 1) + _rounds("b", "XS", 8, 2) + _rounds("c", "XS", 8, 3)


def _sourced(rows, source):
    return [dict(row, source=source) for row in rows]


class ProvenanceTests(unittest.TestCase):
    def test_manual_unverified_rounds_never_feed_calibration(self):
        rows = _sourced(_drifting_xs_rows(), "manual-unverified")
        for require_measured in (None, True, False):
            result = calibration.calibrate(rows, require_measured=require_measured)
            self.assertEqual((result["drift"], result["features"], result["rounds_used"]), ([], [], 0))
            self.assertEqual(result["ignored_rounds"], 24)
            self.assertEqual(result["ignored_by_reason"], {"unattributed": 0, "unverified": 24})
            self.assertIn("24 round(s) sem usage medido", " ".join(result["notes"]))

    def test_sourced_rounds_without_tokens_are_unverified_in_every_mode(self):
        rows = _sourced(_drifting_xs_rows(), "host-transcript")  # hand-edited: a host row must carry tokens
        result = calibration.calibrate(rows, require_measured=False)
        self.assertEqual((result["drift"], result["ignored_by_reason"]["unverified"]), ([], 24))

    def test_legacy_input_keeps_v1_fallback_but_flags_it(self):
        result = calibration.calibrate(_drifting_xs_rows())
        self.assertEqual(result["drift"][0]["tier"], "XS")
        self.assertIs(result["require_measured"], False)
        self.assertEqual(result["unverified_rounds_used"], 24)
        self.assertIn("24 round(s) v1 sem source e com 0 tokens", " ".join(result["notes"]))

    def test_require_measured_ignores_unsourced_zero_token_rounds(self):
        result = calibration.calibrate(_drifting_xs_rows(), require_measured=True)
        self.assertEqual((result["drift"], result["rounds_used"]), ([], 0))
        self.assertEqual(result["ignored_by_reason"], {"unattributed": 0, "unverified": 24})

    def test_any_sourced_row_switches_to_measured_only(self):
        measured = _sourced(_rounds("d", "S", 2, 4, tokens=1000), "host-transcript")
        result = calibration.calibrate(_drifting_xs_rows() + measured)
        self.assertIs(result["require_measured"], True)
        self.assertEqual([f["feature"] for f in result["features"]], ["d"])
        self.assertEqual((result["features"][0]["basis"], result["rounds_used"]), ("total_tokens", 2))
        self.assertEqual((result["ignored_by_reason"]["unverified"], result["unverified_rounds_used"]), (24, 0))
        self.assertEqual(result["drift"], [])

    def test_measured_rounds_still_detect_drift(self):
        rows = []
        for day, fid in enumerate("abc", start=1):
            rows += _sourced(_rounds(fid, "XS", 2, day, tokens=100_000), "host-headless")  # 200k > 150k budget
        result = calibration.calibrate(rows)
        self.assertEqual((result["drift"][0]["tier"], result["drift"][0]["direction"]), ("XS", "under"))
        self.assertEqual(result["basis_counts"]["total_tokens"], 3)
        self.assertEqual(result["ignored_rounds"], 0)

    def test_ignored_reasons_are_split_and_the_attribution_note_stays_first(self):
        unattributed = metrics.record_round(round_id="u", phase="plan", started_at="2026-03-01T00:00:00Z",
                                            ended_at="2026-03-01T00:10:00Z", input_tokens=10, source="host-transcript")
        unverified = dict(_rounds("f", "S", 1, 2)[0], source="manual-unverified")
        result = calibration.calibrate([unattributed, unverified])
        self.assertEqual(result["ignored_rounds"], 2)
        self.assertEqual(result["ignored_by_reason"], {"unattributed": 1, "unverified": 1})
        self.assertIn("sem feature_id/tier", result["notes"][0])
        self.assertIn("sem usage medido", result["notes"][1])


class ScaleTests(unittest.TestCase):
    def test_scaling_stays_monotonic_and_at_least_one(self):
        thresholds = risk_profile.merge_thresholds({"XS": {"tasks": 5, "layers": 1}, "S": {"tasks": 6, "layers": 1}})
        tightened = calibration.scale_tier(thresholds, "S", calibration.TIGHTEN_FACTOR)
        self.assertEqual(tightened["tasks"], 5)   # 6*0.8 -> 5, not below XS
        self.assertEqual(tightened["layers"], 1)  # never below the XS limit / 1
        xs = calibration.scale_tier(thresholds, "XS", calibration.TIGHTEN_FACTOR)
        self.assertEqual(xs["layers"], 1)
        loosened = calibration.scale_tier(thresholds, "XS", calibration.LOOSEN_FACTOR)
        self.assertEqual(loosened["tasks"], 6)    # capped by S
        small_step = calibration.scale_tier(risk_profile.DEFAULT_THRESHOLDS, "M", calibration.LOOSEN_FACTOR)
        self.assertEqual(small_step["layers"], 4)  # 3*1.25 rounds to 4


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_apply_writes_monotonic_thresholds_and_logs(self):
        rows = _rounds("a", "XS", 8, 1) + _rounds("b", "XS", 8, 2) + _rounds("c", "XS", 8, 3)
        rows += _rounds("d", "L", 2, 4) + _rounds("e", "L", 2, 5) + _rounds("f", "L", 2, 6)
        result = calibration.calibrate(rows, thresholds=risk_profile.load_thresholds(self.root))
        self.assertEqual({r["target_tier"] for r in result["recommendations"]}, {"XS", "M"})
        applied = calibration.apply(self.root, result)
        self.assertTrue(applied["applied"])
        with open(risk_profile.thresholds_path(self.root)) as fh:
            written = json.load(fh)
        self.assertEqual(written["source"], "calibration")
        loaded = risk_profile.load_thresholds(self.root)
        self.assertEqual(loaded, result["proposed_thresholds"])
        self.assertEqual(risk_profile.validate_thresholds(loaded), [])
        self.assertLess(loaded["XS"]["tasks"], risk_profile.DEFAULT_THRESHOLDS["XS"]["tasks"])
        self.assertGreater(loaded["M"]["tasks"], risk_profile.DEFAULT_THRESHOLDS["M"]["tasks"])
        for signal in risk_profile.SCOPE_SIGNALS:
            values = [loaded[t][signal] for t in risk_profile.LIMITED_TIERS]
            self.assertEqual(values, sorted(values), signal)
            self.assertGreaterEqual(min(values), 1)
        log = calibration.read_log(self.root)
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["previous"], risk_profile.DEFAULT_THRESHOLDS)
        self.assertEqual(set(log[0]["consumed_until"]), {"XS", "L"})
        # the consumed drift does not fire again
        again = calibration.calibrate(rows, thresholds=loaded, since=calibration.consumed_until(self.root))
        self.assertEqual(again["drift"], [])
        self.assertFalse(calibration.apply(self.root, again)["applied"])
        self.assertEqual(len(calibration.read_log(self.root)), 1)

    def test_apply_is_noop_without_adjustable_tier(self):
        rows = _rounds("a", "XL", 30, 1) + _rounds("b", "XL", 30, 2) + _rounds("c", "XL", 30, 3)
        result = calibration.calibrate(rows)
        self.assertEqual(result["drift"][0]["tier"], "XL")
        self.assertIsNone(result["recommendations"][0]["target_tier"])
        self.assertFalse(calibration.apply(self.root, result)["applied"])
        self.assertFalse(os.path.exists(risk_profile.thresholds_path(self.root)))

    def test_load_rounds(self):
        path = os.path.join(self.root, "rounds.json")
        self.assertEqual(calibration.load_rounds(path), [])
        with open(path, "w") as fh:
            json.dump({"rounds": [{"round_id": "x"}, "junk"]}, fh)
        self.assertEqual(calibration.load_rounds(path), [{"round_id": "x"}])


if __name__ == "__main__":
    unittest.main()
