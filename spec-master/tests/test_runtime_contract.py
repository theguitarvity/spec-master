import unittest

import _pathfix  # noqa: F401
import runtime_contract


class RuntimeContractTests(unittest.TestCase):
    def test_runtime_contract_declares_hybrid_without_model_ownership(self):
        result = runtime_contract.describe("hybrid")
        self.assertEqual(result["harness_type"], "HYBRID")
        self.assertIs(result["owns_model_runtime"], False)
        self.assertEqual(result["capabilities"]["workflow_state"], "spec_master")
        self.assertEqual(result["capabilities"]["llm_inference"], "host")


if __name__ == "__main__":
    unittest.main()
