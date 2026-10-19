"""Brownfield and greenfield tracks (roadmap Onda 6: B1 + G1 + scoped adoption).

Brownfield: read-only mapping of an existing codebase (stack, monorepo
packages, architecture, conventions, risks), a constitution *proposal* built
only from what the repository shows, and a ranking of untested files for the
optional characterization-test step. Every finding carries `evidence`
(repository-relative path, `path:line` when a line applies); nothing is
invented, and an absent signal produces an absent finding.

Greenfield: asks for the stack, then *proposes* a skeleton, CI workflow and a
minimal test gate. Nothing is written unless the caller confirms, and an
existing file is never overwritten (constitution Principles IV, VIII, X).
"""
from __future__ import annotations

import os
import re
import tempfile

import discovery

SOURCE_EXTS = (".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt", ".rb", ".php", ".cs")
ENTRYPOINT_NAMES = ("main.py", "__main__.py", "cli.py", "app.py", "server.py", "index.js", "index.ts",
                    "main.go", "main.rs", "lib.rs", "Main.java")
LOCKFILES = ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "uv.lock", "Pipfile.lock",
             "go.sum", "Cargo.lock")
CI_PATHS = (".github/workflows", ".gitlab-ci.yml", "azure-pipelines.yml", ".circleci")
CONVENTION_FILES = (
    ("editorconfig", (".editorconfig",)),
    ("eslint", (".eslintrc", ".eslintrc.json", ".eslintrc.js", "eslint.config.js", "eslint.config.mjs")),
    ("prettier", (".prettierrc", ".prettierrc.json", "prettier.config.js")),
    ("python-lint", ("ruff.toml", ".flake8", "tox.ini", ".pylintrc")),
    ("pre-commit", (".pre-commit-config.yaml",)),
    ("contributing", ("CONTRIBUTING.md",)),
    ("agent-instructions", ("CLAUDE.md", "AGENTS.md")),
)
TEST_DIRS = {"tests", "test", "__tests__", "spec"}
MARKER_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b")
MAX_FILE_BYTES = 1_000_000
LARGE_FILE_LINES = 800
STACKS = ("python", "node", "go", "rust")
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class ConfirmationRequired(ValueError):
    """Raised when a proposal is applied without explicit confirmation."""


# --- shared helpers ----------------------------------------------------------

def _rel(root: str, path: str) -> str:
    return os.path.relpath(path, root).replace(os.sep, "/")


def _base(root: str, scope: str | None) -> tuple[str, str]:
    root = os.path.abspath(root)
    return root, (discovery._resolve_scope(root, scope) if scope else root)


def _is_test_file(rel_path: str) -> bool:
    parts = rel_path.split("/")
    name = parts[-1]
    return (name.startswith("test_") or re.search(r"(_test\.(py|go)|\.(test|spec)\.[jt]sx?|Tests?\.(java|kt|cs))$", name)
            is not None or any(p in TEST_DIRS for p in parts[:-1]))


def _test_stem(name: str) -> str:
    stem = re.sub(r"\.(test|spec)(\.[a-z]+)$", "", name)
    stem = os.path.splitext(stem)[0]
    stem = re.sub(r"^test_", "", stem)
    return re.sub(r"(_test|Tests?)$", "", stem)


def _source_files(root: str, base: str) -> list[tuple[str, str]]:
    """(relative path, absolute path) of source files below `base`, pruned walk."""
    found = []
    for dirpath, _dirs, files in discovery._walk_pruned(base, 8):
        for name in files:
            if name.endswith(SOURCE_EXTS):
                path = os.path.join(dirpath, name)
                found.append((_rel(root, path), path))
    return found


def _read_lines(path: str) -> list[str]:
    try:
        if os.path.getsize(path) > MAX_FILE_BYTES:
            return []
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read().splitlines()
    except OSError:
        return []


def _exists(root: str, rel_path: str) -> bool:
    return os.path.exists(os.path.join(root, *rel_path.split("/")))


def write_new_file(root: str, rel_path: str, text: str) -> bool:
    """Write `text` atomically to `root/rel_path` unless the file exists. True if written."""
    target = os.path.join(root, *rel_path.split("/"))
    if os.path.exists(target):
        return False
    os.makedirs(os.path.dirname(target), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target), suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return True


# --- brownfield --------------------------------------------------------------

