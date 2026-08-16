import unittest

import _pathfix  # noqa: F401
import traceability


class TraceabilityTests(unittest.TestCase):
    def test_render_empty_state(self):
        rendered = traceability.render({})
        self.assertIn("no requirements traced yet", rendered)

    def test_add_row_normalizes_columns(self):
        state = {}
        traceability.add_row(state, {"requirement": "R001", "source": "app-features.md"})
        row = state["traceability"][0]
        self.assertEqual(row["requirement"], "R001")
        self.assertEqual(row["status"], "")

    def test_render_is_deterministic(self):
        state = {"traceability": []}
        traceability.add_row(state, {
            "requirement": "R001", "source": "app-features.md", "feature": "F001",
            "spec": "FR-001", "plan": "P03", "task": "T007", "test": "test_x", "status": "PASS",
        })
        rendered_a = traceability.render(state)
        rendered_b = traceability.render(state)
        self.assertEqual(rendered_a, rendered_b)
        self.assertIn("| R001 | app-features.md | F001 | FR-001 | P03 | T007 | test_x | PASS |", rendered_a)


if __name__ == "__main__":
    unittest.main()
