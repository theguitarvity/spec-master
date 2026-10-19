# Contract: dispatch manifest v1 (INFERRED)

```json
{
  "schema": "spec-master.dispatch/v1",
  "feature_id": "string", "wave_index": 0, "lane": "standard|critical",
  "max_agents": 4,
  "batches": [["agent_key", "..."], ["..."]],
  "entries": [{
    "agent_key": "<feature>:<package>:sm-implement",
    "package_id": "string", "role": "sm-spec|sm-implement|sm-review",
    "card": "cards/....md", "playbook": "knowledge/playbooks/<owner>.md",
    "model": "string|null", "effort": "string|null",
    "worktree": "path|null", "branch": "string|null",
    "owner": "backend-dev", "reviewer": "fullstack-dev",
    "owned_paths": ["glob"], "depends_on": ["package_id"],
    "result_path": ".spec-master/dispatch/<feature>/<wave>/<package>.json"
  }],
  "fallback_instructions": "string (sequential steps for hosts without subagents)",
  "integration": {"auto_merge": false, "gate": "workstreams review -> integrate (Tech Lead) -> human"}
}
```

- Result record (`dispatch result`): `{schema: "spec-master.dispatch-result/v1", package_id, agent_key, role, phase_result, summary, files[], questions[], evidence, truncated, recorded_at}`, at most 8000 chars serialized.
- Scope record (`.spec-master/dispatch/scope/<agent_key>.json`) and worktree marker (`.spec-master/worktree.json`): `{main_root, agent_key, package_id, role, owned_paths[], read_only}`.
- Events consumed (token-ledger-v1 §1): `agent.started|finished` with `agent_id`, `agent_type` = role, `worktree`; `agent_key` maps to `agent_id` via the scope record (the host-provided id is recorded by `dispatch result --agent-id`).
- Per-host agent files (`contracts/host-agents.md`) are written at implement time after verifying each host's documented format.
