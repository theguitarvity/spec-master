"""Risk-adaptive ceremony for Spec Master (roadmap item 15).

Every feature is classified on two independent axes:

- **scope** — how much work: acceptance criteria / description size at
  intake, then the real task count, files and layers from `tasks.md` right
  before `implement` (scope is only clear after plan/tasks);
- **sensitivity** — what is touched: auth, payment, secrets, schema, public
  contract, external provider. Sensitivity is *not* a parallel trigger
  mechanism: it is whatever `raise_tier` actions the declarative hooks
  (`hooks.py`, events `feature.intake` / `feature.pre_implement`) return, so
  projects tune it in `.spec-master/hooks.json`.

The ceremony tier is the MAX of the scope tier, every sensitivity floor, and
the user's override — never scope alone, so a 3-line change in auth code does
not get the lightweight XS treatment. Users may force a tier *above* the
computed one; every override is appended to `.spec-master/risk/overrides.jsonl`
as a calibration signal for `calibration.py` (roadmap item 16).

Scope thresholds are data (`DEFAULT_THRESHOLDS`), overridable per project in
`.spec-master/risk/thresholds.json` (written by `calibration.apply`). The
intake context surface is the fingerprint delta (`context_delta.report`)
plus the decision nodes for the feature (`decision_memory`) — no separate
context pack. Pure stdlib; classification itself is read-only.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import re

import context_delta
import decision_memory
import hooks
import state as state_mod
import team_model

TIER_ORDER = hooks.TIER_ORDER  # ("XS", "S", "M", "L", "XL")
STAGES = ("intake", "pre_implement")
STAGE_EVENTS = {"intake": "feature.intake", "pre_implement": "feature.pre_implement"}

RISK_RELDIR = os.path.join(".spec-master", "risk")
THRESHOLDS_RELPATH = os.path.join(RISK_RELDIR, "thresholds.json")
OVERRIDES_RELPATH = os.path.join(RISK_RELDIR, "overrides.jsonl")
HISTORY_LIMIT = 20

# --------------------------------------------------------------------------- scope thresholds

# Upper limits per tier; a feature gets the smallest tier whose limits all
# hold for the signals measured at that stage (XL is the catch-all). Intake
# measures acceptance_criteria, description_words, files, layers (estimate);
# pre_implement measures tasks, files, layers from tasks.md.
SCOPE_SIGNALS = ("acceptance_criteria", "description_words", "tasks", "files", "layers")

DEFAULT_THRESHOLDS = {
    "XS": {"acceptance_criteria": 2, "description_words": 40, "tasks": 5, "files": 2, "layers": 1},
    "S": {"acceptance_criteria": 4, "description_words": 120, "tasks": 12, "files": 5, "layers": 2},
    "M": {"acceptance_criteria": 8, "description_words": 300, "tasks": 30, "files": 12, "layers": 3},
    "L": {"acceptance_criteria": 15, "description_words": 800, "tasks": 60, "files": 30, "layers": 5},
}
LIMITED_TIERS = TIER_ORDER[:-1]

# --------------------------------------------------------------------------- ceremony profiles

ADR_SENSITIVE_CATEGORIES = ("auth", "payment", "secrets", "external_provider")


def _profile(clarify: str, analyze: str, work_packages: bool, adr_check: bool, review: str, summary: str) -> dict:
    return {
        "phases": {"specify": "required", "clarify": clarify, "plan": "required", "tasks": "required",
                   "analyze": "required", "implement": "required", "validate": "required"},
        "clarify": clarify,
        "analyze": analyze,
        "work_packages": work_packages,
        "adr_check": adr_check,
        "review": review,
        "summary": summary,
    }


CEREMONY_PROFILES = {
    "XS": _profile("skippable", "light", False, False, "self",
                   "Trivial change: clarify may be SKIPPED, light analyze, author self-review plus gates."),
    "S": _profile("skippable", "light", False, False, "peer",
                  "Small change: clarify may be SKIPPED, light analyze, one peer review."),
    "M": _profile("required", "deep", False, False, "peer",
                  "Regular feature: full clarify and deep analyze, one peer review."),
    "L": _profile("required", "deep", True, True, "peer+tech-lead",
                  "Large or sensitive: full cycle, work packages per role, ADR check, Tech Lead approval."),
    "XL": _profile("required", "deep", True, True, "peer+tech-lead+architect",
                   "Very large: full cycle, work packages, ADR check, Tech Lead and Architect approval."),
}

# Work packages for L/XL, chained in this order (each depends on the previous).
WORK_PACKAGE_TEMPLATE = (
    {"kind": "contract", "owner_agent": "architect", "title": "Define or confirm the interface contracts"},
    {"kind": "data-model", "owner_agent": "backend-dev", "title": "Data model and migrations"},
    {"kind": "backend", "owner_agent": "backend-dev", "title": "Backend implementation"},
    {"kind": "frontend", "owner_agent": "frontend-dev", "title": "Frontend implementation"},
    {"kind": "e2e", "owner_agent": "qa", "title": "End-to-end and acceptance tests"},
    {"kind": "docs", "owner_agent": "tech-lead", "title": "Documentation and integration notes"},
)

# --------------------------------------------------------------------------- scope evidence

_EXT = (r"py|pyi|md|mdx|rst|txt|ts|tsx|js|jsx|mjs|cjs|json|ya?ml|toml|ini|cfg|conf|sql|go|rs|java|kt|kts|"
        r"scala|rb|php|cs|swift|mm?|c|h|cc|cpp|hpp|sh|bash|zsh|ps1|html?|css|scss|sass|less|vue|svelte|"
        r"proto|graphql|gql|prisma|tf|tfvars|hcl|xml|gradle|dart|exs?|erl|lua|ipynb|pem|key|p12|pfx|jks|"
        r"keystore|env|lock")
_EXT_RE = re.compile(rf"\.(?:{_EXT})$", re.IGNORECASE)
_PATH_TOKEN_RE = re.compile(
    r"(?<![\w./@-])"
    r"(\.?[\w-]+(?:\.[\w-]+)*/(?:[\w.-]+/)*[\w.-]*"      # dir/.../file or dir/
    r"|\.env(?:\.[\w-]+)*"                               # dotenv files
    rf"|[\w-]+(?:\.[\w-]+)*\.(?:{_EXT}))"                 # bare file with a known extension
    r"(?![\w/-])",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.IGNORECASE)
_TASK_LINE_RE = re.compile(r"^\s*[-*]\s*\[[ xX]\]\s*T\d+\b")
_SPECKIT_ARTIFACTS = {"spec.md", "plan.md", "tasks.md", "research.md", "data-model.md", "quickstart.md",
                      "constitution.md"}

# Path directory segment -> layer. tests/docs are recorded but never counted.
_PATH_LAYERS = {
    "ui": {"frontend", "web", "ui", "client", "components", "pages", "views", "screens", "public", "static",
           "styles", "assets"},
    "api": {"api", "apis", "routes", "controllers", "handlers", "endpoints", "graphql", "rest"},
    "domain": {"backend", "server", "services", "service", "domain", "core", "lib", "usecases", "use_cases"},
    "data": {"db", "database", "models", "migrations", "repositories", "repos", "schema", "schemas",
             "entities", "alembic", "prisma", "dao"},
    "infra": {"infra", "infrastructure", "terraform", "deploy", "deployment", "k8s", "helm", "docker",
              ".github", "ci", "ops", "ansible"},
    "cli": {"cli", "bin", "cmd", "scripts"},
    "tests": {"tests", "test", "e2e", "__tests__", "spec", "testing"},
    "docs": {"docs", "doc", "documentation"},
}
UNCOUNTED_LAYERS = ("tests", "docs")

# Intake only (no paths yet): layer keywords in the feature text, EN + PT.
_TEXT_LAYERS = {
    "ui": r"\b(?:ui|ux|front[\s-]?end|screens?|telas?|components?|componentes?|user\s+interface|"
          r"interface\s+(?:de\s+usu[áa]rio|gr[áa]fica))\b",
    "api": r"\b(?:apis?|endpoints?|rest|graphql|grpc|controllers?|rotas?\s+http|http\s+routes?)\b",
    "domain": r"\b(?:back[\s-]?end|business\s+logic|regras?\s+de\s+neg[óo]cio|domain\s+services?|"
              r"servi[çc]os?\s+de\s+dom[íi]nio)\b",
    "data": r"\b(?:database|banco\s+de\s+dados|db|tables?|tabelas?|migrations?|migra[çc](?:ão|ao|ões|oes)|"
            r"repositor(?:y|ies)|reposit[óo]rios?|schemas?)\b",
    "infra": r"\b(?:infra(?:structure|estrutura)?|deploy(?:ment)?|terraform|kubernetes|k8s|helm|docker|"
             r"ci/cd|pipelines?)\b",
    "cli": r"\b(?:cli|command[\s-]line|linha\s+de\s+comando)\b",
}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rank(tier: str) -> int:
    return TIER_ORDER.index(tier)


def normalize_tier(tier) -> str:
    value = str(tier or "").strip().upper()
    if value not in TIER_ORDER:
        raise ValueError(f"unknown tier `{tier}` (known: {', '.join(TIER_ORDER)})")
    return value


def max_tier(*tiers) -> str:
    present = [t for t in tiers if t]
    return max(present, key=rank) if present else TIER_ORDER[0]


def _ac_text(item) -> str:
    if isinstance(item, dict):
        return " ".join(str(v) for v in item.values() if isinstance(v, str))
    return str(item)


def feature_text(feature: dict) -> str:
    parts = [feature.get("name") or "", feature.get("description") or ""]
    parts += [_ac_text(item) for item in feature.get("acceptance_criteria") or []]
    return "\n".join(p for p in parts if p)


def extract_paths(text: str, spec_directory: str | None = None) -> list[str]:
    """Path-like tokens: files with a known extension (bare or nested), `.env*`
    and `dir/` mentions. Spec Kit's own artifacts (spec.md, contracts/*.md,
    specs/...) describe the work rather than being touched by it, so they
    are dropped."""
    text = _URL_RE.sub(" ", text or "")
    text = re.sub(r"(?<![\w.])\./", "", text)
    spec_prefix = (spec_directory or "").strip("/")
    found: list[str] = []
    for match in _PATH_TOKEN_RE.finditer(text):
        token = match.group(1).rstrip(".-")
        if not token or token in found:
            continue
        if not is_file_path(token) and not token.endswith("/"):
            continue  # "and/or", "load/mutate/save", "US1/US2" are prose, not paths
        segments = token.strip("/").split("/")
        if segments[0] == "specs" or (spec_prefix and token.startswith(spec_prefix)):
            continue
        if segments[-1] in _SPECKIT_ARTIFACTS and len(segments) == 1:
            continue
        if segments[0] in ("contracts", "checklists") and token.endswith(".md"):
            continue
        if segments[0] == ".specify":
            continue
        found.append(token)
    return found


def path_layer(path: str) -> str | None:
    segments = [s.lower() for s in path.strip("/").split("/")]
    dirs = segments if path.endswith("/") else segments[:-1]
    for segment in reversed(dirs):
        for layer, names in _PATH_LAYERS.items():
            if segment in names:
                return layer
    if not dirs:
        return None
    # tool/config dot-dirs (.spec-master/, .claude/, .vscode/ ...) are one layer
    return "config" if dirs[0].startswith(".") else f"dir:{dirs[0]}"


def text_layers(text: str) -> list[str]:
    return [layer for layer, pattern in _TEXT_LAYERS.items() if re.search(pattern, text or "", re.IGNORECASE)]


def task_blocks(text: str) -> list[str]:
    """Each Spec Kit task line joined with its indented continuation lines
    (`context_delta.parse_tasks` only keeps the first line, but file paths
    usually wrap onto the next ones)."""
    blocks: list[list[str]] = []
    current: list[str] | None = None
    for line in (text or "").splitlines():
        if _TASK_LINE_RE.match(line):
            current = [line.strip()]
            blocks.append(current)
        elif current is not None and line.strip() and line[:1].isspace():
            current.append(line.strip())
        else:
            current = None
    return [" ".join(block) for block in blocks]


def _read_text(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


def is_file_path(path: str) -> bool:
    return bool(_EXT_RE.search(path) or re.search(r"(?:^|/)\.env(?:\.[\w-]+)*$", path))


def _layer_summary(paths: list[str], fallback_text: str | None) -> tuple[list[str], list[str]]:
    layers: list[str] = []
    for path in paths:
        layer = path_layer(path)
        if layer and layer not in layers:
            layers.append(layer)
    if fallback_text is not None:
        for layer in text_layers(fallback_text):
            if layer not in layers:
                layers.append(layer)
    counted = [layer for layer in layers if layer not in UNCOUNTED_LAYERS]
    return layers, counted


def gather_evidence(root: str, feature: dict, stage: str, paths: list[str] | None = None) -> dict:
    """Signals + the hook payload for one stage. Read-only."""
    if stage not in STAGES:
        raise ValueError(f"unknown stage `{stage}` (known: {', '.join(STAGES)})")
    root = os.path.abspath(root)
    spec_dir = feature.get("spec_directory")
    base_text = feature_text(feature)
    hint_paths = [p for p in list(feature.get("paths") or []) + list(paths or []) if isinstance(p, str) and p]
    warnings: list[str] = []
    source = "estimate"
    text = base_text
    tasks_count = None
    task_text = ""
    if stage == "pre_implement":
        tasks_rel = os.path.join(spec_dir, "tasks.md") if spec_dir else None
        tasks_raw = _read_text(os.path.join(root, tasks_rel)) if tasks_rel else None
        if tasks_raw is None:
            warnings.append("tasks.md not found — pre_implement scope estimated from intake signals")
        else:
            source = "tasks.md"
            tasks_count = len(context_delta.parse_tasks(tasks_raw))
            task_text = "\n".join(task_blocks(tasks_raw))
            text = base_text + "\n" + task_text
    extracted = extract_paths(base_text + "\n" + task_text, spec_dir)
    all_paths = list(dict.fromkeys(hint_paths + extracted))
    files = [p for p in all_paths if is_file_path(p)]
    use_text_layers = source == "estimate" or not all_paths
    layers, counted = _layer_summary(all_paths, base_text if use_text_layers else None)
    if source == "tasks.md":
        signals = {"tasks": tasks_count, "files": len(files), "layers": len(counted)}
    else:
        description = feature.get("description") or ""
        signals = {
            "acceptance_criteria": len(feature.get("acceptance_criteria") or []),
            "description_words": len(re.findall(r"\w+", description)),
            "files": len(files),
            "layers": len(counted),
        }
    payload = {"feature": feature.get("id"), "text": text, "paths": all_paths}
    return {"signals": signals, "source": source, "paths": all_paths, "layers": layers,
            "warnings": warnings, "payload": payload}


# --------------------------------------------------------------------------- thresholds

def thresholds_path(root: str) -> str:
    return os.path.join(os.path.abspath(root), THRESHOLDS_RELPATH)


def validate_thresholds(thresholds: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(thresholds, dict):
        return ["thresholds must be an object of tier -> {signal: limit}"]
    for tier, limits in thresholds.items():
        if tier == "XL":
            errors.append("XL is the catch-all tier and takes no limits")
            continue
        if tier not in LIMITED_TIERS:
            errors.append(f"unknown tier `{tier}` (limited tiers: {', '.join(LIMITED_TIERS)})")
            continue
        if not isinstance(limits, dict):
            errors.append(f"{tier}: limits must be an object")
            continue
        for signal, value in limits.items():
            if signal not in SCOPE_SIGNALS:
                errors.append(f"{tier}.{signal}: unknown signal (known: {', '.join(SCOPE_SIGNALS)})")
            elif isinstance(value, bool) or not isinstance(value, int) or value < 1:
                errors.append(f"{tier}.{signal}: limit must be an integer >= 1")
    if errors:
        return errors
    for signal in SCOPE_SIGNALS:
        values = [(t, thresholds[t][signal]) for t in LIMITED_TIERS if signal in thresholds.get(t, {})]
        for (t1, v1), (t2, v2) in zip(values, values[1:]):
            if v2 < v1:
                errors.append(f"{signal}: {t2} limit ({v2}) is below {t1} limit ({v1}) — tiers must be monotonic")
    return errors


def merge_thresholds(overrides: dict | None) -> dict:
    merged = copy.deepcopy(DEFAULT_THRESHOLDS)
    for tier, limits in (overrides or {}).items():
        if tier in merged and isinstance(limits, dict):
            merged[tier].update(limits)
    errors = validate_thresholds({t: l for t, l in (overrides or {}).items()}) or validate_thresholds(merged)
    if errors:
        raise ValueError("invalid risk thresholds: " + "; ".join(errors))
    return merged


def read_thresholds_file(root: str) -> dict | None:
    path = thresholds_path(root)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{THRESHOLDS_RELPATH}: invalid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{THRESHOLDS_RELPATH}: expected an object")
    if "tiers" in data:
        return data["tiers"]
    return {k: v for k, v in data.items() if k in TIER_ORDER}


def load_thresholds(root: str | None = None) -> dict:
    """DEFAULT_THRESHOLDS merged with `.spec-master/risk/thresholds.json`."""
    return merge_thresholds(read_thresholds_file(root) if root else None)


def scope_tier(signals: dict, thresholds: dict) -> tuple[str, list[dict]]:
    """Smallest tier whose limits all hold, else XL; plus the signals that
    ruled out the tier just below (why it is not smaller)."""
    measured = {k: v for k, v in signals.items() if v is not None}
    previous_limits = None
    previous_tier = None
    for tier in LIMITED_TIERS:
        limits = thresholds.get(tier, {})
        if all(value <= limits[name] for name, value in measured.items() if name in limits):
            return tier, _binding(measured, previous_tier, previous_limits)
        previous_tier, previous_limits = tier, limits
    return "XL", _binding(measured, previous_tier, previous_limits)


def _binding(measured: dict, tier: str | None, limits: dict | None) -> list[dict]:
    if not tier:
        return []
    return [{"signal": name, "value": value, "limit": limits[name], "exceeds": tier}
            for name, value in measured.items() if name in limits and value > limits[name]]


# --------------------------------------------------------------------------- profiles & packages

def profile_for(tier: str, sensitivity_categories=()) -> dict:
    tier = normalize_tier(tier)
    profile = copy.deepcopy(CEREMONY_PROFILES[tier])
    profile["tier"] = tier
    sensitive = sorted(set(sensitivity_categories) & set(ADR_SENSITIVE_CATEGORIES))
    if sensitive and not profile["adr_check"]:
        profile["adr_check"] = True
        profile["adr_reason"] = "sensitivity: " + ", ".join(sensitive)
    elif profile["adr_check"]:
        profile["adr_reason"] = f"tier {tier}" + (f" + sensitivity: {', '.join(sensitive)}" if sensitive else "")
    return profile


def _reviewer_for(owner: str) -> str:
    reviewer = team_model.assign_peer_review(owner)
    return "architect" if reviewer == owner else reviewer


def work_packages(feature_id: str, tier: str) -> list[dict]:
    """Chained role packages for L/XL (empty for smaller tiers). Same shape as
    `team workstreams` packages, so `workstreams review/integrate` accept them."""
    tier = normalize_tier(tier)
    if not CEREMONY_PROFILES[tier]["work_packages"]:
        return []
    packages = []
    previous = None
    for template in WORK_PACKAGE_TEMPLATE:
        package_id = f"{feature_id}-wp-{template['kind']}"
        packages.append({
            "id": package_id,
            "feature_id": feature_id,
            "kind": template["kind"],
            "title": template["title"],
            "owner_agent": template["owner_agent"],
            "reviewer_agent": _reviewer_for(template["owner_agent"]),
            "depends_on": [previous] if previous else [],
        })
        previous = package_id
    return packages


def obligations_added(old_tier: str, new_tier: str, old_categories=(), new_categories=()) -> list[dict]:
    """Profile obligations present at `new_tier` that `old_tier` did not impose."""
    old = profile_for(old_tier, old_categories)
    new = profile_for(new_tier, new_categories)
    added = []
    if old["clarify"] == "skippable" and new["clarify"] == "required":
        added.append({"obligation": "clarify", "from": "skippable", "to": "required"})
    if old["analyze"] == "light" and new["analyze"] == "deep":
        added.append({"obligation": "analyze", "from": "light", "to": "deep"})
    if not old["work_packages"] and new["work_packages"]:
        added.append({"obligation": "work_packages", "from": False, "to": True})
    if not old["adr_check"] and new["adr_check"]:
        added.append({"obligation": "adr_check", "from": False, "to": True})
    if old["review"] != new["review"]:
        added.append({"obligation": "review", "from": old["review"], "to": new["review"]})
    return added


# --------------------------------------------------------------------------- context

def intake_context(root: str, state: dict | None, feature_id: str, limit: int = 5) -> dict:
    """What already changed (fingerprint delta) + what was already decided
    (decision nodes) for this feature. Small on purpose."""
    context: dict = {}
    try:
        report = context_delta.report(root, state)
        context["delta"] = {
            "baseline": report.get("baseline", False),
            "since": report.get("since"),
            "summary": report.get("summary", {}),
            "artifacts": [
                {"artifact": e["artifact"], "change": e["change"], "kind": e["kind"]}
                for e in report.get("artifacts", []) if e.get("feature") in (None, feature_id)
            ][:10],
            "stale_phases": {k: v for k, v in report.get("stale_phases", {}).items() if k in ("*", feature_id)},
        }
    except Exception as exc:  # noqa: BLE001 — context must never block classification
        context["delta"] = {"baseline": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        context["decisions"] = [
            {"id": d["id"], "title": d.get("title"), "kind": d.get("kind"), "decided_by": d.get("decided_by"),
             "decision": (d.get("decision") or "")[:240], "recorded_at": d.get("recorded_at"), "adr": d.get("adr")}
            for d in decision_memory.decisions_for_feature(root, feature_id, limit=limit)
        ]
    except Exception as exc:  # noqa: BLE001
        context["decisions"] = []
        context["decisions_error"] = f"{type(exc).__name__}: {exc}"
    return context


# --------------------------------------------------------------------------- classification

def _sensitivity(hooks_list: list[dict], event_type: str, payload: dict) -> list[dict]:
    found = []
    for fired in hooks.evaluate(hooks_list, {"type": event_type, "payload": payload}):
        action = fired["action"]
        if action.get("type") != "raise_tier" or action.get("floor") not in TIER_ORDER:
            continue
        found.append({"category": action.get("category") or fired["hook"], "floor": action["floor"],
                      "hook": fired["hook"]})
    return found


def _intake_baseline(feature: dict) -> tuple[str | None, list[str]]:
    risk = feature.get("risk") or {}
    for entry in reversed(risk.get("history") or []):
        if entry.get("stage") == "intake":
            return entry.get("tier"), list(entry.get("sensitivity") or [])
    if risk.get("stage") == "intake" and risk.get("tier"):
        return risk["tier"], list(risk.get("sensitivity") or [])
    return None, []


def classify(root: str, state: dict, feature_id: str, stage: str = "intake", *, paths: list[str] | None = None,
             hooks_list: list[dict] | None = None, thresholds: dict | None = None,
             include_context: bool = True) -> dict:
    """Pure classification (writes nothing). tier = max(scope, floors, override)."""
    if stage not in STAGES:
        raise ValueError(f"unknown stage `{stage}` (known: {', '.join(STAGES)})")
    root = os.path.abspath(root)
    feature = state_mod.find_feature(state, feature_id)
    thresholds = load_thresholds(root) if thresholds is None else merge_thresholds(thresholds)
    hooks_list = hooks.load_hooks(root) if hooks_list is None else hooks_list

    evidence = gather_evidence(root, feature, stage, paths)
    scope, binding = scope_tier(evidence["signals"], thresholds)
    event_type = STAGE_EVENTS[stage]
    sensitivity = _sensitivity(hooks_list, event_type, evidence["payload"])
    categories = sorted({s["category"] for s in sensitivity})
    computed = max_tier(scope, *(s["floor"] for s in sensitivity))
    override = (feature.get("risk") or {}).get("override")
    tier = max_tier(computed, (override or {}).get("tier"))
    profile = profile_for(tier, categories)

    result = {
        "feature": feature_id,
        "stage": stage,
        "scope": {"tier": scope, "source": evidence["source"], "signals": evidence["signals"],
                  "binding": binding, "paths": evidence["paths"][:25], "layers": evidence["layers"]},
        "sensitivity": sensitivity,
        "override": override,
        "computed_tier": computed,
        "tier": tier,
        "profile": profile,
        "work_packages": work_packages(feature_id, tier) if profile["work_packages"] else [],
        "event": {"type": event_type, "paths": len(evidence["payload"]["paths"]),
                  "text_chars": len(evidence["payload"]["text"])},
        "escalated": False,
        "warnings": evidence["warnings"],
    }
    if stage == "pre_implement":
        baseline, baseline_categories = _intake_baseline(feature)
        baseline_source = "stored"
        if baseline is None:
            intake = classify(root, state, feature_id, "intake", paths=paths, hooks_list=hooks_list,
                              thresholds=thresholds, include_context=False)
            baseline = intake["tier"]
            baseline_categories = [s["category"] for s in intake["sensitivity"]]
            baseline_source = "computed"
        result["baseline"] = {"tier": baseline, "source": baseline_source}
        if rank(tier) > rank(baseline):
            added = obligations_added(baseline, tier, baseline_categories, categories)
            phases = feature.get("phases") or {}
            rerun = []
            if any(a["obligation"] == "clarify" for a in added) and phases.get("clarify") != "PASSED":
                rerun.append("clarify")
            if any(a["obligation"] == "analyze" for a in added):
                rerun.append("analyze")
            result.update({"escalated": True, "added_obligations": added, "rerun_phases": rerun})
        elif rank(tier) < rank(baseline):
            result["deescalated"] = True
    if include_context:
        result["context"] = intake_context(root, state, feature_id)
    result["classified_at"] = _now()
    return result


def event_payload(root: str, state: dict, feature_id: str, stage: str,
                  paths: list[str] | None = None) -> tuple[str, dict]:
    """(event type, payload) exactly as `classify` evaluates it."""
    feature = state_mod.find_feature(state, feature_id)
    return STAGE_EVENTS[stage], gather_evidence(root, feature, stage, paths)["payload"]


def emit_event(root: str, state: dict, feature_id: str, stage: str, paths: list[str] | None = None) -> dict | None:
    """Emit the stage event through the hooks so the sensitivity firings are
    logged in `.spec-master/hooks/firings.jsonl`. Never raises."""
    try:
        event_type, payload = event_payload(root, state, feature_id, stage, paths)
    except Exception:  # noqa: BLE001
        return None
    return hooks.safe_emit(root, event_type, payload)


def save_classification(state: dict, feature_id: str, classification: dict) -> dict:
    """Persist into `feature["risk"]` (the dashboard reads `feature["risk"]["tier"]`)."""
    feature = state_mod.find_feature(state, feature_id)
    previous = feature.get("risk") or {}
    categories = sorted({s["category"] for s in classification.get("sensitivity") or []})
    entry = {"stage": classification["stage"], "tier": classification["tier"],
             "computed_tier": classification["computed_tier"], "scope_tier": classification["scope"]["tier"],
             "sensitivity": categories, "at": classification.get("classified_at") or _now()}
    if classification.get("escalated"):
        entry["escalated"] = True
    history = list(previous.get("history") or []) + [entry]
    feature["risk"] = {
        "tier": classification["tier"],
        "computed_tier": classification["computed_tier"],
        "stage": classification["stage"],
        "scope_tier": classification["scope"]["tier"],
        "sensitivity": categories,
        "override": previous.get("override"),
        "escalated": bool(classification.get("escalated")),
        "classified_at": entry["at"],
        "history": history[-HISTORY_LIMIT:],
    }
    return feature["risk"]


# --------------------------------------------------------------------------- overrides

def overrides_path(root: str) -> str:
    return os.path.join(os.path.abspath(root), OVERRIDES_RELPATH)


def read_overrides(root: str) -> list[dict]:
    path = overrides_path(root)
    if not os.path.isfile(path):
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _append_override(root: str, entry: dict) -> str:
    path = overrides_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def override(root: str, state: dict, feature_id: str, tier: str, reason: str, by: str = "user") -> dict:
    """Force the feature's tier upward (mutates `state`; the caller saves it).

    Every attempt is appended to overrides.jsonl: accepted ones
    (`accepted: true`) are "tier was underestimated" calibration signals;
    a downward attempt is logged with `accepted: false` and raises ValueError.
    """
    tier = normalize_tier(tier)
    if not reason or not str(reason).strip():
        raise ValueError("an override needs a reason")
    feature = state_mod.find_feature(state, feature_id)
    if not (feature.get("risk") or {}).get("tier"):
        save_classification(state, feature_id, classify(root, state, feature_id, "intake", include_context=False))
    risk = feature["risk"]
    current = risk["tier"]
    computed = risk.get("computed_tier") or current
    at = _now()
    entry = {"feature": feature_id, "computed_tier": computed, "previous_tier": current, "forced_tier": tier,
             "reason": str(reason).strip(), "by": by, "stage": risk.get("stage"), "at": at}
    if rank(tier) < rank(current):
        _append_override(root, dict(entry, accepted=False))
        raise ValueError(f"overrides can only raise the tier: {tier} is below the current tier {current} "
                         f"for `{feature_id}`")
    entry["accepted"] = True
    path = _append_override(root, entry)
    categories = risk.get("sensitivity") or []
    risk["override"] = {"tier": tier, "reason": entry["reason"], "by": by, "at": at, "computed_tier": computed}
    risk["tier"] = tier
    risk["history"] = (list(risk.get("history") or []) + [{"stage": "override", "tier": tier, "at": at}])[-HISTORY_LIMIT:]
    profile = profile_for(tier, categories)
    return {
        "feature": feature_id,
        "override": entry,
        "raised": rank(tier) > rank(current),
        "added_obligations": obligations_added(current, tier, categories, categories),
        "profile": profile,
        "work_packages": work_packages(feature_id, tier) if profile["work_packages"] else [],
        "risk": risk,
        "log": path,
    }
