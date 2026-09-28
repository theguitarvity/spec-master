"""Host telemetry: real usage from Claude Code transcripts and `claude -p` results.

Why: `.spec-master/metrics/rounds.json` rows used to be typed in by the model
(0 tokens in 9/9 rows, invented and overlapping timestamps) while the host
already records real usage. This module reads that usage -- metadata only --
and turns it into rounds.json rows (`to_round`) whose `source` says where the
numbers came from. Pure stdlib, no network, no subprocesses; reading files is
its only side effect.

Public API
    project_dir_name(path) -> str            host's directory name for a project
    locate_transcripts(project_root, home=None) -> [path]   newest first
    session_transcripts(path) -> [path]      a session file + its subagent files
    read_transcript_usage(path, since=None, until=None) -> usage dict
    read_headless_result(obj_or_path) -> usage dict
    to_round(usage, *, round_id, phase, source, ...) -> rounds.json row

Transcript location (verified in the Claude Code 2.1.283 binary and against
the directories on the development machine; 2.1.42 used the same rule without
the length cap):

    <config>/projects/<name>/<session-id>.jsonl                       main thread
    <config>/projects/<name>/<session-id>/subagents/agent-<id>.jsonl  subagents
    <config>/projects/<name>/<session-id>/subagents/workflows/<run>/agent-<id>.jsonl

- <config> is $CLAUDE_CONFIG_DIR, else ~/.claude.
- <name> is the directory Claude Code was launched from, with every UTF-16
  code unit outside [A-Za-z0-9] replaced by "-" (so "/home/user/spec-master"
  -> "-home-user-spec-master"). Names longer than 200 characters are cut at
  200 and suffixed with "-" + base36(|32-bit Java-style string hash|).
- With $CLAUDE_CONFIG_DIR set, $CLAUDE_CODE_PROJECT_DIR_NAME (when it
  matches ^[A-Za-z0-9_-]{1,64}$) replaces <name>.
- `workflows/<run>/journal.jsonl` and `subagents/*.meta.json` are not
  transcripts. A resumed session may live under another project's <name>
  (the host's `sessionProjectDir`); pass that file explicitly.

Transcript line schema (verified on 2.1.283 transcripts; the fields below are
the only ones this module reads):

- One JSON object per line. `type` is user, assistant, attachment, system,
  queue-operation, mode, ai-title, last-prompt, atis-latch, cost-state, ...;
  unknown types are ignored.
- `timestamp`: ISO 8601 UTC with milliseconds ("2026-09-27T20:23:13.643Z").
  Bookkeeping lines (mode, ai-title, last-prompt, cost-state) have none.
- `sessionId` on every conversational line. Subagent files carry the PARENT
  session's id plus `agentId`.
- `isSidechain`: false on every main-thread line, true on every line of a
  subagent file. Current versions write subagents to separate files, older
  ones interleaved sidechain lines in the main file; the flag splits both.
- assistant lines: `message.id` (API message id), `requestId`,
  `message.model`, `message.usage` = {input_tokens (uncached input),
  output_tokens, cache_read_input_tokens, cache_creation_input_tokens, ...}.
  ONE API response is written as several lines (one per content block) that
  share `message.id` and `requestId` and repeat the SAME usage object (95/95
  multi-line responses in the sample). Usage is taken once per message id --
  the per-field max over its lines, which is also right if a version streams
  growing counters -- and never summed per line. `message.model ==
  "<synthetic>"` marks client-made messages, not API responses.
- Finality: main-thread lines carry the FINAL usage (`message.stop_reason`
  set, `usage.iterations` / `output_tokens_details` present). Subagent lines
  are written with the streaming-START snapshot: `stop_reason` is null on
  every line, and while input / cache counts are already exact, output_tokens
  is a placeholder (median 8 per response in the sample). A response with no
  `stop_reason` on any line is counted in `incomplete_responses`, and
  `output_tokens_complete` becomes False: output (and total) tokens are then
  a LOWER BOUND.
- Coverage: transcripts hold only conversational API calls. Auxiliary calls
  (session titles, classifiers, summaries) never appear: on the sample
  session the host's own `cost-state` snapshot had 0.93M extra input
  tokens, while cache-read / cache-creation tokens matched it within 0.27% /
  0.013%. For complete totals use the headless result (`modelUsage`).
- user lines are human prompts, tool results or host injections:
  - tool result: `toolUseResult` and/or `sourceToolAssistantUUID` on the line;
    `message.content` is a list of `tool_result` blocks;
  - genuine human prompt: `origin.kind == "human"` (`turnOrigin == "human"`);
  - injected turns: any other `origin.kind` (task-notification, channel, peer,
    coordinator, auto-continuation, observer, unclassified, ...);
  - `isMeta: true` (skill / hook injections), `isCompactSummary: true`.
  Once a file shows origin metadata, an unstamped user line (e.g. an
  interruption marker) is not a human prompt; files with no origin metadata
  at all (older hosts) fall back to "a user line that is none of the above".

Human wait = time from the last main-thread assistant/tool activity (assistant
line, tool result, injected turn) to the next genuine human prompt; waits that
happen INSIDE a tool call (a permission prompt, an AskUserQuestion answer) are
invisible without reading tool names and count as tool time.

Headless result (`claude -p --output-format json`, verified in the 2.1.283
SDK schema): {type: "result", subtype: success | error_during_execution |
error_max_turns | error_max_budget_usd | error_max_structured_output_retries,
is_error, duration_ms, duration_api_ms, num_turns, result, stop_reason,
total_cost_usd, usage, modelUsage, permission_denials, session_id, uuid,
errors?, terminal_reason?, ...}. The host documents `usage` as "MAIN AGENT
LOOP ONLY -- excludes Task subagent, sidechain, and auxiliary model calls"
and says to prefer `modelUsage` for accounting, so totals are summed over
`modelUsage` (inputTokens, outputTokens, cacheReadInputTokens,
cacheCreationInputTokens, costUSD) and `usage` is reported as `main`.

Privacy: message text is never read, returned or logged. Inside
`message.content` only each block's `type` discriminator is read, as a
fallback to recognise tool results; the headless `result`,
`structured_output`, `errors` and `permission_denials` payloads are reduced
to counts. Outputs hold counts, ids, model names and timestamps.

Cost: only the host's own figure (`total_cost_usd`) becomes `cost_usd`, with
`cost_basis: "measured"`. There is no price table here.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import math
import os
import re
import unicodedata

import metrics
import metrics_export

SOURCE_TRANSCRIPT = "host-transcript"
SOURCE_HEADLESS = "host-headless"

TOKEN_FIELDS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
# modelUsage (camelCase) -> usage field names
_MODEL_USAGE_FIELDS = (
    ("inputTokens", "input_tokens"),
    ("outputTokens", "output_tokens"),
    ("cacheReadInputTokens", "cache_read_input_tokens"),
    ("cacheCreationInputTokens", "cache_creation_input_tokens"),
)

PROJECT_DIR_NAME_MAX = 200
_PROJECT_DIR_OVERRIDE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_WINDOWS_RESERVED_RE = re.compile(r"^(?:con|prn|aux|nul|com[0-9]|lpt[0-9])$", re.IGNORECASE)
SYNTHETIC_MODEL = "<synthetic>"
_BASE36 = "0123456789abcdefghijklmnopqrstuvwxyz"


# ----------------------------------------------------------------------- location

def _utf16_units(text: str) -> list[int]:
    raw = text.encode("utf-16-le", "surrogatepass")
    return [raw[i] | (raw[i + 1] << 8) for i in range(0, len(raw), 2)]


def _java_string_hash(units) -> int:
    """JS `h = (h << 5) - h + charCode | 0` over UTF-16 code units (signed 32-bit)."""
    value = 0
    for unit in units:
        value = (value * 31 + unit) & 0xFFFFFFFF
    return value - 0x100000000 if value >= 0x80000000 else value


def _base36(number: int) -> str:
    if number == 0:
        return "0"
    digits = []
    while number:
        number, rem = divmod(number, 36)
        digits.append(_BASE36[rem])
    return "".join(reversed(digits))


def project_dir_name(project_path: str) -> str:
    """The `~/.claude/projects/<name>` Claude Code uses for a launch directory."""
    units = _utf16_units(os.fspath(project_path))
    name = "".join(chr(u) if (0x30 <= u <= 0x39 or 0x41 <= u <= 0x5A or 0x61 <= u <= 0x7A) else "-"
                   for u in units)
    if len(name) <= PROJECT_DIR_NAME_MAX:
        return name
    return f"{name[:PROJECT_DIR_NAME_MAX]}-{_base36(abs(_java_string_hash(units)))}"


def claude_config_dir(home=None, env=None) -> str:
    """`<home>/.claude` when `home` is given; else $CLAUDE_CONFIG_DIR, else ~/.claude."""
    if home is not None:
        return os.path.join(os.fspath(home), ".claude")
    env = os.environ if env is None else env
    configured = env.get("CLAUDE_CONFIG_DIR")
    if configured:
        return unicodedata.normalize("NFC", configured)
    return os.path.join(os.path.expanduser("~"), ".claude")


def project_transcript_dirs(project_root, home=None, env=None) -> list[str]:
    """Candidate transcript directories for a project (they need not exist).

    Both the absolute and the symlink-resolved path are tried, because the
    host names the directory after its process cwd.
    """
    env = os.environ if env is None else env
    projects = os.path.join(claude_config_dir(home, env), "projects")
    names: list[str] = []
    if home is None and env.get("CLAUDE_CONFIG_DIR"):
        override = env.get("CLAUDE_CODE_PROJECT_DIR_NAME") or ""
        if _PROJECT_DIR_OVERRIDE_RE.match(override) and not _WINDOWS_RESERVED_RE.match(override):
            names.append(override)
    root = os.fspath(project_root)
    for candidate in (os.path.abspath(root), os.path.realpath(root)):
        name = project_dir_name(candidate)
        if name not in names:
            names.append(name)
    return [os.path.join(projects, name) for name in names]


def _newest_first(paths) -> list[str]:
    def key(path):
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = 0.0
        return (-mtime, path)
    return sorted(set(paths), key=key)


def locate_transcripts(project_root, home=None, *, include_subagents: bool = False, env=None) -> list[str]:
    """Claude Code session transcripts of a project, newest first (by mtime).

    project_root      the directory Claude Code was launched from
    home              user home holding `.claude/` (tests); default honours
                      $CLAUDE_CONFIG_DIR, else ~/.claude
    include_subagents also return `<session>/subagents/**/agent-*.jsonl`
    env               environment mapping (default os.environ)

    Returns [] when the project has no transcript directory.
    """
    found: list[str] = []
    for directory in project_transcript_dirs(project_root, home, env):
        base = glob.escape(directory)
        found.extend(p for p in glob.glob(os.path.join(base, "*.jsonl")) if os.path.isfile(p))
        if include_subagents:
            pattern = os.path.join(base, "*", "subagents", "**", "agent-*.jsonl")
            found.extend(p for p in glob.glob(pattern, recursive=True) if os.path.isfile(p))
    return _newest_first(found)


def session_transcripts(transcript_path) -> list[str]:
    """[session file] + its subagent transcripts (sorted), for full-session usage."""
    path = os.fspath(transcript_path)
    stem = path[:-len(".jsonl")] if path.endswith(".jsonl") else path
    pattern = os.path.join(glob.escape(stem), "subagents", "**", "agent-*.jsonl")
    return [path] + sorted(p for p in glob.glob(pattern, recursive=True) if os.path.isfile(p))


# ------------------------------------------------------------------------ helpers

def _count(value) -> int:
    """A non-negative token count; anything unreadable counts as 0."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    if isinstance(value, float) and not math.isfinite(value):
        return 0
    return max(0, int(value))


