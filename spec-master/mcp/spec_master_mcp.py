#!/usr/bin/env python3
"""Spec Master MCP server (stdio transport, stdlib only).

Exposes every `spec-master/lib/cli.py` command as an MCP tool, and the two
entrypoints as MCP prompts (`spec-master` for the full cycle, `spec-master-lane`
for the lane flow), which most hosts offer as slash commands. The prompt text
comes from `templates/entrypoints/` with this engine's absolute path filled
in, so the same package works wherever a host installs it. The tool list
is built at startup by introspecting `cli.build_parser()`, so CLI groups added
later appear automatically:

    state show            -> tool `state_show`
    git-strategy plan     -> tool `git_strategy_plan`
    <group> (no actions)  -> tool `<group>`

Each option/positional of the leaf parser becomes an `inputSchema` property
(named after its argparse `dest`). `tools/call` rebuilds the argv from the
arguments and runs the CLI in a subprocess (argv list, never a shell) rooted
at the fixed project root, so the server shares the exact code path, JSON
output and exit codes of the CLI.

Transport: newline-delimited JSON-RPC 2.0 on stdin/stdout, logs on stderr.
Batches (JSON arrays) are processed per JSON-RPC 2.0 (one array reply with
the non-notification responses; an empty array is -32600).

    python3 spec-master/mcp/spec_master_mcp.py [--project PATH] [--tools all|entrypoint] [--list-tools]

Project root: --project, then SPEC_MASTER_PROJECT, then the host's own
variable (CLAUDE_PROJECT_DIR, CURSOR_PROJECT_DIR, GEMINI_PROJECT_DIR), then
the cwd at startup. Plugin hosts often start servers inside the plugin
directory, so when the client supports MCP roots the server asks for them
after `initialized` and adopts the first workspace folder. A server left
pointing at its own install directory refuses every tool that touches the
project instead of writing Spec Master state into the plugin. The plugins
start it with `--tools entrypoint`: only `harness_entrypoint` is listed.

Env: SPEC_MASTER_MCP_TIMEOUT (seconds per tool call, default 120).
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import subprocess
import sys
import traceback
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

SERVER_NAME = "spec-master"
SERVER_TITLE = "Spec Master"
SERVER_VERSION = "0.3.0"
LATEST_PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_TIMEOUT = 120.0
STDERR_TAIL_CHARS = 4000

PACKAGE_DIR = Path(__file__).resolve().parent.parent  # spec-master/
LIB_DIR = PACKAGE_DIR / "lib"
ENTRYPOINTS_DIR = PACKAGE_DIR / "templates" / "entrypoints"

# name -> (flow, title, description, argument name, argument description, argument required)
PROMPTS = {
    "spec-master": ("full-cycle", "Spec Master: full cycle",
                    "Run the whole spec-driven cycle (constitution to validate) from a context file.",
                    "context", "Context file (e.g. CLAUDE.md); leave empty for the guided discovery", False),
    "spec-master-lane": ("lane", "Spec Master: lane flow",
                         "Triage a change into patch, standard or critical; a patch closes only on evidence.",
                         "request", "The change, in the user's words (optionally starting with a lane)", True),
}
CLI_PATH = LIB_DIR / "cli.py"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Conservative readOnlyHint allowlist. An action name listed here must never
# write in any group; anything that *may* write (render/report --output,
# health, snapshot, init, transition, ...) is deliberately absent.
READ_ONLY_ACTIONS = frozenset({
    "show", "list", "get", "search", "validate", "stats", "neighbors", "stale",
    "query", "detect", "scan", "order", "diff", "compare", "compute", "firings",
    "routes", "decisions", "roles", "intake", "adopt", "summarize", "check",
    "for-role", "route", "maps", "drift", "waves", "conflicts", "estimate",
    "preflight", "contract",
})
# Verified pure tools whose action name is too generic for the allowlist
# (e.g. `worktree plan` creates a git worktree, `git-strategy plan` does not).
READ_ONLY_TOOLS = frozenset({
    "git_strategy_plan", "team_workstreams",
    "worktree_aggregate", "workstreams_aggregate", "tracker_orchestrate",
    "evals_run", "budget_file", "dashboard_model",
    "risk_profiles", "risk_work_packages",
    "telemetry_locate", "baseline_plan", "lane_triage", "step_next",
})

_MISSING = object()
_TRUE_STRINGS = {"true", "1", "yes", "on"}
_FALSE_STRINGS = {"false", "0", "no", "off"}


def _entrypoint_text(flow: str, argument: str) -> str:
    """Same renderer as `cli.py harness entrypoint` (imported lazily: the
    server must start even when the CLI cannot be loaded)."""
    if str(LIB_DIR) not in sys.path:
        sys.path.insert(0, str(LIB_DIR))
    import cli  # noqa: PLC0415
    return cli.entrypoint_text(flow, argument)


def log(message: str) -> None:
    print(f"[spec-master-mcp] {message}", file=sys.stderr, flush=True)


class ArgumentError(ValueError):
    """Tool arguments that cannot be turned into a valid CLI argv."""


# --------------------------------------------------------------------------
# Introspection: argparse -> MCP tools
# --------------------------------------------------------------------------

@dataclass
class Param:
    name: str
    level: int            # 0 = root parser, i = parser reached by tokens[:i]
    kind: str             # flag|boolopt|count|option|multi|append|positional|positional_multi
    schema: dict
    required: bool = False
    flag: str | None = None
    neg_flag: str | None = None
    value_type: str = "string"
    choices: list | None = None


@dataclass
class ToolSpec:
    name: str
    tokens: list[str]
    description: str
    params: list[Param] = field(default_factory=list)
    read_only: bool = False

    @property
    def command(self) -> str:
        return " ".join(self.tokens)

    def input_schema(self) -> dict:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {p.name: p.schema for p in self.params},
            "additionalProperties": False,
        }
        required = [p.name for p in self.params if p.required]
        if required:
            schema["required"] = required
        return schema

    def to_mcp(self) -> dict:
        return {
            "name": self.name,
            "title": f"spec-master {self.command}",
            "description": self.description,
            "inputSchema": self.input_schema(),
            "annotations": {"readOnlyHint": self.read_only},
        }


def _tool_name(tokens: list[str]) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", "_".join(tokens).replace("-", "_"))[:128]


def _subparsers_action(parser: argparse.ArgumentParser):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _clean(text: str | None) -> str | None:
    if not text or text == argparse.SUPPRESS:
        return None
    return " ".join(str(text).split()) or None


def _expand_help(action: argparse.Action, parser: argparse.ArgumentParser) -> str | None:
    text = action.help
    if not text or text == argparse.SUPPRESS:
        return None
    if "%" in text:  # same expansion argparse's HelpFormatter does
        params = {k: v for k, v in vars(action).items() if v is not argparse.SUPPRESS}
        params["prog"] = parser.prog
        if params.get("choices") is not None:
            params["choices"] = ", ".join(str(c) for c in params["choices"])
        try:
            text = text % params
        except (KeyError, TypeError, ValueError):
            pass
    return _clean(text)


def _value_type(action: argparse.Action) -> str:
    if action.type is int:
        return "integer"
    if action.type is float:
        return "number"
    choices = action.choices
    if action.type is None and choices is not None:
        values = list(choices)
        if values and all(isinstance(c, int) and not isinstance(c, bool) for c in values):
            return "integer"
    return "string"


def _json_default(value):
    if value is None or value is argparse.SUPPRESS:
        return _MISSING
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)) and all(isinstance(v, (bool, int, float, str)) for v in value):
        return list(value)
    return _MISSING


def _enum(action: argparse.Action) -> list | None:
    if action.choices is None:
        return None
    try:
        values = list(action.choices)
    except TypeError:
        return None
    if not values or len(values) > 200:
        return None
    if not all(isinstance(v, (str, int, float)) and not isinstance(v, bool) for v in values):
        return None
    return values


def _preferred_flag(action: argparse.Action) -> str:
    for opt in action.option_strings:
        if opt.startswith("--"):
            return opt
    return action.option_strings[0]


def _flag_name(flag: str) -> str:
    return flag.lstrip("-+").replace("-", "_")


def _is_multi(nargs) -> bool:
    return nargs in ("*", "+", argparse.REMAINDER) or (isinstance(nargs, int) and not isinstance(nargs, bool))


def _param_for(action: argparse.Action, parser: argparse.ArgumentParser, level: int) -> Param | None:
    """Map one argparse action to a Param (without resolving name collisions)."""
    if isinstance(action, (argparse._HelpAction, argparse._VersionAction, argparse._SubParsersAction)):
        return None
    if action.dest == argparse.SUPPRESS:
        return None
    description = _expand_help(action, parser)
    vtype = _value_type(action)
    enum = _enum(action)
    base: dict[str, Any] = {}
    if description:
        base["description"] = description

    def scalar_schema() -> dict:
        s = {"type": vtype}
        if enum is not None:
            s["enum"] = enum
        return s

    if not action.option_strings:  # positional
        multi = _is_multi(action.nargs)
        schema = dict(base)
        if multi:
            schema.update({"type": "array", "items": scalar_schema()})
            if action.nargs == "+":
                schema["minItems"] = 1
            elif isinstance(action.nargs, int):
                schema["minItems"] = schema["maxItems"] = action.nargs
        else:
            schema.update(scalar_schema())
        default = _json_default(action.default)
        if default is not _MISSING and action.nargs in ("?", "*"):
            schema["default"] = default
        required = action.nargs not in ("?", "*", argparse.REMAINDER)
        return Param(name=action.dest, level=level, kind="positional_multi" if multi else "positional",
                     schema=schema, required=required, value_type=vtype, choices=enum)

    flag = _preferred_flag(action)
    if hasattr(argparse, "BooleanOptionalAction") and isinstance(action, argparse.BooleanOptionalAction):
        positive = next((o for o in action.option_strings if not o.startswith("--no-")), flag)
        negative = next((o for o in action.option_strings if o.startswith("--no-")), None)
        schema = dict(base, type="boolean")
        default = _json_default(action.default)
        if isinstance(default, bool):
            schema["default"] = default
        return Param(name=action.dest, level=level, kind="boolopt", schema=schema,
                     required=bool(action.required), flag=positive, neg_flag=negative, value_type="boolean")
    if isinstance(action, argparse._StoreTrueAction):
        return Param(name=action.dest, level=level, kind="flag", flag=flag, value_type="boolean",
                     schema=dict(base, type="boolean", default=False))
    if isinstance(action, (argparse._StoreFalseAction, argparse._StoreConstAction, argparse._AppendConstAction)):
        # Name after the flag (`--no-color` -> `no_color`): true means "pass the flag".
        return Param(name=_flag_name(flag), level=level, kind="flag", flag=flag, value_type="boolean",
                     schema=dict(base, type="boolean", default=False))
    if isinstance(action, argparse._CountAction):
        return Param(name=action.dest, level=level, kind="count", flag=flag, value_type="integer",
                     schema=dict(base, type="integer", minimum=0))
    if isinstance(action, argparse._AppendAction):  # also covers `extend`
        schema = dict(base, type="array", items=scalar_schema())
        return Param(name=action.dest, level=level, kind="append", flag=flag, schema=schema,
                     required=bool(action.required), value_type=vtype, choices=enum)
    if action.nargs == 0:  # custom zero-argument action
        return Param(name=_flag_name(flag), level=level, kind="flag", flag=flag, value_type="boolean",
                     schema=dict(base, type="boolean", default=False))
    if _is_multi(action.nargs):
        schema = dict(base, type="array", items=scalar_schema())
        if action.nargs == "+":
            schema["minItems"] = 1
        elif isinstance(action.nargs, int):
            schema["minItems"] = schema["maxItems"] = action.nargs
        default = _json_default(action.default)
        if isinstance(default, list):
            schema["default"] = default
        return Param(name=action.dest, level=level, kind="multi", flag=flag, schema=schema,
                     required=bool(action.required), value_type=vtype, choices=enum)
    schema = dict(base)
    schema.update(scalar_schema())
    default = _json_default(action.default)
    if default is not _MISSING and not isinstance(default, list):
        schema["default"] = default
    return Param(name=action.dest, level=level, kind="option", flag=flag, schema=schema,
                 required=bool(action.required), value_type=vtype, choices=enum)


def _describe(tokens: list[str], helps: list[str | None]) -> str:
    command = " ".join(tokens)
    leaf = helps[-1] if helps else None
    text = f"{leaf} (Spec Master CLI: `{command}`)." if leaf else f"Spec Master CLI: {command}."
    group_help = helps[0] if len(helps) > 1 else None
    if group_help:
        text += f" Group `{tokens[0]}`: {group_help}."
    return text


def build_tools(parser: argparse.ArgumentParser) -> list[ToolSpec]:
    """Walk nested argparse subparsers into one ToolSpec per leaf command."""
    tools: list[ToolSpec] = []
    names: set[str] = set()

    def emit(tokens, levels, helps):
        name = _tool_name(tokens)
        if name in names:
            log(f"skipping `{' '.join(tokens)}`: tool name {name!r} already taken")
            return
        params: list[Param] = []
        used: set[str] = set()
        for level, (level_parser, actions) in enumerate(levels):
            for action in actions:
                param = _param_for(action, level_parser, level)
                if param is None:
                    continue
                if param.name in used and param.flag:
                    param.name = _flag_name(param.flag)
                if param.name in used:
                    log(f"skipping argument {param.name!r} of `{' '.join(tokens)}`: name collision")
                    continue
                used.add(param.name)
                params.append(param)
        names.add(name)
        read_only = tokens[-1] in READ_ONLY_ACTIONS or name in READ_ONLY_TOOLS
        tools.append(ToolSpec(name=name, tokens=list(tokens), description=_describe(tokens, helps),
                              params=params, read_only=read_only))

    def walk(p, tokens, levels, helps):
        sub = _subparsers_action(p)
        levels = levels + [(p, [a for a in p._actions if not isinstance(a, argparse._SubParsersAction)])]
        if sub is None:
            if tokens:
                emit(tokens, levels, helps)
            return
        choice_help = {c.dest: _clean(c.help) for c in sub._choices_actions}
        seen: set[int] = set()
        for choice, child in sub.choices.items():
            if id(child) in seen:  # alias of an already-walked parser
                continue
            seen.add(id(child))
            walk(child, tokens + [choice], levels, helps + [choice_help.get(choice) or _clean(child.description)])

    walk(parser, [], [], [])
    return tools


def load_cli_parser() -> argparse.ArgumentParser:
    """Import spec-master/lib/cli.py in-process (stdout guarded) and build its parser."""
    if str(LIB_DIR) not in sys.path:
        sys.path.insert(0, str(LIB_DIR))
    with contextlib.redirect_stdout(sys.stderr):
        import cli  # noqa: WPS433 (deferred on purpose: the CLI may be mid-edit)
        return cli.build_parser()


# --------------------------------------------------------------------------
# Arguments -> argv
# --------------------------------------------------------------------------

def _to_string(param: Param, value) -> str:
    if isinstance(value, bool):
        raise ArgumentError(f"argument {param.name!r}: expected a string, got a boolean")
    if isinstance(value, str):
        text = value
    elif isinstance(value, (int, float)):
        text = str(value)
    elif isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)  # e.g. --feature-json / --payload-json
    else:
        raise ArgumentError(f"argument {param.name!r}: unsupported value {value!r}")
    return text


def _integer(name: str, value) -> int:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    elif isinstance(value, str):
        try:
            value = int(value.strip())
        except ValueError:
            raise ArgumentError(f"argument {name!r}: expected an integer, got {value!r}") from None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ArgumentError(f"argument {name!r}: expected an integer, got {value!r}")
    return value


def _scalar(param: Param, value) -> str:
    if param.value_type == "integer":
        text = str(_integer(param.name, value))
    elif param.value_type == "number":
        if isinstance(value, bool):
            raise ArgumentError(f"argument {param.name!r}: expected a number, got a boolean")
        try:
            text = repr(float(value)) if isinstance(value, str) else str(value + 0)
        except (TypeError, ValueError):
            raise ArgumentError(f"argument {param.name!r}: expected a number, got {value!r}") from None
    else:
        text = _to_string(param, value)
    if "\x00" in text:
        raise ArgumentError(f"argument {param.name!r}: NUL bytes are not allowed")
    if param.choices is not None and text not in {str(c) for c in param.choices}:
        allowed = ", ".join(str(c) for c in param.choices)
        raise ArgumentError(f"argument {param.name!r}: {value!r} is not one of: {allowed}")
    return text


def _boolean(param: Param, value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in _TRUE_STRINGS | _FALSE_STRINGS:
        return value.strip().lower() in _TRUE_STRINGS
    raise ArgumentError(f"argument {param.name!r}: expected a boolean, got {value!r}")


def _items(param: Param, value) -> list[str]:
    values = value if isinstance(value, list) else [value]
    items = [_scalar(param, v) for v in values if v is not None]
    min_items = param.schema.get("minItems")
    max_items = param.schema.get("maxItems")
    if min_items is not None and len(items) < min_items:
        raise ArgumentError(f"argument {param.name!r}: expected at least {min_items} item(s)")
    if max_items is not None and len(items) > max_items:
        raise ArgumentError(f"argument {param.name!r}: expected at most {max_items} item(s)")
    return items


def _option(flag: str, value: str) -> list[str]:
    # `--flag=value` keeps values that start with "-" from being read as options.
    return [f"{flag}={value}"] if flag.startswith("--") else [flag, value]


def build_argv(tool: ToolSpec, arguments: dict | None) -> list[str]:
    """Turn MCP tool arguments into the CLI argv (tokens interleaved with each level's args)."""
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ArgumentError("arguments must be a JSON object")
    known = {p.name for p in tool.params}
    unknown = sorted(set(arguments) - known)
    if unknown:
        expected = ", ".join(sorted(known)) or "(none)"
        raise ArgumentError(f"unknown argument(s) for {tool.name}: {', '.join(unknown)}; expected: {expected}")
    missing = [p.name for p in tool.params if p.required and arguments.get(p.name) is None]
    if missing:
        raise ArgumentError(f"missing required argument(s) for {tool.name}: {', '.join(missing)}")

    depth = len(tool.tokens)
    options: list[list[str]] = [[] for _ in range(depth + 1)]
    positionals: list[list[str]] = [[] for _ in range(depth + 1)]
    for p in tool.params:
        value = arguments.get(p.name)
        if value is None:
            continue
        opts, pos = options[p.level], positionals[p.level]
        if p.kind == "flag":
            if _boolean(p, value):
                opts.append(p.flag)
        elif p.kind == "boolopt":
            enabled = _boolean(p, value)
            if enabled:
                opts.append(p.flag)
            elif p.neg_flag:
                opts.append(p.neg_flag)
        elif p.kind == "count":
            times = _integer(p.name, value)
            if times < 0:
                raise ArgumentError(f"argument {p.name!r}: must be >= 0")
            opts.extend([p.flag] * times)
        elif p.kind == "append":
            for item in _items(p, value):
                opts.extend(_option(p.flag, item))
        elif p.kind == "multi":
            items = _items(p, value)
            if items:
                opts.append(p.flag)
                opts.extend(items)
        elif p.kind == "option":
            opts.extend(_option(p.flag, _scalar(p, value)))
        elif p.kind == "positional":
            pos.append(_scalar(p, value))
        elif p.kind == "positional_multi":
            pos.extend(_items(p, value))

    argv: list[str] = []
    for level in range(depth + 1):
        argv.extend(options[level])
        if positionals[level]:
            if level == depth and any(v.startswith("-") for v in positionals[level]):
                argv.append("--")
            argv.extend(positionals[level])
        if level < depth:
            argv.append(tool.tokens[level])
    return argv


# --------------------------------------------------------------------------
# Server
# --------------------------------------------------------------------------

def _error(msg_id, code: int, message: str, data=None) -> dict:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": msg_id, "error": err}


def _result(msg_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error_result(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": True}


def _valid_id(value) -> bool:
    return isinstance(value, (str, int)) and not isinstance(value, bool)


def _timeout_from_env() -> float:
    raw = os.environ.get("SPEC_MASTER_MCP_TIMEOUT")
    if not raw:
        return DEFAULT_TIMEOUT
    try:
        value = float(raw)
        if value > 0:
            return value
    except ValueError:
        pass
    log(f"ignoring invalid SPEC_MASTER_MCP_TIMEOUT={raw!r}; using {DEFAULT_TIMEOUT:g}s")
    return DEFAULT_TIMEOUT


PROJECT_ENV_VARS = ("SPEC_MASTER_PROJECT", "CLAUDE_PROJECT_DIR", "CURSOR_PROJECT_DIR", "GEMINI_PROJECT_DIR")
# Tools that never touch the project, so they work before the project is known.
PROJECT_FREE_TOOLS = frozenset({"harness_entrypoint"})
ROOTS_REQUEST_PREFIX = "spec-master-roots-"


def _initial_project_root(explicit) -> tuple[str, str]:
    if explicit:
        return str(Path(explicit).expanduser().resolve()), "--project"
    for name in PROJECT_ENV_VARS:
        value = os.environ.get(name)
        if value and Path(value).expanduser().is_dir():
            return str(Path(value).expanduser().resolve()), name
    return str(Path(os.getcwd()).resolve()), "cwd"


def looks_like_install_dir(path: str | os.PathLike) -> bool:
    """True when `path` is where a host installed this engine rather than a
    user's project: the engine directory itself, or its parent inside a
    hidden configuration directory (~/.kiro/..., ~/.codex/..., ...)."""
    resolved = Path(path).resolve()
    if resolved == PACKAGE_DIR:
        return True
    return resolved == PACKAGE_DIR.parent and any(part.startswith(".") for part in resolved.parts[1:])


def _path_from_uri(uri: str) -> str | None:
    parsed = urllib.parse.urlparse(uri or "")
    if parsed.scheme != "file":
        return None
    path = urllib.parse.unquote(parsed.path)
    if os.name == "nt" and re.match(r"^/[A-Za-z]:", path):
        path = path[1:]
    return path if Path(path).is_dir() else None


# `entrypoint` is what the plugins start: every tool schema a host loads costs
# context in each session (all of them: ~49 KB), and the skills need only this one.
TOOLSETS = {"all": None, "entrypoint": frozenset({"harness_entrypoint"})}


class Server:
    def __init__(self, project_root: str | os.PathLike | None = None, timeout: float | None = None,
                 parser_factory: Callable[[], argparse.ArgumentParser] = load_cli_parser,
                 toolset: str = "all"):
        self.toolset = toolset
        self.project_root, self.project_source = _initial_project_root(project_root)
        self.client_supports_roots = False
        self.outbox: list[dict] = []
        self._roots_requests = 0
        self.timeout = timeout if timeout is not None else _timeout_from_env()
        self.load_error: str | None = None
        try:
            self.tools = build_tools(parser_factory())
        except (Exception, SystemExit) as exc:  # noqa: BLE001 - the server must still start
            self.tools = []
            self.load_error = f"{type(exc).__name__}: {exc}"
            log(f"could not load the Spec Master CLI parser: {self.load_error}")
            log(traceback.format_exc())
        if TOOLSETS[toolset] is not None:
            self.tools = [t for t in self.tools if t.name in TOOLSETS[toolset]]
        self.tools_by_name = {t.name: t for t in self.tools}

    # -- MCP methods ------------------------------------------------------
    def instructions(self) -> str:
        if self.toolset == "entrypoint":
            return ("Spec Master harness for spec-driven development. Call `harness_entrypoint` (flow "
                    "`full-cycle` or `lane`, argument: the user's input) and follow the instructions it "
                    "returns: they carry this engine's paths, and the core runs through its CLI.")
        text = (
            "Spec Master deterministic orchestration core. Each tool runs one "
            "`spec-master/lib/cli.py <group> <action>` command (tool `<group>_<action>`, dashes as "
            f"underscores) in a subprocess rooted at {self.project_root}; relative paths resolve there. "
            "Results carry the CLI's JSON (also as structuredContent) or Markdown text; isError mirrors "
            "a non-zero exit. Tools annotated readOnlyHint=true never write; the others may update "
            ".spec-master/ exactly as the CLI does. Start with `harness_entrypoint` (flow `full-cycle` or "
            "`lane`): it returns the instructions to follow, with this engine's paths."
        )
        if self.load_error:
            text += f" WARNING: the CLI could not be loaded ({self.load_error}); no tools are available."
        return text

    def initialize(self, params: dict) -> dict:
        capabilities = params.get("capabilities")
        self.client_supports_roots = isinstance(capabilities, dict) and "roots" in capabilities
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else LATEST_PROTOCOL_VERSION
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}, "prompts": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "title": SERVER_TITLE, "version": SERVER_VERSION},
            "instructions": self.instructions(),
        }

    def list_tools(self) -> dict:
        return {"tools": [t.to_mcp() for t in self.tools]}

    def list_prompts(self) -> dict:
        return {"prompts": [
            {"name": name, "title": title, "description": description,
             "arguments": [{"name": arg, "description": arg_help, "required": required}]}
            for name, (_template, title, description, arg, arg_help, required) in PROMPTS.items()]}

    def blind_note(self) -> str:
        """When the host started this server in its install directory and
        shared no roots (Codex does this), the agent must use the CLI. With
        the entrypoint toolset the instructions already say so."""
        if self.toolset != "all" or not looks_like_install_dir(self.project_root):
            return ""
        return (f"This MCP server cannot see your project (the host started it in {self.project_root} and "
                f"shared no workspace roots): run every Spec Master command through the CLI, "
                f"`python3 {CLI_PATH.as_posix()} <group> <action>`, from your project root.")

    def get_prompt(self, name: str, arguments) -> dict:
        """The entrypoint text with this engine's path filled in."""
        if name not in PROMPTS:
            raise ArgumentError(f"unknown prompt: {name!r}")
        flow, _title, description, arg, _arg_help, required = PROMPTS[name]
        value = str((arguments or {}).get(arg) or "").strip()
        if required and not value:
            raise ArgumentError(f"prompt {name!r} needs the {arg!r} argument")
        text = _entrypoint_text(flow, value)
        if self.blind_note():
            text = f"{text.rstrip()}\n\n{self.blind_note()}\n"
        return {"description": description,
                "messages": [{"role": "user", "content": {"type": "text", "text": text}}]}

    def request_roots(self) -> None:
        if self.client_supports_roots and self.project_source in ("cwd", "roots"):
            self._roots_requests += 1
            self.outbox.append({"jsonrpc": "2.0", "id": f"{ROOTS_REQUEST_PREFIX}{self._roots_requests}",
                                "method": "roots/list"})

    def receive_roots(self, result) -> None:
        roots = result.get("roots") if isinstance(result, dict) else None
        for root in roots if isinstance(roots, list) else []:
            path = _path_from_uri(root.get("uri") if isinstance(root, dict) else "")
            if path:
                self.project_root, self.project_source = str(Path(path).resolve()), "roots"
                log(f"project root from the client's roots: {self.project_root}")
                return

    def call_tool(self, name: str, arguments) -> dict:
        if self.load_error:
            return _error_result(f"Spec Master CLI could not be loaded: {self.load_error}")
        tool = self.tools_by_name.get(name)
        if tool is None:
            return _error_result(f"unknown tool: {name!r}")
        if name not in PROJECT_FREE_TOOLS and looks_like_install_dir(self.project_root):
            return _error_result(
                f"Spec Master does not know your project directory: the host started this server in "
                f"its install directory ({self.project_root}) and did not share its workspace roots. "
                f"Run the core from your project instead: `python3 {CLI_PATH.as_posix()} <group> <action>` "
                "(call the `harness_entrypoint` tool for the full instructions), or set SPEC_MASTER_PROJECT.")
        try:
            argv = build_argv(tool, arguments)
        except ArgumentError as exc:
            return _error_result(str(exc))
        result = self.run_cli(argv)
        note = self.blind_note()
        if note and not result["isError"]:
            result["content"].append({"type": "text", "text": note})
            if isinstance(result.get("structuredContent"), dict):
                result["structuredContent"]["note"] = note
        return result

    def run_cli(self, argv: list[str]) -> dict:
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(LIB_DIR), env.get("PYTHONPATH")]))
        env["PYTHONIOENCODING"] = "utf-8"
        cmd = [sys.executable, str(CLI_PATH), *argv]
        try:
            proc = subprocess.run(cmd, cwd=self.project_root, env=env, stdin=subprocess.DEVNULL,
                                  capture_output=True, timeout=self.timeout, check=False)
        except subprocess.TimeoutExpired:
            return _error_result(f"`{' '.join(argv)}` timed out after {self.timeout:g}s")
        except OSError as exc:
            return _error_result(f"could not start the Spec Master CLI: {exc}")
        stdout = proc.stdout.decode("utf-8", errors="replace").rstrip()
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        is_error = proc.returncode != 0
        content = [{"type": "text", "text": stdout}] if stdout else []
        if is_error and stderr:
            content.append({"type": "text",
                            "text": f"stderr (exit code {proc.returncode}):\n{stderr[-STDERR_TAIL_CHARS:]}"})
        if not content:
            content.append({"type": "text", "text": f"(no output; exit code {proc.returncode})"})
        result: dict[str, Any] = {"content": content, "isError": is_error}
        try:
            parsed = json.loads(stdout) if stdout else None
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            result["structuredContent"] = parsed
        return result

    # -- JSON-RPC ---------------------------------------------------------
    def handle_line(self, line: str):
        try:
            message = json.loads(line)
        except ValueError as exc:
            return _error(None, PARSE_ERROR, f"Parse error: {exc}")
        return self.handle(message)

    def handle(self, message):
        """One JSON-RPC message (or batch) in, the response (or None for notifications) out."""
        if isinstance(message, list):
            if not message:
                return _error(None, INVALID_REQUEST, "Invalid Request: empty batch")
            responses = [r for r in (self._handle_one(m) for m in message) if r is not None]
            return responses or None
        return self._handle_one(message)

    def _handle_one(self, message):
        if not isinstance(message, dict):
            return _error(None, INVALID_REQUEST, "Invalid Request: expected a JSON object")
        method = message.get("method")
        if method is None and ("result" in message or "error" in message):
            if str(message.get("id", "")).startswith(ROOTS_REQUEST_PREFIX) and "result" in message:
                self.receive_roots(message["result"])
            return None  # a response to one of our requests
        is_request = "id" in message
        msg_id = message.get("id")
        if message.get("jsonrpc") != "2.0" or not isinstance(method, str):
            return _error(msg_id if _valid_id(msg_id) else None, INVALID_REQUEST,
                          "Invalid Request: expected jsonrpc '2.0' and a string method")
        if is_request and not _valid_id(msg_id):
            return _error(None, INVALID_REQUEST, "Invalid Request: id must be a string or an integer")
        params = message.get("params")
        if params is None:
            params = {}
        if not is_request:
            if method in ("notifications/initialized", "notifications/roots/list_changed"):
                self.request_roots()
            return None  # notifications never get a reply
        if not isinstance(params, dict):
            return _error(msg_id, INVALID_PARAMS, "Invalid params: params must be an object")
        try:
            return self._dispatch(msg_id, method, params)
        except Exception as exc:  # noqa: BLE001
            log(traceback.format_exc())
            return _error(msg_id, INTERNAL_ERROR, f"Internal error: {type(exc).__name__}: {exc}")

    def _dispatch(self, msg_id, method: str, params: dict) -> dict:
        if method == "initialize":
            return _result(msg_id, self.initialize(params))
        if method == "ping":
            return _result(msg_id, {})
        if method == "tools/list":
            return _result(msg_id, self.list_tools())
        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments")
            if not isinstance(name, str) or not name:
                return _error(msg_id, INVALID_PARAMS, "Invalid params: tools/call requires a string 'name'")
            if arguments is not None and not isinstance(arguments, dict):
                return _error(msg_id, INVALID_PARAMS, "Invalid params: 'arguments' must be an object")
            return _result(msg_id, self.call_tool(name, arguments))
        if method == "prompts/list":
            return _result(msg_id, self.list_prompts())
        if method == "prompts/get":
            name = params.get("name")
            arguments = params.get("arguments")
            if not isinstance(name, str) or not name:
                return _error(msg_id, INVALID_PARAMS, "Invalid params: prompts/get requires a string 'name'")
            if arguments is not None and not isinstance(arguments, dict):
                return _error(msg_id, INVALID_PARAMS, "Invalid params: 'arguments' must be an object")
            try:
                return _result(msg_id, self.get_prompt(name, arguments))
            except ArgumentError as exc:
                return _error(msg_id, INVALID_PARAMS, f"Invalid params: {exc}")
        return _error(msg_id, METHOD_NOT_FOUND, f"Method not found: {method}")


