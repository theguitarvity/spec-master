"""Quality gate command derivation (CLAUDE.md section 28).

Never hardcodes a command family (e.g. `npm test`) for every project: every
gate comes from the target repository's own configuration or tooling
(constitution Principle VIII).

- Declared (`source: "declared"`): `.spec-master/gates.json`, a JSON list of
  `{name, command, blocking, category, timeout_seconds, cwd}` objects. The
  file is validated as a whole; a present but invalid file raises
  `DeclaredGatesError` naming every problem instead of silently dropping
  entries. A declared gate whose name matches a detected gate replaces it in
  place; the other declared gates follow the detected ones, in file order.
- Detected (`source: "detected"`): commands backed by a manifest that
  `discovery.scan()` actually found; security scanners the repository already
  configures (sast_gates.py); and, only when no Python manifest was found,
  stdlib `unittest` suites whose `test_*.py` files actually import unittest
  or subclass `unittest.TestCase`.

Every gate carries `name`, `command` (a shell command string: a declared argv
list is shell-quoted, a CI-only scanner has None), `blocking`, `category`,
`source`, `timeout_seconds` (None: no limit) and `cwd` (repository-relative,
None: the repository root).
"""
from __future__ import annotations

import ast
import json
import os
import posixpath
import shlex
import warnings
from pathlib import PureWindowsPath

try:
    from . import discovery, sast_gates
except ImportError:  # executed as a plain script/module, not a package
    import discovery
    import sast_gates

_GATE_ORDER = ["build", "lint", "type_check", "test", "coverage"]

DECLARED_GATES_FILE = ".spec-master/gates.json"
_DECLARED_KEYS = ("name", "command", "blocking", "category", "timeout_seconds", "cwd")
_DEFAULT_CATEGORY = "test"

_UNITTEST_MAX_DEPTH = 3
_UNITTEST_SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".spec-master",
    ".venv", "venv", ".tox", ".nox", ".eggs", "site-packages",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
})
_TESTCASE_CLASSES = frozenset({"TestCase", "IsolatedAsyncioTestCase"})
_MAX_TEST_FILE_BYTES = 1_000_000
_EVIDENCE_LIMIT = 3


class DeclaredGatesError(ValueError):
    """`.spec-master/gates.json` is present but invalid; `errors` lists every problem."""

    def __init__(self, errors: list[str], path: str = DECLARED_GATES_FILE):
        self.errors = list(errors)
        self.path = path
        super().__init__(f"{path} is invalid: " + "; ".join(self.errors))


# --- declared gates ----------------------------------------------------------

def _json_type(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object" if isinstance(value, dict) else type(value).__name__


def _command_errors(where: str, command) -> list[str]:
    if isinstance(command, str):
        if not command.strip():
            return [f"{where}.command: must not be empty"]
        if "\x00" in command:
            return [f"{where}.command: must not contain NUL characters"]
        return []
    if isinstance(command, list):
        if not command:
            return [f"{where}.command: argv list must not be empty"]
        for index, arg in enumerate(command):
            if not isinstance(arg, str):
                return [f"{where}.command[{index}]: argv items must be strings, got {_json_type(arg)}"]
            if "\x00" in arg:
                return [f"{where}.command[{index}]: must not contain NUL characters"]
        if not command[0].strip():
            return [f"{where}.command[0]: program must not be empty"]
        return []
    return [f"{where}.command: must be a string or a list of strings, got {_json_type(command)}"]


def _cwd_errors(where: str, cwd) -> list[str]:
    if not isinstance(cwd, str) or not cwd.strip():
        return [f"{where}.cwd: must be a non-empty relative path, got {_json_type(cwd)}"]
    if "\x00" in cwd:
        return [f"{where}.cwd: must not contain NUL characters"]
    posix = cwd.replace("\\", "/")
    windows = PureWindowsPath(cwd)
    if posix.startswith("/") or os.path.isabs(cwd) or windows.drive or windows.root:
        return [f"{where}.cwd: must be relative to the repository root, got absolute path {cwd!r}"]
    if ".." in posix.split("/"):
        return [f"{where}.cwd: must stay inside the repository, '..' is not allowed ({cwd!r})"]
    return []


def validate_declared(payload) -> list[str]:
    """Every problem in a parsed `gates.json` payload; [] when it is valid."""
    if not isinstance(payload, list):
        return [f"gates must be a JSON array of gate objects, got {_json_type(payload)}"]
    errors: list[str] = []
    seen: dict[str, int] = {}
    for index, entry in enumerate(payload):
        where = f"gates[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{where}: must be an object, got {_json_type(entry)}")
            continue
        unknown = sorted(str(key) for key in entry if key not in _DECLARED_KEYS)
        if unknown:
            errors.append(f"{where}: unknown key(s) {', '.join(unknown)}; "
                          f"allowed: {', '.join(_DECLARED_KEYS)}")
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{where}.name: required non-empty string")
        elif name.strip() in seen:
            errors.append(f"{where}.name: {name.strip()!r} is already declared by gates[{seen[name.strip()]}]")
        else:
            seen[name.strip()] = index
        if "command" not in entry:
            errors.append(f"{where}.command: required (a string or a list of strings)")
        else:
            errors.extend(_command_errors(where, entry["command"]))
        blocking = entry.get("blocking")
        if blocking is not None and not isinstance(blocking, bool):
            errors.append(f"{where}.blocking: must be true or false, got {_json_type(blocking)}")
        category = entry.get("category")
        if category is not None and (not isinstance(category, str) or not category.strip()):
            errors.append(f"{where}.category: must be a non-empty string, got {category!r}")
        timeout = entry.get("timeout_seconds")
        if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0):
            errors.append(f"{where}.timeout_seconds: must be an integer > 0, got {timeout!r}")
        if entry.get("cwd") is not None:
            errors.extend(_cwd_errors(where, entry["cwd"]))
    return errors


