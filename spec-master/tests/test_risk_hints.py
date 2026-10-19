"""P3: ceremony profiles declare a per-phase model/effort hint."""
import json
import unittest

import _pathfix  # noqa: F401
import risk_profile
import state as state_mod

MODELS = ("fast", "balanced", "deep")
EFFORTS = ("low", "medium", "high")


class HintTests(unittest.TestCase):
    def test_every_tier_declares_a_hint_per_phase(self):
        for tier in risk_profile.TIER_ORDER:
            hints = risk_profile.profile_for(tier)["hints"]
            self.assertEqual(sorted(hints), sorted(state_mod.FEATURE_PHASES), tier)
            for phase, hint in hints.items():
                self.assertIn(hint["model"], MODELS, (tier, phase))
                self.assertIn(hint["effort"], EFFORTS, (tier, phase))

    def test_hint_for_matches_profile(self):
        self.assertEqual(risk_profile.hint_for("M", "plan"), risk_profile.profile_for("M")["hints"]["plan"])

    def test_unknown_tier_or_phase(self):
        with self.assertRaises(ValueError):
            risk_profile.hint_for("Q", "plan")
        with self.assertRaises(ValueError):
            risk_profile.hint_for("M", "nope")

    def test_small_tiers_never_cost_more_than_large(self):
        rank = {"fast": 0, "balanced": 1, "deep": 2}
        erank = {"low": 0, "medium": 1, "high": 2}
        for phase in state_mod.FEATURE_PHASES:
            costs = [(rank[risk_profile.hint_for(t, phase)["model"]],
                      erank[risk_profile.hint_for(t, phase)["effort"]]) for t in risk_profile.TIER_ORDER]
            self.assertEqual(costs, sorted(costs), phase)

    def test_hints_are_json_serialisable(self):
        json.dumps(risk_profile.profile_for("L"))

    def test_hint_text(self):
        text = risk_profile.hint_text("M", "plan")
        self.assertIn("model", text)
        self.assertIn("effort", text)


class ControllerPromptHintTests(unittest.TestCase):
    def test_first_attempt_prompt_carries_the_hint(self):
        import controller
        prompt = controller._render_prompt("plan", 1, None, ("a",), ("plan.md",), None, hint="HINT-X")
        self.assertTrue(prompt.endswith("HINT-X"))

    def test_prompt_without_hint_is_unchanged(self):
        import controller
        base = controller._render_prompt("plan", 1, None, ("a",), ("plan.md",), None)
        self.assertNotIn("Hint", base)

    def test_retry_prompt_has_no_hint(self):
        import controller
        retry = controller._render_prompt("plan", 2, {"reason": "x"}, ("a",), ("plan.md",), None, hint="HINT-X")
        self.assertNotIn("HINT-X", retry)

    def test_phase_hint_text_from_feature_tier(self):
        import controller
        state = {"features": [{"id": "f", "risk": {"tier": "XS"}, "phases": {}}]}
        self.assertIn("tier XS", controller._phase_hint(state, "f", "plan"))
        self.assertEqual(controller._phase_hint(state, None, "plan"), "")
        self.assertEqual(controller._phase_hint({"features": [{"id": "f", "phases": {}}]}, "f", "plan"), "")


if __name__ == "__main__":
    unittest.main()
