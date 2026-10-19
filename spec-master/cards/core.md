# Core rules (every lane)

- **Source of truth**: the user's request and the repository. Tag every claim
  you write down: `[EXPLICIT]` (the user said it), `[INFERRED]` (your
  deduction — never an acceptance check without the user's word),
  `[DISCOVERED_FROM_CODEBASE]` (cite `file:line`), `[UNRESOLVED]` (ask; a
  patch cannot carry one).
- **Done means evidence**: `step end` checks the real diff and runs the
  project's own gates. Never say "done" before it answers `PASSED`.
- **Core-owned files**: never edit `.spec-master/state.json`,
  `.spec-master/changes/*.json`, `.spec-master/metrics/rounds.json`,
  `.spec-master/policy.json` or `.spec-master/gates.json` — the kernel writes
  them.
- **Questions**: only at a step boundary, all in one batch. When a safe
  default exists and the answer changes neither scope, security, data nor a
  public contract, take it and record `SAFE_DEFAULT: <decision>` in the note.
- **Never**: `git reset --hard`, `git clean -f`, force pushes, deleting work
  you did not create, or piping a download into a shell.
