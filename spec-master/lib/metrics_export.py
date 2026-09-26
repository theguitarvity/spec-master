"""Export `.spec-master/metrics/rounds.json` in portable formats (roadmap item 12).

Two pieces, pure stdlib (no jsonschema / opentelemetry dependency, no network):

1. A versioned JSON Schema (draft 2020-12) for one round row, shipped at
   `spec-master/schemas/metrics-round.schema.json`. Its ROOT describes a
   single row; `#/$defs/rounds` describes the whole rounds.json array.
   `validate_rounds()` checks rows with a deliberately small validator that
   supports exactly the keywords that schema uses — see `SUPPORTED_KEYWORDS`.
   Any other assertion keyword in a schema raises `SchemaError` instead of
   being silently ignored, so a "valid" verdict is never a false positive
   caused by an unimplemented keyword.

2. Serializers:
   - `to_otlp()` -> an OTLP/JSON `ExportMetricsServiceRequest` (the protobuf
     JSON mapping used by OTLP/HTTP `application/json`: lowerCamelCase field
     names, enums as integers, 64-bit integers as decimal strings), ready
     for any OpenTelemetry Collector `otlphttp` receiver (`POST /v1/metrics`).
   - JSONL -> one row per line, for log pipelines / `jq`.

Validator notes (the honest subset):
- `type`: "integer" follows JSON Schema — any number with a zero fractional
  part (so 3.0 is an integer), but booleans are NEVER numbers/integers.
- `pattern`: `re.search` semantics (unanchored, per the spec); the shipped
  schema anchors its own patterns.
- `format`: only "date-time" is asserted — parsed by `parse_timestamp()`
  (RFC 3339 shape; a naive value is accepted and read as UTC, matching
  `metrics._parse_iso`). Other formats are annotations and are ignored.
- `$ref`: local JSON Pointers only ("#", "#/$defs/name"); siblings of `$ref`
  are applied too (2020-12 semantics).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import tempfile
from pathlib import Path

SCHEMA_VERSION = "1.0.0"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "metrics-round.schema.json"
ROUNDS_RELPATH = os.path.join(".spec-master", "metrics", "rounds.json")

FORMATS = ("otlp", "jsonl")

OTLP_SCOPE_NAME = "spec-master.metrics"
# OTLP enum AggregationTemporality: 0 UNSPECIFIED, 1 DELTA, 2 CUMULATIVE.
AGGREGATION_TEMPORALITY_DELTA = 1

# Assertion keywords the validator implements. Annotation keywords are
# accepted and ignored; anything else raises SchemaError.
SUPPORTED_KEYWORDS = frozenset((
    "$ref", "type", "required", "properties", "additionalProperties", "enum",
    "minimum", "minLength", "pattern", "format", "items",
))
ANNOTATION_KEYWORDS = frozenset((
    "$schema", "$id", "$comment", "$defs", "title", "description", "default",
    "examples", "deprecated", "readOnly", "writeOnly",
))

# (metric name, row field, OTLP kind, unit, description) — order is the
# export order.
OTLP_METRICS = (
    ("spec_master.round.duration", "duration_seconds", "gauge", "s",
     "Wall-clock duration of a Spec Master delivery round."),
    ("spec_master.tokens.input", "input_tokens", "sum", "{token}",
     "Input (prompt) tokens consumed during the round."),
    ("spec_master.tokens.output", "output_tokens", "sum", "{token}",
     "Output (completion) tokens produced during the round."),
    ("spec_master.work_packages.completed", "work_packages_completed", "sum", "{package}",
     "Team Mode work packages completed during the round."),
    ("spec_master.features.completed", "features_completed", "sum", "{feature}",
     "Features completed during the round."),
)

# Row field -> data point attribute key; optional fields are emitted only
# when present. `notes` is free text and deliberately never exported.
OTLP_ATTRIBUTES = (
    ("round_id", "spec_master.round_id"),
    ("phase", "spec_master.phase"),
    ("feature_id", "spec_master.feature_id"),
    ("tier", "spec_master.tier"),
)

_TIMESTAMP_RE = re.compile(
    r"^(?P<base>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<frac>\d+))?"
    r"(?P<tz>Z|z|[+-]\d{2}:\d{2})?$"
)
_EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)


class SchemaError(ValueError):
    """The schema itself uses something this validator cannot enforce."""


class InvalidRoundsError(ValueError):
    """Rounds failed schema validation; `.report` holds the full report."""

    def __init__(self, report: dict):
        self.report = report
        count = len(report.get("errors", []))
        super().__init__(f"rounds failed metrics-round schema validation ({count} error(s))")


# --------------------------------------------------------------------------- IO

def default_rounds_path(root: str = ".") -> str:
    return os.path.join(root, ROUNDS_RELPATH)


def load_schema(path: str | os.PathLike | None = None) -> dict:
    with open(path or SCHEMA_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_rounds(path: str) -> list:
    """Read a rounds.json file. Missing file / bad JSON -> ValueError."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise ValueError(f"rounds file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"rounds file is not valid JSON: {path}: {exc}") from exc


