Run this change through the Spec Master lane flow: a deterministic triage
decides patch, standard or critical before any artifact exists, and a patch
is closed only on evidence (`step end`).

Follow `{engine}/cards/router.md`, with the rules in `{engine}/cards/core.md`.
Every `spec-master/lib/cli.py` in the cards means `{engine}/lib/cli.py`,
run from the project root with `--path .`.

The request: {request}

If its first word is `patch`, `standard` or `critical`, that is the lowest
lane the user asked for (pass it as `--lane` to `lane triage`) and the rest,
verbatim, is `--intent`; otherwise all of it is `--intent`.
