# Quickstart: Spec Kit Tracker Orchestration

1. Run detection standalone or as part of discovery: `discovery scan --path .` now includes a
   `tracker_extensions` field; against this repository it reports one entry for
   `.claude/skills/speckit-taskstoissues/SKILL.md` (`tracker_type: "github_issues"`).
2. Ask what to do about it: `tracker orchestrate --path .` — returns `orchestrated: true` with an
   `invocations` list naming the exact command to run (`/speckit-taskstoissues`).
3. If `orchestrated` is `false` (no tracker extension installed), do nothing further — the rest of
   the Spec Master pipeline continues unaffected (FR-005, US3).
4. The orchestrating agent actually runs the named command (e.g. `/speckit-taskstoissues`) — Spec
   Master itself never calls a tracker's API (SC-003). The skill's own guards apply unchanged (e.g.
   it refuses to run when the git remote isn't a GitHub URL).
5. For each requirement whose issue was created/synced, record the link in the traceability matrix
   by including `"issue"` in the row JSON — no new flag, the existing `--row-json`/`--row-file`
   mechanism already passes any supplied key through: `traceability add --path
   .spec-master/state.json --row-json '{"requirement": "<id>", "issue": "<issue-url-or-id>"}'`.
6. `traceability render` now shows an `Issue` column; rows that never synced an issue render an
   empty cell, identical to their pre-feature output (SC-004).

A repository with no tracker skill installed at all needs no new step — `tracker orchestrate`
returns `orchestrated: false` and step 4 onward simply doesn't happen.
