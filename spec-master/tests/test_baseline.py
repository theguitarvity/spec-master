import _pathfix  # noqa: F401

import contextlib
import datetime as dt
import json
import os
import shutil
import subprocess
import tempfile
import unittest

import baseline

SECRET = "SECRET-ANSWER-MARKER"


def _case(case_id="bugfix-xs", **overrides):
    case = {
        "id": case_id, "repo": "/repos/app", "rev": "abc123",
        "prompts": {"specmaster": "/spec-master fix the off-by-one", "direct": "Fix the off-by-one in pager.py"},
        "checks": [["python3", "-m", "unittest"], ["git", "diff", "--quiet", "HEAD", "--", "README.md"]],
        "permission_mode": "acceptEdits",
        "allowed_tools": ["Edit", "Bash(python3:*)"],
        "description": "extra keys are ignored",
    }
    case.update(overrides)
    return case


def _result_json(cost=0.5, turns=10, tokens=(100, 900), is_error=False, subtype="success", duration_ms=60000):
    return json.dumps({
        "type": "result", "subtype": subtype, "is_error": is_error, "duration_ms": duration_ms,
        "duration_api_ms": duration_ms - 5000, "num_turns": turns, "result": f"{SECRET} done",
        "session_id": "sess", "total_cost_usd": cost,
        "usage": {"input_tokens": tokens[0], "output_tokens": tokens[1]},
        "modelUsage": {"m": {"inputTokens": tokens[0], "outputTokens": tokens[1], "cacheReadInputTokens": 1000,
                             "cacheCreationInputTokens": 10, "costUSD": cost}},
    })


class FakeRunner:
    """Scripted stand-in for subprocess.run: records calls, never executes anything."""

    def __init__(self, claude=None, checks=None, diff="diff --git a/x b/x\n"):
        self.calls = []
        self.claude = list(claude or [])   # queue of (returncode, stdout) or exception instances
        self.checks = checks or {}         # argv[0] -> returncode
        self.diff = diff

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        if argv[0] == "claude":
            item = self.claude.pop(0) if self.claude else (0, _result_json())
            if isinstance(item, BaseException):
                raise item
            return subprocess.CompletedProcess(argv, item[0], stdout=item[1], stderr="warn: something\n")
        if argv[0] == "git":
            if "diff" in argv:
                return subprocess.CompletedProcess(argv, 0, stdout=self.diff, stderr="")
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        code = self.checks.get(argv[0], 0)
        return subprocess.CompletedProcess(argv, code, stdout="" if code == 0 else "1 failed\n", stderr="")

    def of(self, program):
        return [(argv, kwargs) for argv, kwargs in self.calls if argv[0] == program]


class FakeWorkdirs:
    def __init__(self):
        self.created = []
        self.cleaned = []

    @contextlib.contextmanager
    def __call__(self, case, *, runner):
        path = tempfile.mkdtemp(prefix="wd-")
        self.created.append((case["id"], path))
        try:
            yield path
        finally:
            shutil.rmtree(path, ignore_errors=True)
            self.cleaned.append(path)


class Clock:
    def __init__(self, step=2.5):
        self.value = 0.0
        self.step = step

    def __call__(self):
        self.value += self.step
        return self.value


def _now():
    return dt.datetime(2026, 9, 27, 12, 0, tzinfo=dt.timezone.utc)


