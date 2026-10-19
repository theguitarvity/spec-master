#!/usr/bin/env python3
"""Package Spec Master for every agent host from one source of truth.

The repository is at the same time a Claude Code / Codex / Copilot / Cursor
marketplace (plugin root: `spec-master/`), an Agent Plugins 1.0 plugin and a
Gemini CLI extension (plugin root: the repository itself). Every manifest,
hooks file and skill those hosts read is rendered here; nothing is edited by
hand, and `check` (run by `doctor` and the tests) fails when a committed file
drifts from what this module renders.

    python3 spec-master/lib/packaging.py generate [--root .]
    python3 spec-master/lib/packaging.py check [--root .]

What each host reads (the plugin root is `spec-master/` unless noted):

- Claude Code: .claude-plugin/plugin.json, hooks/hooks.json, .mcp.json, skills/
- Codex: .codex-plugin/plugin.json, .codex-mcp.json, hooks/codex-hooks.json, skills/
- GitHub Copilot CLI and VS Code: .github/plugin/plugin.json,
  hooks/copilot-hooks.json, .mcp.json, skills/
- Cursor: .cursor-plugin/plugin.json, hooks/cursor-hooks.json, .mcp.json, skills/
- Agent Plugins 1.0 hosts (Kiro powers, Qwen Code, others), repository root:
  plugin.json, mcp.json, skills/
- Gemini CLI (and hosts that import its extensions), repository root:
  gemini-extension.json, hooks/hooks.json, skills/
- Antigravity, repository root: plugin.json (it accepts the Agent Plugins
  manifest), hooks.json, mcp_config.json, skills/; it runs hook commands and
  MCP servers from the plugin's own directory, so their paths are relative.
- Marketplaces, repository root: .claude-plugin/marketplace.json (Claude,
  Codex, Copilot, VS Code) and .cursor-plugin/marketplace.json.

Kiro powers cannot carry hooks, and Qwen Code loads a repository with an
Agent Plugins manifest as skills and MCP only: for both, `harness
install-hooks --host kiro|qwen` writes the hooks into the project instead
(see kernel/install.py).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

VERSION = "0.3.0"
NAME = "spec-master"
DISPLAY_NAME = "Spec Master"
ENGINE = "spec-master"  # the engine directory, relative to the repository root
SHORT_DESCRIPTION = "Harness for spec-driven development"
DESCRIPTION = ("Harness for spec-driven development: a deterministic triage decides how much process each "
               "change needs, hooks enforce the workflow's rules, nothing is done without evidence, and "
               "GitHub Spec Kit runs the full cycle.")
AUTHOR = {"name": "Spec Master maintainers"}
REPOSITORY = "https://github.com/theguitarvity/spec-master"
LICENSE = "MIT"
KEYWORDS = ["spec-driven-development", "harness", "spec-kit", "hooks", "mcp"]
CATEGORY = "development"
AGENT_PLUGINS_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
AGENT_PLUGINS_MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"

HOOKD = "lib/kernel/hookd.py"  # relative to the engine
MCP_SERVER = "mcp/spec_master_mcp.py"  # relative to the engine
# The skills need only `harness_entrypoint`; the full tool list would cost every
# session of a host that loads MCP schemas up front about 12k tokens.
MCP_ARGS = ["--tools", "entrypoint"]

# Spec Master event -> (timeout in seconds). The host-specific event names
# and matchers live with each host below.
EVENTS = {"pre-tool-use": 10, "post-tool-use": 30, "stop": 10, "session-start": 10}

SKILLS = {
    "spec-master": {
        "flow": "full-cycle",
        "description": ("Run the Spec Master full cycle (constitution, specify, clarify, plan, tasks, analyze, "
                        "implement, validate) from a context file. Use for a whole feature or product "
                        "described in a document, or with no file for a guided discovery."),
        "argument": "the context file the user named (leave it empty for the guided discovery)",
    },
    "spec-master-lane": {
        "flow": "lane",
        "description": ("Run one change through the Spec Master lane flow: a deterministic triage decides "
                        "patch, standard or critical before any artifact exists, and a patch closes only on "
                        "evidence. Use for a concrete change request."),
        "argument": "the change the user asked for, verbatim (it may start with patch, standard or critical)",
    },
}


def _json(value) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------- skills

def skill(name: str) -> str:
    spec = SKILLS[name]
    # A JSON string is a valid double-quoted YAML scalar: descriptions may hold ": ".
    return f"""---
