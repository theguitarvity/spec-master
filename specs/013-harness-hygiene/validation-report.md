# Validation Report: Harness Hygiene (H1–H8)

**Date**: 2026-10-19 | **Feature**: `harness-hygiene` (cycle 2) | **Spec**: [spec.md](spec.md)
**Tier**: M at intake → **L** at pre-implement (`risk classify --stage pre_implement --save`; never lowered)

Executed by the agent per PROTOCOL.md Step 7 in Auto Mode, trunk-based on `main` (no branch, no commit).

## Baseline vs After (T001)

| Measure | Baseline (before) | After |
|---|---|---|
| `python3 -m unittest discover -s spec-master/tests` | Ran 502, **FAILED (errors=21)** — 21 modules `import pytest`; 4 more modules of plain functions silently not collected | **Ran 658, OK** |
| `.venv/bin/python -m pytest spec-master/tests -q -o pythonpath=spec-master/tests` | 631 passed, 37 subtests | **658 passed**, 37 subtests |
| `.venv/bin/python -m pytest -q` (repo root, no flags) | **62 collection errors** (`No module named '_pathfix'`) | **658 passed**, 37 subtests |
| `.venv/bin/python -m pytest spec-master/tests -q` (no `pythonpath`) | 62 collection errors | **658 passed** |
| `gates detect --path .` | `[]` (no test gate) | `test (python: spec-master/tests)` → `python3 -m unittest discover -s spec-master/tests`, blocking |
| Modules importing pytest in `spec-master/tests` | 21 | **0** |

658 = 631 pre-existing tests (every name and `assert` preserved) + 27 new tests (19 from TDD, 8 from review repairs).

## Acceptance Criteria → Evidence

1. **"unittest discover passes without pytest installed"** — PASS (H1, FR-001..FR-003, SC-001). 25 modules
   (`test_graph_*` ×15, `test_knowledge_*` ×5, `test_traceability_graph`, plus the unittest-invisible
   `test_context_budget`, `test_evals`, `test_runtime_contract`, `test_tool_policy`) were converted to one
   `unittest.TestCase` each by an AST-guided converter (scratchpad only, not shipped). A second AST script
   compared each module before/after: identical sorted test-name lists and identical sorted `assert` sets
   (150 tests, 349 asserts, 25/25 "ok"). `grep -rn "^import pytest\|^from pytest" spec-master/tests` → none.
   Fixtures became `_fixture_<name>()` helpers; `tmp_path` is a per-test `tempfile.mkdtemp()` with `addCleanup`.
2. **"Suite runs from repo root without manual pythonpath"** — PASS (H2, FR-004, SC-002). RED reproduced
   (62 collection errors), GREEN after adding the path-only `spec-master/tests/conftest.py` (no pytest import).
   Verified: `pytest -q`, `pytest spec-master/tests -q`, and the brief's flagged form all → 658 passed.
