# Data Model: Guarded Mode Controller

All shapes below extend `.spec-master/state.json` (owned/written only via
`spec-master/lib/state.py`'s atomic `save()`, per Constitution Principle
IV). Nothing here replaces the existing `version`, `context`, `workflow`,
`status`, `constitution`, `features`, `quality_gates`, `fingerprint` keys
already defined in `state.py::default_state`.

## Execution

```json
"execution": {
  "requested_mode": "auto",
  "active_mode": "guarded",
  "integration": "opencode",
  "model": "ollama-neon/qwen3-coder-agent:30b",
  "recoverable_event_count": 0,
  "mode_transitions": [
    {
      "from": "native",
      "to": "guarded",
      "reason": "implementation_before_implement_phase",
      "timestamp": "2026-08-17T18:00:00Z"
    }
  ]
}
```

| Field | Type | Notes |
|---|---|---|
| `requested_mode` | `"native" \| "guarded" \| "auto"` | What was passed to `--mode`; never changes after `run` starts (FR-002). |
| `active_mode` | `"native" \| "guarded"` | What is actually driving execution right now. Equals `requested_mode` unless `requested_mode == "auto"`, in which case it starts `"native"` and may become `"guarded"` — never the reverse (FR-009). |
| `integration` | `str` | Adapter name; only `"opencode"` is implemented this increment (FR-012). |
| `model` | `str` | Passed through verbatim to the integration; not validated/resolved by the controller (explicit non-goal: "escolher ou baixar modelos automaticamente"). |
| `recoverable_event_count` | `int >= 0` | Cumulative across the **whole workflow**, not reset per phase (Clarified 2026-08-17 in `spec.md`). Reaching 2 triggers the same migration as a critical event. |
| `mode_transitions` | `list[ModeTransition]` | Append-only. Empty unless `active_mode` actually changed. |

### ModeTransition

| Field | Type | Notes |
|---|---|---|
| `from` | `"native"` | Only ever `"native"` — migration is one-directional. |
| `to` | `"guarded"` | Only ever `"guarded"`. |
| `reason` | `str` | One of the critical-event reason codes, or `"recoverable_event_threshold"` when triggered by accumulation. |
| `timestamp` | `str` (ISO 8601 UTC) | Supplied by the caller (`controller.py`), not generated inside `execution_mode.py`, so the module stays a pure function for tests. |

## Attempts

```json
"attempts": {
  "constitution": [
    {
      "number": 1,
      "status": "FAILED",
      "reason": "placeholder_artifact",
      "events": ["placeholder_not_removed"],
      "transcript": ".spec-master/logs/20260817T180000Z-constitution.jsonl",
      "changed_paths": [".specify/memory/constitution.md"],
      "forbidden_writes": [],
      "started_at": "2026-08-17T18:00:00Z",
      "finished_at": "2026-08-17T18:03:12Z"
    }
  ]
}
```

`state["attempts"]` is a dict keyed by **phase name**
(`constitution|specify|clarify|plan|tasks|analyze|implement|validate`),
each value a list of attempt records **in attempt order** (index 0 =
attempt 1). A phase is considered `PASSED` if and only if its last
attempt record has `status == "PASSED"`.

### PhaseAttempt

| Field | Type | Notes |
|---|---|---|
| `number` | `int >= 1` | 1-based; resets to 1 only if the phase is re-run after a fingerprint change invalidated a prior `PASSED` result. |
| `status` | `"PASSED" \| "FAILED"` | Never `"RUNNING"` in the persisted record — a record is only appended once the attempt finishes (or times out). |
| `reason` | `str \| null` | Objective, machine-classified cause (`"placeholder_artifact"`, `"forbidden_write"`, `"fake_tool_marker"`, `"missing_artifact"`, `"timeout"`, `"exit_nonzero"`); `null` when `status == "PASSED"`. |
| `events` | `list[str]` | Zero or more `execution_mode` event-type strings this attempt produced (see Events below); used to drive `auto` migration and to explain *why* in the final report. |
| `transcript` | `str` | Relative path to the archived transcript for this attempt; never deleted, even for a `FAILED` attempt (FR-011). |
| `changed_paths` | `list[str]` | Every path that differed between the before/after snapshot, project-relative. |
| `forbidden_writes` | `list[str]` | Subset of `changed_paths` outside the phase's allowlist (empty on a clean `PASSED`). |
| `started_at` / `finished_at` | `str` (ISO 8601 UTC) | Wall-clock bounds of the attempt; `finished_at` may reflect a timeout cutoff. |

