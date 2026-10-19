---
name: spec-master
description: "Run the Spec Master full cycle (constitution, specify, clarify, plan, tasks, analyze, implement, validate) from a context file. Use for a whole feature or product described in a document, or with no file for a guided discovery."
---

# Spec Master: full cycle

1. Get the instructions for this run: call the `harness_entrypoint` tool of
   the `spec-master` MCP server with `flow: "full-cycle"` and `argument`:
   the context file the user named (leave it empty for the guided discovery).
   Without the MCP server, run
   `python3 <engine>/lib/cli.py harness entrypoint --flow full-cycle --argument "<argument>"`,
   where `<engine>` is the directory of this plugin that contains
   `lib/cli.py` (the plugin root or its `spec-master/` subdirectory).
2. Follow the returned `instructions` exactly: they carry the engine's real
   paths for this installation.

The user's input is `$ARGUMENTS`; when that still reads `$ARGUMENTS`
literally, use the text the user wrote after this skill's name.
