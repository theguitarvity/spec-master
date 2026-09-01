import _pathfix

import evals


def test_harness_evals_pass():
    result = evals.run()
    assert result["success"] is True
    assert result["failed"] == 0
    assert result["passed"] == result["total"]
