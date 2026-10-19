# Feature Specification: Harness Hygiene (H1–H8)

**Feature Branch**: `013-harness-hygiene` (trunk-based: no dedicated branch created, isolated logically under this directory)

**Created**: 2026-10-19

**Status**: Draft

**Input**: User description: "Corrigir os achados H1–H8 da auditoria (doc §2.2) antes de qualquer otimização." (`docs/performance-multiagent-speed-roadmap.md` §2.2; `.spec-master/context/app-features.md` Ciclo 2, Feature 13)

## Grounding (DISCOVERED_FROM_CODEBASE)

- **H1**: 21 modules under `spec-master/tests/` (`test_graph_*`, `test_knowledge_*`, `test_traceability_graph`) `import pytest` and are written as pytest-style module functions with `@pytest.fixture` / `tmp_path`. `python3 -m unittest discover -s spec-master/tests` currently reports `Ran 502 tests … FAILED (errors=21)` (one import error per module), while the pytest run reports 631 tests. Four more modules (`test_context_budget`, `test_evals`, `test_runtime_contract`, `test_tool_policy`) do not import pytest but contain only module-level `def test_*` functions, which the unittest loader silently never runs (9 tests).
- **H2**: from the repository root, `pytest` fails to import every module with `No module named '_pathfix'`; the suite only works with `-o pythonpath=spec-master/tests`. There is no root `pytest.ini`/`pyproject.toml`/`conftest.py`.
- **H3**: `discovery.scan()` only recognises a Python project via a root `pyproject.toml`, `setup.cfg` or `requirements.txt`. This repository has none, so `discovery scan` returns `stacks: []` and `gates detect --path .` returns no build/test gate — the dogfood runs with no test gate.
- **H4**: `team_model._infer_owner` (`spec-master/lib/team_model.py:472-506`) uses substring membership, so "ui" matches "build", "api" matches "capital", "db" matches "feedback", making "Build CLI parser" a frontend task.
- **H5**: `team_model.build_workstreams` (`spec-master/lib/team_model.py:536-549`) makes every task depend on the previous one when it has no explicit `depends_on`, so every feature becomes a single serial chain and the parallel lanes are never exploitable.
- **H8**: `metrics record-round` (`spec-master/lib/cli.py:455-472`) only prints the row; the agent appends it to `.spec-master/metrics/rounds.json` by hand (non-atomic, error-prone).
- **H6** (analyze "light" is only a label) and **H7** (tokens always `0` in `rounds.json`) are **out of scope**: they are recorded as dependencies of features 17 (`speed-mode-tdd-first`) and 14 (`token-ledger-and-statusline`).

## Clarifications

### Session 2026-10-19

Autonomous run (no user available, per Spec Master brief): every question below had a reasonable default and none was blocking, so each was resolved as INFERRED.

- Q: Is dropping the implicit serial chaining in `team workstreams` an acceptable behaviour change? → A: Yes (INFERRED, backed by the explicit acceptance criterion "Tasks without explicit depends_on are not chained serially by default"); documented in PROTOCOL/README as a scoped change; explicit `depends_on` and `risk work-packages` chains are untouched.
- Q: How deep should discovery look for a Python test suite without a manifest? → A: Root `tests/`/`test/` and `<child>/tests/`/`<child>/test/` of non-hidden, non-ignored immediate children only (INFERRED; deeper monorepo discovery belongs to feature 19).
- Q: If a discovered suite mixes unittest and pytest modules, which runner is used? → A: pytest for that directory (INFERRED: pytest also runs unittest TestCases, the reverse is not true).
- Q: Should converted tests rewrite `assert` into `self.assert*` calls? → A: No; plain `assert` statements are kept verbatim to guarantee identical assertions (INFERRED).
- Q: Should `--append` reject a duplicate `round_id`? → A: No; it appends and leaves duplicate detection to `metrics validate`, which already reports it as a non-blocking warning (INFERRED).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The test suite runs with the standard library alone (Priority: P1)

