"""Declarative event hooks for Spec Master (roadmap items 8 and 15).

The orchestration used to live only in prose ("if a blocking gate fails, send
it back to implement"; "a security finding goes to the Tech Lead"). This
module turns those rules into data:

    {"id": "...", "on": ["gate.result"],
     "when": {"result": {"equals": "FAILED"}, "blocking": {"equals": true}},
     "action": {"type": "repair", "phase": "implement", "gate": "$gate"}}

- `evaluate()` is pure: event in, matched actions out.
- `emit()` evaluates, runs the few *internal* actions the core owns
  (re-rendering the dashboard, recording a decision), and returns every other
  action as a *directive* for the calling agent. The core never runs a build,
  opens a PR, or calls a model from here.
- Every event that fired at least one hook is appended to
  `.spec-master/hooks/firings.jsonl` so resumes and the dashboard can show why
  something happened.

Project hooks live in `.spec-master/hooks.json`; the defaults below encode the
role playbooks and the sensitivity floors of the risk-adaptive ceremony.
Pure stdlib.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import uuid

import team_model

HOOKS_RELPATH = os.path.join(".spec-master", "hooks.json")
FIRINGS_RELPATH = os.path.join(".spec-master", "hooks", "firings.jsonl")
CONFIG_VERSION = 1

# Payload shapes are documented in PROTOCOL.md ("Hooks").
EVENT_TYPES = (
    "phase.started",          # {feature, phase, attempt}
    "phase.transition",       # {feature, phase, status, previous}
    "gate.result",            # {gate, category, tool, result, blocking, feature}
    "package.contract_changed",  # {package, contracts, feature}
    "analyze.findings",       # {feature, count, critical}
    "feature.intake",         # {feature, text, paths}
    "feature.pre_implement",  # {feature, text, paths}
    "workflow.status",        # {status, previous}
    "escalation.raised",      # {kind, raised_by, feature, summary}
    "escalation.resolved",    # {kind, raised_by, decided_by, decision, rationale, ...}
)

INTERNAL_ACTIONS = ("render_dashboard", "record_decision")
DIRECTIVE_ACTIONS = ("repair", "revalidate", "escalate", "raise_tier", "block", "notify")
ACTION_TYPES = INTERNAL_ACTIONS + DIRECTIVE_ACTIONS

OPERATORS = ("equals", "not_equals", "in", "not_in", "contains", "matches",
             "gt", "gte", "lt", "lte", "exists")

TIER_ORDER = ("XS", "S", "M", "L", "XL")

# Sensitivity categories (roadmap item 15). Regexes are EN + PT and
# deliberately conservative: "secrets" does not match a bare "token" so a
# feature about LLM tokens or design tokens is not escalated to L.
SENSITIVITY_RULES = {
    "auth": {
        "floor": "L",
        "text": (r"\b(?:auth(?:n|z|entic\w*|ori[sz]\w*)?|oauth2?|oidc|openid|saml|sso|"
                 r"log[\s-]?ins?|sign[\s-]?(?:in|on|up)|pass(?:word|wd|phrase)s?|senhas?|"
                 r"jwt|rbac|abac|mfa|2fa|access[\s-]control|controle\s+de\s+acesso|"
                 r"permiss(?:ion|ions|ão|ões|ao|oes)|autentica\w*|autoriza\w*)\b"),
        "paths": r"(?:^|/)(?:auth|authn|authz|authentication|authorization|login|oauth|sso|iam|permissions?)(?:/|[._-])",
    },
    "payment": {
        "floor": "L",
        "text": (r"\b(?:payments?|pagamentos?|billing|cobran[çc]as?|checkout|invoices?|faturas?|"
                 r"faturamento|stripe|paypal|adyen|pix|credit[\s-]cards?|"
                 r"cart[ãa]o\s+de\s+cr[ée]dito|refunds?|reembolsos?)\b"),
        "paths": r"(?:^|/)(?:payments?|billing|checkout|invoices?|pagamentos?)(?:/|[._-])",
    },
    "secrets": {
        "floor": "L",
        "text": (r"\b(?:secrets?|segredos?|api[\s_-]?keys?|chaves?\s+de\s+api|private[\s_-]?keys?|"
                 r"chaves?\s+privadas?|(?:access|refresh|bearer)[\s_-]?tokens?|vault|kms|keystore|"
                 r"credentials?|credenciais|credencial)\b"),
        "paths": r"(?:^|/)\.env(?:\.|$)|(?:^|/)secrets?/|\.(?:pem|key|p12|pfx|jks|keystore)$",
    },
    "schema": {
        "floor": "M",
        "text": (r"\b(?:schemas?|migrations?|migra[çc](?:ão|ao|ões|oes)|ddl|"
                 r"(?:alter|create|drop)\s+table|data[\s-]models?|modelos?\s+de\s+dados|"
                 r"esquemas?\s+de\s+(?:dados|banco))\b"),
        "paths": r"(?:^|/)(?:migrations?|alembic)/|\.sql$|(?:^|/)schema\.(?:prisma|sql|rb)$",
    },
    "public_contract": {
        "floor": "M",
        "text": (r"\b(?:public\s+api|api\s+p[úu]blica|endpoints?|openapi|swagger|graphql|grpc|"
                 r"protobuf|contracts?|contratos?|webhooks?|breaking[\s-]changes?|sdk)\b"),
        "paths": r"(?:^|/)(?:openapi|swagger|contracts?)(?:/|[._-])|\.(?:proto|graphql|gql)$",
    },
    # Actions that leave the local repository and cannot be taken back by a
    # later commit (constitution Principle X): pushing, opening a PR/MR,
    # publishing a package, deploying to a shared environment.
    "irreversible": {
        "floor": "M",
        "text": (r"\b(?:git\s+push|force[\s-]push|push(?:es|ed|ing)?\s+to\s+(?:the\s+)?(?:remote|origin|upstream)|"
                 r"pull[\s-]requests?|merge[\s-]requests?|"
                 r"(?:open|opens|opening|create|creates|creating)\s+(?:a\s+|the\s+)?(?:pr|mr)s?|"
                 r"gh\s+pr\s+create|glab\s+mr\s+create|"
                 r"(?:npm|yarn|pnpm|cargo|gem|poetry)\s+publish|twine\s+upload|"
                 r"publish(?:es|ed|ing)?\s+(?:to\s+)?(?:npm|pypi|the\s+registry|a\s+registry|the\s+marketplace)|"
                 r"deploy(?:s|ed|ing)?\s+to\s+(?:prod(?:uction)?|staging)|production\s+deploy(?:ment)?s?|"
                 r"abr(?:ir|e)\s+(?:um\s+)?(?:pr|pull\s+request)|"
                 r"implanta(?:r|ção|cao)\s+em\s+produ[çc][ãa]o)\b"),
        "paths": r"(?:^|/)\.github/workflows/|(?:^|/)(?:deploy|deployment|release)s?/",
    },
    "external_provider": {
        "floor": "M",
        "text": (r"\b(?:third[\s-]party|terceiros?|external\s+(?:providers?|services?|apis?|systems?)|"
                 r"provedor(?:es)?\s+externos?|servi[çc]os?\s+externos?|"
                 r"integra(?:tion|ção|cao)\s+(?:with|com)|integrat(?:e|es|ing)\s+with|"
                 r"vendors?|fornecedor(?:es)?)\b"),
        "paths": r"(?:^|/)(?:integrations?|providers?|vendors?|third[_-]?party)(?:/|[._-])",
    },
}


def _sensitivity_hooks() -> list[dict]:
    hooks = []
    for category, rule in SENSITIVITY_RULES.items():
        hooks.append({
            "id": f"sensitivity-{category.replace('_', '-')}",
            "on": ["feature.intake", "feature.pre_implement"],
            "when": {"any": [{"text": {"matches": rule["text"]}}, {"paths": {"matches": rule["paths"]}}]},
            "action": {"type": "raise_tier", "category": category, "floor": rule["floor"]},
            "description": f"{category} sensitivity raises the ceremony tier to at least {rule['floor']}.",
        })
    return hooks


DEFAULT_HOOKS = [
    {
        "id": "repair-on-blocking-gate-failure",
        "on": ["gate.result"],
        "when": {"result": {"equals": "FAILED"}, "blocking": {"equals": True}},
        "action": {"type": "repair", "phase": "implement", "gate": "$gate",
                   "reason": "blocking quality gate failed"},
        "description": "A failing blocking gate sends the feature back to implement for repair.",
    },
    {
        "id": "escalate-security-gate-failure",
        "on": ["gate.result"],
        "when": {"result": {"equals": "FAILED"}, "category": {"in": ["sast", "secrets"]}},
        "action": {"type": "escalate", "kind": "security_finding", "raised_by": "security", "gate": "$gate"},
        "description": "SAST/secret-scan failures are security findings routed per the Security playbook.",
    },
    {
        "id": "revalidate-on-contract-change",
        "on": ["package.contract_changed"],
        "when": {},
        "action": {"type": "revalidate", "target": "constitution", "package": "$package"},
        "description": "A work package that changes a shared contract revalidates against the constitution.",
    },
    {
        "id": "repair-on-analyze-findings",
        "on": ["analyze.findings"],
        "when": {"count": {"gt": 0}},
        "action": {"type": "repair", "phase": "analyze", "reason": "analyze reported findings"},
        "description": "Analyze findings go back through the bounded analyze/repair loop.",
    },
    {
        "id": "escalate-blocked-phase",
        "on": ["phase.transition"],
        "when": {"status": {"equals": "BLOCKED"}},
        "action": {"type": "escalate", "kind": "unowned_blocker", "raised_by": "scrum-master", "phase": "$phase"},
        "description": "A BLOCKED phase is an unowned blocker until the Tech Lead assigns it.",
    },
    {
        "id": "dashboard-refresh",
        "on": ["phase.started", "phase.transition", "workflow.status"],
        "when": {},
        "action": {"type": "render_dashboard"},
        "description": "Keep .spec-master/reports/dashboard.html current while a cycle runs.",
    },
    {
        "id": "route-raised-escalation",
        "on": ["escalation.raised"],
        "when": {},
        "action": {"type": "escalate", "kind": "$kind", "raised_by": "$raised_by"},
        "description": "Resolve who handles an escalation from the playbook routing table.",
    },
    {
        "id": "record-resolved-decision",
        "on": ["escalation.resolved"],
        "when": {},
        "action": {"type": "record_decision"},
        "description": "Persist the decision in the knowledge graph (and an ADR when triggered).",
    },
] + _sensitivity_hooks()


# --------------------------------------------------------------------------- config

def config_path(root: str) -> str:
    return os.path.join(os.path.abspath(root), HOOKS_RELPATH)


def default_config() -> dict:
    return {"version": CONFIG_VERSION, "include_defaults": True, "disabled": [], "hooks": []}


def _read_config(root: str) -> dict | None:
    path = config_path(root)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{HOOKS_RELPATH}: invalid JSON ({exc})") from exc


def effective_hooks(config: dict | None) -> list[dict]:
    """Defaults (unless excluded) overlaid by project hooks with the same id."""
    config = config or default_config()
    disabled = set(config.get("disabled") or [])
    merged: dict[str, dict] = {}
    if config.get("include_defaults", True):
        for hook in DEFAULT_HOOKS:
            merged[hook["id"]] = {**hook, "source": "default"}
    for hook in config.get("hooks") or []:
        merged[hook.get("id")] = {**hook, "source": "project"}
    return [hook for hook_id, hook in merged.items() if hook_id not in disabled]


def load_hooks(root: str) -> list[dict]:
    hooks = effective_hooks(_read_config(root))
    errors = validate_hooks(hooks)
    if errors:
        raise ValueError("invalid hooks: " + "; ".join(errors))
    return hooks


def init_config(root: str, force: bool = False) -> dict:
    path = config_path(root)
    if os.path.exists(path) and not force:
        raise ValueError(f"{HOOKS_RELPATH} already exists (use --force to overwrite)")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    config = default_config()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)
        fh.write("\n")
    return {"path": path, "config": config, "default_hooks": [h["id"] for h in DEFAULT_HOOKS]}


# --------------------------------------------------------------------------- validation

def _validate_when(when, where: str, errors: list[str]) -> None:
    if not isinstance(when, dict):
        errors.append(f"{where}: `when` must be an object")
        return
    for field, spec in when.items():
        if field == "any":
            if not isinstance(spec, list) or not spec:
                errors.append(f"{where}: `any` must be a non-empty list of conditions")
                continue
            for i, sub in enumerate(spec):
                _validate_when(sub, f"{where}.any[{i}]", errors)
            continue
        if not isinstance(spec, dict):
            continue  # scalar shorthand for equals
        for op, value in spec.items():
            if op not in OPERATORS:
                errors.append(f"{where}.{field}: unknown operator `{op}`")
            elif op == "matches":
                try:
                    re.compile(value)
                except (re.error, TypeError) as exc:
                    errors.append(f"{where}.{field}: invalid regex ({exc})")
            elif op in ("in", "not_in") and not isinstance(value, list):
                errors.append(f"{where}.{field}: `{op}` needs a list")


def validate_hooks(hooks: list[dict]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for index, hook in enumerate(hooks):
        hook_id = hook.get("id")
        where = f"hook[{index}]" + (f" `{hook_id}`" if hook_id else "")
        if not hook_id or not isinstance(hook_id, str):
            errors.append(f"{where}: missing string `id`")
        elif hook_id in seen:
            errors.append(f"{where}: duplicate id")
        else:
            seen.add(hook_id)
        on = hook.get("on")
        if not isinstance(on, list) or not on:
            errors.append(f"{where}: `on` must be a non-empty list of event types")
        else:
            for event in on:
                if event not in EVENT_TYPES:
                    errors.append(f"{where}: unknown event `{event}`")
        _validate_when(hook.get("when", {}), where, errors)
        action = hook.get("action")
        if not isinstance(action, dict) or action.get("type") not in ACTION_TYPES:
            errors.append(f"{where}: action.type must be one of {', '.join(ACTION_TYPES)}")
        elif action["type"] == "raise_tier" and action.get("floor") not in TIER_ORDER:
            errors.append(f"{where}: raise_tier needs floor in {', '.join(TIER_ORDER)}")
        elif action["type"] == "escalate" and not (action.get("kind") and action.get("raised_by")):
            errors.append(f"{where}: escalate needs `kind` and `raised_by`")
    return errors


# --------------------------------------------------------------------------- evaluation

_MISSING = object()


def resolve(payload: dict, dotted: str):
    value = payload
    for part in dotted.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return _MISSING
    return value


def _ci(value):
    return value.lower() if isinstance(value, str) else value


def _check(op: str, actual, expected) -> bool:
    if op == "exists":
        return (actual is not _MISSING) == bool(expected)
    if actual is _MISSING:
        return op in ("not_equals", "not_in")
    if op == "equals":
        return actual == expected
    if op == "not_equals":
        return actual != expected
    if op == "in":
        return actual in expected
    if op == "not_in":
        return actual not in expected
    if op == "contains":
        if isinstance(actual, str):
            return str(expected).lower() in actual.lower()
        if isinstance(actual, (list, tuple)):
            return _ci(expected) in [_ci(item) for item in actual]
        return False
    if op == "matches":
        pattern = re.compile(expected, re.IGNORECASE)
        items = actual if isinstance(actual, (list, tuple)) else [actual]
        return any(isinstance(item, str) and pattern.search(item) for item in items)
    try:
        if op == "gt":
            return actual > expected
        if op == "gte":
            return actual >= expected
        if op == "lt":
            return actual < expected
        if op == "lte":
            return actual <= expected
    except TypeError:
        return False
    return False


def matches(when: dict, payload: dict) -> bool:
    for field, spec in (when or {}).items():
        if field == "any":
            if not any(matches(sub, payload) for sub in spec):
                return False
            continue
        actual = resolve(payload, field)
        conditions = spec if isinstance(spec, dict) else {"equals": spec}
        for op, expected in conditions.items():
            if not _check(op, actual, expected):
                return False
    return True


def _render_params(action: dict, payload: dict) -> dict:
    """`"$field"` params are read from the event payload (dotted paths allowed)."""
    rendered = {}
    for key, value in action.items():
        if isinstance(value, str) and value.startswith("$") and len(value) > 1:
            found = resolve(payload, value[1:])
            rendered[key] = None if found is _MISSING else found
        else:
            rendered[key] = value
    return rendered


def evaluate(hooks: list[dict], event: dict) -> list[dict]:
    """Pure: which hooks fire for `event` ({"type", "payload"}) and with which action."""
    payload = event.get("payload") or {}
    fired = []
    for hook in hooks:
        if event.get("type") not in hook.get("on", []):
            continue
        if not matches(hook.get("when") or {}, payload):
            continue
        fired.append({"hook": hook["id"], "action": _render_params(hook["action"], payload)})
    return fired


# --------------------------------------------------------------------------- emission

def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_internal(root: str, action: dict, payload: dict) -> dict:
    try:
        if action["type"] == "render_dashboard":
            import dashboard  # lazy: optional at import time, never breaks the caller
            return {"executed": True, "output": dashboard.write(root)}
        if action["type"] == "record_decision":
            import decision_memory
            return {"executed": True, **decision_memory.record_from_event(root, payload)}
    except Exception as exc:  # noqa: BLE001 — hooks must never break the controller
        return {"executed": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"executed": False, "error": "unknown internal action"}


def _directive(fired: dict, payload: dict) -> dict:
    action = dict(fired["action"])
    directive = {"hook": fired["hook"], **action}
    if action["type"] == "escalate":
        try:
            directive["route"] = team_model.escalation_route(action.get("kind"), action.get("raised_by"))
        except ValueError as exc:
            directive["error"] = str(exc)
    for key in ("feature", "phase"):
        if key not in directive and key in payload:
            directive[key] = payload[key]
    return directive


def emit(root: str, event_type: str, payload: dict | None = None, hooks: list[dict] | None = None,
         execute_internal: bool = True, log: bool = True) -> dict:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event type: {event_type} (known: {', '.join(EVENT_TYPES)})")
    payload = dict(payload or {})
    hooks = load_hooks(root) if hooks is None else hooks
    event = {"id": uuid.uuid4().hex[:12], "type": event_type, "at": _now()}
    fired_entries = []
    directives = []
    for fired in evaluate(hooks, {"type": event_type, "payload": payload}):
        entry = {"hook": fired["hook"], "action": fired["action"]["type"]}
        if fired["action"]["type"] in INTERNAL_ACTIONS:
            if execute_internal:
                entry["result"] = _run_internal(root, fired["action"], payload)
            else:
                entry["result"] = {"executed": False, "reason": "internal actions disabled"}
        else:
            directive = _directive(fired, payload)
            directives.append(directive)
            entry["directive"] = directive
        fired_entries.append(entry)
    if log and fired_entries:
        _append_firing(root, {"event": {**event, "payload": payload}, "fired": fired_entries})
    return {"event": event, "fired": fired_entries, "directives": directives}


def safe_emit(root, event_type: str, payload: dict | None = None) -> dict | None:
    """emit() that never raises — for the controller and state transitions."""
    try:
        return emit(str(root), event_type, payload)
    except Exception:  # noqa: BLE001
        return None


def _append_firing(root: str, record: dict) -> None:
    path = os.path.join(os.path.abspath(root), FIRINGS_RELPATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_firings(root: str, limit: int | None = None, event_type: str | None = None) -> list[dict]:
    path = os.path.join(os.path.abspath(root), FIRINGS_RELPATH)
    if not os.path.isfile(path):
        return []
    records = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event_type and record.get("event", {}).get("type") != event_type:
                continue
            records.append(record)
    return records[-limit:] if limit else records


def project_root_for_state(state_path: str) -> str:
    """`<root>/.spec-master/state.json` -> `<root>`; any other location -> its directory."""
    parent = os.path.dirname(os.path.abspath(state_path))
    return os.path.dirname(parent) if os.path.basename(parent) == ".spec-master" else parent