class PlanTests(unittest.TestCase):
    def test_matrix_argv_and_worst_case_budget(self):
        cases = [_case("a"), _case("b", permission_mode=None, allowed_tools=None)]
        result = baseline.plan(cases, ["specmaster", "direct"], 3, 5)
        self.assertEqual(result["total_runs"], 12)
        self.assertEqual(result["worst_case_budget_usd"], 60.0)  # 3 runs x 2 cases x 2 arms x US$ 5
        first = result["matrix"][0]
        self.assertEqual(first["argv"], ["claude", "-p", "/spec-master fix the off-by-one", "--output-format", "json",
                                         "--max-budget-usd", "5", "--permission-mode", "acceptEdits",
                                         "--allowedTools", "Edit", "Bash(python3:*)"])
        self.assertEqual((first["case"], first["arm"], first["run"], first["out"]), ("a", "specmaster", 1,
                                                                                     "a/specmaster-1.json"))
        self.assertEqual(result["matrix"][3]["argv"][-4:], ["--output-format", "json", "--max-budget-usd", "5"])
        # interleaved: repetition -> case -> arm
        self.assertEqual([(m["run"], m["case"], m["arm"]) for m in result["matrix"][:4]],
                         [(1, "a", "specmaster"), (1, "a", "direct"), (1, "b", "specmaster"), (1, "b", "direct")])
        self.assertEqual(result["matrix"][0]["checks"], _case()["checks"])

    def test_budget_and_model_formatting(self):
        argv = baseline.plan([_case()], ["direct"], 1, 2.5, model="claude-x", claude="/opt/claude")["matrix"][0]["argv"]
        self.assertEqual(argv[:9], ["/opt/claude", "-p", "Fix the off-by-one in pager.py", "--output-format", "json",
                                    "--max-budget-usd", "2.5", "--model", "claude-x"])

    def test_invalid_input_is_rejected(self):
        bad = [
            ([_case(prompts={"direct": "x"})], ["specmaster", "direct"], 1, 5, "missing prompt"),
            ([_case(id="../escape")], ["direct"], 1, 5, ".id must match"),
            ([_case(), _case()], ["direct"], 1, 5, "duplicated"),
            ([_case(rev="--upload-pack=evil")], ["direct"], 1, 5, "rev"),
            ([_case(prompts={"direct": "--dangerously-skip-permissions"})], ["direct"], 1, 5, "starts with '-'"),
            ([_case(checks=[[]])], ["direct"], 1, 5, "checks"),
            ([_case(checks="make test")], ["direct"], 1, 5, "checks"),
            ([_case(allowed_tools=["--all"])], ["direct"], 1, 5, "allowed_tools"),
            ([_case()], ["direct", "direct"], 1, 5, "unique"),
            ([_case()], ["di rect"], 1, 5, "arm"),
            ([_case()], ["direct"], 0, 5, "runs"),
            ([_case()], ["direct"], True, 5, "runs"),
            ([_case()], ["direct"], 1, 0, "max_budget_usd"),
            ([_case()], ["direct"], 1, float("inf"), "max_budget_usd"),
            ([], ["direct"], 1, 5, "non-empty list"),
        ]
        for cases, arms, runs, budget, needle in bad:
            with self.assertRaises(ValueError) as ctx:
                baseline.plan(cases, arms, runs, budget)
            self.assertIn(needle, str(ctx.exception))

    def test_load_cases(self):
        tmp = tempfile.mkdtemp()
        try:
            listed = os.path.join(tmp, "a.json")
            wrapped = os.path.join(tmp, "b.json")
            broken = os.path.join(tmp, "c.json")
            with open(listed, "w", encoding="utf-8") as fh:
                json.dump([_case()], fh)
            with open(wrapped, "w", encoding="utf-8") as fh:
                json.dump({"cases": [_case()]}, fh)
            with open(broken, "w", encoding="utf-8") as fh:
                json.dump({"case": 1}, fh)
            self.assertEqual(baseline.load_cases(listed), baseline.load_cases(wrapped))
            with self.assertRaises(ValueError):
                baseline.load_cases(broken)
        finally:
            shutil.rmtree(tmp)


