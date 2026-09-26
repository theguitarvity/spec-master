# Phase 1 Data Model: Spec Kit Tracker Orchestration

## Tracker Extension (detected, never invented)

Returned by `tracker_orchestration.detect_tracker_extensions(root)`, one entry per matching
`SKILL.md` actually found on disk (research.md #1, #2).

| Field | Type | Notes |
|---|---|---|
| `skill` | `str` | The skill's directory name, e.g. `"speckit-taskstoissues"` |
| `integration` | `"claude" \| "opencode" \| "qwen"` | Which of `discovery.py`'s three known integration directories the manifest was found under |
| `path` | `str` | Path to the manifest, relative to `root`, e.g. `.claude/skills/speckit-taskstoissues/SKILL.md` |
| `tracker_type` | `"jira" \| "azure_devops" \| "linear" \| "github_issues"` | Classified from the manifest's own `description`/`name` front-matter keywords (research.md #2); a skill matching none of these keywords is not included in the result at all — there is no `"unknown"` value that could be silently treated as a real tracker |
| `description` | `str` | The manifest's own declared `description`, carried through unmodified for the agent to read |

## Discovery Result (extended)

`discovery.scan()`'s existing return dict (`stacks`, `ci_present`, `spec_kit_present`,
`speckit_commands`, `speckit_command_paths`, ...) gains exactly one new key, additive only:

| Field | Type | Notes |
|---|---|---|
| `tracker_extensions` | `list[Tracker Extension]` | `[]` when none detected (FR-001, FR-003) — every other existing key's value and shape is unchanged |

## Orchestration Result

Returned by `tracker_orchestration.orchestrate(root)` — the detect-then-instruct record the agent
consumes; never itself the output of a tracker API call (FR-004).

| Field | Type | Notes |
|---|---|---|
| `orchestrated` | `bool` | `True` iff `tracker_extensions` is non-empty |
| `extensions` | `list[Tracker Extension]` | Same shape as above; empty list when `orchestrated` is `False` |
| `invocations` | `list[dict]` | One `{skill, tracker_type, command}` per extension — `command` is the literal invocation string the agent should run, e.g. `"/speckit-taskstoissues"` for a Claude-integration skill (FR-004) |
| `reason` | `str \| null` | Human-readable explanation when `orchestrated` is `False` (FR-005), e.g. `"no tracker extension detected under .claude/skills, .opencode/skill, .qwen/skill"`; `null` when `orchestrated` is `True` |

## Traceability Row (extended)

`traceability.py`'s existing 8-column row gains one new, optional, trailing column
(research.md #4, FR-007):

| Field | Type | Notes |
|---|---|---|
| `issue` | `str` | Link or id of a tracker issue synced for this requirement, e.g. a GitHub issue URL; `""` when not yet synced — identical rendering to every other row that predates this feature |

`add_row()`'s existing normalization (`{col: row.get(col, "") for col in _COLUMNS}`) requires no
logic change — adding `"issue"` to the module-level `_COLUMNS`/`_HEADERS` constants is the entire
change; a caller that never passes `issue` is unaffected (Principle VI).
