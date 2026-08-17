# Feature Specification: Guarded Mode Controller

**Feature Branch**: `001-guarded-mode-controller` (trunk-based: no dedicated branch created, isolated logically under this directory)

**Created**: 2026-08-17

**Status**: Draft

**Input**: User description: "Adicionar ao Spec Master três modos de execução (native, guarded, auto) e um controlador determinístico que, em modo guarded, conduza todas as transições de fase e entregue ao modelo somente uma fase por sessão, validando artefatos antes de promover o estado." (docs/spec-master/guarded-mode-spec.md)

## Clarifications

### Session 2026-08-17

- Q: The spec says `auto` mode migrates to `guarded` after two "recoverable events" (wrong path, un-removed placeholder, artifact in wrong location, recoverable tool-error stop). Does that 2-event count accumulate across the whole workflow, or reset at the start of each phase? → A: Cumulative across the whole workflow — the recoverable-event counter is a single workflow-level counter, not reset per phase.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run a workflow protected against an unreliable model (Priority: P1)

An operator running Spec Master against a smaller/less reliable local model
invokes `/spec-master --mode guarded context.md`. Each Spec Kit phase
(`constitution`, `specify`, `clarify`, `plan`, `tasks`, `analyze`,
`implement`, `validate`) runs in its own isolated session with only that
phase's minimal context. The controller only advances the workflow after
verifying the phase's required artifact actually exists, is non-empty, and
contains no leftover template placeholders.

**Why this priority**: This is the core value proposition of the whole
feature — without it, `guarded` mode doesn't exist and there is no
protection against a model declaring false success.

**Independent Test**: Can be fully tested by running the guarded-mode
controller against a fake agent that produces a valid constitution and
confirming the phase is promoted to `PASSED` only after the artifact is
verified — see integration scenario 1 in `docs/spec-master/guarded-mode-spec.md`
§16.

**Acceptance Scenarios**:

1. **Given** a fresh project with no prior `.spec-master/state.json`, **When**
   the operator runs the guarded-mode CLI for the `constitution` phase,
   **Then** the controller creates a snapshot, runs the phase in an isolated
   session, and only marks `constitution` as `PASSED` after confirming
   `.specify/memory/constitution.md` has no remaining placeholders.
2. **Given** a fake agent that returns exit code 0 without modifying any
   required artifact, **When** the controller validates the attempt,
   **Then** the phase is marked `FAILED` (not `PASSED`) and the failure
   reason is recorded.

---

### User Story 2 - Automatic degradation when the model misbehaves (Priority: P1)

An operator runs `/spec-master context.md` without specifying `--mode`
(defaulting to `auto`). The workflow starts in `native` (full agentic
control). If the model creates application code before the `implement`
phase, writes outside the current phase's allowlist, prints a simulated
tool call as plain text, declares a phase complete without producing its
artifact, tries to re-enter the Spec Master skill mid-phase, or triggers
two recoverable events (wrong path, un-removed placeholder, artifact in
the wrong location, or a recoverable tool-error stop), the workflow
irreversibly switches to `guarded` mode for the remainder of the run and
resumes from the first phase not yet validated.

**Why this priority**: This is what makes `auto` — the documented default
mode — safe to use without the operator having to pre-judge whether a
given model needs guarding.

**Independent Test**: Can be fully tested by simulating each critical/
recoverable event against a fake agent driving the `auto` mode and
confirming `mode_transition: native -> guarded` is recorded with the
correct reason, and that mode never reverts to `native` within the same
workflow — see integration scenarios 3-5 in `docs/spec-master/guarded-mode-spec.md`
§16.

**Acceptance Scenarios**:

1. **Given** a workflow running in `auto`/`native`, **When** the model
   creates `src/app.py` during the `constitution` phase, **Then** the
   controller rejects the attempt, records the critical event, and
   transitions `active_mode` from `native` to `guarded`.
2. **Given** a workflow already transitioned to `guarded` mid-run, **When**
   the run is later resumed, **Then** it never returns to `native` and
   resumes from the first phase not yet `PASSED`.

---

### User Story 3 - Resume an interrupted protected run without redoing valid work (Priority: P2)

An operator's guarded-mode run is interrupted (process killed, machine
restarted, timeout). Running `resume` for the same project picks up from
the first phase that isn't yet validated, without re-running phases whose
artifacts and fingerprint are still valid, and without needing to redo the
whole workflow.

**Why this priority**: Without safe resume, every interruption costs the
full workflow's worth of (slow, local-model) work, which defeats the
purpose of running smaller models at all.

