# Contract: manifest-less Python test-suite discovery

`discovery.scan(root)` — when none of `pyproject.toml`, `setup.cfg`, `requirements.txt` exists at `root`:

- Candidates (in sorted order): `root/tests`, `root/test`, then `root/<child>/tests`, `root/<child>/test` for each immediate child directory that is not hidden (`.`-prefixed) and not in `{node_modules, venv, env, build, dist, target, site-packages, __pycache__}`.
- A candidate qualifies when it directly contains at least one `test_*.py` or `*_test.py` file.
- Runner: `python3 -m pytest <scope>` when any test module or the suite's `conftest.py` matches `^\s*(import pytest|from pytest\b)`, or a test module has top-level `def test*(` functions and does not import `unittest` (pytest-style suite that `unittest discover` would not collect); otherwise `python3 -m unittest discover -s <scope>`. A path-only `conftest.py` does not switch the runner. (Refined after peer review, finding 1.)
- One stack per qualifying candidate (see data-model.md).

`quality_gates.detect(root)` → for such stacks: `{"name": "test (python: <scope>)", "command": <cmd>, "blocking": true}`.

Repos with a Python manifest: output byte-identical to the previous behaviour.