def map_codebase(root: str = ".", scope: str | None = None) -> dict:
    """Stack, packages, architecture, conventions and risks of an existing repo."""
    root, base = _base(root, scope)
    info = discovery.scan(root, scope)
    sources = _source_files(root, base)
    tests = [rel for rel, _ in sources if _is_test_file(rel)]
    prod = [(rel, path) for rel, path in sources if not _is_test_file(rel)]

    architecture = []
    top = {}
    for rel, _path in prod:
        inside = rel[len(_rel(root, base)) + 1:] if base != root else rel
        head = inside.split("/")[0] if "/" in inside else "."
        top.setdefault(head, []).append(rel)
    for head in sorted(top):
        folder = _rel(root, base) if head == "." else (head if base == root else _rel(root, base) + "/" + head)
        architecture.append({"kind": "module", "path": folder, "source_files": len(top[head]),
                             "evidence": [top[head][0]]})
    for rel, _path in prod:
        if rel.split("/")[-1] in ENTRYPOINT_NAMES:
            architecture.append({"kind": "entrypoint", "path": rel, "evidence": [rel]})

    conventions = []
    for kind, names in CONVENTION_FILES:
        for name in names:
            if _exists(root, name):
                conventions.append({"kind": kind, "detail": name, "evidence": [name]})
                break
    for ci in CI_PATHS:
        if _exists(root, ci):
            conventions.append({"kind": "ci", "detail": ci, "evidence": [ci]})
            break
    if tests:
        conventions.append({"kind": "tests", "detail": f"{len(tests)} test file(s)", "evidence": [tests[0]]})
    for stack in info["stacks"]:
        manifest = _rel(root, stack["manifest"])
        if stack["commands"]:
            conventions.append({"kind": "commands", "detail": stack["commands"], "evidence": [manifest]})
    lockfiles = [name for name in LOCKFILES if _exists(root, name)]
    for name in lockfiles:
        conventions.append({"kind": "lockfile", "detail": name, "evidence": [name]})

    risks = []
    anchor = _rel(root, info["stacks"][0]["manifest"]) if info["stacks"] else None
    if anchor:
        if not any(c["kind"] == "ci" for c in conventions):
            risks.append({"kind": "no-ci", "detail": "no CI configuration found", "evidence": [anchor]})
        if not lockfiles and info["stacks"][0]["language"] in ("node", "python"):
            risks.append({"kind": "no-lockfile", "detail": "no dependency lockfile found", "evidence": [anchor]})
        if prod and not tests:
            risks.append({"kind": "no-tests", "detail": "source files without any test file", "evidence": [anchor]})
    markers = []
    for rel, path in prod + [(r, p) for r, p in sources if r in tests]:
        for number, line in enumerate(_read_lines(path), 1):
            if MARKER_RE.search(line):
                markers.append(f"{rel}:{number}")
    if markers:
        risks.append({"kind": "todo-markers", "detail": f"{len(markers)} TODO/FIXME/HACK marker(s)",
                      "evidence": markers[:3]})
    large = [(len(_read_lines(path)), rel) for rel, path in prod]
    for lines, rel in sorted([x for x in large if x[0] > LARGE_FILE_LINES], reverse=True)[:3]:
        risks.append({"kind": "large-file", "detail": f"{lines} lines", "evidence": [rel]})
    if len(info["packages"]) > 1:
        risks.append({"kind": "multi-package", "detail": f"{len(info['packages'])} sub-packages share one repository",
                      "evidence": [info["packages"][0]["stacks"][0]["manifest"]]})

    return {"root": root, "scope": info["scope"], "stack": info["stacks"], "packages": info["packages"],
            "architecture": architecture, "conventions": conventions, "risks": risks,
            "facts": {"source_files": len(prod), "test_files": len(tests), "ci_present": info["ci_present"]}}


def render_codebase_map(mapping: dict) -> str:
    lines = ["# Codebase map (brownfield intake)", "",
             "Generated from repository evidence only; `[DISCOVERED_FROM_CODEBASE]` for every line.", ""]
    if mapping["scope"]:
        lines += [f"Scope: `{mapping['scope']}`", ""]
    lines += ["## Stack", *[f"- {s['language']}: {s['commands'] or 'no commands detected'} (`{_rel(mapping['root'], s['manifest'])}`)"
                            for s in mapping["stack"]], ""]
    lines += ["## Packages", *[f"- `{p['path']}`: {', '.join(s['language'] for s in p['stacks'])}"
                               for p in mapping["packages"]], ""]
    for title, key in (("Architecture", "architecture"), ("Conventions", "conventions"), ("Risks", "risks")):
        lines.append(f"## {title}")
        for item in mapping[key]:
            label = item.get("path") or item.get("detail") or ""
            lines.append(f"- {item['kind']}: {label} ({', '.join(item['evidence'])})")
        lines.append("")
    return "\n".join(lines)