def _optional_count(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return max(0, int(value))


def _cost(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value >= 0 else None


def _parse_time(value) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=dt.timezone.utc)
    if not isinstance(value, str):
        return None
    try:
        return metrics_export.parse_timestamp(value)
    except ValueError:
        return None


def _bound(value, name: str) -> dt.datetime | None:
    if value is None:
        return None
    parsed = _parse_time(value)
    if parsed is None:
        raise ValueError(f"{name} is not an ISO 8601 date-time: {value!r}")
    return parsed


def _iso(moment: dt.datetime) -> str:
    text = moment.astimezone(dt.timezone.utc).isoformat(timespec="milliseconds")
    return text.replace("+00:00", "Z")


def _in_window(moment: dt.datetime | None, since, until) -> bool:
    if since is None and until is None:
        return True
    if moment is None:
        return False
    return (since is None or moment >= since) and (until is None or moment <= until)


def _overlap_seconds(start: dt.datetime, end: dt.datetime, since, until) -> float:
    low = max(start, since) if since is not None else start
    high = min(end, until) if until is not None else end
    return max(0.0, (high - low).total_seconds())


def _bucket() -> dict:
    return {**{field: 0 for field in TOKEN_FIELDS}, "turns": 0, "incomplete_responses": 0}


# ------------------------------------------------------------------- transcripts

def _is_tool_result(obj: dict) -> bool:
    if "toolUseResult" in obj or obj.get("sourceToolAssistantUUID"):
        return True
    message = obj.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):  # only the block `type` discriminator is read
        return any(isinstance(block, dict) and block.get("type") == "tool_result" for block in content)
    return False


