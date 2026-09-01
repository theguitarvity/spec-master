import _pathfix

import runtime_contract


def test_runtime_contract_declares_hybrid_without_model_ownership():
    result = runtime_contract.describe("hybrid")
    assert result["harness_type"] == "HYBRID"
    assert result["owns_model_runtime"] is False
    assert result["capabilities"]["workflow_state"] == "spec_master"
    assert result["capabilities"]["llm_inference"] == "host"
