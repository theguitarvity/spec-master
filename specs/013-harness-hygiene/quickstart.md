# Quickstart: validating Harness Hygiene

From the repository root:

1. **H1** — stdlib only: `python3 -m unittest discover -s spec-master/tests` → `OK`, `Ran ≥ 631 tests`, no `ImportError`.
   `grep -l "import pytest" spec-master/tests/*.py` → no output.
2. **H2** — pytest from root without flags: `.venv/bin/python -m pytest spec-master/tests -q` and `.venv/bin/python -m pytest -q` → all pass, 0 collection errors.
3. **H3** — `python3 spec-master/lib/cli.py gates detect --path .` → contains `test (python: spec-master/tests)` with
   `python3 -m unittest discover -s spec-master/tests`; `policy preflight "<that command>"` → allowed.
4. **H4/H5** — `python3 -m unittest -v test_team_model` (from `spec-master/tests`) → owner/word-boundary and no-implicit-chain tests pass.
5. **H8** — `python3 spec-master/lib/cli.py metrics record-round --round-id x --phase plan --started-at 2026-10-19T10:00:00Z --ended-at 2026-10-19T10:01:00Z --append /tmp/r.json` twice → `/tmp/r.json` holds two rows; see [contracts/cli-metrics-append.md](contracts/cli-metrics-append.md).
