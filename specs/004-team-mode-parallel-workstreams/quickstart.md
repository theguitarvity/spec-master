# Quickstart: Team Mode Parallel Workstreams

1. Produce `workstreams.json` exactly as today: `team workstreams --file <features-with-tasks.json>`
   → write the result to `.spec-master/workstreams.json`.
2. Compute waves over its `packages`, reusing the existing worktree CLI (no new verb):
   map each package to `{"id": p["id"], "dependencies": p["depends_on"]}` and run
   `worktree waves --features <mapped.json>`.
3. For each package in a multi-package wave (including packages sharing a `feature_id`), plan its
   worktree: `worktree plan --feature-id <package-id> --project-root . --strategy trunk`.
4. Once a package's owner agent finishes its work, its assigned `reviewer_agent` records a
   verdict: `workstreams review --file .spec-master/workstreams.json --package <id> --reviewer
   <agent-id> --status APPROVED`.
5. The tech lead records the integration verdict: `workstreams integrate --file
   .spec-master/workstreams.json --package <id> --status APPROVED`.
6. Aggregate the wave: `workstreams aggregate --wave-index 0 --handles <handles.json> --packages
   .spec-master/workstreams.json` — only packages with both verdicts `APPROVED` report
   `integration_state: "integration_ready"`.
7. For conflicts between two package worktrees in the same wave, reuse `worktree conflicts
   --path-a <p1> --path-b <p2>` unchanged (contracts/cli-workstreams.md Non-goals).

Single-package waves and non-git repos need no worktree at all — step 3 is skipped and the
package's owner agent works directly on the current tree, exactly as today (SC-004).
