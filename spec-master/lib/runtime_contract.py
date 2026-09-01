"""Runtime capability contract for hosted, self-hosted, and hybrid harnesses."""
from __future__ import annotations


HOSTED_CAPABILITIES = {
    "llm_inference": "host",
    "conversation_context_window": "host",
    "tool_execution": "host_with_spec_master_preflight",
    "filesystem_sandbox": "host",
    "subagent_concurrency": "host_optional",
    "workflow_state": "spec_master",
    "context_budgeting": "spec_master",
    "knowledge_routing": "spec_master",
    "graph_memory": "spec_master",
    "quality_gates": "spec_master",
    "evals": "spec_master",
}


def describe(runtime_type: str = "hosted") -> dict:
    if runtime_type not in ("hosted", "hybrid"):
        raise ValueError(f"unsupported runtime type: {runtime_type}")
    return {
        "runtime_type": runtime_type,
        "harness_type": "HYBRID" if runtime_type == "hybrid" else "HOSTED",
        "owns_model_runtime": False,
        "capabilities": HOSTED_CAPABILITIES,
        "self_hosted_blockers": [
            "Spec Master does not perform model inference.",
            "Spec Master does not provide an OS-level sandbox.",
        ],
    }