class RunTests(unittest.TestCase):
    def setUp(self):
        self.out = tempfile.mkdtemp()
        self.workdirs = FakeWorkdirs()

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)

    def _run(self, runner, cases=None, arms=("direct",), runs=1, **kwargs):
        return baseline.run(cases or [_case()], arms=list(arms), runs=runs, max_budget_usd=3,
                            out_dir=self.out, confirm=True, runner=runner, workdir_factory=self.workdirs,
                            clock=Clock(), now=_now, **kwargs)

    def test_refuses_without_confirmation(self):
        runner = FakeRunner()
        for confirm in (False, None, "yes"):
            with self.assertRaises(baseline.ConfirmationRequired) as ctx:
                baseline.run([_case()], arms=["direct"], runs=2, max_budget_usd=4, out_dir=self.out,
                             confirm=confirm, runner=runner, workdir_factory=self.workdirs)
            self.assertIn("US$ 8.00", str(ctx.exception))
            self.assertEqual(ctx.exception.plan["total_runs"], 2)
        self.assertEqual((runner.calls, self.workdirs.created, os.listdir(self.out)), ([], [], []))

    def test_successful_runs_write_one_result_each(self):
        runner = FakeRunner()
        summary = self._run(runner, arms=["specmaster", "direct"], runs=2)
        self.assertEqual(summary["total_runs"], 4)
        self.assertEqual(sorted(os.listdir(os.path.join(self.out, "bugfix-xs"))),
                         ["direct-1.diff", "direct-1.json", "direct-2.diff", "direct-2.json",
                          "specmaster-1.diff", "specmaster-1.json", "specmaster-2.diff", "specmaster-2.json"])
        with open(os.path.join(self.out, "bugfix-xs", "direct-2.json"), encoding="utf-8") as fh:
            result = json.load(fh)
        self.assertEqual((result["case"], result["arm"], result["run"], result["success"]),
                         ("bugfix-xs", "direct", 2, True))
        self.assertEqual((result["exit_code"], result["timed_out"], result["error"]), (0, False, None))
        self.assertEqual(result["wall_seconds"], 2.5)
        self.assertEqual((result["started_at"], result["ended_at"]), ("2026-09-27T12:00:00.000Z",
                                                                      "2026-09-27T12:00:00.000Z"))
        self.assertEqual((result["headless"]["cost_usd"], result["headless"]["turns"],
                          result["headless"]["total_tokens"]), (0.5, 10, 1000))
        self.assertEqual([c["passed"] for c in result["checks"]], [True, True])
        self.assertEqual(result["diff_path"], "bugfix-xs/direct-2.diff")
        self.assertEqual(result["stderr_tail"], "warn: something\n")
        self.assertNotIn(SECRET, json.dumps(result))  # the answer text is never stored
        self.assertEqual(len(self.workdirs.created), 4)
        self.assertEqual(len(self.workdirs.cleaned), 4)

    def test_processes_are_argv_lists_run_inside_the_workdir(self):
        runner = FakeRunner()
        self._run(runner)
        workdir = self.workdirs.created[0][1]
        (argv, kwargs), = runner.of("claude")
        self.assertEqual(argv[:3], ["claude", "-p", "Fix the off-by-one in pager.py"])
        self.assertEqual((kwargs["cwd"], kwargs["stdin"], kwargs["capture_output"], kwargs["text"]),
                         (workdir, subprocess.DEVNULL, True, True))
        self.assertNotIn("shell", kwargs)
        self.assertEqual(kwargs["timeout"], baseline.DEFAULT_TIMEOUT_SECONDS)
        checks = [(argv, kwargs) for argv, kwargs in runner.calls if argv[0] == "python3"]
        self.assertEqual(checks[0][1]["cwd"], workdir)
        git = [argv for argv, _ in runner.of("git")]
        self.assertIn(["git", "-C", workdir, "add", "-A"], git)
        self.assertIn(["git", "-C", workdir, "diff", "--cached", "--binary"], git)

    def test_failures_are_recorded_not_raised(self):
        runner = FakeRunner(claude=[
            (0, _result_json(cost=0.7)),                                   # check fails below
            (1, _result_json(is_error=True, subtype="error_max_budget_usd", cost=3.1)),
            (0, "not json at all"),
            subprocess.TimeoutExpired(["claude"], 10, output=b'{"type": "res'),
            FileNotFoundError(2, "No such file or directory: 'claude'"),
        ], checks={"python3": 1})
        cases = [_case("c1"), _case("c2"), _case("c3"), _case("c4"), _case("c5")]
        outcome = self._run(runner, cases=cases, keep_diff=False)
        by_case = {r["case"]: r for r in outcome["results"]}
        self.assertFalse(any(r["success"] for r in outcome["results"]))
        self.assertEqual([c["passed"] for c in by_case["c1"]["checks"]], [False, True])
        self.assertEqual(by_case["c1"]["checks"][0]["output_tail"], "1 failed\n")
        self.assertEqual((by_case["c2"]["exit_code"], by_case["c2"]["headless"]["is_error"],
                          by_case["c2"]["headless"]["subtype"]), (1, True, "error_max_budget_usd"))
        self.assertIsNone(by_case["c3"]["headless"])
        self.assertIn("not a `--output-format json` result", by_case["c3"]["error"])
        self.assertTrue(by_case["c4"]["timed_out"])
        self.assertIn("FileNotFoundError", by_case["c5"]["error"])
        self.assertEqual(by_case["c5"]["checks"], [])
        self.assertIsNone(by_case["c1"]["diff_path"])
        captures = [argv for argv, _ in runner.of("git") if "add" in argv or "--cached" in argv]
        self.assertEqual(captures, [])  # keep_diff=False: no diff capture (the git check itself still runs)
        self.assertEqual(len(self.workdirs.cleaned), 5)
        for case_id in by_case:
            self.assertTrue(os.path.exists(os.path.join(self.out, case_id, "direct-1.json")))

    def test_workdir_failure_is_recorded(self):
        @contextlib.contextmanager
        def broken(case, *, runner):
            raise RuntimeError("git worktree add failed")
            yield  # pragma: no cover

        result = baseline.run([_case()], arms=["direct"], runs=1, max_budget_usd=1, out_dir=self.out,
                              confirm=True, runner=FakeRunner(), workdir_factory=broken)["results"][0]
        self.assertEqual((result["success"], result["workdir"]), (False, None))
        self.assertIn("git worktree add failed", result["error"])

    def test_load_results_round_trip(self):
        self._run(FakeRunner(), arms=["specmaster", "direct"], runs=2)
        with open(os.path.join(self.out, "notes.json"), "w", encoding="utf-8") as fh:
            fh.write("{}")
        loaded = baseline.load_results(self.out)
        self.assertEqual([(r["arm"], r["run"]) for r in loaded],
                         [("direct", 1), ("direct", 2), ("specmaster", 1), ("specmaster", 2)])


