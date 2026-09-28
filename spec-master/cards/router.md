# Spec Master — lane router (opt-in)

You were invoked with `--lane`: the harness decides how much process this
change needs **before** any artifact exists. Follow these steps; read
`PROTOCOL.md` only if the lane sends you there. Rules: `core.md`.

1. **Look** (read-only, at most 5 turns): open what the change needs and list
   every file you will touch, tests included.
2. **Triage**:
   `python3 spec-master/lib/cli.py lane triage --path . --intent "<the request, verbatim>" --paths <a,b,...>`
   (add `--lane <lane>` when the user asked for one: it can only raise the lane)
   - `questions` not empty: ask them all in one `AskUserQuestion` batch, then
     re-run with `--confirm <signal>` / `--deny <signal>` for each answer.
   - `lane: patch`: go to step 3.
   - `lane: standard` or `critical`: this change needs the full cycle. Put the
     request, verbatim, in a context file and run `/spec-master <context file>`
     (`PROTOCOL.md`).
3. **Begin**:
   `python3 spec-master/lib/cli.py step begin --path . --lane patch --intent "<the request>" --paths <a,b,...>`
   (bugfix: add `--kind bugfix --regression-test <test file> --test-command "<command>"`).
   It prints the implement card — follow it.
4. **End**: `python3 spec-master/lib/cli.py step end --path .` verifies the
   change. It is done only when the answer says `status: PASSED`; on
   `ESCALATED`, follow the card it prints. `step next --path .` reprints the
   current card at any time (e.g. after a context compaction).

The lane only goes up: never shrink the declared files to fit a lane.
Irreversible actions (push, PR, publish, deploy) always need the user's
explicit yes, whatever the lane.