name: {name}
description: {json.dumps(spec['description'], ensure_ascii=False)}
---

# {DISPLAY_NAME}: {"full cycle" if spec['flow'] == "full-cycle" else "lane flow"}

1. Get the instructions for this run: call the `harness_entrypoint` tool of
   the `spec-master` MCP server with `flow: "{spec['flow']}"` and `argument`:
   {spec['argument']}.
   Without the MCP server, run
   `python3 <engine>/lib/cli.py harness entrypoint --flow {spec['flow']} --argument "<argument>"`,
   where `<engine>` is the directory of this plugin that contains
   `lib/cli.py` (the plugin root or its `{ENGINE}/` subdirectory).
2. Follow the returned `instructions` exactly: they carry the engine's real
   paths for this installation.

The user's input is `$ARGUMENTS`; when that still reads `$ARGUMENTS`
literally, use the text the user wrote after this skill's name.
"""


# --------------------------------------------------------------------------- hooks

def _command(host: str, event: str) -> str:
    if host == "claude":
        return f'python3 "${{CLAUDE_PLUGIN_ROOT}}/{HOOKD}" {event}'
    if host == "codex":
        return f'python3 "${{PLUGIN_ROOT}}/{HOOKD}" {event} --host codex'
    if host == "copilot":  # a failing preToolUse hook blocks in Copilot: never let a missing engine do that
        return f"python3 \"$PLUGIN_ROOT/{HOOKD}\" {event} --host copilot || echo '{{}}'"
    if host == "cursor":
        return f'python3 "${{CURSOR_PLUGIN_ROOT}}/{HOOKD}" {event} --host cursor'
    if host == "gemini":
        return f'python3 "${{extensionPath}}/{ENGINE}/{HOOKD}" {event} --host gemini'
    if host == "antigravity":  # run from the directory that holds hooks.json: the repository root
        return f"python3 {ENGINE}/{HOOKD} {event} --host antigravity"
    raise ValueError(host)


def claude_style_hooks(host: str) -> dict:
    """Claude Code's hooks.json shape, also read by Codex."""
    shell = "Bash"
    writes = "apply_patch|Edit|Write" if host == "codex" else "Edit|Write|MultiEdit|NotebookEdit"
    layout = {
        "PreToolUse": (f"{shell}|{writes}", "pre-tool-use"),
        "PostToolUse": (writes, "post-tool-use"),
        "Stop": (None, "stop"),
        "SessionStart": ("startup|resume|compact", "session-start"),
    }
    hooks = {}
    for host_event, (matcher, event) in layout.items():
        entry = {"hooks": [{"type": "command", "command": _command(host, event), "timeout": EVENTS[event]}]}
        hooks[host_event] = [{"matcher": matcher, **entry} if matcher else entry]
    return {"hooks": hooks}


def copilot_hooks() -> dict:
    layout = {
        "sessionStart": (None, "session-start"),
        "preToolUse": ("bash|edit|create|apply_patch|str_replace_editor", "pre-tool-use"),
        "postToolUse": ("edit|create|apply_patch|str_replace_editor", "post-tool-use"),
        "agentStop": (None, "stop"),
    }
    hooks = {}
    for host_event, (matcher, event) in layout.items():
        entry = {"type": "command", "bash": _command("copilot", event), "timeoutSec": EVENTS[event]}
        hooks[host_event] = [{**entry, "matcher": matcher} if matcher else entry]
    return {"version": 1, "hooks": hooks}


def cursor_hooks() -> dict:
    def entry(event, **extra):
        return {"command": _command("cursor", event), "timeout": EVENTS[event], **extra}
    return {"version": 1, "hooks": {
        "beforeShellExecution": [entry("pre-tool-use")],  # preToolUse does not enforce "ask"
        "preToolUse": [entry("pre-tool-use", matcher="Write|Delete")],
        "postToolUse": [entry("post-tool-use", matcher="Write")],
        "stop": [entry("stop", loop_limit=2)],
        "sessionStart": [entry("session-start")],
    }}


