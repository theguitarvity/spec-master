import unittest
import _pathfix

import evals


class EvalsTests(unittest.TestCase):

    def test_harness_evals_pass(self):
        result = evals.run()
        assert result["success"] is True
        assert result["failed"] == 0
        assert result["passed"] == result["total"]


if __name__ == "__main__":
    unittest.main()
