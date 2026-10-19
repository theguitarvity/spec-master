"""The baseline cases in evals/baseline/: the builder's output feeds `baseline
plan`, and the hidden check of bugfix-xs tells a real fix from the others."""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _pathfix  # noqa: F401
import baseline

EVALS = Path(__file__).resolve().parents[2] / "evals" / "baseline"
FIX = ("shop/catalog.py", "start = number * size", "start = (number - 1) * size")
TEST = ("tests/test_catalog.py", "\n\nclass FirstPageTests(unittest.TestCase):\n"
        "    def test_page_one_starts_at_the_first_item(self):\n"
        "        self.assertEqual(page(list(range(25)), 1, 10), list(range(10)))\n")


def load_builder():
    spec = importlib.util.spec_from_file_location("baseline_build", EVALS / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(EVALS.is_dir() and shutil.which("git"), "needs the repository's evals/ and git")
class BaselineCasesTests(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.out, True)
        self.builder = load_builder()
        with mock.patch.object(self.builder, "_spec_kit"):  # Spec Kit needs uvx and the network
            self.data = self.builder.build(self.out)
        self.case = self.data["cases"][0]

    def test_cases_file_feeds_the_plan(self):
        cases = baseline.load_cases(str(self.out / "cases.json"))
        self.assertEqual(baseline.validate_cases(cases, ["specmaster", "direct"]), [])
        plan = baseline.plan(cases, ["specmaster", "direct"], 1, 5)
        self.assertEqual((plan["total_runs"], plan["worst_case_budget_usd"]), (2, 10.0))
        self.assertEqual(self.case["prompts"]["specmaster"], "/spec-master BUG.md")

    def test_headless_decisions_are_seeded(self):
        repo = Path(self.case["repo"])
        state = json.loads((repo / ".spec-master" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual((state["context"], state["workflow"]), ("BUG.md", "trunk"))
        self.assertEqual(list(state["fingerprint"]), ["BUG.md"])  # Step 0 resumes: no "resume or restart?"
        self.assertEqual(subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True,
                                        text=True, check=True).stdout, "")

    def scenario(self, *edits):
        work = self.out / f"work-{len(edits)}-{'-'.join(e[0].split('/')[0] for e in edits)}"
        subprocess.run(["git", "-C", self.case["repo"], "worktree", "add", "-q", "--detach", str(work),
                        self.case["rev"]], check=True)
        self.addCleanup(subprocess.run, ["git", "-C", self.case["repo"], "worktree", "remove", "--force",
                                         str(work)], capture_output=True, check=False)
        for relative, *change in edits:
            path = work / relative
            text = path.read_text(encoding="utf-8")
            path.write_text(text.replace(change[0], change[1]) if len(change) == 2 else text + change[0],
                            encoding="utf-8")
        results = []
        for check in self.case["checks"]:
            argv = [sys.executable, *check[1:]] if check[0] == "python3" else check
            results.append(subprocess.run(argv, cwd=work, capture_output=True, text=True, timeout=120,
                                          check=False).returncode == 0)
        return results

    def test_only_a_fix_with_a_regression_test_passes(self):
        self.assertEqual(self.scenario(), [True, False])  # the suite does not catch the bug
        self.assertEqual(self.scenario(FIX), [True, False])  # fixed, but no test would catch a relapse
        self.assertEqual(self.scenario(TEST), [False, False])
        self.assertEqual(self.scenario(FIX, TEST), [True, True])

    def test_out_must_stay_outside_the_repository(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            self.builder.main(["--out", str(EVALS / "out")])


if __name__ == "__main__":
    unittest.main()
