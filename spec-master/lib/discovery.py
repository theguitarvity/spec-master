"""Read-only repository discovery (CLAUDE.md section 6).

Detects language/framework signals, build/test/lint commands, CI, existing
Spec Kit installation, existing constitution/specs, from manifest files that
are actually present on disk. Never invents a command for a stack that has no
supporting manifest.

Spec Kit phase entrypoints come from what Spec Kit itself recorded:
`.specify/integration.json` (version, active integration, invoke separator)
and `.specify/integrations/<name>.manifest.json` (the files it installed).
Both layouts Spec Kit has shipped are recognised: `commands/speckit.<phase>.md`
(invoked as `/speckit.<phase>`) and, since Spec Kit 0.4.5,
`skills/speckit-<phase>/SKILL.md` (invoked as `/speckit-<phase>`). A scan of
the known agent directories is the fallback when there is no manifest.
"""
from __future__ import annotations

import json
import os
import posixpath
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


# --- Spec Kit integration ----------------------------------------------------

_INVOKE_SEPARATORS = (".", "-")
_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
# Command files: `speckit.<name>.<ext>`. Copilot writes `.agent.md` plus a
# companion `.prompt.md`, Gemini/Tabnine `.toml`, Firebender `.mdc`, Goose
# `.yaml`; every other commands-layout agent writes `.md`.
_COMMAND_FILE_RE = re.compile(
    r"^speckit\.(?P<name>[A-Za-z0-9][A-Za-z0-9_.-]*?)\.(?P<ext>agent\.md|prompt\.md|md|toml|mdc|yaml)$"
)
# Cline and Forge write hyphenated command files: `speckit-<name>.md`.
_HYPHEN_COMMAND_FILE_RE = re.compile(r"^speckit-(?P<name>[A-Za-z0-9][A-Za-z0-9_.-]*?)\.md$")

# Fallback scan for integrations without a readable manifest: (directory,
# integration keys that install there). Every agent directory is probed for
# both layouts. A directory several integrations share belongs to the first
# one `.specify/integration.json` lists as installed, else to the first here.
_ENTRYPOINT_DIRS = (
    (".claude/skills", ("claude",)),
    (".claude/commands", ("claude",)),
    (".github/skills", ("copilot",)),
    (".github/commands", ("copilot",)),
    (".github/agents", ("copilot",)),
    (".github/prompts", ("copilot",)),
    (".agents/skills", ("codex", "agy", "zed")),
    (".agents/commands", ("amp",)),
    (".codex/skills", ("codex",)),
    (".codex/commands", ("codex",)),
    (".codex/prompts", ("codex",)),
    (".opencode/skills", ("opencode",)),
    (".opencode/skill", ("opencode",)),
    (".opencode/commands", ("opencode",)),
    (".opencode/command", ("opencode",)),
    (".qwen/skills", ("qwen",)),
    (".qwen/skill", ("qwen",)),
    (".qwen/commands", ("qwen",)),
    (".gemini/commands", ("gemini",)),
    (".cursor/skills", ("cursor-agent",)),
    (".cursor/commands", ("cursor-agent",)),
)


def _read_json_object(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):  # ValueError covers JSON and UTF-8 decode errors
        return None
    return data if isinstance(data, dict) else None


def _clean_key(value) -> str | None:
    if isinstance(value, str) and _KEY_RE.match(value.strip()):
        return value.strip()
    return None


def _entrypoint(rel_path: str, integration: str) -> dict | None:
    """Describe a Spec Kit phase entrypoint at `rel_path` (POSIX), or None.

    `entry` is how `speckit_commands` lists it (`speckit.plan.md` for a command
    file, `speckit-plan` for a skill), `name` drops the `speckit` prefix, and
    `rank` orders several entrypoints for one name (lower wins).
    """
    parts = rel_path.split("/")
    base = parts[-1]
    parent = parts[-2] if len(parts) > 1 else ""
    found = None
    if base == "SKILL.md":
        name = parent[len("speckit-"):] if parent.startswith("speckit-") else ""
        if _KEY_RE.match(name):
            found = (parent, name, "-", 0)
    else:
        match = _COMMAND_FILE_RE.match(base)
        if match:
            rank = {"agent.md": 1, "prompt.md": 3}.get(match.group("ext"), 2)
            found = (base, match.group("name"), ".", rank)
        else:
            match = _HYPHEN_COMMAND_FILE_RE.match(base)
            if match and not parent.startswith("speckit-"):
                found = (base, match.group("name"), "-", 2)
    if found is None:
        return None
    entry, name, separator, rank = found
    return {"integration": integration, "path": rel_path, "entry": entry,
            "name": name, "separator": separator, "rank": rank}


def _manifest_entrypoints(root: str, integration: str) -> tuple[dict | None, list[dict]]:
    """(manifest, entrypoints it lists that exist on disk); (None, []) if unreadable."""
    manifest = _read_json_object(
        os.path.join(root, ".specify", "integrations", f"{integration}.manifest.json")
    )
    files = manifest.get("files") if manifest else None
    if not isinstance(files, dict):
        return None, []
    found = []
    for raw_path in sorted(files):
        rel_path = posixpath.normpath(raw_path.replace("\\", "/"))
        parts = rel_path.split("/")
        if rel_path.startswith("/") or ".." in parts or ":" in parts[0]:
            continue  # only repository-relative paths are evidence
        ep = _entrypoint(rel_path, integration)
        if ep and os.path.isfile(os.path.join(root, *parts)):
            found.append(ep)
    return manifest, found


