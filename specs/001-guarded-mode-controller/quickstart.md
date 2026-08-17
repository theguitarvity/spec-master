# Quickstart: Validating the Guarded Mode Controller

## Prerequisites

- Python 3.14 (stdlib only, no install step).
- This repository, at the commit where `spec-master/lib/controller.py`,
  `execution_mode.py`, `phase_contracts.py`, and the updated
  `phase_runner.py`/`opencode_runner.py` exist.

## 1. Run the deterministic test suite (no LLM, no network)

```bash
python3 -m unittest discover -s spec-master/tests -v
```

Expected: all tests pass, including the new
`test_execution_mode.py`, `test_phase_contracts.py`,
`test_phase_runner.py`, `test_controller.py`, and the fake-agent
integration cases in `test_controller.py` (see `docs/spec-master/guarded-mode-spec.md`
§16 for the full list this must cover). This is `SC-002`.

## 2. Exercise a single phase against a fake agent (fast, deterministic)

Fake agents referenced in `spec-master/tests/` fixtures stand in for
`opencode run`; no real model or OpenCode install is required for this
step, matching the NFR that unit/integration tests never depend on
Ollama/OpenCode/network. See the fake-agent scenarios enumerated in
`docs/spec-master/guarded-mode-spec.md` §16 for the exact behaviors
exercised (valid constitution, false success, early code creation,
simulated tool call, out-of-project write, retry-then-pass,
attempts-exhausted, full simulated workflow to `COMPLETED`).

## 3. Inspect status and reports

```bash
python3 spec-master/lib/controller.py status --project .
```

Expected: JSON with `phases` reflecting each phase's last-attempt status
and `blocked_phase: null` on a healthy/in-progress run.

## 4. Optional smoke test with a real model (non-blocking)

Not part of the blocking suite (`docs/spec-master/guarded-mode-spec.md`
§16, "Smoke test opcional"). Requires OpenCode and a reachable Ollama
model:

```bash
python3 spec-master/lib/controller.py run \
  --project <path-to-qwen-todo-api-case> \
  --context context.md \
  --mode guarded \
  --integration opencode \
  --model ollama-neon/qwen3-coder-agent:30b
```

Expected: a final report (printed to stdout, and human-readable status
lines emitted per attempt) that separates the workflow's own result from
the model's actual contribution — a run where the controller had to
retry or repair must never read the same as a run where the model
succeeded unaided (`SC-006`). Preserve
`.spec-master/logs/*` and any `.spec-master/failed-attempts/*` from this
run for inspection; do not treat it as evidence of the workflow's own
correctness (that's what step 1 is for).

## Out of scope for this quickstart

Wiring `--mode` into `/spec-master` itself (the agent-level command) is a
later increment (see `research.md` item 1) — this quickstart only
exercises `controller.py` directly.
