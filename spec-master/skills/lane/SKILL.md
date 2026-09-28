---
name: lane
description: Run a change through the Spec Master lane flow — triage decides patch, standard or critical before any artifact exists; a patch is implemented in this session and closed only by evidence (step end). Use for a concrete change request; use /spec-master for a whole product context.
---

# Spec Master lane flow

Follow `${CLAUDE_PLUGIN_ROOT}/cards/router.md`, with the rules in
`${CLAUDE_PLUGIN_ROOT}/cards/core.md`. The user's request is `$ARGUMENTS`:
if its first word is `patch`, `standard` or `critical`, that is the lowest
lane the user asked for (pass it as `--lane` to `lane triage`) and the rest,
verbatim, is `--intent`; otherwise all of it is `--intent`.

In every command the cards show, `spec-master/lib/cli.py` means
`${CLAUDE_PLUGIN_ROOT}/lib/cli.py` (the engine shipped with this plugin), and
`--path .` is the project you are working in. For example:

`python3 "${CLAUDE_PLUGIN_ROOT}/lib/cli.py" lane triage --path . --intent "<request>" --paths <a,b>`

The plugin's hooks run in audit mode until the project opts into blocking:
`python3 "${CLAUDE_PLUGIN_ROOT}/lib/cli.py" harness mode --project . --mode block`
writes `hooks_mode: block` to `.spec-master/policy.json` (do not run
`harness install-hooks` as well: the plugin already provides the hooks).