def _origin_kind(obj: dict) -> str | None:
    origin = obj.get("origin")
    kind = origin.get("kind") if isinstance(origin, dict) else None
    if isinstance(kind, str):
        return kind
    turn_origin = obj.get("turnOrigin")
    if isinstance(turn_origin, str):
        return "human" if turn_origin == "human" else turn_origin
    return None


def _user_line_kind(obj: dict, origin_aware: bool) -> str:
    """'human', 'activity' (tool result / injected turn) or 'other' for a user line.

    `origin_aware`: this file already showed origin metadata, so the host
    stamps genuine prompts and an unstamped line (e.g. an interruption
    marker) is not a human prompt. Files without any origin metadata (older
    hosts) fall back to "a user line that is nothing else is human".
    """
    if obj.get("isMeta") is True or obj.get("isCompactSummary") is True or obj.get("isVisibleInTranscriptOnly") is True:
        return "other"
    if _is_tool_result(obj):
        return "activity"
    kind = _origin_kind(obj)
    if kind is not None:
        return "human" if kind == "human" else "activity"
    if obj.get("sourceToolUseID") or origin_aware:
        return "other"
    return "human"


def read_transcript_usage(path, since=None, until=None) -> dict:
    """Aggregate host-measured usage from Claude Code transcript JSONL.

    path   one transcript path, or a list of them (e.g.
           `session_transcripts(p)` for a session plus its subagents); API
           responses are de-duplicated by message id across all files
    since  / until
           inclusive window bounds (ISO 8601 string or datetime, naive = UTC).
           With a window, a line counts only if its timestamp is inside it,
           and an API response by its first line; human waits are clipped
           to the window.

    Returns a usage dict: `source` ("host-transcript"), `transcripts`,
    `session_id` (None unless exactly one), `session_ids`, `window`,
    `started_at` / `ended_at` (raw min / max timestamps inside the window),
    `duration_seconds`, the TOKEN_FIELDS totals, `total_tokens`
    (input + output), `turns` (unique API responses),
    `incomplete_responses` + `output_tokens_complete` (see "Finality" in the
    module docstring), `main` / `sidechain` splits of the same counters,
    `subagents` (distinct agentIds), `human_wait_seconds`, `human_prompts`,
    `models` ({model: turns}), `lines` and `skipped_lines` (lines that are
    not JSON objects).
    """
    paths = [os.fspath(path)] if isinstance(path, (str, os.PathLike)) else [os.fspath(p) for p in path]
    since_dt = _bound(since, "since")
    until_dt = _bound(until, "until")

    responses: dict[str, dict] = {}
    session_ids: set[str] = set()
    agent_ids: set[str] = set()
    first = last = None  # (datetime, raw string)
    human_wait = 0.0
    human_prompts = 0
    lines = skipped = 0

    for file_index, file_path in enumerate(paths):
        wait_start: dt.datetime | None = None
        origin_aware = False
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            for line_number, raw in enumerate(fh, 1):
                if not raw.strip():
                    continue
                lines += 1
                try:
                    obj = json.loads(raw)
                except ValueError:
                    skipped += 1
                    continue
                if not isinstance(obj, dict):
                    skipped += 1
                    continue

                stamp = obj.get("timestamp")
                moment = _parse_time(stamp)
                inside = _in_window(moment, since_dt, until_dt)
                sidechain = obj.get("isSidechain") is True
                if inside:
                    if moment is not None:
                        if first is None or moment < first[0]:
                            first = (moment, stamp)
                        if last is None or moment > last[0]:
                            last = (moment, stamp)
                    if isinstance(obj.get("sessionId"), str) and obj["sessionId"]:
                        session_ids.add(obj["sessionId"])
                    if sidechain and isinstance(obj.get("agentId"), str) and obj["agentId"]:
                        agent_ids.add(obj["agentId"])

                kind = obj.get("type")
                if kind == "assistant":
                    if not sidechain and moment is not None and (wait_start is None or moment > wait_start):
                        wait_start = moment
                    message = obj.get("message") if isinstance(obj.get("message"), dict) else {}
                    model = message.get("model")
                    if model == SYNTHETIC_MODEL or obj.get("isApiErrorMessage") is True:
                        continue
                    key = message.get("id") or obj.get("requestId") or obj.get("uuid") \
                        or f"{file_index}:{line_number}"
                    response = responses.get(key)
                    if response is None:
                        response = responses[key] = {"tokens": dict.fromkeys(TOKEN_FIELDS, 0), "first": moment,
                                                     "sidechain": sidechain, "final": False,
                                                     "model": model if isinstance(model, str) else None}
                    elif moment is not None and (response["first"] is None or moment < response["first"]):
                        response["first"] = moment
                    if isinstance(message.get("stop_reason"), str) and message["stop_reason"]:
                        response["final"] = True
                    usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
                    for field in TOKEN_FIELDS:
                        response["tokens"][field] = max(response["tokens"][field], _count(usage.get(field)))
                elif kind == "user" and not sidechain:
                    origin_aware = origin_aware or _origin_kind(obj) is not None
                    line_kind = _user_line_kind(obj, origin_aware)
                    if line_kind == "activity":
                        if moment is not None and (wait_start is None or moment > wait_start):
                            wait_start = moment
                    elif line_kind == "human":
                        if inside:
                            human_prompts += 1
                        if wait_start is not None and moment is not None:
                            human_wait += _overlap_seconds(wait_start, moment, since_dt, until_dt)
                        wait_start = None

    totals, main, side = _bucket(), _bucket(), _bucket()
    models: dict[str, int] = {}
    for response in responses.values():
        if not _in_window(response["first"], since_dt, until_dt):
            continue
        bucket = side if response["sidechain"] else main
        for field in TOKEN_FIELDS:
            bucket[field] += response["tokens"][field]
            totals[field] += response["tokens"][field]
        bucket["turns"] += 1
        totals["turns"] += 1
        if not response["final"]:
            bucket["incomplete_responses"] += 1
            totals["incomplete_responses"] += 1
        model = response["model"] or "unknown"
        models[model] = models.get(model, 0) + 1

    ordered_sessions = sorted(session_ids)
    return {
        "source": SOURCE_TRANSCRIPT,
        "transcripts": paths,
        "session_id": ordered_sessions[0] if len(ordered_sessions) == 1 else None,
        "session_ids": ordered_sessions,
        "window": {"since": _iso(since_dt) if since_dt else None, "until": _iso(until_dt) if until_dt else None},
        "started_at": first[1] if first else None,
        "ended_at": last[1] if last else None,
        "duration_seconds": round((last[0] - first[0]).total_seconds(), 3) if first and last else None,
        **totals,
        "total_tokens": totals["input_tokens"] + totals["output_tokens"],
        "output_tokens_complete": totals["incomplete_responses"] == 0,
        "main": main,
        "sidechain": side,
        "subagents": len(agent_ids),
        "human_wait_seconds": round(human_wait, 3),
        "human_prompts": human_prompts,
        "models": dict(sorted(models.items())),
        "lines": lines,
        "skipped_lines": skipped,
    }


