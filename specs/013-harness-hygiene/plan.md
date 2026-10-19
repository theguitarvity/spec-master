# Implementation Plan: Harness Hygiene (H1–H8)

**Branch**: `013-harness-hygiene` (trunk-based, no branch created) | **Date**: 2026-10-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/013-harness-hygiene/spec.md`

## Summary

Fix the six in-scope audit findings of `docs/performance-multiagent-speed-roadmap.md` §2.2 so cycle 2 is validated against a working harness:
convert the 25 pytest-only / unittest-invisible test modules to `unittest.TestCase` classes (H1), add a path-only
`spec-master/tests/conftest.py` so pytest works from the root (H2), add a manifest-less Python test-suite fallback to
`discovery.scan()` with suite-scoped gate names in `quality_gates.detect()` (H3), switch `_infer_owner` to token matching
(H4), drop implicit serial chaining in `build_workstreams` (H5), and add `metrics.append_round()` + `record-round --append`
(H8). H6/H7 are deferred to features 17/14.

## Technical Context

**Language/Version**: Python 3 (stdlib only; local interpreter 3.14)
**Primary Dependencies**: none (Principle II); pytest only as an optional, pre-existing `.venv` runner
**Storage**: JSON files (`.spec-master/metrics/rounds.json`)
**Testing**: `python3 -m unittest discover -s spec-master/tests` (normative); pytest from `.venv` (secondary)
**Target Platform**: macOS/Linux CLI
**Project Type**: single project (CLI + library under `spec-master/lib/`)
**Performance Goals**: discovery fallback bounded to root + immediate children (O(children), no recursive walk)
**Constraints**: no behaviour change for repos with Python manifests, for `--mode native`, or for `record-round` without `--append`
**Scale/Scope**: ~25 test modules (~1,470 lines) converted; 5 lib files touched (`discovery.py`, `quality_gates.py`, `team_model.py`, `metrics.py`, `cli.py`)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I Deterministic core | All fixes are in `spec-master/lib/` pure Python, exposed via `cli.py` | PASS |
| II Stdlib-only | No new imports beyond stdlib (`fcntl` optional, guarded by `try/except ImportError`); tests drop pytest | PASS |
| III Test-first / mirrored tests | New tests added to `test_discovery.py`, `test_quality_gates.py`, `test_team_model.py`, `test_metrics.py`; unittest discover becomes green | PASS |
| IV Atomic state | `append_round` uses temp file + `os.replace`; `state.json` untouched | PASS |
| V Non-destructive | Corrupt rounds file is refused, never overwritten | PASS |
| VI Backwards-compatible | Manifest-based discovery unchanged; `record-round` unchanged without flag; H5 behaviour change explicitly scoped and documented (spec Clarifications) | PASS (documented change) |
| VII Reuse ecosystem | n/a (no new integration) | PASS |
| VIII Gates auto-detected | Test command derived from the suite actually found and its imports; nothing repo-specific hardcoded | PASS |
| IX Dependency exceptions | none introduced | PASS |
| X No auto-publishing | nothing published | PASS |

## Project Structure

### Documentation (this feature)

```text
specs/013-harness-hygiene/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli-metrics-append.md
│   └── discovery-test-suite.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
spec-master/
├── lib/
│   ├── discovery.py        # H3: _scan_python_test_suites() fallback
│   ├── quality_gates.py    # H3: suite-scoped gate name when stack has "scope"
│   ├── team_model.py       # H4: _tokens()/_has_term(); H5: no implicit chaining
│   ├── metrics.py          # H8: append_round(path, row)
│   └── cli.py              # H8: record-round --append
└── tests/
    ├── conftest.py         # H2 (new, path-only, no pytest import)
    ├── test_graph_*.py, test_knowledge_*.py, test_traceability_graph.py   # H1 conversion
    ├── test_context_budget.py, test_evals.py, test_runtime_contract.py, test_tool_policy.py  # H1 extension
    ├── test_discovery.py, test_quality_gates.py, test_team_model.py, test_metrics.py        # new tests
```

**Structure Decision**: single project; edits in place, one new file (`conftest.py`).

## Design

1. **H1 conversion** (mechanical, AST-guided): per module, remove `import pytest`, add `import unittest` (+ `shutil`, `tempfile`, `pathlib.Path` when `tmp_path` is used); rename each `@pytest.fixture def f(...)` to a plain module-level `_fixture_f(...)`; wrap every `def test_x(<args>)` in one `class <Module>Tests(unittest.TestCase)` as `def test_x(self)`, prefixed by argument resolution (`tmp_path = self._tmp_path()`, `f = _fixture_f(<deps>)`). Bodies and `assert` statements stay byte-identical (re-indented). `_tmp_path()` uses `tempfile.mkdtemp` + `addCleanup(shutil.rmtree)`; one temp dir per test shared between `tmp_path` and fixtures that need it (pytest semantics). Add `if __name__ == "__main__": unittest.main()`.
2. **H2**: `spec-master/tests/conftest.py` inserts its own directory into `sys.path` (so `import _pathfix` resolves under pytest's rootdir-based import); it imports nothing from pytest.
3. **H3**: in `discovery.scan()`, when `_scan_python(root)` returns `None`, call `_scan_python_test_suites(root)` → list of stacks `{"language": "python", "commands": {"test": cmd}, "manifest": <suite dir>, "scope": <rel dir>, "detected_from": "test-suite"}`. Candidates: `root/{tests,test}` and `root/<child>/{tests,test}` for children not hidden and not in an ignore set (`node_modules`, `venv`, `env`, `build`, `dist`, `target`, `site-packages`, `__pycache__`). A candidate qualifies if it has `test_*.py` / `*_test.py`. Runner: pytest (`python3 -m pytest <rel>`) if any module matches `^\s*(import pytest|from pytest\b)`, else `python3 -m unittest discover -s <rel>`. `quality_gates.detect()` names such gates `test (python: <scope>)`.
4. **H4**: `_tokens(text)` = lowercase alphanumeric runs; a term matches when `term in tokens` or `term + "s" in tokens`.
5. **H5**: delete the implicit `previous_package_id` fallback for both string and dict tasks; keep explicit `depends_on`.
6. **H8**: `metrics.append_round(path, row)`: load (missing → `[]`; invalid JSON / non-list → `ValueError`), append, write via `tempfile.mkstemp` in the same dir + `os.replace`; serialise with `fcntl.flock` on the parent directory when `fcntl` is available (no stray lock file). CLI: `--append FILE` → print row, then append; on `ValueError` exit 1 with message on stderr.
7. **Docs**: PROTOCOL Step 6 metrics paragraph mentions `--append`; README team-workstreams/metrics mention if documented there.

## Complexity Tracking

No constitution violations to justify. The H5 behaviour change is scoped and documented (Principle VI).
