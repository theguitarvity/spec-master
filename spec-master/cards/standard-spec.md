# Standard {change_id} — spec-lite

Intent [EXPLICIT]: {intent}
Declared files: {envelope}

1. Write ONE file, `{spec_dir}/spec.md` (at most 8 KB), with: the problem,
   acceptance checks, a short plan and at most 12 tasks. Tags as in `core.md`.

       - [EXPLICIT] <acceptance check> (test: <test file>)
       - [DISCOVERED_FROM_CODEBASE] <fact> at `<file>:<line>` (task: T001)
       - [ ] T001 <task>

   Every acceptance check needs `(test: <test file>)` or `(task: Tnnn)`.
   An open question is `[UNRESOLVED]`: ask them all in one batch, or take a
   safe default and record `SAFE_DEFAULT: <decision>`.
2. `python3 spec-master/lib/cli.py standard verify-pre --path .` is the
   analyze of this lane (deterministic, no Spec Kit skill). Fix what it
   reports and run it again. Production code is blocked until it passes.
