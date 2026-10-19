"""Throwaway git repositories for the kernel tests (real git, real unittest)."""
import json
import os
import shutil
import subprocess
import tempfile

CALC = "def add(a, b):\n    return a + b\n"
TEST_CALC = (
    "import unittest\n\nfrom src.calc import add\n\n\n"
    "class CalcTests(unittest.TestCase):\n"
    "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n"
)


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


def write(root, relative, text):
    path = os.path.join(root, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def make_repo(with_tests=True):
    root = tempfile.mkdtemp(prefix="sm-kernel-")
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Kernel Test")
    git(root, "config", "commit.gpgsign", "false")
    write(root, "src/__init__.py", "")
    write(root, "src/calc.py", CALC)
    if with_tests:
        write(root, "tests/__init__.py", "")
        write(root, "tests/test_calc.py", TEST_CALC)
        # Declared gate: the suite imports `src.`, so it runs from the root.
        write(root, ".spec-master/gates.json", json.dumps([
            {"name": "unit", "command": ["python3", "-m", "unittest", "discover", "-s", "tests", "-t", "."]},
        ]))
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    return root


def remove(root):
    subprocess.run(["git", "worktree", "prune"], cwd=root, capture_output=True)
    shutil.rmtree(root, ignore_errors=True)


def note(change_id, intent, checks, files):
    lines = [f"Intent: {intent} [EXPLICIT]"] + [f"- {check}" for check in checks] + [f"Files: {', '.join(files)}"]
    return "\n".join(lines) + "\n"
