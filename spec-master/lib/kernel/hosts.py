"""Host adapters for hookd (import-light: this runs on every tool call).

Each agent host sends its own hook payload and expects its own reply. hookd
decides on one canonical shape — Claude Code's: `tool_name` "Bash" for shell
commands, "Write" for file writes, `tool_input.command` / `.file_path` (and
`.file_paths` when one call touches several files) — and these adapters
translate in and out.

- claude, qwen: Claude Code's protocol (Qwen Code speaks it natively).
- codex: Claude's shape, but files change through `apply_patch` (the paths
  are inside the patch) and a PreToolUse "ask" is not supported, so asks are
  left to Codex's own approval policy; a Stop hook must always print JSON.
- gemini: BeforeTool / AfterTool / AfterAgent / SessionStart, with
  `{"decision": "deny"|"ask", "reason"}` and `additionalContext`, and its own
  tool names (`run_shell_command`, `write_file`, `replace`).
- copilot: Copilot CLI's camelCase events (preToolUse, postToolUse,
  agentStop, sessionStart) with `{toolName, toolArgs}` (toolArgs may be a
  JSON string), replying with exactly one JSON object: top-level
  `permissionDecision`, `additionalContext`, or `{"decision": "block"}`.
- cursor: beforeShellExecution / preToolUse / postToolUse / stop /
  sessionStart, replying `{"permission": ...}`, `additional_context` and
  `followup_message`; a hook that prints nothing (or invalid JSON) blocks the
  action, so every reply is JSON.
- kiro: blocks through exit code 2 with the reason on stderr; a Stop hook
  keeps the agent going with `{"decision": "block"}`; there is no "ask".
- antigravity: camelCase payloads with `toolCall: {name, args}` (PascalCase
  args: `CommandLine`, `TargetFile`) and `workspacePaths`, since hooks run
  from the plugin's directory. Replies are parsed as protojson, so they carry
  only known fields: PreToolUse `{"decision": "deny"|"ask", "reason"}` or
  `{}` (an "allow" would skip the user's own approval), Stop
  `{"decision": "continue", "reason"}` or `{}`.

The host comes from `--host` on the hook command; without it, the payload
identifies Gemini, Cursor and Antigravity, and anything else is read as
Claude.
"""
from __future__ import annotations

import json
import re

HOSTS = ("claude", "qwen", "codex", "copilot", "gemini", "cursor", "kiro", "antigravity")
CANONICAL_SHELL = "Bash"
CANONICAL_WRITE = "Write"

# Compared case-insensitively. Claude's own write tools keep their names.
SHELL_TOOLS = {"bash", "run_shell_command", "shell", "execute_bash", "run_command"}
WRITE_TOOLS = {"edit", "write", "multiedit", "notebookedit", "write_file", "replace", "delete",
               "apply_patch", "fs_write", "str_replace", "delete_file", "create", "str_replace_editor",
               "write_to_file", "replace_file_content", "multi_replace_file_content"}
CLAUDE_WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
PATH_KEYS = ("file_path", "notebook_path", "absolute_path", "path", "target_file", "filePath", "TargetFile")
GEMINI_EVENTS = {"BeforeTool", "AfterTool", "AfterAgent", "BeforeAgent", "BeforeModel", "AfterModel",
                 "BeforeToolSelection", "PreCompress", "SessionEnd", "Notification"}
CURSOR_EVENTS = {"beforeShellExecution", "afterShellExecution", "beforeMCPExecution", "afterMCPExecution",
                 "beforeReadFile", "afterFileEdit", "beforeSubmitPrompt", "afterAgentResponse",
                 "afterAgentThought", "postToolUseFailure"}
_PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$|^\*\*\* Move to: (.+?)\s*$", re.MULTILINE)


def detect(payload: dict, requested: str | None = None) -> str:
    if requested in HOSTS:
        return requested
    event = payload.get("hook_event_name")
    if event in GEMINI_EVENTS:
        return "gemini"
    if event in CURSOR_EVENTS or "cursor_version" in payload:
        return "cursor"
    if "conversationId" in payload or "toolCall" in payload:
        return "antigravity"
    return "claude"


def patch_paths(patch: str) -> list[str]:
    """Files an `apply_patch` envelope adds, updates, deletes or moves to."""
    return [add or move for add, move in _PATCH_FILE_RE.findall(patch or "")]


def _camel_to_snake(payload: dict) -> dict:
    """Copilot's camelCase payload (`toolName`, `toolArgs`, `sessionId`) and
    Antigravity's (`toolCall: {name, args}`, `conversationId`, `workspacePaths`)."""
    call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else {}
    if not ({"toolName", "sessionId", "conversationId", "workspacePaths"} & payload.keys() or call):
        return payload
    args = payload.get("toolArgs", call.get("args"))
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            args = {"command": args}
    converted = dict(payload)
    converted.setdefault("tool_name", payload.get("toolName") or call.get("name"))
    converted.setdefault("tool_input", args if isinstance(args, dict) else {})
    converted.setdefault("session_id", payload.get("sessionId") or payload.get("conversationId"))
    if isinstance(payload.get("workspacePaths"), list):
        converted.setdefault("workspace_roots", payload["workspacePaths"])
    return converted


