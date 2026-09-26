# Quickstart: Parallel Worktree Execution

## Prerequisites

- Python 3 (stdlib only, no install step)
- A git repository (`discovery scan` reports `is_git_repo: true`)

## Validate wave computation (US1)

```bash
python3 spec-master/lib/cli.py features order --path .spec-master/state.json > /tmp/ordered.json
python3 spec-master/lib/cli.py worktree waves --features /tmp/ordered.json
```

**Expected**: two independent features (no dependency edge) appear in the same
`wave_index`; a feature depending on another appears in a strictly later wave.

## Validate worktree isolation (US1, US3)

```bash
python3 spec-master/lib/cli.py worktree plan --feature-id <id> --project-root . --strategy trunk
```

**Expected**: for a wave of exactly one feature, this verb is never invoked by the caller
(US3) — the feature runs directly against the current working tree. For a wave of two or
more, each feature gets its own handle under `.spec-master/worktrees/<feature-id>`.

## Validate conflict reporting (US2)

```bash
python3 spec-master/lib/cli.py worktree conflicts --path-a .spec-master/worktrees/feature-a --path-b .spec-master/worktrees/feature-b
```

**Expected**: `{"files": []}` when no overlap; `{"files": ["path/to/file.py"]}` when both
worktrees touched the same file incompatibly — neither worktree's content is modified by
running this command.

## Validate aggregation (US2)

```bash
python3 spec-master/lib/cli.py worktree aggregate --wave-index 0 --handles /tmp/handles.json
```

**Expected**: a JSON `Aggregation Result` listing each feature's final status and changed
files, with `conflicts: []` unless a prior `worktree conflicts` call found overlap.

## Regression check (US3, SC-004)

```bash
python3 -m unittest discover -s spec-master/tests -v
```

**Expected**: full suite passes unmodified, including existing single-feature and
non-git-repo sequential-execution tests — this feature is additive only.
