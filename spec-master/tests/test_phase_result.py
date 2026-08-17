import unittest

import _pathfix  # noqa: F401
import phase_result


class ParsePhaseResultTests(unittest.TestCase):
    def test_single_block_after_prose_is_parsed(self):
        text = (
            "I reviewed the spec and it is already complete.\n\n"
            '{"phase_result": "no_changes_required", "checks": '
            '{"needs_clarification_markers": 0, "user_decision_required": false}}\n'
        )
        result = phase_result.parse_last_phase_result(text)
        self.assertEqual(result["phase_result"], "no_changes_required")
        self.assertEqual(result["checks"]["needs_clarification_markers"], 0)

    def test_returns_last_of_multiple_valid_blocks(self):
        text = (
            '{"phase_result": "failed", "checks": {}}\n'
            "Actually, on reflection:\n"
            '{"phase_result": "no_changes_required", "checks": {}}\n'
        )
        result = phase_result.parse_last_phase_result(text)
        self.assertEqual(result["phase_result"], "no_changes_required")

    def test_nested_checks_object_parses_correctly(self):
        text = (
            '{"phase_result": "no_changes_required", "artifact": '
            '"specs/001-x/spec.md", "checks": {"needs_clarification_markers": 0, '
            '"user_decision_required": false}}'
        )
        result = phase_result.parse_last_phase_result(text)
        self.assertEqual(result["artifact"], "specs/001-x/spec.md")
        self.assertEqual(result["checks"], {"needs_clarification_markers": 0, "user_decision_required": False})

    def test_invalid_json_is_ignored_not_raised(self):
        text = '{"phase_result": "no_changes_required", oops not json}'
        self.assertIsNone(phase_result.parse_last_phase_result(text))

    def test_unrecognized_phase_result_value_is_ignored(self):
        text = '{"phase_result": "something_else"}'
        self.assertIsNone(phase_result.parse_last_phase_result(text))

    def test_no_block_returns_none(self):
        self.assertIsNone(phase_result.parse_last_phase_result("just plain prose, no JSON here"))

    def test_object_without_phase_result_key_is_ignored(self):
        text = '{"some_other_key": "value"}'
        self.assertIsNone(phase_result.parse_last_phase_result(text))


if __name__ == "__main__":
    unittest.main()