# ---------------------------------------------------------------------- headless

def _result_object(value) -> dict:
    """The `type: result` object from a dict, a message list, JSON or JSONL text."""
    if isinstance(value, dict):
        if value.get("type") not in (None, "result"):
            raise ValueError(f"not a claude -p result object (type={value.get('type')!r})")
        return value
    if isinstance(value, list):
        for item in reversed(value):
            if isinstance(item, dict) and item.get("type") == "result":
                return item
        raise ValueError("no 'result' message in the claude -p output")
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            parsed = None
        if isinstance(parsed, (dict, list)):
            try:
                return _result_object(parsed)
            except ValueError:
                pass  # e.g. one non-result message: fall through to the line scan
        found = None
        for raw in value.splitlines():  # stream-json: one message per line
            try:
                item = json.loads(raw)
            except ValueError:
                continue
            if isinstance(item, dict) and item.get("type") == "result":
                found = item
        if found is None:
            raise ValueError("no 'result' message in the claude -p output")
        return found
    raise TypeError(f"expected a dict, a list or JSON text, got {type(value).__name__}")


def read_headless_result(obj_or_path) -> dict:
    """Parse the result of `claude -p --output-format json` (tolerant of gaps).

    obj_or_path  the parsed result dict (or message list), or a path to a file
                 holding the JSON / stream-json output.

    Returns a usage dict: `source` ("host-headless"), `session_id`,
    `subtype`, `is_error`, `stop_reason`, `terminal_reason`, `turns`
    (num_turns), `duration_ms`, `duration_api_ms`, `duration_seconds`,
    TOKEN_FIELDS totals (summed over modelUsage, see `token_basis`),
    `total_tokens`, `main` (the host's main-loop-only `usage`),
    `token_basis` ("modelUsage" or "usage"), `models`, `cost_usd` +
    `cost_basis` ("measured" when total_cost_usd is present, else None),
    `permission_denials` / `errors` (counts), and `started_at` / `ended_at`
    = None (the result carries no wall-clock bounds; see `to_round`).
    Missing fields come back as None / 0. The `result` text is never copied.
    """
    if isinstance(obj_or_path, (str, os.PathLike)):
        with open(obj_or_path, "r", encoding="utf-8") as fh:
            obj = _result_object(fh.read())
    else:
        obj = _result_object(obj_or_path)

    usage = obj.get("usage") if isinstance(obj.get("usage"), dict) else {}
    main = {field: _count(usage.get(field)) for field in TOKEN_FIELDS}
    models: dict[str, dict] = {}
    model_usage = obj.get("modelUsage") if isinstance(obj.get("modelUsage"), dict) else {}
    for model, entry in model_usage.items():
        if not isinstance(entry, dict):
            continue
        row = {target: _count(entry.get(source)) for source, target in _MODEL_USAGE_FIELDS}
        cost = _cost(entry.get("costUSD"))
        if cost is not None:
            row["cost_usd"] = cost
        models[str(model)] = row
    if models:
        totals = {field: sum(row[field] for row in models.values()) for field in TOKEN_FIELDS}
        token_basis = "modelUsage"
    else:
        totals = dict(main)
        token_basis = "usage"

    subtype = obj.get("subtype") if isinstance(obj.get("subtype"), str) else None
    if isinstance(obj.get("is_error"), bool):
        is_error = obj["is_error"]
    else:
        is_error = None if subtype is None else subtype != "success"
    duration_ms = _optional_count(obj.get("duration_ms"))
    cost_usd = _cost(obj.get("total_cost_usd"))

    def _text(key):
        value = obj.get(key)
        return value if isinstance(value, str) and value else None

    def _length(key):
        value = obj.get(key)
        return len(value) if isinstance(value, list) else 0

    return {
        "source": SOURCE_HEADLESS,
        "session_id": _text("session_id"),
        "subtype": subtype,
        "is_error": is_error,
        "stop_reason": _text("stop_reason"),
        "terminal_reason": _text("terminal_reason"),
        "turns": _optional_count(obj.get("num_turns")),
        "duration_ms": duration_ms,
        "duration_api_ms": _optional_count(obj.get("duration_api_ms")),
        "duration_seconds": duration_ms / 1000 if duration_ms is not None else None,
        **totals,
        "total_tokens": totals["input_tokens"] + totals["output_tokens"],
        "main": main,
        "token_basis": token_basis,
        "models": models,
        "cost_usd": cost_usd,
        "cost_basis": "measured" if cost_usd is not None else None,
        "permission_denials": _length("permission_denials"),
        "errors": _length("errors"),
        "started_at": None,
        "ended_at": None,
    }


