# Validation Report: 019 brownfield-greenfield-tracks

Date: 2026-10-19 | Result: implementation PASSED all gates; state PASSED transitions BLOCKED (see Bookkeeping).

## Gates
- `python3 -m unittest discover -s spec-master/tests`: before 956, after 988 (+32), OK (skipped=1)
- `.venv` pytest: not available (no .venv)
- `gates detect --path .`: one gate (unittest), run above
- `evals run`: 5/5 passed; `graph validate --path .`: valid, 0 issues
- `doctor run --errors-only`: exit 0 (cards 1786 B and 1430 B, within 3 KB; protocol conformance green)

## Acceptance criteria -> tests
| Criterion | Test |
|---|---|
| Brownfield map with monorepo sub-packages and pruned walk | test_discovery.py::MonorepoDiscoveryTests (walk_pruned_*, scan_lists_subpackages_*); test_tracks.py::MapCodebaseTests |
| Constitution from repository evidence only | test_tracks.py::ConstitutionProposalTests |
| Optional characterization phase before implement | test_tracks.py::CharacterizationTests; spec-master/cards/brownfield.md |
| Partial adoption scoped to a directory | MonorepoDiscoveryTests::test_scope_*, MapCodebaseTests::test_scope_limits_the_map, TracksCliTests::test_discovery_scan_accepts_scope |
| Greenfield asks stack, proposes, never applies unconfirmed | test_tracks.py::GreenfieldTests, TracksCliTests::test_greenfield_* |

## Bookkeeping
`state transition ... PASSED` runs an evidence check against the project root of the `--path` state file (the main checkout), where this worktree's `specs/019-*` does not exist; the only bypass (`--import-unverified`) and mirroring the dir into main were not used. Phases specify..validate therefore remain to be transitioned by the caller after merge.