_default_server: Server | None = None


def handle(message):
    """Module-level convenience: handle one message with a server rooted at SPEC_MASTER_PROJECT/cwd."""
    global _default_server
    if _default_server is None:
        _default_server = Server()
    return _default_server.handle(message)


def serve(server: Server, stdin, stdout) -> None:
    """Read newline-delimited JSON-RPC from `stdin` (bytes), write replies to `stdout` (bytes)."""
    while True:
        raw = stdin.readline()
        if not raw:
            return
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        response = server.handle_line(line)
        outgoing = ([response] if response is not None else []) + server.outbox
        server.outbox = []
        for message in outgoing:
            stdout.write(json.dumps(message, ensure_ascii=True, separators=(",", ":")).encode("ascii") + b"\n")
        if outgoing:
            stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spec_master_mcp", description="Spec Master MCP server (stdio).")
    parser.add_argument("--project", default=None,
                        help="project root the CLI runs in (default: $SPEC_MASTER_PROJECT or the cwd)")
    parser.add_argument("--timeout", type=float, default=None,
                        help="seconds per tool call (default: $SPEC_MASTER_MCP_TIMEOUT or 120)")
    parser.add_argument("--tools", choices=sorted(TOOLSETS), default=os.environ.get("SPEC_MASTER_MCP_TOOLS", "all"),
                        help="all: one tool per CLI command; entrypoint: only harness_entrypoint, as the plugins "
                             "start it (default: $SPEC_MASTER_MCP_TOOLS or all)")
    parser.add_argument("--list-tools", action="store_true", help="print the tool list as JSON and exit")
    args = parser.parse_args(argv)
    if args.tools not in TOOLSETS:
        parser.error(f"--tools must be one of {', '.join(sorted(TOOLSETS))}")

    project = args.project or os.environ.get("SPEC_MASTER_PROJECT")
    if project and not Path(project).expanduser().is_dir():
        print(json.dumps({"error": f"project root is not a directory: {project}"}), file=sys.stderr)
        return 2

    server = Server(project_root=project, timeout=args.timeout, toolset=args.tools)
    if args.list_tools:
        if server.load_error:
            print(json.dumps({"error": server.load_error}, indent=2))
            return 1
        print(json.dumps(server.list_tools(), indent=2, ensure_ascii=False))
        return 0

    out = sys.stdout.buffer
    sys.stdout = sys.stderr  # stray prints must never corrupt the protocol stream
    log(f"serving {len(server.tools)} tools for {server.project_root} (timeout {server.timeout:g}s)")
    try:
        serve(server, sys.stdin.buffer, out)
    except (KeyboardInterrupt, BrokenPipeError):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