class GitWorktreeTests(unittest.TestCase):
    def test_creates_detached_worktree_and_removes_it(self):
        runner = FakeRunner()
        with baseline.git_worktree(_case(), runner=runner) as path:
            self.assertTrue(path.endswith(os.sep + "wt"))
            parent = os.path.dirname(path)
            self.assertTrue(os.path.isdir(parent))
        calls = [argv for argv, _ in runner.calls]
        self.assertEqual(calls, [["git", "-C", "/repos/app", "worktree", "add", "--detach", path, "abc123"],
                                 ["git", "-C", "/repos/app", "worktree", "remove", "--force", path]])
        self.assertFalse(os.path.exists(parent))

    def test_cleans_up_on_error_and_prunes_when_remove_fails(self):
        class Runner(FakeRunner):
            def __call__(self, argv, **kwargs):
                self.calls.append((list(argv), kwargs))
                return subprocess.CompletedProcess(argv, 1 if "remove" in argv else 0, stdout="", stderr="")

        runner = Runner()
        with self.assertRaises(KeyError):
            with baseline.git_worktree(_case(), runner=runner) as path:
                raise KeyError("boom")
        self.assertEqual([argv[3:5] for argv, _ in runner.calls],
                         [["worktree", "add"], ["worktree", "remove"], ["worktree", "prune"]])
        self.assertFalse(os.path.exists(os.path.dirname(path)))

    def test_failed_add_raises_and_removes_nothing(self):
        class Runner(FakeRunner):
            def __call__(self, argv, **kwargs):
                self.calls.append((list(argv), kwargs))
                return subprocess.CompletedProcess(argv, 128, stdout="", stderr="fatal: invalid reference: abc123")

        runner = Runner()
        with self.assertRaises(RuntimeError) as ctx:
            with baseline.git_worktree(_case(), runner=runner):
                self.fail("must not yield")
        self.assertIn("invalid reference", str(ctx.exception))
        self.assertEqual(len(runner.calls), 1)


