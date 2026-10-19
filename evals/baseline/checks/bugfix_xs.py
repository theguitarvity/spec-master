#!/usr/bin/env python3
"""Hidden acceptance check of the bugfix-xs baseline case.

Runs in the run's worktree (the cwd) after the agent finished. It passes when:

1. `page` behaves as BUG.md describes, and still refuses page 0 and sizes
   below 1;
2. the tests in `tests/` fail once the base revision's `shop/catalog.py`
   (the bug) is put back into a copy of the tree, so the fix came with a
   regression test that catches it.

    python3 bugfix_xs.py --base <case revision>

Exit 0 when both hold; otherwise 1, with the reasons on stderr. The agent
never sees this file: it lives outside the case repository.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

SUITE = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."]


def behaviour(root: str) -> list[str]:
    sys.path.insert(0, root)
    from shop.catalog import page  # noqa: PLC0415 - the tree under test

    items = list(range(1, 26))
    problems = []
    expected = {1: list(range(1, 11)), 2: list(range(11, 21)), 3: list(range(21, 26)), 4: []}
    for number, want in expected.items():
        got = page(items, number, 10)
        if got != want:
            problems.append(f"page(1..25, {number}, 10) returned {got}, expected {want}")
    if page(items, 1) != list(range(1, 11)):
        problems.append("page(1..25, 1) no longer uses pages of 10")
    for args in ((items, 0), (items, 1, 0)):
        try:
            page(*args)
        except ValueError:
            continue
        problems.append(f"page(items, {', '.join(map(str, args[1:]))}) no longer raises ValueError")
    return problems


def regression_test(root: str, base: str) -> list[str]:
    buggy = subprocess.run(["git", "-C", root, "show", f"{base}:shop/catalog.py"],
                           capture_output=True, text=True, check=False)
    if buggy.returncode != 0:
        return [f"cannot read shop/catalog.py at {base}: {buggy.stderr.strip()}"]
    with tempfile.TemporaryDirectory() as copy:
        for name in ("shop", "tests"):
            shutil.copytree(os.path.join(root, name), os.path.join(copy, name),
                            ignore=shutil.ignore_patterns("__pycache__"))
        with open(os.path.join(copy, "shop", "catalog.py"), "w", encoding="utf-8") as fh:
            fh.write(buggy.stdout)
        suite = subprocess.run(SUITE, cwd=copy, capture_output=True, text=True, timeout=300, check=False)
    if suite.returncode == 0:
        return ["the tests in tests/ still pass with the bug put back: no regression test catches it"]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", required=True, help="the case revision (the buggy commit)")
    args = parser.parse_args(argv)
    root = os.getcwd()
    problems = behaviour(root) + regression_test(root, args.base)
    for problem in problems:
        print(f"bugfix-xs: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
