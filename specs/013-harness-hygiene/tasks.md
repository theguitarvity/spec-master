# Tasks: Harness Hygiene (H1–H8)

**Input**: Design documents from `specs/013-harness-hygiene/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: REQUIRED (constitution Principle III, Spec Master TDD rule): each behaviour change gets a failing unittest first.

## Phase 1: Setup

- [x] T001 Record baseline counts (unittest: 502 run / 21 errors; pytest with flag: 631; pytest from root: 62 collection errors; `gates detect --path .`: no test gate) in specs/013-harness-hygiene/validation-report.md

## Phase 2: Foundational

No shared prerequisites — each story touches disjoint files.

## Phase 3: User Story 1 — stdlib-only test suite (P1) 🎯 MVP

**Goal**: `python3 -m unittest discover -s spec-master/tests` passes without pytest (FR-001..FR-003, FR-013).
**Independent Test**: quickstart step 1.

- [x] T002 [US1] Write AST-guided converter in the session scratchpad (not shipped) that wraps module-level `test_*` functions into a `unittest.TestCase`, turns `@pytest.fixture` into `_fixture_<name>` helpers and `tmp_path` into a per-test temp dir; bodies/asserts kept verbatim
- [x] T003 [P] [US1] Convert graph modules spec-master/tests/test_graph_{blast_radius,context,drift,enrichment,health,maps,model,ontology,parser,query,resolver,store,temporal,traversal,validation}.py
- [x] T004 [P] [US1] Convert knowledge modules spec-master/tests/test_knowledge_{manifest,model,profiles,router,validation}.py and spec-master/tests/test_traceability_graph.py
- [x] T005 [P] [US1] Wrap unittest-invisible modules spec-master/tests/test_{context_budget,evals,runtime_contract,tool_policy}.py
- [x] T006 [US1] Verify per-module test names before/after are identical (scratchpad script) and that no module in spec-master/tests imports pytest; run unittest discover (expect ≥ 631, OK)

## Phase 4: User Story 2 — pytest from the repository root (P1)

**Goal**: FR-004. **Independent Test**: quickstart step 2.

- [x] T007 [US2] Reproduce failure: `.venv/bin/python -m pytest spec-master/tests -q` → `No module named '_pathfix'` (RED)
- [x] T008 [US2] Add path-only spec-master/tests/conftest.py (no pytest import) inserting its directory into sys.path; re-run root pytest with and without path (GREEN)

## Phase 5: User Story 3 — manifest-less Python test-suite discovery (P1)

**Goal**: FR-005..FR-007. **Independent Test**: quickstart step 3.

- [x] T009 [P] [US3] Add failing tests to spec-master/tests/test_discovery.py: unittest suite in `<child>/tests` detected with `python3 -m unittest discover -s <child>/tests`; pytest-importing suite → `python3 -m pytest <dir>`; root `tests/` detected; hidden/`node_modules`/`.venv` suites ignored; dir without test files ignored; manifest repo unchanged (no `scope` key, command `pytest`)
- [x] T010 [P] [US3] Add failing tests to spec-master/tests/test_quality_gates.py: suite stack yields blocking gate named `test (python: <scope>)`; two suites yield two distinct gate names
- [x] T011 [US3] Implement `_scan_python_test_suites()` and the no-manifest fallback in spec-master/lib/discovery.py
- [x] T012 [US3] Implement scope-aware gate naming in spec-master/lib/quality_gates.py; run `gates detect --path .` on this repo and preflight the returned command

## Phase 6: User Story 4 — owner inference and parallel-by-default packages (P2)

**Goal**: FR-008, FR-009. **Independent Test**: quickstart step 4.

- [x] T013 [US4] Add failing tests to spec-master/tests/test_team_model.py: "Build CLI parser" not frontend-dev, "Compute capital gains report" not backend-dev, "Collect feedback" / "Write user guide" fall back to fullstack-dev, plurals ("Render dashboard screens", "Expose REST endpoints") still match, path tokens ("spec-master/lib/ui.py") match; string tasks and dict tasks without `depends_on` get `[]`; explicit `depends_on` preserved
- [x] T014 [US4] Implement token-based `_infer_owner` and remove implicit chaining in spec-master/lib/team_model.py

## Phase 7: User Story 5 — atomic `record-round --append` (P2)

**Goal**: FR-010, FR-011. **Independent Test**: quickstart step 5.

- [x] T015 [P] [US5] Add failing tests to spec-master/tests/test_metrics.py: `append_round` creates missing file (and parent dir), appends in order, refuses invalid JSON / non-list leaving file untouched, leaves no temp files; CLI `--append` twice → two rows; CLI without `--append` writes nothing; CLI on corrupt file exits 1
- [x] T016 [US5] Implement `metrics.append_round()` in spec-master/lib/metrics.py and `--append` in spec-master/lib/cli.py

## Phase 8: Polish & Cross-Cutting

- [x] T017 Update spec-master/PROTOCOL.md (Step 6 metrics append + workstreams no implicit chaining, Step 7 suite-detected gates) and README.md where they document the changed behaviour
- [x] T018 Record H6 → feature 17 and H7 → feature 14 deferral in specs/013-harness-hygiene/validation-report.md
- [x] T019 Run quality gates (unittest, pytest, gates detect + preflight, evals run, graph validate), confirm no third-party import in spec-master/lib or spec-master/tests (FR-013), and write specs/013-harness-hygiene/validation-report.md; add traceability rows

## Dependencies & Execution Order

- T001 first. US1 (T002→T003/T004/T005→T006) before any other story so later RED/GREEN runs use the stdlib runner.
- US2 (T007→T008) independent of US3–US5.
- US3: T009, T010 [P] → T011 → T012. US4: T013 → T014. US5: T015 → T016. US3/US4/US5 are mutually independent (different files).
- Polish (T017–T019) after all stories.

## Parallel Example

T003, T004, T005 touch disjoint test files; T009/T010/T013/T015 touch disjoint test files and can be written in parallel.

## Implementation Strategy

MVP = US1 (stdlib suite green), then US2/US3 (harness runs and gates detected), then US4/US5.
