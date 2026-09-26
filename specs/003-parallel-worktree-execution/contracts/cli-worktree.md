# CLI Contract: `worktree` subcommand group

Exposed via `spec-master/lib/cli.py`, mirroring the existing `state`/`features`/`git-strategy`
subcommand pattern (argparse subparsers, JSON in/out, stdlib only).

## `worktree waves`

Compute execution waves from an ordered feature list.

```text
python3 cli.py worktree waves --features <path-to-ordered-features.json>
```

- **Input**: JSON array of `{id, dependencies}` in the order returned by `features order`.
- **Output**: JSON array of `{wave_index, feature_ids}`.
- **Errors**: exits non-zero with a message if a `dependencies` entry references an unknown id
  (mirrors `feature_model.CycleError` handling already used by `features order`).

## `worktree plan`

Create (or idempotently resume) the isolated `git worktree` for a feature and return its
handle. Unlike `git-strategy plan` (a genuinely pure, dry decision function with no I/O), this
verb performs the real `git worktree add` — the "plan" in its name refers to planning *which*
feature gets *which* isolated directory, not to deferring the filesystem mutation to a later
step.

```text
python3 cli.py worktree plan --feature-id <id> --project-root <path> --strategy trunk|git-flow
```

- **Output**: JSON `Worktree Handle` (see data-model.md) with `state: "created"`.
- **Idempotent** (research.md #2 idempotency note, data-model.md Worktree Handle lifecycle,
  added during `/speckit-analyze` repair cycle 1): if the target path already exists, this
  verb reuses/resumes it and returns a handle for the existing directory instead of calling
  `git worktree add` again — it never recreates or deletes an existing worktree.

## `worktree conflicts`

Read-only conflict check between two worktree paths.

```text
python3 cli.py worktree conflicts --path-a <path> --path-b <path>
```

- **Output**: JSON `{files: [...]}` — empty list when no overlap. Internally shells out to
  `git merge-tree` through the mockable `run_git()` boundary (research.md #3); never mutates
  either worktree.

## `worktree aggregate`

Build an `Aggregation Result` from a list of finished worktree handles.

```text
python3 cli.py worktree aggregate --wave-index <n> --handles <path-to-handles.json>
```

- **Output**: JSON `Aggregation Result` (see data-model.md).
- **Errors**: none — this is a pure fold over already-known handle states; it never talks to
  git itself (conflict detection is a separate, explicit `worktree conflicts` call per handle
  pair, so the caller controls when the read-only git cost is paid).

## Non-goals of this contract

- No `worktree remove` verb in this contract: deletion of a finished/aggregated worktree is
  left to the caller's own housekeeping (FR-008 forbids the core from ever auto-deleting a
  non-terminal one; deciding *when* to clean up a terminal one is a caller policy, not a
  structural decision Principle I reserves for the core).