def _escapes_root(root: str, cwd: str) -> bool:
    """True when `cwd` resolves (through symlinks) outside `root`."""
    real_root = os.path.realpath(root)
    target = os.path.realpath(os.path.join(root, *cwd.split("/")))
    try:
        return os.path.commonpath([real_root, target]) != real_root
    except ValueError:  # different drives
        return True


def _normalize_declared(entry: dict) -> dict:
    """A validated entry in the gate shape; null optional keys take their defaults."""
    command = entry["command"]
    cwd = entry.get("cwd")
    return {
        "name": entry["name"].strip(),
        "command": shlex.join(command) if isinstance(command, list) else command,
        "blocking": entry.get("blocking") is not False,
        "category": (entry.get("category") or _DEFAULT_CATEGORY).strip(),
        "source": "declared",
        "timeout_seconds": entry.get("timeout_seconds"),
        "cwd": posixpath.normpath(cwd.replace("\\", "/")) if cwd is not None else None,
    }


def load_declared(root: str = ".") -> list[dict]:
    """Normalized gates from `<root>/.spec-master/gates.json`; [] when absent.

    Raises DeclaredGatesError listing every problem when the file exists but
    cannot be read, is not valid JSON, fails `validate_declared`, or declares
    a `cwd` that resolves outside the repository.
    """
    root = os.path.abspath(root)
    path = os.path.join(root, *DECLARED_GATES_FILE.split("/"))
    if not os.path.lexists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except json.JSONDecodeError as exc:
        raise DeclaredGatesError([f"invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})"]) from exc
    except UnicodeDecodeError as exc:
        raise DeclaredGatesError(["not valid UTF-8"]) from exc
    except OSError as exc:
        raise DeclaredGatesError([f"cannot be read: {exc.strerror or exc}"]) from exc
    errors = validate_declared(payload)
    if not errors:
        errors = [
            f"gates[{index}].cwd: resolves outside the repository ({entry['cwd']!r})"
            for index, entry in enumerate(payload)
            if entry.get("cwd") is not None and _escapes_root(root, entry["cwd"].replace("\\", "/"))
        ]
    if errors:
        raise DeclaredGatesError(errors)
    return [_normalize_declared(entry) for entry in payload]


# --- stdlib unittest suites --------------------------------------------------

def _unittest_usage(path: str) -> tuple[bool, bool]:
    """(the file imports unittest or subclasses unittest.TestCase,
    it uses package-relative imports). Unreadable/unparsable files are no evidence."""
    try:
        if os.path.getsize(path) > _MAX_TEST_FILE_BYTES:
            return False, False
        with open(path, "rb") as fh:
            source = fh.read()
        with warnings.catch_warnings():  # e.g. invalid escape sequences in the scanned file
            warnings.simplefilter("ignore")
            tree = ast.parse(source, filename=path)
    except (OSError, SyntaxError, ValueError):
        return False, False
    imports_unittest = relative = False
    module_names: set[str] = set()     # names bound to the unittest module
    testcase_names: set[str] = set()   # names bound to unittest's TestCase classes
    classes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "unittest":
                    imports_unittest = True
                elif alias.name.startswith("unittest.") and not alias.asname:
                    module_names.add("unittest")  # `import unittest.mock` binds `unittest`
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative = True
            elif node.module == "unittest":
                testcase_names.update(alias.asname or alias.name for alias in node.names
                                      if alias.name in _TESTCASE_CLASSES)
        elif isinstance(node, ast.ClassDef):
            classes.append(node)
    subclasses_testcase = any(
        (isinstance(base, ast.Name) and base.id in testcase_names)
        or (isinstance(base, ast.Attribute) and base.attr in _TESTCASE_CLASSES
            and isinstance(base.value, ast.Name) and base.value.id in module_names)
        for node in classes for base in node.bases
    )
    return imports_unittest or subclasses_testcase, relative