# ------------------------------------------------------------------------- rows

def _timestamp_text(value, name: str) -> str:
    if isinstance(value, dt.datetime):
        return _iso(value if value.tzinfo is not None else value.replace(tzinfo=dt.timezone.utc))
    if isinstance(value, str) and _parse_time(value) is not None:
        return value
    raise ValueError(f"{name} is not an ISO 8601 date-time: {value!r}")


def _round_bounds(usage: dict, started_at, ended_at) -> tuple[str, str]:
    start = started_at if started_at is not None else usage.get("started_at")
    end = ended_at if ended_at is not None else usage.get("ended_at")
    duration = usage.get("duration_seconds")
    has_duration = isinstance(duration, (int, float)) and not isinstance(duration, bool) \
        and math.isfinite(duration) and duration >= 0
    if start is None and end is not None and has_duration:
        start = _bound(end, "ended_at") - dt.timedelta(seconds=duration)
    elif end is None and start is not None and has_duration:
        end = _bound(start, "started_at") + dt.timedelta(seconds=duration)
    if start is None or end is None:
        raise ValueError("usage has no started_at/ended_at (a headless result carries only its duration): "
                         "pass started_at= and/or ended_at= to to_round")
    return _timestamp_text(start, "started_at"), _timestamp_text(end, "ended_at")