def _scanned_entrypoints(root: str, installed: list[str]) -> list[dict]:
    found = []
    for rel_dir, owners in _ENTRYPOINT_DIRS:
        directory = os.path.join(root, *rel_dir.split("/"))
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            continue
        owner = next((key for key in owners if key in installed), owners[0])
        for name in names:
            path = os.path.join(directory, name)
            if os.path.isdir(path):
                if not os.path.isfile(os.path.join(path, "SKILL.md")):
                    continue
                rel_path = f"{rel_dir}/{name}/SKILL.md"
            elif os.path.isfile(path):
                rel_path = f"{rel_dir}/{name}"
            else:
                continue
            ep = _entrypoint(rel_path, owner)
            if ep:
                found.append(ep)
    return found


def _integrations(state: dict, init_options: dict) -> tuple[list[str], str | None]:
    """(installed integration keys, active key), resolved the way Spec Kit does:
    `default_integration`, then `integration`, then the first installed one;
    older installs only have `.specify/init-options.json` (`ai`)."""
    installed: list[str] = []
    raw_installed = state.get("installed_integrations")
    for value in raw_installed if isinstance(raw_installed, list) else []:
        key = _clean_key(value)
        if key and key not in installed:
            installed.append(key)
    active = (_clean_key(state.get("default_integration")) or _clean_key(state.get("integration"))
              or (installed[0] if installed else None)
              or _clean_key(init_options.get("ai")) or _clean_key(init_options.get("integration")))
    if active and active not in installed:
        installed.insert(0, active)
    return installed, active


def _speckit_install(root: str) -> dict:
    """Spec Kit version, active integration and the entrypoints on disk.

    `speckit_commands`/`speckit_command_paths` inventory every entrypoint the
    manifests list or the scan finds (extension commands such as the git
    extension's are not in the integration manifest). The phase map uses the
    active integration's manifest when it lists existing entrypoints, and the
    directory scan otherwise.
    """
    state = _read_json_object(os.path.join(root, ".specify", "integration.json")) or {}
    init_options = _read_json_object(os.path.join(root, ".specify", "init-options.json")) or {}
    installed, active = _integrations(state, init_options)

    manifests: dict[str, dict] = {}
    from_manifest: dict[str, list[dict]] = {}
    for key in installed:
        manifest, found = _manifest_entrypoints(root, key)
        if manifest is not None:
            manifests[key] = manifest
            from_manifest[key] = found
    from_scan: dict[str, list[dict]] = {}
    for ep in _scanned_entrypoints(root, installed):
        from_scan.setdefault(ep["integration"], []).append(ep)

    command_paths: dict[str, set[str]] = {}
    entries: set[str] = set()
    for by_integration in (from_manifest, from_scan):
        for key, found in by_integration.items():
            for ep in found:
                command_paths.setdefault(key, set()).add(ep["path"])
                entries.add(ep["entry"])

    if active is None and len(command_paths) == 1:
        active = next(iter(command_paths))  # a single integration on disk is the active one

    candidates = (from_manifest.get(active) or from_scan.get(active) or []) if active else []
    chosen: dict[str, dict] = {}
    for ep in sorted(candidates, key=lambda item: (item["rank"], item["path"])):
        chosen.setdefault(ep["name"], ep)

    separator = None
    settings = state.get("integration_settings")
    setting = settings.get(active) if isinstance(settings, dict) and active else None
    if isinstance(setting, dict) and isinstance(setting.get("invoke_separator"), str):
        separator = setting["invoke_separator"].strip()
    if separator not in _INVOKE_SEPARATORS:
        implied = {ep["separator"] for ep in chosen.values()}
        separator = implied.pop() if len(implied) == 1 else None

    version = next((value.strip() for value in (
        state.get("version"), init_options.get("speckit_version"),
        manifests.get(active, {}).get("version"),
    ) if isinstance(value, str) and value.strip()), None)

    return {
        "speckit_commands": sorted(entries),
        "speckit_command_paths": {key: sorted(paths) for key, paths in sorted(command_paths.items())},
        "speckit_version": version,
        "speckit_integration": active,
        "speckit_invoke_separator": separator,
        "speckit_phase_entrypoints": {name: chosen[name]["path"] for name in sorted(chosen)},
    }


def _is_git_repo(root: str) -> bool:
    """A `.git` directory, or the `.git` file of a worktree/submodule checkout."""
    git_path = os.path.join(root, ".git")
    if os.path.isdir(git_path):
        return True
    try:
        with open(git_path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(512).lstrip().startswith("gitdir:")
    except OSError:
        return False


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

    # Spec Kit installs phase entrypoints in a platform-specific directory.
    # Keep the relative paths so an orchestrator can execute the phase for the
    # active integration instead of assuming Claude's layout.
    speckit = _speckit_install(root)

    docs_present = os.path.isdir(os.path.join(root, "docs"))
    readme_present = any(
        os.path.exists(os.path.join(root, name)) for name in ("README.md", "readme.md")
    )
    claude_md_present = os.path.exists(os.path.join(root, "CLAUDE.md"))
    agents_md_present = os.path.exists(os.path.join(root, "AGENTS.md"))

    is_git_repo = _is_git_repo(root)

    tracker_extensions = tracker_orchestration.detect_tracker_extensions(root)

    return {
        "stacks": stacks,
        "ci_present": ci_present,
        "spec_kit_present": spec_kit_present,
        "constitution_present": constitution_present,
        "specs_dir_present": specs_dir_present,
        "existing_specs": existing_specs,
        **speckit,
        "docs_present": docs_present,
        "readme_present": readme_present,
        "claude_md_present": claude_md_present,
        "agents_md_present": agents_md_present,
        "is_git_repo": is_git_repo,
        "tracker_extensions": tracker_extensions,
        "sast_scanners": sast_gates.summarize(root),
    }