def propose_constitution(mapping: dict) -> dict:
    """Principles supported by repository evidence. Never written to the real constitution."""
    kinds = {}
    for item in mapping["conventions"]:
        kinds.setdefault(item["kind"], item)
    principles = []

    def add(pid, title, statement, evidence):
        principles.append({"id": pid, "title": title, "statement": statement, "evidence": evidence})

    if "tests" in kinds:
        add("tests", "Existing tests stay green", "Changes keep the current test suite passing; new behaviour "
            "ships with tests next to the existing ones.", kinds["tests"]["evidence"])
    if "ci" in kinds:
        add("ci", "CI is the merge gate", "Work is not done until the configured CI checks pass.",
            kinds["ci"]["evidence"])
    if "commands" in kinds:
        add("gates", "The repository's own commands are the quality gates",
            f"Use the detected commands ({kinds['commands']['detail']}) instead of inventing new ones.",
            kinds["commands"]["evidence"])
    lint = [kinds[k] for k in ("editorconfig", "eslint", "prettier", "python-lint", "pre-commit") if k in kinds]
    if lint:
        add("style", "Follow the configured style tooling", "Formatting and lint rules come from the committed "
            "configuration files.", [e for item in lint for e in item["evidence"]])
    if "lockfile" in kinds:
        add("deps", "Dependencies are pinned", "Dependency changes update the lockfile in the same change.",
            kinds["lockfile"]["evidence"])
    if "agent-instructions" in kinds:
        add("agent", "Honour committed agent instructions", "The repository's agent instruction file takes "
            "precedence over defaults.", kinds["agent-instructions"]["evidence"])
    if len(mapping["packages"]) > 1:
        add("boundaries", "Respect package boundaries", "A change stays inside one package unless the spec names "
            "the cross-package contract.", [p["stacks"][0]["manifest"] for p in mapping["packages"][:3]])

    unresolved = []
    if not principles:
        unresolved.append("No repository evidence found to derive principles; the constitution must come from the user.")
    lines = ["# Constitution PROPOSAL (not applied)", "",
             "Derived only from repository evidence. A human must review it, then run `speckit-constitution`.", ""]
    for number, p in enumerate(principles, 1):
        lines += [f"## {number}. {p['title']}", p["statement"], f"Evidence: {', '.join(p['evidence'])}", ""]
    lines += [f"- [UNRESOLVED] {text}" for text in unresolved]
    return {"applied": False, "principles": principles, "unresolved": unresolved, "markdown": "\n".join(lines) + "\n"}


def characterization_targets(root: str = ".", scope: str | None = None, limit: int = 10) -> list[dict]:
    """Source files with no matching test file, largest first (candidates for characterization tests)."""
    root, base = _base(root, scope)
    sources = _source_files(root, base)
    # Tests usually live outside the scoped directory, so coverage is judged repo-wide.
    covered = {_test_stem(rel.split("/")[-1]) for rel, _ in _source_files(root, root) if _is_test_file(rel)}
    targets = []
    for rel, path in sources:
        name = rel.split("/")[-1]
        if _is_test_file(rel) or name == "__init__.py":
            continue
        if os.path.splitext(name)[0] in covered:
            continue
        lines = len(_read_lines(path))
        if lines:
            targets.append({"path": rel, "lines": lines, "reason": "no matching test file", "evidence": [rel]})
    targets.sort(key=lambda t: (-t["lines"], t["path"]))
    return targets[:limit]


# --- greenfield --------------------------------------------------------------

_CI_HEADER = "name: ci\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n"


def greenfield_intake() -> dict:
    return {"proposes_only": True, "questions": [
        {"id": "stack", "question": "Which stack should the new project use?", "options": list(STACKS), "required": True},
        {"id": "name", "question": "Project name (lowercase letters, digits, - or _)?", "required": True},
    ], "note": "Answers feed `tracks greenfield propose`; nothing is written until `apply --confirm`."}


