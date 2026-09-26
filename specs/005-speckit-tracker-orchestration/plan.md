# Implementation Plan: Spec Kit Tracker Orchestration

**Branch**: `005-speckit-tracker-orchestration` (trunk-based: no dedicated branch) | **Date**: 2026-09-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-speckit-tracker-orchestration/spec.md`

## Summary

Detect Spec Kit tracker-orchestration skills already installed in the target repository (evidence
from actual `SKILL.md` manifests, mirroring `discovery.py`'s existing manifest-only detection
precedent), and surface a detect-then-instruct orchestration result the agent acts on — never a
Spec-Master-owned tracker client. Adds one new optional traceability column (`issue`) so a synced
issue link/id has a structural home in the matrix. Zero new tracker-sync logic; `speckit-
taskstoissues` (already installed, already working) is reused unmodified (research.md #3, #4;
constitution Principle VII).

## Technical Context

**Language/Version**: Python 3 (stdlib only), matching the rest of `spec-master/lib/`

**Primary Dependencies**: None — reads `SKILL.md` YAML front-matter with a minimal hand-rolled
parser (no `pyyaml`; the front-matter is a small flat key/value block, same complexity class as
`discovery.py`'s existing `json.load` manifest reads); no new Python package

**Storage**: Filesystem only — reads existing `SKILL.md` files; the new `issue` field lives on
existing traceability rows in `.spec-master/state.json`; no new file

**Testing**: `python3 -m unittest discover -s spec-master/tests -v`; detection/orchestration
functions are pure filesystem readers (no subprocess, no network) — mocked via a temp-directory
fixture the same way `test_discovery.py` already mocks manifest presence

**Target Platform**: Same as the rest of the repo — any host with Python 3; no new platform
constraint

**Project Type**: Library/CLI (extends `spec-master/lib/` + `cli.py`; does not modify
`discovery.py`'s existing fields or `.claude/skills/speckit-taskstoissues/SKILL.md`)

**Performance Goals**: SC-001/SC-002 — detection and orchestration are 100% deterministic given a
fixed filesystem state in the test suite; no new performance goal, detection is a bounded directory
walk identical in cost to `discovery.py`'s existing `speckit_commands` scan

**Constraints**: No tracker network/API call anywhere in `spec-master/lib/` (research.md #3,
SC-003); `tracker_type` classification MUST be evidence-based (skill's own declared metadata only,
research.md #2); the new `issue` traceability column MUST NOT change rendered output for any row
that doesn't set it (research.md #4, FR-007)

**Scale/Scope**: One new module (`spec-master/lib/tracker_orchestration.py`) exposing
`detect_tracker_extensions(root) -> list[dict]` and `orchestrate(root) -> dict`; one additive field
(`tracker_extensions`) on `discovery.scan()`'s return value; one new `cli.py` subcommand
(`tracker orchestrate`); one additive column (`issue`) on `traceability.py`; zero changes to
`discovery.py`'s existing scan functions' behavior, `team_model.py`, `worktree.py`, or
`team_workstreams.py`

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design below.*

| Principle | Check | Result |
|---|---|---|
| I. Deterministic Core | Detection and orchestration-instruction building are pure stdlib functions in `spec-master/lib/tracker_orchestration.py`; actually invoking a detected Skill and judging its result is semantic work the orchestrating agent performs after calling the CLI verb, never something the core decides | PASS |
| II. Stdlib-Only | No new dependency; front-matter parsing is a minimal hand-rolled reader, not a YAML library | PASS |
| III. Test-First, Mockable Boundaries | `tracker_orchestration.py` functions take a `root` path and only read files under it — mockable via a temp-directory fixture exactly like `test_discovery.py`'s existing pattern | PASS |
| IV. Atomic, Verifiable State Promotion | An extension is reported only when its manifest file + matching metadata both exist; no path exists to report a tracker extension from directory presence alone (spec.md US1 Acceptance Scenario 3) | PASS |
| V. Non-Destructive Recovery | Orchestration never deletes or mutates a target repository's files; it only reads `SKILL.md` and writes an additive traceability column | PASS |
| VI. Backwards-Compatible Evolution | `discovery.scan()`'s existing fields are unchanged in value and shape (FR-003); `traceability.render()`'s output for any pre-existing row is byte-for-byte identical (FR-007, SC-004) | PASS |
| VII. Reuse the Ecosystem Before Reimplementing It | `speckit-taskstoissues` is detected and instructed, never reimplemented or modified; no bespoke Jira/Azure DevOps/Linear client is written (SC-003) | PASS |
| VIII. Auto-Detected Quality Gates, Never Hardcoded | Not a quality gate itself, but detection follows the identical "never hardcode, only report what a manifest on disk actually proves" discipline `quality_gates.py` established | PASS |
| IX. Scoped Dependency Exceptions | Not applicable — no new dependency introduced | N/A |

No violations; Complexity Tracking section below is empty.

## Project Structure

### Documentation (this feature)

```text
specs/005-speckit-tracker-orchestration/
├── plan.md                    # This file
├── research.md                # Phase 0 output
├── data-model.md              # Phase 1 output
├── quickstart.md              # Phase 1 output
├── contracts/
│   └── cli-tracker.md         # Phase 1 output
└── tasks.md                   # Phase 2 output (/speckit-tasks, not this command)
```

### Source Code (repository root)

```text
spec-master/
├── lib/
│   ├── discovery.py               # extended — new tracker_extensions field, existing fields unchanged
│   ├── tracker_orchestration.py   # NEW — detect_tracker_extensions(), orchestrate()
│   ├── traceability.py            # extended — new optional `issue` column
│   └── cli.py                     # extended — new `tracker orchestrate` verb
└── tests/
    ├── test_discovery.py          # existing — MUST still pass unmodified (SC-004)
    ├── test_traceability.py       # existing — MUST still pass unmodified (SC-004)
    └── test_tracker_orchestration.py   # NEW
```

**Structure Decision**: Single project (Option 1 from the template) — one new module beside
`discovery.py`, following the codebase's established one-module-per-concern convention; `discovery.py`
and `traceability.py` each gain one additive field/column rather than being forked or wrapped.

## Complexity Tracking

*No Constitution Check violations — this section intentionally left empty.*
