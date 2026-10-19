# Research: Harness Hygiene (H1–H8)

## R1 — How to make 21 pytest modules run under unittest (H1)

- **Decision**: Convert each module into a single `unittest.TestCase` subclass, keeping test names and plain `assert` statements verbatim; fixtures become plain `_fixture_<name>()` helpers called at the start of each test; `tmp_path` becomes a per-test `tempfile.mkdtemp()` wrapped in `pathlib.Path` and cleaned with `addCleanup`.
- **Rationale**: Only two pytest features are used (`@pytest.fixture` ×7 and `tmp_path`); no `raises`, `parametrize`, `monkeypatch` or `capsys`. A deterministic, AST-guided rewrite preserves bodies exactly, so the risk of altering an assertion is nil. pytest still collects `TestCase` classes, so the secondary runner keeps working.
- **Alternatives considered**: (a) a stdlib shim that emulates pytest fixtures — rejected (magic, harder to read); (b) rewriting asserts to `self.assertEqual` — rejected (risk of semantic drift, larger diff, no gain under unittest).

## R2 — Why pytest fails from the root (H2)

- **Finding**: `spec-master/tests/` has `__init__.py`, `spec-master/` does not. In the default `prepend` import mode pytest inserts `spec-master/` into `sys.path` and imports modules as `tests.test_x`; `import _pathfix` then fails because `spec-master/tests/` itself is not on `sys.path`. unittest discover inserts the start dir, so it works there.
- **Decision**: `spec-master/tests/conftest.py` that inserts its own directory into `sys.path`. pytest imports `conftest.py` before collecting sibling modules; unittest ignores it (pattern `test*.py`).
- **Alternatives**: root `pytest.ini`/`pyproject.toml` with `pythonpath = spec-master/tests` — rejected: a root `pyproject.toml` changes discovery output (couples H2 with H3), and `pythonpath` ini needs pytest ≥ 7 config knowledge in the repo; removing `tests/__init__.py` — rejected (changes package layout other tools may rely on).

## R3 — Detecting a manifest-less Python test suite (H3)

- **Decision**: Fallback only when no Python manifest exists; candidates at depth ≤ 2 (`tests`, `test`, `<child>/tests`, `<child>/test`); runner chosen by module imports.
- **Rationale**: Generic (any repo that keeps a stdlib suite in a subpackage), cheap (no recursive walk; feature 15/19 handle pruning and monorepos), evidence-based (Principle VIII: the command reflects the suite actually on disk), and leaves manifest-based repos untouched (Principle VI).
- **Alternatives**: always prefer `pytest` — rejected (wrong for stdlib suites, pytest may be absent); recursive search — rejected (cost on brownfield repos, roadmap §3 item 3).

## R4 — Whole-word owner inference (H4)

- **Decision**: tokenize on non-alphanumerics; a term matches the token itself or the token with a trailing `s`.
- **Rationale**: Removes the documented false positives ("build"→ui, "capital"→api, "feedback"→db, "guide"→ui) while keeping plural task titles ("screens", "endpoints") routed as before.
- **Alternatives**: regex `\b` boundaries — equivalent but `\b` treats `_` as a word char (`ui_kit` would not match); stemming — overkill.

## R5 — Implicit chaining (H5)

- **Finding**: no test in the suite asserts the implicit chain (`test_team_model.py` only checks owners/reviewers; `test_risk_profile.py::test_work_packages_chain` covers `risk_profile.work_packages`, whose `depends_on` is explicit and unaffected).
- **Decision**: remove the fallback; packages without `depends_on` are independent. Documented behaviour change.

## R6 — Atomic append (H8)

- **Decision**: read-modify-write with temp file + `os.replace` (same directory → atomic rename), guarded by an advisory `fcntl.flock` on the parent directory when available, so parallel subagents (feature 18) do not lose rows. (Implementation note: a directory lock replaced the originally planned sibling `<file>.lock` so no lock file is left in `.spec-master/metrics/`; verified with 24 concurrent CLI appends → 24 rows.)
- **Alternatives**: JSON Lines append — rejected (schema/file format is a JSON array consumed by `summarize`, `validate`, `export`, `calibrate`).