def gemini_hooks() -> dict:
    layout = {
        "BeforeTool": ("^(run_shell_command|write_file|replace)$", "pre-tool-use"),
        "AfterTool": ("^(write_file|replace)$", "post-tool-use"),
        "AfterAgent": (None, "stop"),
        "SessionStart": ("*", "session-start"),  # lifecycle matchers are exact strings
    }
    hooks = {}
    for host_event, (matcher, event) in layout.items():
        command = {"name": f"spec-master-{event}", "type": "command", "command": _command("gemini", event),
                   "timeout": EVENTS[event] * 1000}  # Gemini CLI timeouts are in milliseconds
        entry = {"hooks": [command]}
        hooks[host_event] = [{"matcher": matcher, **entry} if matcher else entry]
    return {"hooks": hooks}


def antigravity_hooks() -> dict:
    """Named hook groups. Antigravity has no session-start event, and a
    PostToolUse reply cannot carry context back, so only these two apply."""
    def handler(event):
        return {"type": "command", "command": _command("antigravity", event), "timeout": EVENTS[event]}
    return {NAME: {
        "PreToolUse": [{"matcher": "run_command|write_to_file|replace_file_content|multi_replace_file_content",
                        "hooks": [handler("pre-tool-use")]}],
        "Stop": [handler("stop")],
    }}


# --------------------------------------------------------------------------- manifests

def _plugin_metadata() -> dict:
    return {"name": NAME, "version": VERSION, "description": DESCRIPTION, "author": AUTHOR,
            "homepage": REPOSITORY, "repository": REPOSITORY, "license": LICENSE, "keywords": KEYWORDS}


def claude_plugin() -> dict:
    return {**_plugin_metadata(), "displayName": DISPLAY_NAME}


def codex_plugin() -> dict:
    return {"name": NAME, "version": VERSION, "description": DESCRIPTION, "author": AUTHOR,
            "homepage": REPOSITORY, "repository": REPOSITORY, "license": LICENSE, "keywords": KEYWORDS,
            "skills": "./skills/", "mcpServers": "./.codex-mcp.json", "hooks": "./hooks/codex-hooks.json",
            "interface": {"displayName": DISPLAY_NAME, "shortDescription": SHORT_DESCRIPTION,
                          "longDescription": DESCRIPTION, "developerName": AUTHOR["name"],
                          "category": "Coding", "capabilities": []}}


def codex_mcp() -> dict:
    # Codex does not expand ${CLAUDE_PLUGIN_ROOT} here; a relative cwd resolves against the plugin root.
    return {"mcpServers": {NAME: {"command": "python3", "args": [f"./{MCP_SERVER}", *MCP_ARGS], "cwd": "."}}}


def claude_mcp() -> dict:
    # Read by Claude Code, Copilot and Cursor, which all expand ${CLAUDE_PLUGIN_ROOT}.
    return {"mcpServers": {NAME: {"command": "python3", "args": [f"${{CLAUDE_PLUGIN_ROOT}}/{MCP_SERVER}", *MCP_ARGS]}}}


def copilot_plugin() -> dict:
    return {**_plugin_metadata(), "hooks": "hooks/copilot-hooks.json"}


def cursor_plugin() -> dict:
    return {**_plugin_metadata(), "skills": "./skills/", "hooks": "./hooks/cursor-hooks.json",
            "mcpServers": "./.mcp.json"}


def agent_plugin() -> dict:
    return {"$schema": AGENT_PLUGINS_SCHEMA, **_plugin_metadata()}


def agent_plugin_mcp() -> dict:
    return {"$schema": AGENT_PLUGINS_MCP_SCHEMA, "mcpServers": {
        NAME: {"type": "stdio", "command": "python3", "args": [f"${{PLUGIN_ROOT}}/{ENGINE}/{MCP_SERVER}", *MCP_ARGS]}}}


