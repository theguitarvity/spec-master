# Phase 0 Research: Spec Kit Tracker Orchestration

**Input**: [spec.md](spec.md), constitution Principles I, VI, VII, VIII

## Unknowns from Technical Context

### 1. Which directories/files to scan for tracker skills

- **Decision**: Reuse `discovery.py::scan()`'s existing three integration directories —
  `.claude/skills/`, `.opencode/skill/`, `.qwen/skill/` — mirroring exactly the pattern already used
  for `speckit_command_paths` (`.claude/commands/`, `.opencode/commands/`, `.qwen/commands/`). Each
  directory that exists is walked one level for subdirectories containing a `SKILL.md` (Claude) or
  equivalent manifest file; a directory that does not exist is silently skipped, never an error.
- **Rationale**: `discovery.py` already established this exact multi-integration directory list for
  Spec Kit phase commands; a tracker skill is the same kind of installed artifact (a Skill/command
  the active agent runtime exposes), so reusing the same directory list avoids inventing a second,
  possibly-inconsistent notion of "where Spec Kit integrations live" (Principle VI).
- **Alternatives considered**: Scanning only `.claude/skills/` — rejected, `discovery.py` already
  supports three agent runtimes and narrowing tracker detection to one would silently regress for
  opencode/qwen projects that already get full speckit-command detection today.

### 2. How to classify `tracker_type` from a skill's own metadata

- **Decision**: Read each candidate `SKILL.md`'s YAML front-matter `description` (and `name` as a
  fallback) and match, case-insensitively, against a fixed keyword table:
  `jira` → `jira`; `azure devops` or `azure-devops` or `ado` → `azure_devops`; `linear` → `linear`;
  `github issue` or `github issues` → `github_issues`. A skill whose metadata matches none of these
  is not reported as a tracker extension at all (FR-001's "never invents presence" — matching zero
  keywords is treated as "not a tracker skill," not as `tracker_type: "unknown"` silently included).
- **Rationale**: `speckit-taskstoissues`'s own front-matter description is `"Convert existing tasks
  into actionable, dependency-ordered GitHub issues for the feature based on available design
  artifacts."` — it matches `github issue`. This keeps classification evidence-based (reading text
  that is actually in the file) rather than guessing from the skill's directory name alone, which
  could be renamed without changing behavior.
- **Alternatives considered**: Matching on skill directory name only (e.g. `speckit-<tracker>`) —
  rejected, a community skill is not guaranteed to name itself that way, and matching only the name
  would miss `speckit-taskstoissues` itself (its name mentions "issues" but not "github" — the
  description is what actually disambiguates the tracker).

### 3. Where orchestration output lives and how the agent consumes it

- **Decision**: A new `spec-master/lib/tracker_orchestration.py` module exposes
  `detect_tracker_extensions(root=".") -> list[dict]` (called from `discovery.scan()` to populate
  the new `tracker_extensions` field, per FR-003) and `orchestrate(root=".") -> dict` (the
  detect-then-instruct entry point, per FR-004/FR-005), wired to a new `spec-master/lib/cli.py`
  `tracker orchestrate` verb that prints the JSON instruction to stdout — the same
  detect-print-let-the-agent-act shape `gates detect` already uses for quality gates.
- **Rationale**: Matches Principle I's core/agent split exactly: the deterministic core can detect
  and describe, but only the orchestrating agent can actually invoke a Skill
  (e.g. run `/speckit-taskstoissues`) and capture its result. This is structurally identical to how
  PROTOCOL.md Step 7 already separates `gates detect` (core) from actually running an
  `allowed: true` command (agent).
- **Alternatives considered**: Having `orchestrate()` shell out to invoke the skill's own command —
  rejected; `spec-master/lib/` is pure Python with no subprocess boundary for invoking Claude Skills
  (only `worktree.py::run_git` has a deliberate, narrow, documented subprocess boundary for git —
  extending that pattern to arbitrary skill invocation is out of scope and would violate Principle
  II's stdlib-only, zero-external-dependency core).

### 4. How a synced issue link reaches the traceability matrix

- **Decision**: Add one new optional column, `issue`, to `traceability.py`'s `_COLUMNS`/`_HEADERS`
  (after `status`). `add_row()`'s existing `{col: row.get(col, "") for col in _COLUMNS}` normalization
  needs no logic change — a caller that doesn't pass `issue` simply gets `""`, identical to today's
  behavior for every row that predates this feature.
- **Rationale**: The spec's acceptance criterion is explicit: "Links/ids de issues sincronizados
  aparecem na matriz de rastreabilidade." Overloading the existing free-text `status` column (e.g.
  `"VALIDATED (issue: #42)"`) was considered and rejected because it would make `status` no longer a
  clean enum-like value for any future automation that reads it, and because a dedicated column is
  the same additive-extension shape feature 2 already used successfully for `integration_state` in
  `aggregate_with_verdicts` (extend an existing report structure with one new field, never repurpose
  an existing one).
- **Alternatives considered**: A separate `tracker_links.json` file keyed by requirement id —
  rejected, splits the single source of truth (`traceability` in `state.json`) that Principle V
  already establishes as where a human looks for this information.

## Output

All Technical Context unknowns resolved; no `NEEDS CLARIFICATION` markers remain.
