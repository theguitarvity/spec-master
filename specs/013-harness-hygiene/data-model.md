# Data Model: Harness Hygiene

## Discovered Python stack (test-suite fallback) — `discovery.scan()["stacks"][i]`

| Field | Type | Notes |
|---|---|---|
| `language` | `"python"` | same as manifest-based stacks |
| `commands` | `{"test": str}` | `python3 -m unittest discover -s <scope>` or `python3 -m pytest <scope>` |
| `manifest` | str (abs path) | the suite **directory** (evidence on disk; unlike manifest stacks this is not a file — consumers using it as evidence, e.g. `graph/enrichment.py`, get a directory path) |
| `scope` | str | suite directory relative to the scan root, POSIX separators (new, only on suite stacks) |
| `detected_from` | `"test-suite"` | new, only on suite stacks |

Validation: emitted only when the directory contains ≥ 1 `test_*.py`/`*_test.py`; never when a Python manifest exists.

## Quality gate (unchanged shape)

`{"name": str, "command": str, "blocking": bool}` — for stacks with `scope`, `name` is `"<gate> (python: <scope>)"`; otherwise unchanged `"<gate> (<language>)"`.

## Work package (unchanged shape)

`depends_on` default changes from `[previous_package_id]` to `[]` when the task gives none.

## Metrics round row (unchanged; `schemas/metrics-round.schema.json`)

Persistence: `rounds.json` is a JSON array; `append_round` keeps order and never rewrites prior rows.
