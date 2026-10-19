import unittest
import _pathfix

import runtime_contract


class RuntimeContractTests(unittest.TestCase):

    def test_runtime_contract_declares_hybrid_without_model_ownership(self):
        result = runtime_contract.describe("hybrid")
        assert result["harness_type"] == "HYBRID"
        assert result["owns_model_runtime"] is False
        assert result["capabilities"]["workflow_state"] == "spec_master"
        assert result["capabilities"]["llm_inference"] == "host"


if __name__ == "__main__":
    unittest.main()
