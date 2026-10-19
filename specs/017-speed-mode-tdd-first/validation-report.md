# Validation Report: Speed Mode, TDD First

**Date**: 2026-10-19 | **Feature**: speed-mode-tdd-first (Cycle 2, Feature 17)

## Gates

| Gate | Result |
|------|--------|
| `python3 -m unittest discover -s spec-master/tests` | 977 tests, OK (skipped=1); 21 new in `test_standard_lane.py` |
| `gates detect` | unittest gate detected and run |
| `evals run` | 5/5 success |
| `graph validate` | valid, 0 issues |
| `doctor run --errors-only` | ok, no errors; warnings only: `step_path_budget` (5387 LOC), `evidence` (4 older features) |

## Acceptance criteria to tests

| AC | Test (tests/test_standard_lane.py) |
|----|------|
| AC1 | VerifyPreTests::test_clean_spec_lite_passes |
| AC2 | StandardFlowTests::test_red_requires_a_failing_run_with_a_test_change |
| AC3 | StandardFlowTests::test_end_to_end_passes_only_with_red_then_green_evidence |
| AC4 | TddGuardTests::test_block_mode_denies_production_writes_until_red |
| AC5 | StandardFlowTests::test_critical_signals_go_to_the_full_cycle |
| AC6 | test_protocol_conformance and the kernel step suites stay green |

## Notes

- Kernel growth is about 9 LOC (`step.py`, `hookd.py`); budgets respected.
- Follow-up: `risk_profile.py` (Feature 15) should call `verify_pre.light_analyze` where `analyze == "light"` (H6).