def _skeleton(stack: str, name: str) -> tuple[dict, dict]:
    pkg = name.replace("-", "_")
    readme = f"# {name}\n\nBootstrapped by Spec Master (proposal confirmed by the user).\n"
    if stack == "python":
        gate = "python3 -m unittest discover -s tests"
        files = {
            "README.md": readme,
            "pyproject.toml": f'[project]\nname = "{name}"\nversion = "0.1.0"\nrequires-python = ">=3.10"\n',
            f"{pkg}/__init__.py": 'def greet() -> str:\n    return "hello"\n',
            "tests/test_smoke.py": f"import os\nimport sys\nimport unittest\n\nsys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))\nimport {pkg}\n\n\nclass SmokeTests(unittest.TestCase):\n    def test_greet(self):\n        self.assertEqual({pkg}.greet(), \"hello\")\n\n\nif __name__ == \"__main__\":\n    unittest.main()\n",
            ".github/workflows/ci.yml": _CI_HEADER + f"      - run: {gate}\n",
        }
    elif stack == "node":
        gate = "npm test"
        files = {
            "README.md": readme,
            "package.json": f'{{\n  "name": "{name}",\n  "version": "0.1.0",\n  "scripts": {{"test": "node --test"}}\n}}\n',
            "src/index.js": "exports.greet = () => 'hello';\n",
            "test/index.test.js": "const test = require('node:test');\nconst assert = require('node:assert');\nconst { greet } = require('../src/index.js');\n\ntest('greet', () => assert.strictEqual(greet(), 'hello'));\n",
            ".github/workflows/ci.yml": _CI_HEADER + f"      - uses: actions/setup-node@v4\n      - run: {gate}\n",
        }
    elif stack == "go":
        gate = "go test ./..."
        files = {
            "README.md": readme,
            "go.mod": f"module {name}\n\ngo 1.21\n",
            "main.go": 'package main\n\nfunc Greet() string { return "hello" }\n\nfunc main() { println(Greet()) }\n',
            "main_test.go": 'package main\n\nimport "testing"\n\nfunc TestGreet(t *testing.T) {\n\tif Greet() != "hello" {\n\t\tt.Fatal("greet")\n\t}\n}\n',
            ".github/workflows/ci.yml": _CI_HEADER + f"      - uses: actions/setup-go@v5\n      - run: {gate}\n",
        }
    else:
        gate = "cargo test"
        files = {
            "README.md": readme,
            "Cargo.toml": f'[package]\nname = "{name}"\nversion = "0.1.0"\nedition = "2021"\n',
            "src/lib.rs": 'pub fn greet() -> &\'static str { "hello" }\n\n#[cfg(test)]\nmod tests {\n    #[test]\n    fn greet() { assert_eq!(super::greet(), "hello"); }\n}\n',
            ".github/workflows/ci.yml": _CI_HEADER + f"      - run: {gate}\n",
        }
    return files, {"test": gate}


def greenfield_propose(root: str, stack: str, name: str) -> dict:
    """Describe the skeleton, CI and minimal gate for `stack`. Writes nothing."""
    if stack not in STACKS:
        raise ValueError(f"unknown stack {stack!r}; choose one of {', '.join(STACKS)}")
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise ValueError(f"invalid project name {name!r}: use lowercase letters, digits, '-' or '_'")
    root = os.path.abspath(root)
    files, gates = _skeleton(stack, name)
    return {"applied": False, "requires_confirmation": True, "stack": stack, "name": name, "gates": gates,
            "files": [{"path": path, "content": content, "exists": _exists(root, path)}
                      for path, content in sorted(files.items())],
            "next_step": "Review the files, then run `tracks greenfield apply --confirm` with the same stack and name."}


def greenfield_apply(root: str, stack: str, name: str, confirmed: bool = False) -> dict:
    """Write the proposal's missing files; refuses without explicit confirmation."""
    if not confirmed:
        raise ConfirmationRequired("greenfield apply needs explicit confirmation (--confirm); nothing was written")
    proposal = greenfield_propose(root, stack, name)
    root = os.path.abspath(root)
    written, skipped = [], []
    for item in proposal["files"]:
        (written if write_new_file(root, item["path"], item["content"]) else skipped).append(item["path"])
    return {"applied": True, "stack": stack, "name": name, "written": written, "skipped": skipped,
            "gates": proposal["gates"]}