def normalize(payload: dict) -> dict:
    """The payload with the tool and its input in the canonical shape. The
    host's own tool name is kept as `host_tool_name` for the log."""
    payload = _camel_to_snake(payload)
    tool = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input")
    tool_input = dict(tool_input) if isinstance(tool_input, dict) else {}
    if not tool and payload.get("hook_event_name") == "beforeShellExecution":  # Cursor: no tool name
        tool, tool_input = "Shell", {"command": payload.get("command") or ""}
    lowered = tool.lower()
    if lowered in SHELL_TOOLS:
        canonical = CANONICAL_SHELL
    elif tool in CLAUDE_WRITE_TOOLS:
        canonical = tool
    elif lowered in WRITE_TOOLS:
        canonical = CANONICAL_WRITE
    else:
        return payload
    if canonical == CANONICAL_SHELL:
        if not tool_input.get("command") and isinstance(tool_input.get("CommandLine"), str):  # Antigravity
            tool_input["command"] = tool_input["CommandLine"]
    else:
        if lowered == "apply_patch":
            files = patch_paths(str(tool_input.get("command") or tool_input.get("patch") or tool_input.get("input") or ""))
            if files:
                tool_input["file_paths"] = files
                tool_input.setdefault("file_path", files[0])
        elif not tool_input.get("file_path"):
            for key in PATH_KEYS:
                if isinstance(tool_input.get(key), str) and tool_input[key]:
                    tool_input["file_path"] = tool_input[key]
                    break
    return {**payload, "tool_name": canonical, "tool_input": tool_input, "host_tool_name": tool}


def _claude(event: str, decision: str, reason: str) -> tuple[int, str, str]:
    if event == "pre-tool-use" and decision in ("deny", "ask"):
        return 0, json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                     "permissionDecision": decision,
                                                     "permissionDecisionReason": reason}}), ""
    if event in ("post-tool-use", "stop") and decision in ("block", "escalate"):
        return 0, json.dumps({"decision": "block", "reason": reason}), ""
    return 0, "", ""


def render(host: str, event: str, verdict: dict, enforce: bool) -> tuple[int, str, str]:
    """(exit code, stdout, stderr) in the host's hook protocol. Audit mode
    only ever adds context; it never blocks or asks."""
    decision = verdict["decision"] if enforce else "allow"
    reason = f"[Spec Master] {verdict['reason']}"
    context = verdict.get("context") if event == "session-start" else None

    if host == "cursor":  # every reply must be JSON: an empty one blocks the action
        if event == "pre-tool-use":
            permission = decision if decision in ("deny", "ask") else "allow"
            reply = {"permission": permission}
            if permission != "allow":
                reply.update(user_message=reason, agent_message=reason)
            return 0, json.dumps(reply), ""
        if event == "post-tool-use" and decision in ("block", "escalate"):
            return 0, json.dumps({"additional_context": reason}), ""
        if event == "stop" and decision == "block":
            return 0, json.dumps({"followup_message": reason}), ""
        if context:
            return 0, json.dumps({"additional_context": context}), ""
        return 0, "{}", ""

    if host == "antigravity":  # protojson: only known fields, and never "allow"
        if event == "pre-tool-use" and decision in ("deny", "ask"):
            return 0, json.dumps({"decision": decision, "reason": reason}), ""
        if event == "stop" and decision == "block":
            return 0, json.dumps({"decision": "continue", "reason": reason}), ""
        return 0, "{}", ""

    if host == "copilot":  # exactly one JSON object on stdout, always
        if event == "pre-tool-use" and decision in ("deny", "ask"):
            return 0, json.dumps({"permissionDecision": decision, "permissionDecisionReason": reason}), ""
        if event == "post-tool-use" and decision in ("block", "escalate"):
            return 0, json.dumps({"additionalContext": reason}), ""
        if event == "stop" and decision == "block":
            return 0, json.dumps({"decision": "block", "reason": reason}), ""
        if context:
            return 0, json.dumps({"additionalContext": context}), ""
        return 0, "{}", ""

    if context:
        if host == "kiro":
            return 0, context, ""
        return 0, json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}), ""

    if host == "gemini":
        if event == "pre-tool-use" and decision in ("deny", "ask"):
            return 0, json.dumps({"decision": decision, "reason": reason}), ""
        if event == "post-tool-use" and decision in ("block", "escalate"):
            return 0, json.dumps({"hookSpecificOutput": {"hookEventName": "AfterTool",
                                                         "additionalContext": reason}}), ""
        if event == "stop" and decision == "block":  # AfterAgent: the turn is retried with this prompt
            return 0, json.dumps({"decision": "deny", "reason": reason}), ""
        return 0, "", ""

    if host == "kiro":
        if event == "pre-tool-use" and decision == "deny":
            return 2, "", reason
        if event == "post-tool-use" and decision in ("block", "escalate"):
            return 0, reason, ""
        if event == "stop" and decision == "block":
            return 0, json.dumps({"decision": "block", "reason": reason}), ""
        return 0, "", ""  # no "ask" in Kiro hooks: its permissions.yaml decides

    if host == "codex":
        if event == "pre-tool-use" and decision == "ask":
            return 0, "", ""  # not supported by Codex: its own approval policy decides
        code, out, err = _claude(event, decision, reason)
        if event == "stop" and not out:
            out = "{}"  # a Stop hook that exits 0 must print JSON
        return code, out, err

    return _claude(event, decision, reason)