def _fake_result(case, arm, run, cost, success=True, tokens=1000, turns=10, duration_ms=60000, wall=70.0):
    headless = {"cost_usd": cost, "total_tokens": tokens, "input_tokens": tokens // 10,
                "output_tokens": tokens - tokens // 10, "cache_read_input_tokens": 5000,
                "cache_creation_input_tokens": 100, "turns": turns, "duration_ms": duration_ms}
    return {"case": case, "arm": arm, "run": run, "success": success, "headless": headless, "wall_seconds": wall}


class SummarizeTests(unittest.TestCase):
    def test_medians_cv_success_and_overhead(self):
        results = [
            _fake_result("std", "direct", 1, 1.0, tokens=1000, turns=10, duration_ms=60000),
            _fake_result("std", "direct", 2, 2.0, tokens=2000, turns=12, duration_ms=80000),
            _fake_result("std", "direct", 3, 3.0, tokens=3000, turns=14, duration_ms=100000, success=False),
            _fake_result("std", "specmaster", 1, 5.0, tokens=9000, turns=40, duration_ms=300000),
            _fake_result("std", "specmaster", 2, 6.0, tokens=10000, turns=44, duration_ms=320000),
            {"case": "std", "arm": "specmaster", "run": 3, "success": False, "headless": None, "wall_seconds": 5.0},
        ]
        summary = baseline.summarize(results)
        direct = summary["cases"]["std"]["arms"]["direct"]
        self.assertEqual((direct["runs"], direct["measured_runs"], direct["successes"], direct["success_rate"]),
                         (3, 3, 2, 0.6667))
        self.assertEqual((direct["median_cost_usd"], direct["cv_cost"]), (2.0, 0.5))  # stdev 1 / mean 2
        self.assertEqual((direct["median_total_tokens"], direct["median_turns"], direct["median_duration_ms"]),
                         (2000.0, 12.0, 80000.0))
        spec = summary["cases"]["std"]["arms"]["specmaster"]
        self.assertEqual((spec["runs"], spec["measured_runs"], spec["success_rate"]), (3, 2, 0.6667))
        self.assertEqual((spec["median_cost_usd"], spec["median_wall_seconds"]), (5.5, 70.0))
        self.assertEqual(summary["cases"]["std"]["overhead_vs_direct"],
                         {"specmaster": {"cost_usd": 2.75, "total_tokens": 4.75, "duration_ms": 3.875}})
        self.assertEqual(summary["reference_arm"], "direct")

    def test_without_direct_arm_or_enough_runs(self):
        summary = baseline.summarize([_fake_result("x", "specmaster", 1, 4.0)])
        case = summary["cases"]["x"]
        self.assertNotIn("overhead_vs_direct", case)
        self.assertIsNone(case["arms"]["specmaster"]["cv_cost"])  # one run: no variation to report
        empty = baseline.summarize([{"case": "y", "arm": "direct", "run": 1, "success": False, "headless": None}])
        self.assertIsNone(empty["cases"]["y"]["arms"]["direct"]["median_cost_usd"])
        self.assertEqual(baseline.summarize([]), {"reference_arm": "direct", "cases": {}})


if __name__ == "__main__":
    unittest.main()
