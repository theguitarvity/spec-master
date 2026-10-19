# Standard {change_id} — implement, test first

Intent [EXPLICIT]: {intent}
Declared files: {envelope}
Test command: {test_command}

1. RED: write the failing test for the next acceptance check, then
   `python3 spec-master/lib/cli.py standard red --path .` — it must FAIL.
2. GREEN: write the least production code, then
   `python3 spec-master/lib/cli.py standard green --path .` — it must PASS.
3. Repeat per task; tick each `- [ ] Tnnn` in `{spec_dir}/spec.md` when done.
   Need another file? `step widen --path . --paths <file>` (the lane may go up).
4. `python3 spec-master/lib/cli.py step end --path .` verifies the diff, the
   tasks, the RED-then-GREEN evidence and the gates. Done only at `PASSED`.
5. Work left unbuilt after `step end`? When `{spec_dir}` is a full Spec Kit set,
   `/speckit.converge` appends it to `tasks.md`; do not hand-write that list.