def write_text_atomic(path: str, text: str) -> str:
    """Write `text` to `path` via a same-directory temp file + os.replace."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return path


# -------------------------------------------------------------------- timestamps

def parse_timestamp(value: str) -> dt.datetime:
    """Parse an ISO 8601 / RFC 3339 timestamp to an aware UTC-comparable datetime.

    Accepts `Z` or `+HH:MM` offsets (naive -> UTC, like metrics._parse_iso)
    and any number of fractional digits (microseconds are truncated here;
    use `timestamp_unix_nano()` for exact nanoseconds).
    """
    if not isinstance(value, str):
        raise ValueError(f"timestamp must be a string, got {type(value).__name__}")
    match = _TIMESTAMP_RE.match(value)
    if not match:
        raise ValueError(f"not an ISO 8601 date-time: {value!r}")
    tz = match.group("tz")
    tz = "+00:00" if tz in (None, "Z", "z") else tz
    parsed = dt.datetime.fromisoformat(match.group("base") + tz)
    frac = match.group("frac")
    if frac:
        parsed = parsed.replace(microsecond=int(frac[:6].ljust(6, "0")))
    return parsed


def timestamp_unix_nano(value: str) -> int:
    """Exact nanoseconds since the Unix epoch (fraction digits beyond 9 dropped)."""
    parsed = parse_timestamp(value)
    frac = _TIMESTAMP_RE.match(value).group("frac") or ""
    delta = parsed.replace(microsecond=0) - _EPOCH
    seconds = delta.days * 86400 + delta.seconds
    return seconds * 1_000_000_000 + int(frac[:9].ljust(9, "0") or 0)


# --------------------------------------------------------------------- validator

def _type_ok(value, expected: str) -> bool:
    if expected == "integer":
        if isinstance(value, bool):
            return False
        return isinstance(value, int) or (isinstance(value, float) and value.is_integer())
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "null":
        return value is None
    raise SchemaError(f"unsupported type in schema: {expected!r}")


def _json_type(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _pointer_escape(token) -> str:
    return str(token).replace("~", "~0").replace("/", "~1")


def _resolve_ref(ref: str, root: dict) -> dict:
    if ref == "#":
        return root
    if not ref.startswith("#/"):
        raise SchemaError(f"only local $ref pointers are supported, got {ref!r}")
    node = root
    for raw in ref[2:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or token not in node:
            raise SchemaError(f"unresolvable $ref: {ref!r}")
        node = node[token]
    return node


def _validate(value, schema, root: dict, path: str, errors: list, depth: int = 0) -> None:
    if depth > 64:
        raise SchemaError("$ref recursion too deep")
    if schema is True or schema == {}:
        return
    if schema is False:
        errors.append({"path": path, "message": "no value is allowed here"})
        return
    if not isinstance(schema, dict):
        raise SchemaError(f"schema at {path or '(root)'} must be an object or boolean")

    unknown = [k for k in schema
               if k not in SUPPORTED_KEYWORDS and k not in ANNOTATION_KEYWORDS and not k.startswith("x-")]
    if unknown:
        raise SchemaError(f"unsupported schema keyword(s): {sorted(unknown)}")

    if "$ref" in schema:
        _validate(value, _resolve_ref(schema["$ref"], root), root, path, errors, depth + 1)

    if "type" in schema:
        expected = schema["type"]
        options = expected if isinstance(expected, list) else [expected]
        if not any(_type_ok(value, option) for option in options):
            errors.append({"path": path, "message": f"expected {' or '.join(options)}, got {_json_type(value)}"})
            return  # further assertions on a wrong-typed value only add noise

    if "enum" in schema and not any(
        option == value and isinstance(option, bool) == isinstance(value, bool) for option in schema["enum"]
    ):
        errors.append({"path": path, "message": f"{value!r} is not one of {schema['enum']}"})

    if isinstance(value, (int, float)) and not isinstance(value, bool) and "minimum" in schema:
        if value < schema["minimum"]:
            errors.append({"path": path, "message": f"{value} is less than the minimum of {schema['minimum']}"})

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append({"path": path, "message": f"string is shorter than {schema['minLength']} character(s)"})
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append({"path": path, "message": f"{value!r} does not match pattern {schema['pattern']!r}"})
        if schema.get("format") == "date-time":
            try:
                parse_timestamp(value)
            except ValueError:
                errors.append({"path": path, "message": f"{value!r} is not a valid date-time"})

    if isinstance(value, dict):
        for name in schema.get("required", []):
            if name not in value:
                errors.append({"path": f"{path}/{_pointer_escape(name)}",
                               "message": f"required property {name!r} is missing"})
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for key in value:
            child_path = f"{path}/{_pointer_escape(key)}"
            if key in properties:
                _validate(value[key], properties[key], root, child_path, errors, depth + 1)
            elif additional is False:
                errors.append({"path": child_path, "message": f"additional property {key!r} is not allowed"})
            elif isinstance(additional, dict):
                _validate(value[key], additional, root, child_path, errors, depth + 1)

    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            _validate(item, schema["items"], root, f"{path}/{i}", errors, depth + 1)


def validate(instance, schema: dict, root: dict | None = None) -> list[dict]:
    """Validate any JSON value; returns [{"path", "message"}] (JSON Pointer paths)."""
    errors: list[dict] = []
    _validate(instance, schema, root if root is not None else schema, "", errors)
    return errors


def _consistency_warnings(index: int, row: dict) -> list[dict]:
    """Cross-field checks JSON Schema cannot express. Never block export."""
    warnings = []
    ints = ("input_tokens", "output_tokens", "total_tokens")
    if all(_type_ok(row.get(k), "integer") for k in ints):
        if row["total_tokens"] != row["input_tokens"] + row["output_tokens"]:
            warnings.append({"index": index, "path": "/total_tokens",
                             "message": "total_tokens != input_tokens + output_tokens"})
    try:
        if parse_timestamp(row["ended_at"]) < parse_timestamp(row["started_at"]):
            warnings.append({"index": index, "path": "/ended_at", "message": "ended_at is before started_at"})
    except (KeyError, ValueError):
        pass  # already reported as a schema error
    return warnings


def validate_rounds(rounds, schema: dict | None = None) -> dict:
    """Validate a rounds.json payload row by row.

    Returns {"valid", "errors": [{"index", "path", "message"}], "warnings": [...]}.
    `index` is the row's position (None when `rounds` itself is not an
    array); `path` is a JSON Pointer relative to that row ("" = the row).
    Warnings (duplicate round_id, total/ended_at consistency) never make a
    payload invalid.
    """
    schema = schema if schema is not None else load_schema()
    if not isinstance(rounds, list):
        return {"valid": False,
                "errors": [{"index": None, "path": "",
                            "message": f"rounds must be a JSON array, got {_json_type(rounds)}"}],
                "warnings": []}
    errors: list[dict] = []
    warnings: list[dict] = []
    seen: dict[str, int] = {}
    for index, row in enumerate(rounds):
        for err in validate(row, schema):
            errors.append({"index": index, **err})
        if isinstance(row, dict):
            warnings.extend(_consistency_warnings(index, row))
            rid = row.get("round_id")
            if isinstance(rid, str):
                if rid in seen:
                    warnings.append({"index": index, "path": "/round_id",
                                     "message": f"duplicate round_id {rid!r} (first at index {seen[rid]})"})
                else:
                    seen[rid] = index
    return {"valid": not errors, "errors": errors, "warnings": warnings}


# -------------------------------------------------------------------------- OTLP

def _attr(key: str, value: str) -> dict:
    return {"key": key, "value": {"stringValue": str(value)}}


def _data_point(row: dict, field: str, kind: str) -> dict:
    point = {
        "attributes": [_attr(key, row[name]) for name, key in OTLP_ATTRIBUTES
                       if row.get(name) not in (None, "")],
        "startTimeUnixNano": str(timestamp_unix_nano(row["started_at"])),
        "timeUnixNano": str(timestamp_unix_nano(row["ended_at"])),
    }
    if kind == "gauge":
        point["asDouble"] = float(row[field])
    else:
        point["asInt"] = str(int(row[field]))
    return point


def to_otlp(rounds: list[dict], service_name: str = "spec-master",
            scope_version: str = SCHEMA_VERSION) -> dict:
    """Map rows to an OTLP/JSON ExportMetricsServiceRequest.

    One data point per round per metric. Durations are a Gauge (`asDouble`,
    unit "s"); token/package/feature counts are monotonic DELTA Sums — each
    round is its own [started_at, ended_at] interval — with `asInt` values.
    64-bit fields are decimal strings and the temporality enum is its integer
    value, as the OTLP JSON encoding requires. Rows are ordered by
    (start, end, round_id) so the output is independent of input order.
    Rows are assumed valid (run `validate_rounds` first).
    """
    ordered = sorted(
        rounds,
        key=lambda r: (timestamp_unix_nano(r["started_at"]), timestamp_unix_nano(r["ended_at"]),
                       str(r.get("round_id", ""))),
    )
    metrics = []
    if ordered:
        for name, field, kind, unit, description in OTLP_METRICS:
            points = [_data_point(row, field, kind) for row in ordered]
            metric = {"name": name, "description": description, "unit": unit}
            if kind == "gauge":
                metric["gauge"] = {"dataPoints": points}
            else:
                metric["sum"] = {
                    "dataPoints": points,
                    "aggregationTemporality": AGGREGATION_TEMPORALITY_DELTA,
                    "isMonotonic": True,
                }
            metrics.append(metric)
    return {
        "resourceMetrics": [{
            "resource": {"attributes": [_attr("service.name", service_name)]},
            "scopeMetrics": [{
                "scope": {"name": OTLP_SCOPE_NAME, "version": scope_version},
                "metrics": metrics,
            }],
        }],
    }


def to_jsonl(rounds: list[dict]) -> str:
    """One compact, key-sorted JSON row per line, in input (append) order."""
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
                   for row in rounds)


def export(rounds, fmt: str = "otlp", *, validate_first: bool = True,
           service_name: str = "spec-master", scope_version: str = SCHEMA_VERSION) -> str:
    """Serialize rounds as text ending in a newline (empty for jsonl of no rows).

    Raises InvalidRoundsError (a ValueError) when validation fails, and
    ValueError for an unknown format.
    """
    if fmt not in FORMATS:
        raise ValueError(f"unknown export format {fmt!r}; expected one of {list(FORMATS)}")
    if validate_first:
        report = validate_rounds(rounds)
        if not report["valid"]:
            raise InvalidRoundsError(report)
    if fmt == "jsonl":
        return to_jsonl(rounds)
    payload = to_otlp(rounds, service_name=service_name, scope_version=scope_version)
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