A contributor (or a CI job, or Spec Master's own validate phase) runs the project's standard-library test runner on a machine without any third-party test framework installed and every test module loads and runs.

**Why this priority**: Principles II and III make "the stdlib unittest run passes offline" the project's baseline quality gate; today it fails with 21 import errors, so every later feature of the cycle would be validated against a broken gate.

**Independent Test**: In an environment with no third-party test framework, run the stdlib discovery over `spec-master/tests` and observe zero errors and a test count ≥ 631.

**Acceptance Scenarios**:

1. **Given** a Python environment without pytest, **When** `python3 -m unittest discover -s spec-master/tests` runs, **Then** it exits 0 with no import errors.
2. **Given** the converted modules, **When** the suite runs under the stdlib runner, **Then** every test case that existed before the conversion still exists (same names) with the same assertions, and the total executed count is ≥ 631.
3. **Given** a test module in `spec-master/tests/`, **When** it is inspected, **Then** it does not import pytest.

---

### User Story 2 - The suite also runs from the repository root under pytest without manual configuration (Priority: P1)

A contributor who has pytest in a virtualenv runs it from the repository root without extra `-o pythonpath=…` flags and the whole suite collects and passes.

**Why this priority**: The roadmap's validate gates and contributors both run the suite from the root; a manual flag is undocumented tribal knowledge.

**Independent Test**: `.venv/bin/python -m pytest spec-master/tests -q` (and a bare `.venv/bin/python -m pytest -q`) from the root collect all tests with no import errors.

**Acceptance Scenarios**:

1. **Given** the repository root as cwd, **When** pytest runs without `-o pythonpath`, **Then** no module fails with `No module named '_pathfix'` and all tests pass.
2. **Given** the fix, **When** the stdlib runner is used, **Then** its behaviour is unchanged (the fix adds no dependency and is inert for unittest).

---

### User Story 3 - Discovery finds a test gate in a Python project whose tests live in a subpackage (Priority: P1)

An operator runs `discovery scan` / `gates detect` on a Python repository that has no root packaging manifest but keeps a stdlib test suite in `tests/` or `<subpackage>/tests/`; Spec Master reports a Python stack and a blocking test gate whose command is derived from the suite actually found.

**Why this priority**: Without a detected test gate the validate phase of every feature in this repository silently runs no tests (Principle VIII requires detection, never hardcoding).

**Independent Test**: In a temp repo with only `pkg/tests/test_x.py` using `unittest`, `quality_gates.detect()` returns a blocking test gate running the stdlib discovery against `pkg/tests`; on this repository `gates detect --path .` returns a test gate for `spec-master/tests`.

**Acceptance Scenarios**:

1. **Given** a repo without a Python manifest and with `<child>/tests/test_*.py` written with unittest, **When** discovery scans it, **Then** it reports a `python` stack whose `test` command runs stdlib unittest discovery over that directory.
2. **Given** such a suite whose modules import pytest, **When** discovery scans it, **Then** the test command uses pytest for that directory instead.
3. **Given** a repo that already has `pyproject.toml`/`setup.cfg`/`requirements.txt`, **When** discovery scans it, **Then** the result is exactly what it was before this feature.
4. **Given** an empty repo, or a repo whose only `tests/` directories live in ignored/hidden/vendored directories (e.g. `.venv`, `node_modules`), **When** discovery scans it, **Then** no Python stack and no gate is invented.

---

### User Story 4 - Team workstreams infer owners by whole words and keep tasks parallel by default (Priority: P2)

A Tech Lead generates workstreams from task titles. "Build CLI parser" is not routed to the frontend dev, and two tasks with no declared dependency land in parallel instead of an implicit chain.

**Why this priority**: Wrong owners and forced serialisation defeat Team Mode and the multi-agent features (14–18) that build on it.

**Independent Test**: `team_model.build_workstreams` on string and dict tasks without `depends_on` returns packages with empty `depends_on`; owner inference for "Build CLI parser" and "Compute capital gains" is not frontend/backend by substring.

**Acceptance Scenarios**:

1. **Given** the task "Build CLI parser", **When** the owner is inferred, **Then** it is not `frontend-dev` (no whole-word frontend term).
2. **Given** the task "Compute capital gains report", **When** the owner is inferred, **Then** "api" inside "capital" does not make it `backend-dev`.
3. **Given** the tasks "Create API endpoint", "Build frontend form", "Connect UI screen to backend API", **When** owners are inferred, **Then** they remain backend-dev, frontend-dev and fullstack-dev (existing behaviour preserved), and simple plurals ("screens", "endpoints") still match.
4. **Given** tasks (strings, or dicts without `depends_on`), **When** workstreams are built, **Then** no package depends on its predecessor implicitly.
5. **Given** a dict task with an explicit `depends_on`, **When** workstreams are built, **Then** that dependency is kept verbatim.

---

### User Story 5 - Recording a metrics round appends it atomically (Priority: P2)

The orchestrating agent records a round with `metrics record-round … --append .spec-master/metrics/rounds.json`; the row is printed as before and appended to the file in one atomic write, with no hand-editing.

**Why this priority**: Every phase records a round; manual append is a round-trip and a corruption risk (roadmap §3 item 1).

**Independent Test**: Run the CLI twice with `--append` against a temp file; the file contains both rows in order and is valid JSON; a missing file is created; a corrupt or non-array file is refused and left untouched.

**Acceptance Scenarios**:

1. **Given** an existing rounds array, **When** `record-round --append FILE` runs, **Then** the new row is the last element and earlier rows are unchanged.
2. **Given** a missing file, **When** `--append FILE` runs, **Then** the file is created containing exactly the new row.
3. **Given** a file with invalid JSON or a non-array root, **When** `--append FILE` runs, **Then** the command fails with a clear error and the file content is unchanged.
4. **Given** no `--append`, **When** `record-round` runs, **Then** it only prints the row (backwards-compatible).

### Edge Cases

- A converted test module that used a fixture depending on `tmp_path` (e.g. `router(tmp_path)`) must get an isolated temp directory per test, cleaned up afterwards.
- Plain `assert` statements keep working under the stdlib runner; they are preserved as-is to keep assertions identical.
- Discovery must not walk the whole tree (bounded to root and its immediate children) and must skip hidden, virtualenv, vendored and build directories.
- Multiple suites (e.g. `tests/` and `pkg/tests/`) each yield their own test gate with a distinguishable name.
- Owner inference on text containing paths/punctuation ("spec-master/lib/ui.py") tokenises on non-alphanumerics.
- `--append` to a path whose parent directory does not exist creates the directory.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001** (H1): Every module under `spec-master/tests/` MUST be loadable and executed by the stdlib unittest runner; no module may import pytest.
- **FR-002** (H1): The conversion MUST preserve every existing test case name and assertion; the stdlib run MUST execute at least as many tests as the pytest run did before the change (631).
- **FR-003** (H1, INFERRED extension): The four modules with module-level test functions not collected by unittest (`test_context_budget`, `test_evals`, `test_runtime_contract`, `test_tool_policy`) MUST also be wrapped so the stdlib runner executes them.
- **FR-004** (H2): Running pytest from the repository root against `spec-master/tests` (or with no path) MUST collect and pass without manual `pythonpath` configuration and without adding any dependency.
- **FR-005** (H3): When a repository has no Python manifest, discovery MUST detect a Python test suite in `tests/`, `test/`, `<child>/tests/` or `<child>/test/` (non-hidden, non-ignored children) that contains `test_*.py`/`*_test.py` files, and report a `python` stack with a `test` command derived from the suite's own content: stdlib unittest discovery over that directory, or pytest over that directory when its modules (or its `conftest.py`) import pytest or it holds pytest-style top-level `def test_*` functions without importing unittest.
- **FR-006** (H3): Repositories with an existing Python manifest MUST produce exactly the same discovery/gate output as before (Principle VI).
- **FR-007** (H3): Gates for suite-detected stacks MUST be blocking test gates whose names identify the suite directory, so several suites do not collide.
- **FR-008** (H4): Owner inference MUST match keyword terms against whole tokens of the text (split on non-alphanumerics), accepting a trailing plural "s"; substrings inside other words MUST NOT match.
- **FR-009** (H5): Tasks without an explicit `depends_on` (string tasks and dict tasks) MUST NOT receive an implicit dependency on the previous task; explicit `depends_on` MUST be preserved.
- **FR-010** (H8): `metrics record-round` MUST accept `--append <file>` that appends the produced row to a JSON array file using a temp-file-then-replace write, creating the file (and parent directory) when missing, and refusing (non-zero exit, file untouched) when the file is not a JSON array.
- **FR-011** (H8): Without `--append`, `metrics record-round` output MUST be unchanged.
- **FR-012**: H6 and H7 MUST be documented as deferred to features 17 and 14, not fixed here.
- **FR-013**: `spec-master/lib/` and `spec-master/tests/` MUST remain stdlib-only (Principle II).

### Key Entities

- **Test suite (discovered)**: a directory of test modules with its runner (unittest or pytest) inferred from the modules' imports; yields one Python stack and one test gate.
- **Work package**: unchanged shape (`id`, `owner_agent`, `reviewer_agent`, `depends_on`, …); only the default of `depends_on` and the owner inference change.
- **Metrics round row**: unchanged schema; only the persistence path is new.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The stdlib test run completes with 0 errors and 0 failures and executes ≥ 631 tests (baseline: 502 run, 21 errors).
- **SC-002**: The root-level pytest run collects 100% of test modules with 0 collection errors (baseline: 62 errors) without extra flags.
- **SC-003**: On this repository, gate detection returns ≥ 1 blocking test gate (baseline: 0), and the gate's command passes.
- **SC-004**: 0 of the documented substring false positives ("build", "capital", "feedback", "guide") produce a wrong owner.
- **SC-005**: A feature with N independent tasks yields N packages with no implicit dependency (baseline: N−1 implicit edges).
- **SC-006**: Recording a round and persisting it takes one command instead of two steps (print + manual edit).

## Assumptions

- (INFERRED) Keeping plain `assert` statements in the converted tests is acceptable: the stdlib runner reports `AssertionError` as a failure, and it guarantees assertions are byte-identical to the originals.
- (INFERRED) The H2 fix is a `spec-master/tests/conftest.py` that only manipulates `sys.path` (no pytest import), rather than a root `pyproject.toml`, because a root manifest would change discovery's output for this repository and conflate H2 with H3.
- (INFERRED) A suite whose modules import pytest anywhere is run with pytest; otherwise with stdlib unittest discovery.
- (INFERRED) Suite detection is bounded to the root and its immediate children to stay cheap and predictable; deeper monorepo discovery is feature 19 (`brownfield-greenfield-tracks`).
- (INFERRED) The suite's test command uses the `python3` executable, consistent with every documented command in this repository and allowed by `tool_policy`'s default allowlist.
- (INFERRED) Removing implicit chaining is a deliberate, documented behaviour change of `team workstreams` (Principle VI "explicitly scoped and documented"); no existing test asserts the old chaining, and `risk work-packages` (explicit `depends_on`) is unaffected.
- (INFERRED) `--append` serialises concurrent appenders with an advisory lock when the platform provides one; the write itself is always temp-file + `os.replace`.
- H6 → feature 17; H7 → feature 14 (source: `app-features.md` Ciclo 2).