def gemini_extension() -> dict:
    return {"name": NAME, "version": VERSION, "description": DESCRIPTION, "mcpServers": {NAME: {
        "command": "python3", "args": [f"${{extensionPath}}${{/}}{ENGINE}${{/}}mcp${{/}}spec_master_mcp.py", *MCP_ARGS],
        "cwd": "${workspacePath}"}}}


def antigravity_mcp() -> dict:
    # No cwd: Antigravity starts a plugin's MCP server in the plugin's own directory.
    return {"mcpServers": {NAME: {"command": "python3", "args": [f"{ENGINE}/{MCP_SERVER}", *MCP_ARGS]}}}


def _marketplace_entry() -> dict:
    return {"name": NAME, "source": f"./{ENGINE}", "description": DESCRIPTION, "version": VERSION,
            "category": CATEGORY, "tags": KEYWORDS}


def claude_marketplace() -> dict:
    return {"name": NAME, "description": "The Spec Master harness for spec-driven development.",
            "owner": AUTHOR, "plugins": [_marketplace_entry()]}


def cursor_marketplace() -> dict:
    return {"name": NAME, "owner": AUTHOR, "plugins": [{"name": NAME, "source": f"./{ENGINE}",
                                                        "description": DESCRIPTION}]}


# --------------------------------------------------------------------------- the file set

def render() -> dict[str, str]:
    """Repository-relative path -> exact file content."""
    files = {
        ".claude-plugin/marketplace.json": _json(claude_marketplace()),
        ".cursor-plugin/marketplace.json": _json(cursor_marketplace()),
        "plugin.json": _json(agent_plugin()),
        "mcp.json": _json(agent_plugin_mcp()),
        "gemini-extension.json": _json(gemini_extension()),
        "hooks/hooks.json": _json(gemini_hooks()),
        "hooks.json": _json(antigravity_hooks()),
        "mcp_config.json": _json(antigravity_mcp()),
        f"{ENGINE}/.claude-plugin/plugin.json": _json(claude_plugin()),
        f"{ENGINE}/.mcp.json": _json(claude_mcp()),
        f"{ENGINE}/hooks/hooks.json": _json(claude_style_hooks("claude")),
        f"{ENGINE}/.codex-plugin/plugin.json": _json(codex_plugin()),
        f"{ENGINE}/.codex-mcp.json": _json(codex_mcp()),
        f"{ENGINE}/hooks/codex-hooks.json": _json(claude_style_hooks("codex")),
        f"{ENGINE}/.github/plugin/plugin.json": _json(copilot_plugin()),
        f"{ENGINE}/hooks/copilot-hooks.json": _json(copilot_hooks()),
        f"{ENGINE}/.cursor-plugin/plugin.json": _json(cursor_plugin()),
        f"{ENGINE}/hooks/cursor-hooks.json": _json(cursor_hooks()),
    }
    for name in SKILLS:
        files[f"skills/{name}/SKILL.md"] = skill(name)
        files[f"{ENGINE}/skills/{name}/SKILL.md"] = skill(name)
    return files


def check(root: str | os.PathLike) -> list[str]:
    """Paths whose committed content differs from `render()` (or is missing)."""
    drifted = []
    for relative, content in render().items():
        path = Path(root, relative)
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            drifted.append(relative)
    return drifted


def generate(root: str | os.PathLike) -> list[str]:
    written = []
    for relative, content in render().items():
        path = Path(root, relative)
        if path.is_file() and path.read_text(encoding="utf-8") == content:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(relative)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="packaging", description=__doc__.split("\n\n")[0])
    parser.add_argument("action", choices=["generate", "check"])
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[2]),
                        help="repository root (default: this engine's repository)")
    args = parser.parse_args(argv)
    if args.action == "generate":
        print(json.dumps({"version": VERSION, "written": generate(args.root)}, indent=2))
        return 0
    drifted = check(args.root)
    print(json.dumps({"version": VERSION, "ok": not drifted, "drifted": drifted}, indent=2))
    return 0 if not drifted else 1


if __name__ == "__main__":
    sys.exit(main())