def _package_top_level(root: str, rel_dir: str) -> str | None:
    """The `-t` directory that imports `rel_dir` as a package, when it is one."""
    parts = [] if rel_dir == "." else rel_dir.split("/")
    index = len(parts)
    while index > 0 and os.path.isfile(os.path.join(root, *parts[:index], "__init__.py")):
        index -= 1
    package = parts[index:]
    if not package or not all(part.isidentifier() for part in package):
        return None
    return "/".join(parts[:index]) or "."


def _covered_by(root: str, ancestor: str, rel_dir: str) -> bool:
    """unittest discovery started at `ancestor` recurses into `rel_dir` only
    through packages: every directory below `ancestor` needs an __init__.py."""
    prefix = "" if ancestor == "." else ancestor + "/"
    if not rel_dir.startswith(prefix) or rel_dir == ancestor:
        return False
    below = rel_dir[len(prefix):].split("/")
    base = [] if ancestor == "." else ancestor.split("/")
    return all(os.path.isfile(os.path.join(root, *base, *below[:depth], "__init__.py"))
               for depth in range(1, len(below) + 1))


def detect_unittest_suites(root: str = ".") -> list[dict]:
    """One gate per stdlib unittest suite, from evidence in its test files.

    Scans directories up to depth 3 below `root` (skipping VCS, dependency,
    virtualenv and cache directories) for `test_*.py` files that import
    unittest or subclass `unittest.TestCase`. The gate runs
    `python3 -m unittest discover -s <dir>`: the start directory is the
    top-level directory, which is how a suite that imports sibling helper
    modules (e.g. `import _pathfix`) resolves them. A suite that uses
    package-relative imports (`from . import helpers`) also gets
    `-t <dir above its package>`. A suite that discovery from an enclosing
    suite already reaches (through packages) gets no gate of its own.
    `evidence` lists up to three of the files that justify the gate.
    """
    root = os.path.abspath(root)
    suites: list[tuple[str, list[str], bool]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
        depth = 0 if rel_dir == "." else rel_dir.count("/") + 1
        if depth >= _UNITTEST_MAX_DEPTH:
            dirnames[:] = []
        else:
            dirnames[:] = sorted(
                name for name in dirnames
                if name not in _UNITTEST_SKIP_DIRS
                and not os.path.isfile(os.path.join(dirpath, name, "pyvenv.cfg"))
            )
        evidence, relative = [], False
        for name in sorted(filenames):
            if not (name.startswith("test_") and name.endswith(".py")):
                continue
            uses_unittest, uses_relative = _unittest_usage(os.path.join(dirpath, name))
            if uses_unittest:
                evidence.append(name if rel_dir == "." else f"{rel_dir}/{name}")
                relative = relative or uses_relative
        if evidence:
            suites.append((rel_dir, evidence, relative))

    gates = []
    selected: list[str] = []
    for rel_dir, evidence, relative in sorted(suites):
        if any(_covered_by(root, ancestor, rel_dir) for ancestor in selected):
            continue
        selected.append(rel_dir)
        argv = ["python3", "-m", "unittest", "discover", "-s", rel_dir]
        top_level = _package_top_level(root, rel_dir) if relative else None
        if top_level is not None:
            argv += ["-t", top_level]
        gates.append({
            "name": f"test (unittest: {rel_dir})",
            "command": shlex.join(argv),
            "blocking": True,
            "category": "test",
            "source": "detected",
            "timeout_seconds": None,
            "cwd": None,
            "tool": "unittest",
            "execution": "local",
            "evidence": evidence[:_EVIDENCE_LIMIT],
        })
    return gates


# --- detection ---------------------------------------------------------------

def detect(root: str = ".") -> list[dict]:
    """Declared and detected gates for `root` (see the module docstring).

    Raises DeclaredGatesError (a ValueError) when `.spec-master/gates.json`
    is present but invalid, so a broken declaration fails closed.
    """
    declared = load_declared(root)
    info = discovery.scan(root)
    detected: list[dict] = []
    for stack in info["stacks"]:
        commands = stack["commands"]
        for gate_name in _GATE_ORDER:
            if gate_name in commands:
                detected.append({
                    "name": f"{gate_name} ({stack['language']})",
                    "command": commands[gate_name],
                    "blocking": gate_name in ("build", "test"),
                    "category": gate_name,
                    "source": "detected",
                    "timeout_seconds": None,
                    "cwd": None,
                })
    if not any(stack["language"] == "python" for stack in info["stacks"]):
        detected.extend(detect_unittest_suites(root))
    detected.extend({**gate, "source": "detected", "timeout_seconds": None, "cwd": None}
                    for gate in sast_gates.detect(root))

    overrides = {gate["name"]: gate for gate in declared}
    detected_names = {gate["name"] for gate in detected}
    gates = [overrides.get(gate["name"], gate) for gate in detected]
    gates.extend(gate for gate in declared if gate["name"] not in detected_names)
    return gates