**Independent Test**: Can be fully tested by starting a guarded run,
killing it after one phase passes, then invoking `resume` and confirming
only the remaining phases execute — see integration scenario 8 and
acceptance criterion 7 in `docs/spec-master/guarded-mode-spec.md`.

**Acceptance Scenarios**:

1. **Given** a guarded run where `constitution` is `PASSED` with a matching
   fingerprint, **When** the operator runs `resume`, **Then** the
   controller does not re-run `constitution` and starts at the next
   `PENDING` phase.
2. **Given** an abandoned `run.lock` older than the configured phase
   timeout, **When** the operator runs `resume`, **Then** the controller
   recognizes the lock as stale and proceeds instead of blocking
   indefinitely.

---

### User Story 4 - Trustworthy final report distinguishing workflow success from model performance (Priority: P2)

After a guarded/auto run completes (or gets `BLOCKED`), the operator reads
a final report that clearly separates the workflow's own result, each
quality gate's result, the model's actual contribution, rejected attempts,
any mode change, and which files were preserved for diagnosis — so a
project that only got built because the controller repeatedly retried and
guided the model is never mistaken for evidence that the evaluated model
performed well.

**Why this priority**: This is the stated purpose of running models in
guarded mode in the first place — evaluating a model's real capability —
and an inflated report would silently defeat that purpose.

**Independent Test**: Can be fully tested by running the full simulated
workflow with a fake agent through `COMPLETED` and confirming the report
contains distinguishable sections for workflow result vs. model
contribution — see integration scenario 8 (`docs/spec-master/guarded-mode-spec.md`
§16) and acceptance criterion 8 (§17).

**Acceptance Scenarios**:

1. **Given** a completed guarded workflow where two attempts were rejected
   before a phase passed, **When** the final report is generated, **Then**
   it lists the rejected attempts separately from the passing attempt and
   never reports the workflow as an unqualified model success.

---

### Edge Cases

- What happens when the model exhausts `max_attempts_per_phase` (default 2)
  on a phase? → The phase is marked `BLOCKED` and the workflow stops; it is
  not silently skipped or force-passed.
- What happens when a new attempt is started after a failure? → It receives
  only the objective failure cause, the allowlist, and the expected
  artifacts for that phase — never the full prior transcript.
- What happens when the context file changes between a `PASSED` phase and a
  resume? → The existing fingerprint/staleness mechanism determines which
  phases go stale; `implement` is never auto-invalidated without an impact
  assessment.
- What happens when the controller itself, or a file outside the project,
  is targeted for a write by the model? → The write is rejected regardless
  of phase allowlist; the engine, credentials, `.git/`, `.spec-master/state.json`,
  and prior transcripts are always protected.
- What happens when `analyze` keeps finding blocking issues after repeated
  repair cycles? → After 3 exhausted repair cycles the feature is marked
  `BLOCKED` and escalated, matching the existing (non-guarded) analyze
  repair-cycle limit already enforced by the core.
- What happens if the requested integration (e.g. OpenCode) isn't
  installed/reachable? → Out of scope to auto-install; this is a stopping
  condition, not something the controller silently works around.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001** (GM-001): The command interface MUST accept exactly
  `native`, `guarded`, and `auto` as `--mode` values and reject anything
  else.
- **FR-002** (GM-002): When `--mode` is omitted, the effective mode MUST be
  `auto`.
- **FR-003** (GM-003): In `guarded` mode, the controller MUST run every
  phase in an isolated session containing no history of previous phases.
- **FR-004** (GM-004): The controller MUST NOT promote any phase's status
  to `PASSED` without validating that its required artifact(s) exist, are
  non-empty, and contain no unresolved template placeholders (e.g.
  `[PROJECT_NAME]`).
- **FR-005** (GM-005): The controller MUST reject any write outside the
  allowlist of paths permitted for the current phase (per the contract in
  `docs/spec-master/guarded-mode-spec.md` §6), and treat the attempt as
  failed.
- **FR-006** (GM-006): The controller MUST detect and reject an attempt
  that creates application code before the `implement` phase.
- **FR-007** (GM-007): The controller MUST detect tool calls printed as
  plain text (e.g. `<function=`, `<tool_call>`, or equivalent patterns used
  as a substitute for a real tool invocation) and reject the attempt.
- **FR-008** (GM-008): The controller MUST enforce a per-phase timeout
  (default 600s) and a per-phase attempt limit (default 2); exhausting the
  limit MUST mark the phase `BLOCKED` and stop the workflow.
