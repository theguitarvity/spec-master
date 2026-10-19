# Implementation Plan: Speed Mode TDD First

Stdlib Python, outside `kernel/`:

- `lib/verify_pre.py`: reuses `kernel/verify` parsers and the `evidence` task regex.
- `lib/tdd_gates.py`: RED/GREEN via `kernel/verify.run_gate`; `guard` (hook) and `check` (`step end`).
- `lib/standard_lane.py`: begin, verify-pre step, tdd runs, end, CLI `standard begin|verify-pre|red|green`.
- `cards/standard-spec.md`, `cards/standard-implement.md`; the router card points to the lane.
- Kernel touch points (about 9 LOC): `step.py` delegates cards and `end` for `lane == "standard"`; `hookd.py` calls `tdd_gates.guard` for running standard changes.
- `cli.py`: `standard` subparser registered through `standard_lane.register` (import block untouched).

Constitution check: I stdlib, II mirrored `test_standard_lane.py`, III runners injectable, VI native mode untouched, VII full cycle keeps `/speckit.analyze` (only the Standard lane uses `verify_pre`), kernel and hook budgets enforced by `doctor`.