3. **"discovery/gates detect Python stack and a test gate in this repo"** — PASS (H3, FR-005..FR-007, SC-003).
   `test_discovery.py`: `test_unittest_suite_in_subpackage_detected_without_manifest`,
   `test_pytest_importing_suite_uses_pytest_runner`, `test_root_tests_dir_without_manifest_detected`,
   `test_hidden_and_vendored_suites_ignored`, `test_tests_dir_without_test_modules_ignored`,
   `test_manifest_repo_keeps_manifest_detection` (FR-006, no `scope`, command still `pytest`),
   `test_pytest_style_suite_without_pytest_import_uses_pytest_runner`,
   `test_suite_whose_conftest_imports_pytest_uses_pytest_runner`, `test_path_only_conftest_keeps_unittest_runner`.
   `test_quality_gates.py`: `test_manifestless_suite_yields_scoped_blocking_test_gate`,
   `test_two_suites_yield_distinct_gate_names`. Live: `gates detect --path .` returns the suite gate;
   `policy preflight` → `allowed: true, risk: low`; the command ran → exit 0 (Ran 658, OK). Detection is generic
   (root + immediate children, runner derived from the suite's own imports) — nothing repo-specific (Principle VIII).
4. **"Owner inference matches whole words, not substrings"** — PASS (H4, FR-008, SC-004).
   `test_owner_inference_ignores_terms_inside_other_words` ("Build CLI parser", "Compute capital gains report",
   "Collect feedback", "Write user guide") and `test_owner_inference_keeps_plurals_and_path_tokens`
   ("Render dashboard screens", "Expose REST endpoints", "spec-master/lib/ui.py", "auth_api"),
   `test_owner_inference_keeps_long_forms_of_short_terms` ("authentication", "authorization", "databases"). The 3 pre-existing
   owner tests in `test_team_model.py` pass unchanged.
5. **"Tasks without explicit depends_on are not chained serially by default"** — PASS (H5, FR-009, SC-005).
   `test_tasks_without_depends_on_are_independent` (string + dict tasks → `[]`),
   `test_explicit_depends_on_is_preserved`. **Behaviour change** (Principle VI): no existing test asserted the
   implicit chain (research R5); documented in spec Clarifications and PROTOCOL Step 6 item 3.
6. **"metrics record-round --append writes the row atomically"** — PASS (H8, FR-010, FR-011, SC-006).
   `test_metrics.py`: `test_append_round_creates_missing_file_and_parent_dir`,
   `test_append_round_keeps_existing_rows_in_order`, `test_append_round_refuses_corrupt_or_non_list_file_untouched`,
   `test_append_round_leaves_no_temp_files`, `test_cli_record_round_append_twice_yields_two_rows`,
   `test_cli_record_round_without_append_writes_nothing`, `test_cli_record_round_append_to_corrupt_file_exits_1`,
   `test_cli_record_round_append_failure_prints_no_row`, `test_append_round_preserves_file_mode`,
   `test_append_round_writes_through_symlink`, `test_concurrent_cli_appends_keep_every_row` (8 processes → 8 rows).
   Extra manual check: 24 concurrent CLI `--append` processes → 24 rows, no leftover temp/lock files.
   Dogfooded: implement/validate rounds of this feature were appended with `--append`.

## Quality Gates (Step 7)

| Gate | Command | Result |
|---|---|---|
| unittest (normative) | `python3 -m unittest discover -s spec-master/tests` | PASSED — Ran 658, OK |
| pytest (brief form) | `.venv/bin/python -m pytest spec-master/tests -q -o pythonpath=spec-master/tests` | PASSED — 658 passed |
| pytest (root, no flags) | `.venv/bin/python -m pytest -q` | PASSED — 658 passed |
| detected: `test (python: spec-master/tests)` | `python3 -m unittest discover -s spec-master/tests` (preflight: allowed, low) | PASSED (exit 0) |
| evals | `python3 spec-master/lib/cli.py evals run` | PASSED — 5/5 |
| graph | `python3 spec-master/lib/cli.py graph validate --path .` | PASSED — `total_issues: 0`, `valid: true` |
| FR-013 stdlib-only | `grep -rnE "^\s*(import\|from) (pytest\|yaml\|requests\|numpy)" spec-master/lib spec-master/tests` | PASSED — only the pre-existing, `try/except ImportError`-guarded optional `yaml` import in `lib/graph/{ontology,parser}.py` (untouched by this feature); no new third-party import; tests import no pytest |

## Tier-L Obligations (escalated at pre-implement)

- **Escalation cause**: scope (≈38 touched files > 12) and sensitivity keywords `public_contract` ("endpoints",
  "contracts") and `external_provider` ("third-party" in T019). The sensitivity hits are keyword false positives;
  the scope escalation is legitimate. `rerun_phases` was `[]`, so analyze was not re-run (it already ran at depth).
- **ADR check**: no ADR required — recorded with `team resolve` as decision
  `decision.architecture-inconsistency-adr-check-for-harness-f48e2b65` (decided by architect; no new provider,
  data model, trust boundary or public contract shape; `--append` is additive; H5 is a documented default change).
- **Work packages**: `.spec-master/workstreams.json` generated by `team workstreams` from 6 story packages with
  explicit `depends_on` (US1 → US2..US5 in parallel → docs), dogfooding H4/H5.
- **Peer + tech-lead review**: see below.

## Review

Independent peer + tech-lead review subagent (read-only) → **CHANGES_REQUESTED**, all findings repaired test-first:

| # | Severity | Finding | Repair |
|---|---|---|---|
| 1 | MAJOR | pytest-style suite (plain `def test_*`, no pytest import) got the unittest runner → "NO TESTS RAN", gate always fails | Runner is pytest also when `conftest.py` imports pytest or a module has top-level `def test*` without importing unittest; path-only conftest (this repo) keeps unittest. 3 tests; FR-005 wording and contract refined |
| 2 | MINOR | `append_round`: mkstemp 0600 mode leaked, symlink replaced, no fsync | keep existing mode (umask default for new files), `realpath` target, `flush`+`fsync`. 2 tests |
| 3 | MINOR | CLI printed the row before a failing append; `OSError` → traceback | append first, print only on success; catch `OSError`. 1 test |
| 4 | MINOR | PROTOCOL claimed parallel safety unconditionally | wording: lock is POSIX-only; serialise appends without `fcntl` |
| 5 | MINOR | no concurrent-append test | `test_concurrent_cli_appends_keep_every_row` |
| 6 | MINOR | whole-word match lost "authentication"/"authorization" | added `authn`, `authz`, `authentication`, `authorization` terms. 1 test |
| 7 | NIT | suite stack `manifest` is a directory | documented in data-model.md |

Reviewer confirmed: no consumer relied on implicit chaining (`dashboard.py`, `team_workstreams.py` handle `[]`; `risk_profile.work_packages` keeps its explicit chain); nothing parses gate names; conversion preserved every test.

## Deferred (FR-012)

- **H6** → feature 17 (out of scope here; no change made).
- **H7** → feature 14 (out of scope here; no change made).

## Documentation Updated

- `spec-master/PROTOCOL.md`: Step 6 item 3 (explicit-only `depends_on`, whole-word owner inference), Step 6 metrics
  paragraph (`record-round --append`), Step 7 (manifest-less suite gates).
- `README.md` and `docs/spec-master/README.md`: stdlib test command, test count 658, root pytest works,
  `--append` in the CLI table, suite discovery.

## Implementation Notes

- H8 lock: the plan named a sibling `<file>.lock`; implemented as `fcntl.flock` on the parent directory so no
  lock file is left in `.spec-master/metrics/` (plan/research/contract updated accordingly). Without `fcntl`
  the temp-file + `os.replace` atomicity still holds.
- `append_round` keeps the existing `indent=2`, unsorted-key format so prior rows are not reformatted.
