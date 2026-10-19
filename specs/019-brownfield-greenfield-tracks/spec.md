# Feature Specification: Brownfield and Greenfield Tracks (B1 + G1)

**Feature Branch**: `019-brownfield-greenfield-tracks` (trunk-based: no dedicated branch)
**Created**: 2026-10-19 | **Status**: Draft
**Input**: `docs/performance-multiagent-speed-roadmap.md` §6 Onda 6 (B1, G1, adoção parcial); `.spec-master/context/app-features.md` Ciclo 2, Feature 19.

## Grounding (DISCOVERED_FROM_CODEBASE)

- Discovery of the Spec Kit install via `.specify/integration.json` already exists: `spec-master/lib/discovery.py` (`_speckit_install`).
- `discovery.scan()` only inspects root manifests, so a monorepo (`packages/*`, `services/*`) reports `stacks: []` or only the root stack.
- `team adopt` plan exists (`team_model.py:388`), `min_lane`/`sensitive_paths` exist in `lanes.py`, provenance `file:line` exists in `verify.py` — reused as conventions, not rebuilt (re-scope report F19 "Covered").
- Principle VIII only detects gates; it never creates them. Cards (`spec-master/cards/*.md`) are budgeted at 3 KB each by `doctor run`.

## Re-scope (INFERRED, reason: the upstream merge already covers part of the original criteria)

The re-scope report's "Remaining delta" replaces the original criteria where they conflict: monorepo sub-package discovery; pruned walker (a minimal local `_walk_pruned` in `discovery.py`, to be unified with feature 15's walker later); characterization-test phase for brownfield; evidence-based constitution proposal; greenfield intake that proposes but never applies without confirmation. Directory-scoped adoption is kept (original criterion 4).

## User Scenarios

### US1 - Map a legacy codebase (P1)
A maintainer adopts Spec Master on an existing repo (optionally one directory of it). **Independent test**: run `tracks brownfield-map` on a fixture monorepo; get stack, packages, architecture, conventions and risks, each item carrying evidence.
1. Given `packages/a/package.json` and `services/b/go.mod`, When discovery scans, Then `packages` lists both with their own stacks and commands.
2. Given `node_modules`, `.git`, `dist`, `build`, `target`, `.venv`, `vendor`, `__pycache__` directories containing manifests, When scanning, Then they are never entered.
3. Given `--scope services/b`, When mapping, Then only that directory contributes stacks, packages, architecture and risks; a scope outside the repo or non-existent is rejected.

### US2 - Constitution from evidence (P1)
**Independent test**: `tracks brownfield-constitution` prints a proposal where every principle cites an evidence path; a repo with no signals yields no invented principle.
1. Given a CI workflow and a test dir, Then the "tests gate merges" principle cites them.
2. Given an empty repo, Then the proposal contains zero principles and an `[UNRESOLVED]` note.
3. The proposal is only a proposal: written to `.spec-master/context/constitution-proposal.md` (only with `--write`), never to `.specify/memory/constitution.md`.

### US3 - Characterization tests before implement (P2, optional)
**Independent test**: `tracks brownfield-characterize` lists source files in scope with no matching test, ranked; the brownfield card describes the optional phase.

### US4 - Greenfield bootstrap (P1)
**Independent test**: `tracks greenfield-intake` returns the stack question; `greenfield-propose --stack python` returns a file list with `applied: false`; `greenfield-apply` without `--confirm` writes nothing and exits non-zero; with `--confirm` it writes only files that do not already exist.

## Requirements

- **FR-001** `discovery.scan(root, scope=None)` adds `packages` (monorepo sub-packages, depth-limited, pruned) and `scope`; all existing keys and native behaviour unchanged.
- **FR-002** `_walk_pruned(root, max_depth)` never descends into pruned or hidden directories.
- **FR-003** `tracks.map_codebase` returns stack, packages, architecture, conventions, risks; every finding has `evidence` (relative path, `file:line` where a line applies) — never invented.
- **FR-004** `tracks.propose_constitution` emits only principles backed by evidence; never writes the real constitution.
- **FR-005** `tracks.characterization_targets` ranks untested source files in scope.
- **FR-006** `tracks.greenfield_intake/propose/apply`: propose never writes; apply requires explicit confirmation and never overwrites existing files; writes are atomic (temp file + replace).
- **FR-007** CLI `tracks ...` and `discovery scan --scope`; brownfield/greenfield cards ≤ 3 KB; `doctor run --errors-only` exits 0; stdlib only.
- **FR-008** `.spec-master/context/codebase-map.md` is the only steering doc written by the map (with `--write`), never overwritten.

## Success Criteria
SC-001 all fixtures pass offline under `unittest`; SC-002 native `discovery scan` output for a single-package repo is unchanged apart from the two new keys; SC-003 doctor green.

## Clarifications
Autonomous run; no blocking question. Resolved as INFERRED: (1) the four "parallel readers" are four pure functions run in one pass (stack/architecture/conventions/risks) — the host may parallelize through the card; (2) monorepo depth limit 4; (3) greenfield stacks: python, node, go, rust; (4) characterization is a card plus target ranking, not a new core phase (`phase_contracts.py` belongs to another feature).
