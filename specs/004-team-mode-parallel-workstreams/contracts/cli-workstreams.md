# CLI Contract: `workstreams`

New `spec-master/lib/cli.py` subparser group. Reuses the existing `worktree` group directly for
wave computation, worktree creation, conflict detection, and base aggregation — see Non-goals.

## `workstreams review`

Record a peer-review verdict for a package.

```text
python3 cli.py workstreams review --file <workstreams.json> --package <id> \
  --reviewer <agent-id> --status APPROVED|REJECTED [--reason <text>]
```

- Loads `--file`, finds the package by `id`, sets `review_verdict = {status, reviewer_agent,
  reason}`.
- **Errors** (non-zero exit, `ValueError` from `team_workstreams.record_review_verdict`) if
  `--reviewer` does not equal that package's own `reviewer_agent` field (research.md #3) — peer
  review cannot be self-recorded by the package owner or an arbitrary agent.
- `--reason` is required when `--status REJECTED` (data-model.md).
- **Output**: the updated package JSON. Writes `--file` back to disk.

## `workstreams integrate`

Record the Tech Lead's integration verdict for a package.

```text
python3 cli.py workstreams integrate --file <workstreams.json> --package <id> \
  --status APPROVED|REJECTED [--reason <text>]
```

- No `--reviewer`/`--agent` flag — the approving role is always `"tech-lead"` (research.md #4).
- `--reason` is required when `--status REJECTED`.
- **Output**: the updated package JSON. Writes `--file` back to disk.

## `workstreams aggregate`

Fold a wave's finished worktree handles into an Aggregation Result annotated with each package's
integration state.

```text
python3 cli.py workstreams aggregate --wave-index <n> --handles <handles.json> \
  --packages <workstreams.json>
```

- Calls `worktree.aggregate(wave_index, handles)` unchanged, then calls
  `team_workstreams.aggregate_with_verdicts` to annotate each entry's `integration_state`
  (data-model.md) by matching `handle["feature_id"]` (the package id) against `--packages`.
- **Output**: the annotated Aggregation Result JSON.

## Non-goals — reuse the existing `worktree` CLI group unchanged

- **Wave computation**: use `worktree waves --features <packages-mapped-to-dependencies.json>`
  directly (research.md #2) — map each package to `{"id": package["id"], "dependencies":
  package["depends_on"]}` before calling it. No `workstreams waves` verb exists.
- **Worktree creation**: use `worktree plan --feature-id <package-id> ...` directly, passing the
  package id in the existing `--feature-id` argument. No `workstreams plan` verb exists.
- **Conflict detection**: use `worktree conflicts --path-a <p> --path-b <p>` directly, unchanged
  — it is already fully generic over what the two paths represent. No `workstreams conflicts`
  verb exists.

Introducing wrapper verbs for these three would duplicate `worktree.py`'s existing, already-
tested CLI surface for zero behavioral difference (Principle VI) — see research.md #2.
