# Spec Master Constitution

## Core Principles

### I. Deterministic Core, Model-Agnostic Agent
Structural decisions (state machine, fingerprint/staleness, dependency
ordering, git-strategy planning, quality-gate detection, constitution
structural diff) MUST live in `spec-master/lib/` as pure, LLM-free Python,
callable by any agent/adapter via `spec-master/lib/cli.py`. The agent (or,
in guarded mode, the controller) handles only semantic work: reading
context, writing normalized docs, rendering phase prompts, resolving
ambiguity, and writing reports. Nothing structural is re-derived by hand
when a deterministic tool already computes it.

### II. Stdlib-Only, Zero Dependencies
`spec-master/lib/` and `spec-master/tests/` MUST use Python 3 standard
library only, and `init.sh` MUST rely on POSIX shell tooling. Adding an
external dependency requires an explicit, documented justification; the
default is always stdlib.

### III. Test-First, Mockable Boundaries
Every module under `spec-master/lib/` ships a mirrored
`spec-master/tests/test_<module>.py`. `python3 -m unittest discover -s
spec-master/tests -v` MUST pass without network access, without Ollama,
and without OpenCode installed — every external process (Spec Kit CLI,
OpenCode, git, model runtimes) is invoked through a boundary that can be
mocked in tests.

### IV. Atomic, Verifiable State Promotion
`.spec-master/state.json` writes MUST be atomic (write-temp-then-replace).
No phase, feature, or execution mode is ever promoted to a passing status
because a process exited zero — promotion requires validating that its
required artifact exists, is non-empty, and contains no unresolved
template placeholders. A workflow's own tooling is the only writer
allowed to promote `state.json`.

### V. Non-Destructive Recovery (NON-NEGOTIABLE)
Tooling in this repository MUST NEVER run `git reset --hard` or delete
work it did not itself create in the current attempt. Artifacts from a
failed or rejected attempt are preserved (e.g. under
`.spec-master/failed-attempts/`) rather than silently discarded, so a
human can always diagnose what happened.

### VI. Backwards-Compatible Evolution
Adding a new execution mode, adapter, or capability MUST NOT change the
observable behavior of an already-shipped one unless the change is
explicitly scoped and documented. `--mode native` in particular is the
baseline behavior every other mode is defined relative to, and its tests
must keep passing unmodified when new modes are added.

### VII. Reuse the Ecosystem Before Reimplementing It
Spec Master owns the harness: lane triage, step sequencing, the evidence
required to close a step, and the host enforcement (hooks) around the
agent. GitHub Spec Kit is the Critical-lane pack and the interchange
format: whenever a change runs the full cycle, every `speckit.*` phase is
executed through the integration installed for the running agent and is
never reimplemented. A change MAY close without Spec Kit artifacts only when
the deterministic triage placed it in a lighter lane (the agent can never
lower a lane) and it passes the same evidence checks as any other promotion
(Principle IV). Third-party integrations the Spec Kit ecosystem already
covers (issue trackers, extensions, presets) MUST be reused or extended
instead of building a parallel implementation from scratch.

### VIII. Auto-Detected Quality Gates, Never Hardcoded
The auto-detection precedent already used for build/test/lint gates
(`quality_gates.py`) applies to every quality gate the core adds,
including security/SAST gates: a gate's underlying command MUST be
detected from the target repository's own configuration/tooling, never
hardcoded into `spec-master/lib/`. A gate the target repository declares
itself (`.spec-master/gates.json`) counts as that repository's own
configuration.

### IX. Scoped, Documented Dependency Exceptions
Where an isolated component needs a runtime a stdlib-only implementation
cannot reasonably provide (e.g. a dedicated protocol server), Principle II
may be relaxed only for that component: the exception MUST be isolated to
its own module, MUST NOT be imported by the always-loaded core path, and
MUST be documented at the point of introduction with the reason stdlib was
insufficient.

## Execution Modes & Safety

Spec Master supports multiple execution modes (`native`, and — where a
deterministic controller is implemented — `guarded`, `auto`). In any mode
that isolates a phase in its own controller-driven session, that session
MUST run exactly one phase, be given only the minimal context that phase
needs (not a full prior transcript), respect a documented allowlist of
writable paths for that phase, and be timed out and retry-limited rather
than allowed to run unbounded. A controller MUST distinguish, in its
final report, the workflow's own result from the contribution of the
model it drove — a project completed by fallback/controller logic is
never presented as a pass for the model under evaluation.

### X. Irreversible Publishing Actions Require Explicit Confirmation
Any action that publishes or shares work outside the local repository
(e.g. opening a pull request) MUST NEVER be taken automatically as part
of a workflow. It MUST be offered as an explicit, separately confirmed
step, and the resulting description MUST include the traceability matrix
and final report so the reviewer has full context.

## Development Workflow

This project uses trunk-based development: work happens directly on the
default branch, and individual features are isolated logically under
`specs/<feature>/` rather than via long-lived feature branches. Spec Kit
phases (`speckit.*`) are executed through whichever integration/adapter is
actually installed for the running agent (Skills, commands, or generated
entrypoints) — never simulated or hand-authored as a substitute for a real
phase run. A change the triage places in a lane that does not run Spec Kit
produces that lane's own artifacts (a change note, a spec-lite) instead;
they are never presented as Spec Kit phase output.

## Governance

This constitution supersedes ad hoc conventions. Amending a ratified
principle MUST go through the same structural diff Spec Master itself
uses (`spec-master/lib/constitution_diff.py`): additions and
non-normative modifications may be applied directly, but any conflict
with a `MUST`/`NEVER`-style clause, or the removal of an existing
principle, requires explicit user approval before the file is overwritten.
Complexity in any new module must be justified against Principle I.

**Version**: 2.0.0 | **Ratified**: 2026-08-17 | **Last Amended**: 2026-09-28
