import unittest

import _pathfix  # noqa: F401
import evals


class HarnessEvalsTests(unittest.TestCase):
    def test_harness_evals_pass(self):
        result = evals.run()
        self.assertIs(result["success"], True)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["passed"], result["total"])


if __name__ == "__main__":
    unittest.main()
