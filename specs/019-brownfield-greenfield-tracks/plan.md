# Implementation Plan: Brownfield and Greenfield Tracks

**Spec**: `specs/019-brownfield-greenfield-tracks/spec.md` | **Stack**: Python 3 stdlib only (Principle II)

## Constitution check
- II stdlib only: yes. III tests mirrored: `test_discovery.py` (extended) + `test_tracks.py`. IV atomic writes: greenfield apply and `--write` use temp file + `os.replace`. VI native behaviour unchanged: new keys only, `scope=None` default. VIII gates detected, greenfield *proposes* a minimal test command, never records a gate. X nothing auto-published; greenfield apply needs `--confirm`.
- Budgets: new code lives in `spec-master/lib/tracks.py` and `discovery.py`, outside `kernel/` and the hook path. Cards ≤ 3 KB.

## Design
1. `discovery.py`: `PRUNED_DIRS`, `_walk_pruned(root, max_depth)` (pruned + hidden dirs skipped, depth-limited, sorted for determinism), `_package_stacks(dir)` reusing the existing `_scan_*` functions, `_find_packages(root, scope)`, `scan(root, scope=None)` adds `packages` and `scope`; with a scope, stacks come from the scope directory. `_resolve_scope` rejects absolute, `..` and missing dirs (`ValueError`).
2. `tracks.py` (new): `map_codebase`, `propose_constitution`, `characterization_targets`, `render_codebase_map`, `greenfield_intake`, `greenfield_propose`, `greenfield_apply`, `write_new_file` (atomic, never overwrite). Evidence on every finding.
3. CLI: `tracks brownfield-{map,constitution,characterize}` (`--path`, `--scope`, `--write`) and `tracks greenfield-{intake,propose,apply}` (flat actions: the doc-conformance parser catalog is two levels deep) (`--stack`, `--name`, `--confirm`); `discovery scan --scope`. Handler imports `tracks` lazily (import block belongs to another feature).
4. Cards `brownfield.md`, `greenfield.md` (characterization phase and confirmation rule live in them).

## Follow-ups
- Replace `discovery._walk_pruned` with feature 15's shared walker once merged.
- Optional core-level characterization phase (needs `phase_contracts.py`, owned by another feature).
