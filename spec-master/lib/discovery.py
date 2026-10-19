"""Read-only repository discovery (CLAUDE.md section 6).

Detects language/framework signals, build/test/lint commands, CI, existing
Spec Kit installation, existing constitution/specs, from manifest files that
are actually present on disk. Never invents a command for a stack that has no
supporting manifest.
"""
from __future__ import annotations

import json
import os
import re

import sast_gates
import tracker_orchestration

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


# Manifest-less Python test suites (feature harness-hygiene, H3). Bounded to
# the scan root and its immediate children: no recursive walk.
_SUITE_DIR_NAMES = ("tests", "test")
_SUITE_SKIP_DIRS = frozenset({
    "node_modules", "venv", "env", "build", "dist", "target", "site-packages", "__pycache__",
})
_PYTEST_IMPORT = re.compile(r"^\s*(import pytest|from pytest\b)", re.MULTILINE)


def _is_test_module(name: str) -> bool:
    return name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))


_TOP_LEVEL_TEST_FN = re.compile(r"^def test\w*\s*\(", re.MULTILINE)
_UNITTEST_IMPORT = re.compile(r"^\s*(import unittest\b|from unittest\b)", re.MULTILINE)


def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return ""


def _suite_uses_pytest(suite_dir: str, modules: list[str]) -> bool:
    """pytest when the suite needs it: a module or ``conftest.py`` imports pytest,
    or a module holds plain top-level ``def test_*`` functions without importing
    unittest (pytest-style tests that ``unittest discover`` would not collect)."""
    if _PYTEST_IMPORT.search(_read_text(os.path.join(suite_dir, "conftest.py"))):
        return True
    for name in modules:
        text = _read_text(os.path.join(suite_dir, name))
        if _PYTEST_IMPORT.search(text):
            return True
        if _TOP_LEVEL_TEST_FN.search(text) and not _UNITTEST_IMPORT.search(text):
            return True
    return False


def _scan_python_test_suites(root: str) -> list[dict]:
    """Detect Python test suites that have no manifest (pyproject/setup.cfg/requirements).

    Each suite becomes its own stack with a ``scope`` (suite dir relative to
    the root). The runner is derived from the suite itself: pytest when any
    module imports pytest, stdlib unittest otherwise.
    """
    candidates = list(_SUITE_DIR_NAMES)
    try:
        children = sorted(os.listdir(root))
    except OSError:
        children = []
    for child in children:
        if child.startswith(".") or child in _SUITE_SKIP_DIRS:
            continue
        if not os.path.isdir(os.path.join(root, child)):
            continue
        candidates.extend(f"{child}/{name}" for name in _SUITE_DIR_NAMES)
    stacks = []
    for rel in candidates:
        suite_dir = os.path.join(root, *rel.split("/"))
        if not os.path.isdir(suite_dir):
            continue
        try:
            modules = sorted(n for n in os.listdir(suite_dir) if _is_test_module(n))
        except OSError:
            continue
        if not modules:
            continue
        if _suite_uses_pytest(suite_dir, modules):
            command = f"python3 -m pytest {rel}"
        else:
            command = f"python3 -m unittest discover -s {rel}"
        stacks.append({
            "language": "python",
            "commands": {"test": command},
            "manifest": suite_dir,
            "scope": rel,
            "detected_from": "test-suite",
        })
    return stacks


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
    if not any(stack["language"] == "python" for stack in stacks):
        stacks.extend(_scan_python_test_suites(root))

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

    # Spec Kit installs command files in a platform-specific directory. Keep
    # the relative path so an orchestrator can execute the command for the
    # active integration instead of assuming Claude's layout.
    speckit_commands = []
    command_dirs = (
        ("claude", os.path.join(root, ".claude", "commands")),
        ("opencode", os.path.join(root, ".opencode", "commands")),
        ("qwen", os.path.join(root, ".qwen", "commands")),
    )
    speckit_command_paths = {}
    for integration, commands_dir in command_dirs:
        if not os.path.isdir(commands_dir):
            continue
        found = sorted(
            f for f in os.listdir(commands_dir)
            if f.startswith("speckit.") and f.endswith(".md")
        )
        if found:
            speckit_command_paths[integration] = [
                os.path.relpath(os.path.join(commands_dir, name), root)
                for name in found
            ]
            speckit_commands.extend(found)
    speckit_commands = sorted(set(speckit_commands))

    docs_present = os.path.isdir(os.path.join(root, "docs"))
    readme_present = any(
        os.path.exists(os.path.join(root, name)) for name in ("README.md", "readme.md")
    )
    claude_md_present = os.path.exists(os.path.join(root, "CLAUDE.md"))
    agents_md_present = os.path.exists(os.path.join(root, "AGENTS.md"))

    is_git_repo = os.path.isdir(os.path.join(root, ".git"))

    tracker_extensions = tracker_orchestration.detect_tracker_extensions(root)

    return {
        "stacks": stacks,
        "ci_present": ci_present,
        "spec_kit_present": spec_kit_present,
        "constitution_present": constitution_present,
        "specs_dir_present": specs_dir_present,
        "existing_specs": existing_specs,
        "speckit_commands": speckit_commands,
        "speckit_command_paths": speckit_command_paths,
        "docs_present": docs_present,
        "readme_present": readme_present,
        "claude_md_present": claude_md_present,
        "agents_md_present": agents_md_present,
        "is_git_repo": is_git_repo,
        "tracker_extensions": tracker_extensions,
        "sast_scanners": sast_gates.summarize(root),
    }
