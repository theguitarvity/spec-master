"""Lane triage: how much process a change needs, decided before any artifact.

Three lanes replace the fixed seven-phase cycle (opt-in until the
constitution amendment is approved):

- patch    — one-sentence intent, a few production files in one module, no
             sensitive path, no dependency or irreversible change, tested.
             triage -> implement -> verify:post. Artifact: a change note.
- standard — everything that is not patch and has no critical signal.
             (Opt-in lane of wave 2; today it runs the legacy Spec Kit flow.)
- critical — sensitive paths, schema/migrations, irreversible actions, large
             blast radius, no executable verification, or a project floor.
             The full Spec Kit cycle.

Signals come from paths (declared by the agent after a read-only look, and
later from the real diff), from the repository and from the project policy.
Text is never enough on its own: a sensitive word in the intent becomes a
confirmation question, not a lane change. An override can only raise the
lane. Stdlib only, read-only.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re

import hooks
import quality_gates
import risk_profile

from kernel import paths as paths_mod

LANES = ("patch", "standard", "critical")
_RANK = {lane: index for index, lane in enumerate(LANES)}

POLICY_RELPATH = os.path.join(".spec-master", "policy.json")

# Initial limits; `.spec-master/policy.json` may tighten or loosen them.
DEFAULT_LIMITS = {
    "patch": {"files": 3, "modules": 1, "loc": 50},
    "standard": {"files": 12, "layers": 3, "loc": 800},
}

# Path sensitivity: category -> lane it forces. Critical categories are the
# ones the proposal routes to the full cycle; the others need a confirmation
# (additive or breaking? new provider or existing one?) and at least standard.
CRITICAL_CATEGORIES = ("auth", "payment", "secrets", "schema", "irreversible")
CONFIRM_CATEGORIES = ("public_contract", "external_provider")

QUESTIONS = {
    "public_contract": "Does the change break the public contract (removed/renamed field, endpoint or behavior)?",
    "external_provider": "Does the change add a new external provider or runtime dependency?",
    "irreversible": "Does the change push, open a PR/MR, publish a package or deploy?",
    "auth": "Does the change touch authentication or authorization?",
    "payment": "Does the change touch payments or billing?",
    "secrets": "Does the change handle secrets, keys or credentials?",
    "schema": "Does the change alter a database schema or migrate data?",
}


def rank(lane: str) -> int:
    return _RANK[lane]


def max_lane(*lanes: str) -> str:
    present = [lane for lane in lanes if lane]
    return max(present, key=rank) if present else LANES[0]


def load_policy(root: str) -> dict:
    """`.spec-master/policy.json` (optional): min_lane, sensitive_paths,
    hooks_mode (audit|block), limits. Invalid content raises ValueError."""
    path = os.path.join(root, POLICY_RELPATH)
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{POLICY_RELPATH} must be a JSON object")
    if data.get("min_lane") not in (None, *LANES):
        raise ValueError(f"{POLICY_RELPATH}: min_lane must be one of {', '.join(LANES)}")
    if data.get("hooks_mode") not in (None, "audit", "block"):
        raise ValueError(f"{POLICY_RELPATH}: hooks_mode must be audit or block")
    if not isinstance(data.get("sensitive_paths", []), list):
        raise ValueError(f"{POLICY_RELPATH}: sensitive_paths must be a list of globs")
    if data.get("audit_started_at") is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}",
                                                                      str(data["audit_started_at"])):
        raise ValueError(f"{POLICY_RELPATH}: audit_started_at must be a YYYY-MM-DD date")
    return data


def limits(policy: dict) -> dict:
    merged = {lane: dict(values) for lane, values in DEFAULT_LIMITS.items()}
    for lane, values in (policy.get("limits") or {}).items():
        if lane in merged and isinstance(values, dict):
            merged[lane].update({k: v for k, v in values.items() if isinstance(v, int) and v > 0})
    return merged


_norm = paths_mod.norm
is_test_path = paths_mod.is_test_path
is_doc_path = paths_mod.is_doc_path
is_manifest = paths_mod.is_manifest
production_files = paths_mod.production_files


def path_categories(paths, policy: dict) -> dict:
    """category -> [paths] from the sensitivity path rules and the project's
    own `sensitive_paths` globs (reported as `project`)."""
    found: dict[str, list[str]] = {}
    for path in paths:
        for category, rule in hooks.SENSITIVITY_RULES.items():
            if re.search(rule["paths"], path, re.IGNORECASE):
                found.setdefault(category, []).append(path)
        for pattern in policy.get("sensitive_paths") or []:
            if fnmatch.fnmatch(path, pattern):
                found.setdefault("project", []).append(path)
    return found


def text_categories(text: str) -> list[str]:
    return [category for category, rule in hooks.SENSITIVITY_RULES.items()
            if re.search(rule["text"], text or "", re.IGNORECASE)]


_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".spec-master", "dist", "build", ".tox"}


def test_stems(root: str, max_depth: int = 6) -> set[str]:
    """File stems of every test file in the repository (walked once)."""
    stems: set[str] = set()
    base_depth = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        if dirpath.count(os.sep) - base_depth >= max_depth:
            dirnames[:] = []
        relative_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
        for filename in filenames:
            relative = filename if relative_dir == "." else f"{relative_dir}/{filename}"
            if is_test_path(relative):
                stems.add(os.path.splitext(filename)[0])
    return stems


def _candidates(path: str) -> set[str]:
    stem = os.path.splitext(path.rsplit("/", 1)[-1])[0]
    return {f"test_{stem}", f"{stem}_test", f"{stem}.test", f"{stem}.spec", f"{stem}Test", f"{stem}Tests"}


def _has_test_for(path: str, known_stems: set[str], declared_tests: list[str]) -> bool:
    declared = {os.path.splitext(p.rsplit("/", 1)[-1])[0] for p in declared_tests}
    return bool(_candidates(path) & (known_stems | declared))


def has_test_gate(root: str) -> bool:
    try:
        gates = quality_gates.detect(root)
    except Exception:  # noqa: BLE001 - a broken manifest means no provable gate
        return False
    return any("test" in (gate.get("name") or "") or gate.get("category") == "test" for gate in gates)


def triage(root: str, *, intent: str, paths=(), confirmed=(), denied=(), unresolved: int = 0,
           loc: int | None = None, requested: str | None = None, policy: dict | None = None,
           test_gate: bool | None = None) -> dict:
    """Decide the lane for a change. Pure, read-only.

    `paths` are the files the change will touch (repo-relative); `confirmed`
    and `denied` are answers to earlier `questions`; `loc` is the diff size
    when known (re-triage during the work); `requested` can only raise.
    """
    root = os.path.abspath(root)
    policy = load_policy(root) if policy is None else policy
    caps = limits(policy)
    paths = sorted({_norm(p) for p in paths if p and _norm(p)})
    production = production_files(paths)
    tests = [p for p in paths if is_test_path(p)]
    modules = sorted({paths_mod.module_of(p) for p in production})
    layers = sorted({risk_profile.path_layer(p) or "root" for p in production} - set(risk_profile.UNCOUNTED_LAYERS))
    categories = path_categories(paths, policy)
    manifests = [p for p in paths if is_manifest(p)]
    test_gate = has_test_gate(root) if test_gate is None else test_gate
    # "The module has a test, or the change brings one": when the change
    # declares test files, verify:post checks that every acceptance check is
    # linked to an existing test and that the gates pass.
    stems = test_stems(root) if production and not tests else set()
    untested = [] if tests else [p for p in production
                                 if not p.endswith("__init__.py") and not _has_test_for(p, stems, tests)]

    critical, standard = [], []

    def add(bucket, signal, detail):
        bucket.append({"signal": signal, "detail": detail})

    for category in CRITICAL_CATEGORIES:
        if categories.get(category):
            add(critical, f"sensitive:{category}", ", ".join(categories[category][:5]))
    if categories.get("project"):
        add(critical, "sensitive:project", ", ".join(categories["project"][:5]))
    for category in CONFIRM_CATEGORIES:
        if categories.get(category):
            add(standard, f"sensitive:{category}", ", ".join(categories[category][:5]))
    for category in confirmed:
        add(critical, f"confirmed:{category}", QUESTIONS.get(category, category))
    if len(production) > caps["standard"]["files"]:
        add(critical, "files", f"{len(production)} production files > {caps['standard']['files']}")
    if len(layers) > caps["standard"]["layers"]:
        add(critical, "layers", f"{len(layers)} layers > {caps['standard']['layers']}")
    if loc is not None and loc > caps["standard"]["loc"]:
        add(critical, "loc", f"{loc} changed lines > {caps['standard']['loc']}")
    if not test_gate:
        add(critical, "no_test_gate", "no executable test gate detected or declared (.spec-master/gates.json)")
    if policy.get("min_lane") == "critical":
        add(critical, "policy", "min_lane: critical")

    if not paths:
        add(standard, "no_paths", "no files declared — nothing proves the change is small")
    if len(production) > caps["patch"]["files"]:
        add(standard, "files", f"{len(production)} production files > {caps['patch']['files']}")
    if len(modules) > caps["patch"]["modules"]:
        add(standard, "modules", f"{len(modules)} modules > {caps['patch']['modules']}")
    if loc is not None and loc > caps["patch"]["loc"]:
        add(standard, "loc", f"{loc} changed lines > {caps['patch']['loc']}")
    if manifests:
        add(standard, "manifest", ", ".join(manifests))
    if untested:
        add(standard, "untested", "no test found or declared for " + ", ".join(untested[:5]))
    if unresolved:
        add(standard, "unresolved", f"{unresolved} UNRESOLVED item(s)")
    if policy.get("min_lane") == "standard":
        add(standard, "policy", "min_lane: standard")

    computed = "critical" if critical else "standard" if standard else "patch"
    lane = max_lane(computed, requested)
    answered = set(confirmed) | set(denied)
    path_hit = set(categories)
    questions = [
        {"signal": category, "question": QUESTIONS[category]}
        for category in text_categories(intent)
        if category in QUESTIONS and category not in answered and category not in path_hit
    ]
    return {
        "lane": lane,
        "computed_lane": computed,
        "requested_lane": requested,
        "reasons": {"critical": critical, "standard": standard},
        "signals": {
            "files": len(production), "tests": len(tests), "modules": modules, "layers": layers,
            "sensitive": {k: v[:5] for k, v in categories.items()}, "manifests": manifests,
            "untested": untested, "test_gate": test_gate, "loc": loc,
        },
        "questions": questions,
        "paths": paths,
    }


def escalation(previous: str, current: dict) -> dict | None:
    """Directive when a re-triage (by the real diff) lands above the lane in use."""
    if rank(current["lane"]) <= rank(previous):
        return None
    reasons = current["reasons"]["critical"] if current["lane"] == "critical" else current["reasons"]["standard"]
    return {"type": "escalate", "from": previous, "to": current["lane"],
            "because": [f"{r['signal']}: {r['detail']}" for r in reasons]}
