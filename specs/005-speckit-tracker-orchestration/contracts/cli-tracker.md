# CLI Contract: `tracker`

New `spec-master/lib/cli.py` subparser group. `discovery scan` is extended in place (Non-goals) —
no separate detection verb is needed for that half of the feature.

## `tracker orchestrate`

Detect installed Spec Kit tracker-orchestration skills and produce an invocation instruction for
each — never performs any tracker API/network call itself.

```text
python3 cli.py tracker orchestrate [--path <root>]
```

- Calls `tracker_orchestration.detect_tracker_extensions(root)` then
  `tracker_orchestration.orchestrate(root)` (data-model.md).
- **Output** (always exit 0 — absence of any extension is a normal result, not an error, FR-005):

  ```json
  {
    "orchestrated": true,
    "extensions": [
      {
        "skill": "speckit-taskstoissues",
        "integration": "claude",
        "path": ".claude/skills/speckit-taskstoissues/SKILL.md",
        "tracker_type": "github_issues",
        "description": "Convert existing tasks into actionable, dependency-ordered GitHub issues..."
      }
    ],
    "invocations": [
      {"skill": "speckit-taskstoissues", "tracker_type": "github_issues", "command": "/speckit-taskstoissues"}
    ],
    "reason": null
  }
  ```

  or, when nothing is detected:

  ```json
  {"orchestrated": false, "extensions": [], "invocations": [], "reason": "no tracker extension detected under .claude/skills, .opencode/skill, .qwen/skill"}
  ```

- The agent is responsible for actually running the named `command` (e.g. `/speckit-taskstoissues`)
  and capturing any resulting issue links — `tracker orchestrate` never does this itself
  (research.md #3, Principle I).

## `traceability add` (extended, not a new verb, no new flag)

Existing verb takes a full row dict via `--row-file`/`--row-json` (`cmd_traceability` in
`cli.py`), which `add_row()` already normalizes to `_COLUMNS`. Adding `"issue"` to `_COLUMNS`/
`_HEADERS` (data-model.md, research.md #4) is the entire change — no new CLI flag, since any key
present in the supplied row JSON already flows through unmodified:

```text
python3 cli.py traceability add --path <state.json> --row-json '{"requirement": "FR-004", "issue": "https://github.com/x/y/issues/1"}'
```

- Omitting `"issue"` from the row JSON behaves exactly as before this feature (empty string, same
  as every other column a caller doesn't supply).
- `traceability render` includes the new `Issue` column in its output table for every row,
  populated only where the row JSON supplied one.

## Non-goals — `discovery scan` is extended in place, no new detection verb

- Tracker-extension detection is exposed as a new `tracker_extensions` field on the existing
  `discovery scan` output (data-model.md), the same way `speckit_commands`/`speckit_command_paths`
  already are — not as a separate `tracker detect` verb. `tracker orchestrate` re-runs detection
  internally (calling the same `detect_tracker_extensions` function `discovery.scan()` calls) so it
  can be used standalone without first invoking `discovery scan`.
- No `tracker sync`/`tracker create-issue`/equivalent verb exists, and none will be added — that
  would reimplement `speckit-taskstoissues`'s (or any other detected skill's) own sync logic, which
  Principle VII forbids (research.md #3).
