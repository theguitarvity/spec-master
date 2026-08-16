"""Read-only repository discovery (CLAUDE.md section 6).

Detects language/framework signals, build/test/lint commands, CI, existing
Spec Kit installation, existing constitution/specs, from manifest files that
are actually present on disk. Never invents a command for a stack that has no
supporting manifest.
"""
from __future__ import annotations

import json
import os

# Each entry: manifest file (relative to scan root) -> language + candidate
# commands to report *only if the manifest file exists*.
_NODE_SCRIPT_MAP = {
    "test": "test",
    "lint": "lint",
    "build": "build",
    "coverage": "coverage",
}


def _scan_node(root: str, manifest_path: str) -> dict | None:
    if not os.path.exists(manifest_path):
        return None
    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {"language": "node", "commands": {}, "manifest": manifest_path}
    scripts = data.get("scripts", {}) if isinstance(data, dict) else {}
    pm = "npm run"
    if os.path.exists(os.path.join(root, "pnpm-lock.yaml")):
        pm = "pnpm run"
    elif os.path.exists(os.path.join(root, "yarn.lock")):
        pm = "yarn"
    commands = {}
    for gate, script_name in _NODE_SCRIPT_MAP.items():
        if script_name in scripts:
            commands[gate] = f"{pm} {script_name}" if pm != "yarn" else f"yarn {script_name}"
    if "build" not in commands and "build" in scripts:
        commands["build"] = f"{pm} build" if pm != "yarn" else "yarn build"
    return {"language": "node", "commands": commands, "manifest": manifest_path}


def _scan_python(root: str) -> dict | None:
    pyproject = os.path.join(root, "pyproject.toml")
    setup_cfg = os.path.join(root, "setup.cfg")
    requirements = os.path.join(root, "requirements.txt")
    manifest = None
    for candidate in (pyproject, setup_cfg, requirements):
        if os.path.exists(candidate):
            manifest = candidate
            break
    if manifest is None:
        return None
    commands = {}
    text = ""
    if manifest.endswith("pyproject.toml"):
        with open(manifest, "r", encoding="utf-8") as fh:
            text = fh.read()
    has_tests_dir = os.path.isdir(os.path.join(root, "tests"))
    if "pytest" in text or has_tests_dir:
        commands["test"] = "pytest"
    if "ruff" in text:
        commands["lint"] = "ruff check ."
    elif "flake8" in text:
        commands["lint"] = "flake8"
    if "mypy" in text:
        commands["type_check"] = "mypy ."
    return {"language": "python", "commands": commands, "manifest": manifest}


def _scan_go(root: str) -> dict | None:
    manifest = os.path.join(root, "go.mod")
    if not os.path.exists(manifest):
        return None
    return {"language": "go", "commands": {"test": "go test ./...", "build": "go build ./..."}, "manifest": manifest}


def _scan_rust(root: str) -> dict | None:
    manifest = os.path.join(root, "Cargo.toml")
    if not os.path.exists(manifest):
        return None
    return {"language": "rust", "commands": {"test": "cargo test", "build": "cargo build"}, "manifest": manifest}


def _scan_maven(root: str) -> dict | None:
    manifest = os.path.join(root, "pom.xml")
    if not os.path.exists(manifest):
        return None
    return {"language": "java", "commands": {"test": "mvn test", "build": "mvn verify"}, "manifest": manifest}


def _scan_gradle(root: str) -> dict | None:
    for name in ("build.gradle", "build.gradle.kts"):
        manifest = os.path.join(root, name)
        if os.path.exists(manifest):
            return {"language": "java/kotlin", "commands": {"test": "gradle test", "build": "gradle build"}, "manifest": manifest}
    return None


def scan(root: str = ".") -> dict:
    root = os.path.abspath(root)
    stacks = []
    for fn in (
        lambda: _scan_node(root, os.path.join(root, "package.json")),
        lambda: _scan_python(root),
        lambda: _scan_go(root),
        lambda: _scan_rust(root),
        lambda: _scan_maven(root),
        lambda: _scan_gradle(root),
    ):
        result = fn()
        if result:
            stacks.append(result)

    ci_present = os.path.isdir(os.path.join(root, ".github", "workflows")) or any(
        os.path.exists(os.path.join(root, name))
        for name in (".gitlab-ci.yml", "azure-pipelines.yml", ".circleci")
    )

    spec_kit_present = os.path.isdir(os.path.join(root, ".specify"))
    constitution_present = os.path.exists(
        os.path.join(root, ".specify", "memory", "constitution.md")
    )
    specs_dir_present = os.path.isdir(os.path.join(root, "specs"))
    existing_specs = []
    if specs_dir_present:
        try:
            existing_specs = sorted(
                d for d in os.listdir(os.path.join(root, "specs"))
                if os.path.isdir(os.path.join(root, "specs", d))
            )
        except OSError:
            existing_specs = []

    speckit_commands = []
    commands_dir = os.path.join(root, ".claude", "commands")
    if os.path.isdir(commands_dir):
        speckit_commands = sorted(
            f for f in os.listdir(commands_dir) if f.startswith("speckit.")
        )

    docs_present = os.path.isdir(os.path.join(root, "docs"))
    readme_present = any(
        os.path.exists(os.path.join(root, name)) for name in ("README.md", "readme.md")
    )
    claude_md_present = os.path.exists(os.path.join(root, "CLAUDE.md"))
    agents_md_present = os.path.exists(os.path.join(root, "AGENTS.md"))

    is_git_repo = os.path.isdir(os.path.join(root, ".git"))

    return {
        "stacks": stacks,
        "ci_present": ci_present,
        "spec_kit_present": spec_kit_present,
        "constitution_present": constitution_present,
        "specs_dir_present": specs_dir_present,
        "existing_specs": existing_specs,
        "speckit_commands": speckit_commands,
        "docs_present": docs_present,
        "readme_present": readme_present,
        "claude_md_present": claude_md_present,
        "agents_md_present": agents_md_present,
        "is_git_repo": is_git_repo,
    }