def to_round(usage: dict, *, round_id: str, phase: str, source: str, feature_id: str | None = None,
             tier: str | None = None, lane: str | None = None, notes: str | None = None,
             started_at=None, ended_at=None, work_packages_completed: int = 0,
             features_completed: int = 0) -> dict:
    """Build a rounds.json row (metrics schema v2) from a usage dict.

    The row is `metrics.record_round(...)` output -- same keys, same derived
    rates, `total_tokens = input_tokens + output_tokens` with `input_tokens`
    the uncached input as reported by the API -- plus the v2 fields present
    in `usage`: `cache_read_input_tokens`, `cache_creation_input_tokens`,
    `turns`, `human_wait_seconds`, `session_id`, and `cost_usd` +
    `cost_basis: "measured"` only when the host measured the cost. `lane` is
    written when given. When the usage says `output_tokens_complete: False`,
    a sentence stating that output_tokens is a lower bound is appended to
    `notes`, so the row never overstates its precision.

    source          one of metrics.SOURCES; must match `usage["source"]` when
                    the usage dict declares one
    started_at / ended_at
                    override the usage bounds (ISO 8601 string or datetime);
                    with only one bound and a usage `duration_seconds`, the
                    other is derived (a headless result needs at least one)

    Raises ValueError for an unknown or mismatched source, missing bounds,
    or a host source whose usage has no tokens (nothing was measured in the
    window: fix the window rather than record a zero row).
    """
    if source not in metrics.SOURCES:
        raise ValueError(f"unknown source: {source!r} (known: {', '.join(metrics.SOURCES)})")
    declared = usage.get("source")
    if declared is not None and declared != source:
        raise ValueError(f"usage was read as {declared!r}; refusing to record it as {source!r}")
    input_tokens = _count(usage.get("input_tokens"))
    output_tokens = _count(usage.get("output_tokens"))
    if source in metrics.HOST_SOURCES and input_tokens + output_tokens == 0:
        raise ValueError(f"no tokens measured in this usage ({source}); check the transcript/window "
                         "instead of recording a zero round")
    start, end = _round_bounds(usage, started_at, ended_at)
    if usage.get("output_tokens_complete") is False:
        caveat = (f"telemetry: output_tokens is a lower bound ({_count(usage.get('incomplete_responses'))} "
                  "response(s) recorded before their final usage)")
        notes = f"{notes}; {caveat}" if notes else caveat
    row = metrics.record_round(
        round_id=round_id, phase=phase, started_at=start, ended_at=end,
        input_tokens=input_tokens, output_tokens=output_tokens,
        work_packages_completed=work_packages_completed, features_completed=features_completed,
        notes=notes, feature_id=feature_id, tier=tier, source=source,
    )
    for field in ("cache_read_input_tokens", "cache_creation_input_tokens", "turns"):
        value = _optional_count(usage.get(field))
        if value is not None:
            row[field] = value
    cost = _cost(usage.get("cost_usd"))
    if usage.get("cost_basis") == "measured" and cost is not None:
        row["cost_usd"] = cost
        row["cost_basis"] = "measured"
    wait = usage.get("human_wait_seconds")
    if isinstance(wait, (int, float)) and not isinstance(wait, bool) and math.isfinite(wait) and wait >= 0:
        row["human_wait_seconds"] = round(float(wait), 3)
    if lane:
        row["lane"] = str(lane)
    session_id = usage.get("session_id")
    if isinstance(session_id, str) and session_id:
        row["session_id"] = session_id
    return row
