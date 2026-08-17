# Contract: `spec-master/lib/controller.py` CLI

Stdlib `argparse` CLI, JSON on stdout (mirrors the conventions already
established by `spec-master/lib/cli.py`).

## `run`

```text
python3 spec-master/lib/controller.py run \
  --project <path> \
  --context <path> \
  --mode {native,guarded,auto} \
  --integration opencode \
  --model <model-id> \
  [--max-attempts N]        # default 2
  [--phase-timeout SECONDS] # default 600
  [--feature <feature-id>]  # optional: tie attempts to an existing feature's phase transitions
```

- `--mode native`: prints
  `{"status": "REJECTED", "reason": "native mode does not use this controller; run the agent-driven /spec-master protocol directly"}`
  to stdout and exits `2`. No state is written.
- `--mode guarded` / `--mode auto`: drives phases
  `constitution, specify, clarify, plan, tasks, analyze, implement, validate`
  in order, one attempt loop per phase (see `data-model.md`), writing
  `state["execution"]` and `state["attempts"][<phase>]` after every
  attempt. Stops and exits non-zero the moment a phase is marked
  `BLOCKED`.
- Exit codes: `0` = all phases `PASSED` (workflow `COMPLETED`); `1` = a
  phase reached `BLOCKED`; `2` = invalid invocation (`--mode native`, bad
  `--project`/`--context`, unknown `--integration`).
- Final stdout payload (always JSON):
  ```json
  {
    "workflow_status": "COMPLETED" | "BLOCKED",
    "active_mode": "guarded",
    "mode_transitions": [...],
    "phases": {"constitution": "PASSED", "specify": "PASSED", "...": "..."},
    "blocked_phase": null,
    "attempts_summary": {"constitution": 1, "specify": 2, "...": 1},
    "quality_gates": [{"name": "...", "command": "...", "result": "PASSED", "exit_code": 0, "blocking": true}],
    "outcomes": {"constitution": "artifact_updated", "clarify": "no_changes_required", "...": "..."}
  }
  ```
  `quality_gates` is `[]` until the `validate` phase has run at least once
  (it is populated by `validate`'s attempt, per `data-model.md`'s
  "`validate` phase behavior" note — not by any other phase).
  `outcomes` (added by `specs/002-guarded-noop-phase-validation/`) maps
  each phase to its last attempt's `outcome` field
  (`artifact_updated | no_changes_required | user_decision_required |
  failed | null`) — distinct from `phases`, which reports `status`
  (`PASSED`/`FAILED`/`BLOCKED`/`PENDING`), so the report can
  differentiate an ordinary pass from a validated no-op.

## `resume`

```text
python3 spec-master/lib/controller.py resume --project <path>
```

- Loads `.spec-master/state.json`; if `state["execution"]` is absent,
  fails with `{"status": "REJECTED", "reason": "no guarded/auto run to resume"}`
  (exit `2`).
- Re-derives `--mode`/`--integration`/`--model` from
  `state["execution"]` and re-enters the same loop as `run`, starting
  from the first phase whose last attempt is not `PASSED` (or which has
  no attempts yet). Phases already `PASSED` with a matching fingerprint
  are not re-attempted (FR-010).
- If `.spec-master/run.lock` exists and is stale (older than
  `phase_timeout_seconds`), it is removed and logged before proceeding;
  if it is *not* stale, `resume` fails with
  `{"status": "REJECTED", "reason": "run already in progress (lock held)"}`
  (exit `2`).
- Same exit-code and final-payload contract as `run`.

## `status`

```text
python3 spec-master/lib/controller.py status --project <path>
```

- Read-only; never writes state or a lock.
- Output:
  ```json
  {
    "execution": {"...": "..."},
    "phases": {"constitution": "PASSED", "specify": "FAILED", "...": "PENDING"},
    "attempts_summary": {"constitution": 1, "specify": 1},
    "blocked_phase": "specify" | null
  }
  ```
- Exit `0` always (a missing state file is reported as
  `{"execution": null, "phases": {}, "attempts_summary": {}, "blocked_phase": null}`,
  not an error).
