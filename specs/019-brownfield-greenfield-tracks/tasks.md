# Tasks: Brownfield and Greenfield Tracks

**Tests**: REQUIRED, failing test first (Principle III).

- [x] T001 [US1] Tests+impl: `_walk_pruned` prunes `.git node_modules dist build target .venv vendor __pycache__` and hidden dirs, honours depth — spec-master/tests/test_discovery.py, spec-master/lib/discovery.py
- [x] T002 [US1] Tests+impl: `scan()` returns `packages` for monorepo sub-packages with own stacks/commands; single-package output unchanged — same files
- [x] T003 [US1] Tests+impl: `scan(root, scope)` scoping and rejection of bad scopes — same files
- [x] T004 [US1] Tests+impl: `tracks.map_codebase` (stack, architecture, conventions, risks, evidence) — spec-master/tests/test_tracks.py, spec-master/lib/tracks.py
- [x] T005 [US2] Tests+impl: `propose_constitution` evidence-only, empty repo yields `[UNRESOLVED]`, never touches `.specify/memory/constitution.md` — same files
- [x] T006 [US3] Tests+impl: `characterization_targets` ranking — same files
- [x] T007 [US4] Tests+impl: greenfield intake/propose/apply (confirmation, no overwrite, atomic) — same files
- [x] T008 CLI `tracks ...` and `discovery scan --scope` + protocol-conformance green — spec-master/lib/cli.py, spec-master/tests/test_tracks.py
- [x] T009 [P] Cards brownfield.md and greenfield.md (≤ 3 KB) — spec-master/cards/
- [x] T010 Validate: unittest, doctor, gates, evals, graph; validation-report.md
