"""SAST / secrets scanners promoted to blocking quality gates (roadmap item 4).

Same rule as quality_gates.py: nothing is hardcoded per project. A scanner
becomes a gate only when the target repository already carries evidence of
it (a scanner config file, a CI workflow that runs it, a pre-commit hook, or
a package script that wraps it). No evidence -> no gate; an absent scanner is
never reported as a failure.

Gates found here are always `blocking: true` — once a repository opted into
a scanner, its findings block completion instead of staying a manual
suggestion of the Security Agent.

`execution` is "local" when the core can hand back a runnable command, or
"ci" when the scanner only runs in the repository's CI (CodeQL, `semgrep ci`
against the hosted registry). CI gates carry `command: None`: the
orchestrator must confirm the CI check result before declaring SUCCESS.
"""
from __future__ import annotations

import json
import os
import re

_SEMGREP_CONFIGS = (".semgrep.yml", ".semgrep.yaml", "semgrep.yml", "semgrep.yaml")
_BANDIT_CONFIGS = ("bandit.yml", "bandit.yaml")
_GITLEAKS_CONFIGS = (".gitleaks.toml", "gitleaks.toml")
_SECURITY_SCRIPT_NAMES = ("sast", "security", "security:scan", "scan:security", "semgrep")
_PRE_COMMIT_TOOLS = ("semgrep", "bandit", "gitleaks")

_CODEQL_RE = re.compile(r"github/codeql-action", re.IGNORECASE)
_SEMGREP_CI_RE = re.compile(r"semgrep(?:/semgrep|-action|\s+ci\b)", re.IGNORECASE)
_PRE_COMMIT_ID_RE = re.compile(r"^\s*-?\s*id:\s*([\w.-]+)\s*$", re.MULTILINE)


def _rel(root: str, path: str) -> str:
    return os.path.relpath(path, root)


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _workflow_files(root: str) -> list[str]:
    workflows = os.path.join(root, ".github", "workflows")
    if not os.path.isdir(workflows):
        return []
    return sorted(
        os.path.join(workflows, name) for name in os.listdir(workflows)
        if name.endswith((".yml", ".yaml"))
    )


def _gate(tool: str, category: str, command: str | None, execution: str, evidence: list[str]) -> dict:
    return {
        "name": f"{category} ({tool})",
        "command": command,
        "blocking": True,
        "category": category,
        "tool": tool,
        "execution": execution,
        "evidence": evidence,
    }


def _semgrep(root: str, workflows: list[str]) -> dict | None:
    for name in _SEMGREP_CONFIGS:
        path = os.path.join(root, name)
        if os.path.isfile(path):
            return _gate("semgrep", "sast", f"semgrep scan --config {name} --error", "local", [name])
    rules_dir = os.path.join(root, ".semgrep")
    if os.path.isdir(rules_dir) and any(f.endswith((".yml", ".yaml")) for f in os.listdir(rules_dir)):
        return _gate("semgrep", "sast", "semgrep scan --config .semgrep --error", "local", [".semgrep"])
    ci = [_rel(root, wf) for wf in workflows if _SEMGREP_CI_RE.search(_read(wf))]
    if ci:
        return _gate("semgrep", "sast", None, "ci", ci)
    return None


def _codeql(root: str, workflows: list[str]) -> dict | None:
    evidence = [_rel(root, wf) for wf in workflows if _CODEQL_RE.search(_read(wf))]
    if not evidence:
        return None
    for extra in (os.path.join(".github", "codeql", "codeql-config.yml"),
                  os.path.join(".github", "codeql", "codeql-config.yaml")):
        if os.path.isfile(os.path.join(root, extra)):
            evidence.append(extra)
    return _gate("codeql", "sast", None, "ci", evidence)


def _bandit(root: str) -> dict | None:
    for name in _BANDIT_CONFIGS:
        if os.path.isfile(os.path.join(root, name)):
            return _gate("bandit", "sast", f"bandit -c {name} -r .", "local", [name])
    if os.path.isfile(os.path.join(root, ".bandit")):
        return _gate("bandit", "sast", "bandit --ini .bandit -r .", "local", [".bandit"])
    pyproject = os.path.join(root, "pyproject.toml")
    if "[tool.bandit" in _read(pyproject):
        return _gate("bandit", "sast", "bandit -c pyproject.toml -r .", "local", ["pyproject.toml"])
    return None


def _gitleaks(root: str) -> dict | None:
    for name in _GITLEAKS_CONFIGS:
        if os.path.isfile(os.path.join(root, name)):
            return _gate("gitleaks", "secrets", f"gitleaks detect --no-banner --config {name}", "local", [name])
    return None


def _package_scripts(root: str) -> list[dict]:
    manifest = os.path.join(root, "package.json")
    if not os.path.isfile(manifest):
        return []
    try:
        data = json.loads(_read(manifest))
    except json.JSONDecodeError:
        return []
    scripts = data.get("scripts", {}) if isinstance(data, dict) else {}
    if os.path.exists(os.path.join(root, "pnpm-lock.yaml")):
        runner = "pnpm run"
    elif os.path.exists(os.path.join(root, "yarn.lock")):
        runner = "yarn"
    else:
        runner = "npm run"
    return [
        _gate(f"script:{name}", "sast", f"{runner} {name}", "local", ["package.json"])
        for name in _SECURITY_SCRIPT_NAMES if name in scripts
    ]


def _pre_commit(root: str, already: set[str]) -> list[dict]:
    config = ".pre-commit-config.yaml"
    text = _read(os.path.join(root, config))
    if not text:
        return []
    hook_ids = set(_PRE_COMMIT_ID_RE.findall(text))
    gates = []
    for tool in _PRE_COMMIT_TOOLS:
        if tool in hook_ids and tool not in already:
            category = "secrets" if tool == "gitleaks" else "sast"
            gates.append(_gate(tool, category, f"pre-commit run {tool} --all-files", "local", [config]))
    return gates


def detect(root: str = ".") -> list[dict]:
    """Return one blocking gate per scanner the repository already configures."""
    root = os.path.abspath(root)
    workflows = _workflow_files(root)
    gates = [g for g in (_semgrep(root, workflows), _codeql(root, workflows),
                         _bandit(root), _gitleaks(root)) if g]
    configured = {g["tool"] for g in gates if g["execution"] == "local"}
    gates.extend(_pre_commit(root, configured))
    gates.extend(_package_scripts(root))
    return gates


def summarize(root: str = ".") -> list[dict]:
    """Compact view used by discovery.scan (tool, execution, evidence)."""
    return [
        {"tool": g["tool"], "category": g["category"], "execution": g["execution"], "evidence": g["evidence"]}
        for g in detect(root)
    ]
