"""Path classification shared by the lanes and the hooks (import-light: the
hook daemon runs on every tool call)."""
from __future__ import annotations

import os
import re

TEST_DIRS = {"tests", "test", "e2e", "__tests__", "spec", "testing"}
DOC_DIRS = {"docs", "doc", "documentation"}
DOC_EXTENSIONS = (".md", ".rst", ".txt", ".adoc")
MANIFESTS = {
    "package.json", "pyproject.toml", "setup.py", "setup.cfg", "go.mod", "Cargo.toml", "pom.xml",
    "build.gradle", "build.gradle.kts", "Gemfile", "composer.json", "Pipfile", "poetry.lock",
    "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "Cargo.lock", "go.sum",
}
_REQUIREMENTS_RE = re.compile(r"(^|/)requirements[\w.-]*\.txt$")
_TEST_NAME_RE = re.compile(r"(^test_.*|_test\.\w+|\.test\.\w+|\.spec\.\w+|Tests?\.\w+)$")


def norm(path: str) -> str:
    path = (path or "").replace(os.sep, "/").strip()
    while path.startswith("./"):
        path = path[2:]
    return path


def is_test_path(path: str) -> bool:
    name = norm(path).rsplit("/", 1)[-1]
    parts = norm(path).lower().split("/")
    # CamelCase suffixes (CalcTest.java, CalcTests.cs) only match the original
    # case, so `latest.py` is never a test.
    return any(part in TEST_DIRS for part in parts[:-1]) or bool(_TEST_NAME_RE.search(parts[-1])) \
        or bool(_TEST_NAME_RE.search(name))


def is_doc_path(path: str) -> bool:
    parts = norm(path).lower().split("/")
    return any(part in DOC_DIRS for part in parts[:-1]) or parts[-1].endswith(DOC_EXTENSIONS)


def is_manifest(path: str) -> bool:
    path = norm(path)
    return path.rsplit("/", 1)[-1] in MANIFESTS or bool(_REQUIREMENTS_RE.search(path))


def is_harness(path: str) -> bool:
    return norm(path).startswith((".spec-master/", "specs/"))


def production_files(paths) -> list[str]:
    return [p for p in (norm(x) for x in paths)
            if p and not is_test_path(p) and not is_doc_path(p) and not is_harness(p)]


def module_of(path: str) -> str:
    path = norm(path)
    return path.rsplit("/", 1)[0] if "/" in path else "."