- **FR-009** (GM-009): In `auto` mode, the controller MUST migrate
  `active_mode` from `native` to `guarded` irreversibly within the same
  workflow upon any critical event (early code creation, out-of-project
  write, simulated tool call, phase falsely declared complete, rejected
  transition skip, skill re-entry mid-phase, two consecutive timeouts or
  no-progress responses) or upon accumulating two recoverable events (wrong
  path, un-removed placeholder, artifact in the wrong location, recoverable
  tool-error stop) tracked with a single counter cumulative across the
  entire workflow — not reset at the start of each phase (Clarified
  2026-08-17).
- **FR-010** (GM-010): `resume` MUST continue an interrupted or partially
  completed guarded/auto workflow without repeating phases already
  `PASSED` with a still-valid fingerprint.
- **FR-011** (GM-011): The controller MUST preserve, per attempt,
  transcripts and the objective failure cause, distinct from the state
  history of prior attempts on the same phase.
- **FR-012** (GM-012): The first guarded-mode integration MUST target
  OpenCode without changing the observable behavior of `--mode native` or
  of the existing adapters (Claude Code, Copilot, Codex).
- **FR-013**: A new attempt on a previously-failed phase MUST receive only
  the objective failure cause, the phase's allowlist, and its expected
  artifacts — not the full transcript of the previous attempt.
- **FR-014**: The controller MUST resolve and validate all paths before any
  filesystem operation, and MUST reject any modified path that resolves
  outside the project directory.
- **FR-015**: The controller MUST NOT execute `git reset --hard` or delete
  work not attributable to the current attempt; artifacts from an invalid
  attempt MUST be preserved (e.g. under `.spec-master/failed-attempts/`) or
  reverted only via a recoverable strategy.
- **FR-016**: State writes to `.spec-master/state.json` MUST remain atomic;
  only the controller may promote a phase's status in guarded/auto mode.
- **FR-017**: The final report MUST separate workflow result, per-quality-gate
  result (sourced from the `validate` phase running the project's existing
  quality gates), the model's effective contribution, rejected attempts,
  any mode change, and files preserved for diagnosis.

### Key Entities *(include if feature involves data)*

- **Execution mode**: One of `native`, `guarded`, `auto`; tracked as
  `requested_mode` (what the operator asked for) vs. `active_mode` (what is
  actually driving the workflow right now, relevant once `auto` degrades).
- **Mode transition**: A record of `{from, to, reason, timestamp}` appended
  to `state["execution"]["mode_transitions"]` whenever `auto` degrades to
  `guarded`.
- **Recoverable-event counter**: A single counter for the whole workflow
  (not per phase) that accumulates recoverable events; reaching 2 triggers
  the same `auto -> guarded` migration as a critical event (Clarified
  2026-08-17).
- **Phase attempt**: A record of `{number, status, reason, transcript}` per
  phase, capturing every try (not just the final passing one), stored under
  `state["attempts"][<phase>]`.
- **Phase contract**: The allowlist of writable paths and the set of
  required artifacts for a given phase, as defined in
  `docs/spec-master/guarded-mode-spec.md` §6.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every one of the 12 functional requirements (FR-001..FR-012 /
  GM-001..GM-012) has at least one passing automated test exercising it.
- **SC-002**: `python3 -m unittest discover -s spec-master/tests -v` passes
  with 0 failures, including all new unit and fake-agent integration tests
  described in `docs/spec-master/guarded-mode-spec.md` §16.
- **SC-003**: A fake agent that keeps the constitution template unfilled
  can never cause the workflow to report `constitution` as `PASSED`.
- **SC-004**: A fake agent that creates source code during any phase before
  `implement` can never cause that phase to be marked `PASSED`.
- **SC-005**: An interrupted guarded run, when resumed, re-executes zero
  phases that were already `PASSED` with a valid fingerprint.
- **SC-006**: The final report for a run where the controller had to retry
  or repair on behalf of the model is never textually indistinguishable
  from a report where the model succeeded unaided on the first attempt —
  the two are represented by different, explicit sections.

## Assumptions

- The abandoned-lock file is `.spec-master/run.lock` and its staleness
  threshold reuses `phase_timeout_seconds`, since the source spec (§12)
  references "the configured timeout" without naming a separate value
  (INFERRED — see `.spec-master/context/app-features.md` Open questions).
- "Guarded mode" in this spec always means the deterministic controller
  described in `docs/spec-master/guarded-mode-spec.md`, not a change to how
  `native` mode's existing agent-driven protocol (`PROTOCOL.md`) behaves.
- This feature ships within the existing `spec-master` repository/engine; it
  does not introduce a new distributable package or service.
- Only the OpenCode integration is required to be functional end-to-end for
  this feature to be considered complete; other adapters continue to run
  exclusively in `native` mode until a future increment adds guarded
  support for them (explicit non-goal in the source spec §3).