### Events (vocabulary shared with `execution_mode.py`)

Critical (any one triggers `auto -> guarded` immediately):

- `early_implementation`
- `out_of_project_write`
- `simulated_tool_call`
- `false_phase_completion`
- `rejected_transition_skip`
- `skill_reentry`
- `no_progress` (only critical on the **second consecutive** occurrence — see below)

Recoverable (two of these, cumulative across the workflow, trigger
migration):

- `wrong_path`
- `placeholder_not_removed`
- `artifact_wrong_location`
- `recoverable_tool_error`

`no_progress` and `timeout` are recorded on every occurrence; the
*second consecutive* one (whether two timeouts, two no-progress
responses, or one of each) is what actually counts as critical, per
`docs/spec-master/guarded-mode-spec.md` §9 ("dois timeouts ou duas
respostas consecutivas sem progresso").

**Producibility this increment** (found during `analyze`, finding H1):
`early_implementation`, `out_of_project_write`, `simulated_tool_call`,
`false_phase_completion`, `wrong_path`, `placeholder_not_removed`,
`no_progress`/`timeout` are all derived directly from `phase_runner.py`'s
snapshot/transcript/artifact checks and are fully producible and tested
this increment. `artifact_wrong_location` (a required artifact's basename
appears at an unexpected path instead of its canonical glob location) and
`recoverable_tool_error` (subprocess exits non-zero without a fake-tool
marker, forbidden write, or timeout — i.e. an ordinary tool failure) are
also derivable from the same data and are wired in `phase_runner.py`.
`rejected_transition_skip` and `skill_reentry` are **vocabulary-only**
this increment: both describe behavior only observable while an agent is
driving `native` mode directly, which this increment's controller never
supervises (see `research.md` item 1) — `execution_mode.record_event`
still accepts and classifies these two event-type strings so a future
native-mode supervisor can call it, but no code path in this increment
produces them.

## Phase Contract (static, not persisted — code constant)

| Phase | Required artifacts (glob) | Allowed writes (glob) |
|---|---|---|
| `constitution` | `.specify/memory/constitution.md` | `.specify/memory/constitution.md`, `.specify/templates/*`, `.opencode/commands/*` |
| `specify` | `specs/*/spec.md`, `.specify/feature.json` | `specs/*`, `.specify/feature.json` |
| `clarify` | `specs/*/spec.md` | `specs/*/spec.md` |
| `plan` | `specs/*/plan.md` | `specs/*` |
| `tasks` | `specs/*/tasks.md` | `specs/*/tasks.md` |
| `analyze` | `specs/*/spec.md`, `specs/*/plan.md`, `specs/*/tasks.md` | `specs/*` |
| `implement` | `specs/*/tasks.md` | `*` (minus `PROTECTED_PATHS`, see below) |
| `validate` | `.spec-master/reports/traceability.md`, `.spec-master/reports/quality-gates.md` | `.spec-master/reports/*` |

`PROTECTED_PATHS` (always rejected, on top of the table above, regardless
of phase): `.git/*`, `spec-master/*` (the engine itself),
`.spec-master/state.json`, `.spec-master/logs/*`,
`.spec-master/failed-attempts/*`, and any path whose resolved absolute
form is not inside the project root.

**`validate` phase behavior** (fixed during `analyze`, finding C1): unlike
every other phase, `validate`'s attempt is not purely a passthrough to the
OpenCode adapter — before checking artifacts, `phase_runner.run_phase`
for `phase == "validate"` first invokes the existing, already-tested
`spec-master/lib/quality_gates.py` (`detect` + run each returned command),
writes `.spec-master/reports/quality-gates.md` summarizing
`{name, command, result, exit_code, blocking}` per gate, and merges the
results into `state["quality_gates"]` (the top-level key `state.py`
already defines) before the OpenCode adapter runs at all. This mirrors
`PROTOCOL.md` Step 7 exactly, reusing `quality_gates.py` rather than
duplicating gate-detection logic (Constitution Principle I). A blocking
gate failure makes the `validate` attempt `FAILED` with
`reason: "blocking_quality_gate_failed"`, independent of whatever the
OpenCode adapter itself reports.

## Run Lock

```json
{"phase": "constitution", "pid": 48213, "started_at": "2026-08-17T18:00:00Z"}
```

File: `.spec-master/run.lock`. Present only while a phase attempt is
in-flight; removed on completion (success, failure, or timeout). A lock
whose `started_at` is older than `phase_timeout_seconds` is stale and is
removed automatically by the next `run`/`resume` invocation.
