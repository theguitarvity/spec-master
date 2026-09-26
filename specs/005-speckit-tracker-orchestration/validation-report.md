# Validation Report: Spec Kit Tracker Orchestration

**Date**: 2026-09-26 | **Feature**: `speckit-tracker-orchestration` | **Spec**: [spec.md](spec.md)

Executed directly by the agent per PROTOCOL.md Section 7 (no `templates/prompts/validate.md`
exists for this phase; the agent validates against acceptance criteria in Auto Mode, same as
features 1 and 2's validate phases).

## Acceptance Criteria → Evidence

1. **"No new bespoke tracker client is written where an existing Spec Kit extension/skill already
   covers that tracker"** — PASS. `tracker_orchestration.py` contains no HTTP/network client of any
   kind; `test_tracker_orchestration_module_has_no_network_imports` asserts the module's own source
   contains none of `requests`/`urllib`/`http.client`/`socket`. The module only reads local
   `SKILL.md` files and builds invocation instructions.
2. **"speckit-taskstoissues is reused or extended, not duplicated"** — PASS. Zero modification to
   `.claude/skills/speckit-taskstoissues/SKILL.md` (confirmed via `git diff --stat`, below); a
   manual `tracker orchestrate --path .` run against this repository's own real state detects it
   and names `/speckit-taskstoissues` as the command to invoke, rather than reimplementing its
   dedup-by-task-id/issue-creation logic.
3. **"Tracker selection is auto-detected from the target repository's own configuration, never
   hardcoded"** — PASS. `detect_tracker_extensions()` walks `.claude/skills/`, `.opencode/skill/`,
   `.qwen/skill/` and only reports an extension when a matching `SKILL.md` actually exists on disk
   with tracker-indicating metadata (`DetectTrackerExtensionsTests`, 4 tests covering found/absent/
   non-tracker/malformed cases) — no tracker is ever assumed present.

## Success Criteria → Evidence

- **SC-001** (this repo's own real `speckit-taskstoissues` state detected as `github_issues` 100%
  of the time) — PASS. `test_detect_tracker_extensions_finds_github_issues_skill` (deterministic,
  fixture-based) plus a live `discovery scan --path .` / `tracker orchestrate --path .` run against
  this actual repository, both returning exactly one `github_issues` entry for
  `.claude/skills/speckit-taskstoissues/SKILL.md`.
- **SC-002** (zero detected → `orchestrated: false`, no exception, 100% of the time) — PASS.
  `test_orchestrate_returns_false_when_nothing_detected` (empty temp dir, asserts the exact shape
  and a non-empty `reason`).
- **SC-003** (zero tracker-sync/HTTP/API logic anywhere in `spec-master/lib/` after this feature) —
  PASS, verified two ways: `test_tracker_orchestration_module_has_no_network_imports` (code
  inspection assertion) and manual review — `tracker_orchestration.py` imports only `os` from the
  stdlib.
- **SC-004** (`test_discovery.py`/`test_traceability.py` pass unmodified; `traceability render`'s
  output for a row without `issue` is byte-for-byte identical to pre-feature output) — PASS. Full
  suite run: `test_discovery.py` (8/8 passing, file untouched), `test_traceability.py` (3/3
  passing, file untouched), `test_tracker_orchestration.py` (10/10 passing, new). A manual
  `traceability render` walkthrough (below) confirms every pre-existing row's 8 original columns
  are unchanged and only gained a trailing empty `Issue` cell.

## Analyze-Phase Repairs (1 cycle recorded, within the 3-cycle budget)

Cross-artifact analysis of `tasks.md` against `spec.md`/`plan.md`/`data-model.md`/
`contracts/cli-tracker.md` caught one genuine defect before implementation began, plus two
implementation-time doc corrections caught while building against the real `cli.py`:

1. **Task-ID / dedup-regex incompatibility (the recorded analyze cycle)**: `tasks.md` originally
   inserted a lettered task id `T005a` for the malformed-front-matter edge case, breaking every
   prior feature's strict `T\d{3}` numbering. This is not cosmetic: `speckit-taskstoissues`'s own
   dedup regex (`\bT\d{3,}\b`, read in full from the real `SKILL.md` this session) cannot match
   `T005a` at either the `T005` prefix (no trailing word boundary — `5` and `a` are both `\w`) or
   the full token (the digit run is broken before three digits complete), meaning this exact task
   would silently evade dedup if `tasks.md` were ever run through the very skill this feature
   orchestrates. **Repair**: renumbered every task from `T005a` onward sequentially through `T021`
   and updated every `depends on` reference, the Dependencies & Execution Order section, and the
   Parallel Opportunities section. Re-verified via `grep -n "T005a\|depends on T0[0-9]"` (no stale
   references) and `grep -no "T[0-9]\{3,\}[a-z]"` (no lettered ids remain).
2. **Fictitious `--issue` CLI flag**: `contracts/cli-tracker.md` and `quickstart.md` (written before
   `cli.py`'s actual `traceability add` argparse definition was re-read during implementation)
   described a new `--issue <url-or-id>` flag. Reading `cmd_traceability`/`trace_add` in `cli.py`
   showed the real verb already takes a full row dict via `--row-file`/`--row-json`, so no new flag
   is needed or was added — `add_row()`'s existing normalization already passes an `"issue"` key
   through once it is added to `_COLUMNS`. **Repair**: corrected `contracts/cli-tracker.md`,
   `quickstart.md`, and `tasks.md`#T015 to describe the real mechanism.
3. **FR-002's `unknown` enum value**: `spec.md`'s FR-002 listed `unknown` as a possible
   `tracker_type`, contradicting `data-model.md`'s explicit "no `unknown` value" design and
   Acceptance Scenario 3 (non-matching skills are excluded, not tagged). **Repair**: corrected
   FR-002's wording to match the design and the implementation both already followed.

`state analyze-cycle` recorded 1 cycle for this feature (max 3) — the formally tracked analyze-phase
repair (finding 1) is verified; findings 2-3 were documentation-only corrections caught and fixed
during implementation, consistent with this session's practice of fixing real inconsistencies as
they're found rather than deferring them.

## Manual CLI Walkthrough (quickstart.md steps 1-6, against this repository's own real state)

1. `discovery scan --path .` → `tracker_extensions` contains exactly one entry:
   `{"skill": "speckit-taskstoissues", "integration": "claude", "path":
   ".claude/skills/speckit-taskstoissues/SKILL.md", "tracker_type": "github_issues", ...}`.
2. `tracker orchestrate --path .` → `{"orchestrated": true, "invocations": [{"skill":
   "speckit-taskstoissues", "tracker_type": "github_issues", "command": "/speckit-taskstoissues"}],
   "reason": null}` — matches contracts/cli-tracker.md's documented example exactly.
3. `traceability add --path .spec-master/state.json --row-json '{"requirement": "FR-004", ...,
   "issue": "https://github.com/example/repo/issues/42"}'` → row created with the issue link.
4. `traceability render --path .spec-master/state.json` → the new row's `Issue` column shows the
   link; every one of the 20 pre-existing rows (features 1 and 2) shows an empty trailing cell with
   its original 8 columns byte-for-byte unchanged. This verification row was then reverted (it was
   not a real synced issue) before the real FR-001..FR-008 rows were added.
5. `gates detect --path .` → `[]`, same as features 1 and 2's validate phases — no configured
   quality gates beyond the test suite in this repository today.

`git diff --stat` confirms the change surface is exactly: `spec-master/lib/tracker_orchestration.py`
(new), `spec-master/lib/discovery.py` (+5 lines, additive field only), `spec-master/lib/
traceability.py` (2 lines: `_COLUMNS`/`_HEADERS` + the empty-state fallback row's column count),
`spec-master/lib/cli.py` (new `tracker orchestrate` subparser + handler, existing verbs
untouched), `spec-master/tests/test_tracker_orchestration.py` (new) — zero changes to
`team_model.py`, `worktree.py`, `team_workstreams.py`, or any of their test files.

## Verdict

**PASSED** — all 3 acceptance criteria and all 4 Success Criteria are met with test and/or live CLI
evidence; the 21 pre-existing `ModuleNotFoundError: No module named 'pytest'` errors in
`test_graph_*`/`test_knowledge_*` files (documented in features 1 and 2's validation reports) are
unrelated to this feature and remain unchanged. No scope-boundary caveats: this feature's Assumptions
section in spec.md explicitly scoped Jira/Azure DevOps/Linear coverage to the same generic,
evidence-based detection mechanism rather than per-tracker fixtures, and that is exactly what was
delivered and tested.
