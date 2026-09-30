---
name: spec-master-lane
description: "Run one change through the Spec Master lane flow: a deterministic triage decides patch, standard or critical before any artifact exists, and a patch closes only on evidence. Use for a concrete change request."
---

# Spec Master: lane flow

1. Get the instructions for this run: call the `harness_entrypoint` tool of
   the `spec-master` MCP server with `flow: "lane"` and `argument`:
   the change the user asked for, verbatim (it may start with patch, standard or critical).
   Without the MCP server, run
   `python3 <engine>/lib/cli.py harness entrypoint --flow lane --argument "<argument>"`,
   where `<engine>` is the directory of this plugin that contains
   `lib/cli.py` (the plugin root or its `spec-master/` subdirectory).
2. Follow the returned `instructions` exactly: they carry the engine's real
   paths for this installation.

The user's input is `$ARGUMENTS`; when that still reads `$ARGUMENTS`
literally, use the text the user wrote after this skill's name.
