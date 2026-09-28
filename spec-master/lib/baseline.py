"""Measured baseline: the current Spec Master flow vs a direct agentic arm (Wave 0).

Each case is a real task in a local git repository. Every arm gets its own
prompt for the same task (e.g. arm "specmaster" = "/spec-master ...", arm
"direct" = the bare request), and each (run, case, arm) executes

    claude -p <prompt> --output-format json --max-budget-usd N [--model M]
           [--permission-mode P] [--allowedTools T ...]

in a FRESH detached worktree of the case repository at the case revision,
then runs the case checks there. The measurement is the host's own result
JSON (`telemetry.read_headless_result`: total_cost_usd, modelUsage tokens,
num_turns, duration_ms) plus the checks. `summarize` reduces the runs to
medians, the coefficient of variation of cost and success rates, and the
overhead of every arm against the arm named "direct" -- the "sobretaxa"
that decides whether the ceremony is overengineering.

Cases file (JSON): a list of cases, or {"cases": [...]}. Each case:

    {
      "id": "bugfix-xs",                 # [A-Za-z0-9][A-Za-z0-9._-]*, unique; directory name
      "repo": "/abs/path/to/clone",      # local git repository
      "rev": "a1b2c3d",                  # commit / tag / branch, checked out detached
      "prompts": {"specmaster": "/spec-master fix ...", "direct": "Fix ..."},
      "checks": [["python3", "-m", "unittest", "discover", "-s", "tests"]],
      "permission_mode": "acceptEdits",  # optional -> --permission-mode
      "allowed_tools": ["Edit", "Bash(python3:*)"]   # optional -> --allowedTools
    }

Every requested arm needs a prompt in every case. `checks` are argv lists
that must exit 0 in the worktree after the run (default: none). Extra keys
(e.g. "description") are ignored.

Safety and boundaries:
- `plan()` executes nothing; it returns the matrix, the exact argv of every
  run and the worst-case spend = runs x cases x arms x max_budget_usd (the
  host enforces --max-budget-usd between turns, so one run can overshoot by
  at most its last turn).
- `run()` refuses (ConfirmationRequired) unless `confirm=True`, because it
  spends real money.
- Every process goes through the injectable `runner` (default
  `subprocess.run`) with argv lists -- never a shell -- and stdin closed.
  Prompts, revisions and tool names may not start with "-", so they can
  never be read as options.
- Worktrees are created by the run itself (`git worktree add --detach`) and
  removed afterwards; before removal the run's changes are kept as
  `<case>/<arm>-<n>.diff` next to the result (constitution principle V).
- Results never contain the model's answer text: only the parsed metadata.

Output: `<out_dir>/<case>/<arm>-<n>.json`, one per run, holding case, arm,
run, repo, rev, argv, workdir, started_at, ended_at, wall_seconds,
exit_code, timed_out, headless (parsed result or None), checks
([{argv, exit_code, passed, ...}]), success, error, stderr_tail, diff_path.
A run succeeds when the worktree was created, claude exited 0 without
timing out, the result parsed with is_error false, and every check passed.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import glob
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import tempfile
import time

import metrics_export
import telemetry

DIRECT_ARM = "direct"
RESULT_VERSION = 1
DEFAULT_TIMEOUT_SECONDS = 3600.0
DEFAULT_CHECK_TIMEOUT_SECONDS = 900.0
TAIL_CHARS = 2000
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_TOKEN_KEYS = ("total_tokens", "input_tokens", "output_tokens", "cache_read_input_tokens",
               "cache_creation_input_tokens")


class ConfirmationRequired(RuntimeError):
    """`run()` spends real money; it needs confirm=True. `.plan` holds the plan."""

    def __init__(self, the_plan: dict):
        self.plan = the_plan
        super().__init__(
            f"refusing to execute {the_plan['total_runs']} `claude -p` run(s) without confirm=True: "
            f"they spend real money (worst case US$ {the_plan['worst_case_budget_usd']:.2f})")


# ------------------------------------------------------------------ cases / plan

def load_cases(path: str) -> list[dict]:
    """Read a cases file: a JSON list of cases or {"cases": [...]}."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = data.get("cases")
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a list of cases (or {{\"cases\": [...]}})")
    return data


def _is_option_like(value: str) -> bool:
    return value.startswith("-")


def validate_cases(cases, arms) -> list[str]:
    """Problems with `cases` for the given arms ([] = valid)."""
    if not isinstance(cases, list) or not cases:
        return ["cases must be a non-empty list"]
    problems: list[str] = []
    seen: set[str] = set()
    for index, case in enumerate(cases):
        where = f"cases[{index}]"
        if not isinstance(case, dict):
            problems.append(f"{where} must be an object")
            continue
        case_id = case.get("id")
        if not isinstance(case_id, str) or not _SAFE_NAME_RE.match(case_id):
            problems.append(f"{where}.id must match {_SAFE_NAME_RE.pattern}")
        elif case_id in seen:
            problems.append(f"{where}.id {case_id!r} is duplicated")
        else:
            seen.add(case_id)
            where = f"case {case_id!r}"
        if not isinstance(case.get("repo"), str) or not case["repo"]:
            problems.append(f"{where}: repo must be a non-empty path")
        rev = case.get("rev")
        if not isinstance(rev, str) or not rev or _is_option_like(rev):
            problems.append(f"{where}: rev must be a non-empty revision not starting with '-'")
        prompts = case.get("prompts")
        if not isinstance(prompts, dict):
            problems.append(f"{where}: prompts must be an object {{arm: prompt}}")
        else:
            for arm in arms:
                prompt = prompts.get(arm)
                if not isinstance(prompt, str) or not prompt.strip():
                    problems.append(f"{where}: missing prompt for arm {arm!r}")
                elif _is_option_like(prompt):
                    problems.append(f"{where}: prompt for arm {arm!r} starts with '-' (would be read as an option)")
        checks = case.get("checks", [])
        if not isinstance(checks, list) or not all(
                isinstance(check, list) and check and all(isinstance(part, str) and part for part in check)
                for check in checks):
            problems.append(f"{where}: checks must be a list of non-empty argv lists of strings")
        mode = case.get("permission_mode")
        if mode is not None and (not isinstance(mode, str) or not mode or _is_option_like(mode)):
            problems.append(f"{where}: permission_mode must be a non-empty string not starting with '-'")
        tools = case.get("allowed_tools")
        if tools is not None and (not isinstance(tools, list) or not all(
                isinstance(tool, str) and tool and not _is_option_like(tool) for tool in tools)):
            problems.append(f"{where}: allowed_tools must be a list of tool names not starting with '-'")
    return problems


def _check_parameters(arms, runs, max_budget_usd) -> list[str]:
    problems = []
    if not isinstance(arms, (list, tuple)) or not arms:
        problems.append("arms must be a non-empty list")
    else:
        for arm in arms:
            if not isinstance(arm, str) or not _SAFE_NAME_RE.match(arm):
                problems.append(f"arm {arm!r} must match {_SAFE_NAME_RE.pattern}")
        if len(set(arms)) != len(arms):
            problems.append("arms must be unique")
    if isinstance(runs, bool) or not isinstance(runs, int) or runs < 1:
        problems.append("runs must be an integer >= 1")
    if isinstance(max_budget_usd, bool) or not isinstance(max_budget_usd, (int, float)) \
            or not math.isfinite(max_budget_usd) or max_budget_usd <= 0:
        problems.append("max_budget_usd must be a number > 0")
    return problems


def _format_budget(value) -> str:
    value = float(value)
    return str(int(value)) if value.is_integer() else repr(value)


def claude_argv(prompt: str, *, max_budget_usd, permission_mode: str | None = None,
                allowed_tools=None, model: str | None = None, claude: str = "claude") -> list[str]:
    """The exact headless command for one run (argv list, no shell)."""
    argv = [claude, "-p", prompt, "--output-format", "json", "--max-budget-usd", _format_budget(max_budget_usd)]
    if model:
        argv += ["--model", model]
    if permission_mode:
        argv += ["--permission-mode", permission_mode]
    if allowed_tools:
        argv += ["--allowedTools", *allowed_tools]  # variadic option: keep it last
    return argv


def plan(cases, arms, runs, max_budget_usd, *, model: str | None = None, claude: str = "claude") -> dict:
    """The run matrix, the argv of every run and the worst-case spend. Executes nothing.

    Runs are interleaved (repetition -> case -> arm) so slow drifts of the
    API (latency, cache state) hit every arm alike. Raises ValueError when
    the parameters or the cases are invalid.
    """
    arms = list(arms) if isinstance(arms, (list, tuple)) else arms
    problems = _check_parameters(arms, runs, max_budget_usd)
    if not problems:
        problems = validate_cases(cases, arms)
    if problems:
        raise ValueError("invalid baseline: " + "; ".join(problems))
    matrix = []
    for repetition in range(1, runs + 1):
        for case in cases:
            for arm in arms:
                matrix.append({
                    "case": case["id"],
                    "arm": arm,
                    "run": repetition,
                    "repo": case["repo"],
                    "rev": case["rev"],
                    "argv": claude_argv(case["prompts"][arm], max_budget_usd=max_budget_usd,
                                        permission_mode=case.get("permission_mode"),
                                        allowed_tools=case.get("allowed_tools"), model=model, claude=claude),
                    "checks": [list(check) for check in case.get("checks", [])],
                    "out": f"{case['id']}/{arm}-{repetition}.json",
                })
    return {
        "cases": [case["id"] for case in cases],
        "arms": list(arms),
        "runs": runs,
        "max_budget_usd": float(max_budget_usd),
        "model": model,
        "total_runs": len(matrix),
        "worst_case_budget_usd": round(runs * len(cases) * len(arms) * float(max_budget_usd), 4),
        "matrix": matrix,
    }


# ------------------------------------------------------------------------- run

def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _tail(value, limit: int = TAIL_CHARS) -> str | None:
    text = _text(value)
    return text[-limit:] if text else None


def _quiet(runner, argv, **kwargs):
    return runner(argv, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL, **kwargs)


@contextlib.contextmanager
def git_worktree(case: dict, *, runner=subprocess.run):
    """Default workdir factory: a fresh detached worktree of case["repo"] at case["rev"].

    The worktree lives in a new temporary directory and is removed (with
    `git worktree remove --force`, falling back to `rmtree` + `worktree
    prune`) when the block exits -- only what this call created is deleted.
    """
    parent = tempfile.mkdtemp(prefix=f"sm-baseline-{case['id']}-")
    path = os.path.join(parent, "wt")
    added = False
    try:
        proc = _quiet(runner, ["git", "-C", case["repo"], "worktree", "add", "--detach", path, case["rev"]])
        if proc.returncode != 0:
            raise RuntimeError(f"git worktree add failed (exit {proc.returncode}): {_tail(proc.stderr, 500)}")
        added = True
        yield path
    finally:
        removed = False
        if added:
            removed = _quiet(runner, ["git", "-C", case["repo"], "worktree", "remove", "--force", path]).returncode == 0
        shutil.rmtree(parent, ignore_errors=True)
        if added and not removed:
            _quiet(runner, ["git", "-C", case["repo"], "worktree", "prune"])


def _run_checks(checks, workdir, runner, check_timeout) -> list[dict]:
    outcomes = []
    for check in checks:
        outcome = {"argv": list(check), "exit_code": None, "passed": False}
        try:
            proc = _quiet(runner, list(check), cwd=workdir, timeout=check_timeout)
            outcome["exit_code"] = proc.returncode
            outcome["passed"] = proc.returncode == 0
            if not outcome["passed"]:
                outcome["output_tail"] = _tail(_text(proc.stdout) + _text(proc.stderr))
        except subprocess.TimeoutExpired:
            outcome["timed_out"] = True
        except OSError as exc:
            outcome["error"] = f"{type(exc).__name__}: {exc}"
        outcomes.append(outcome)
    return outcomes


def _save_diff(workdir, runner, out_dir, out_rel) -> str | None:
    """Keep the run's changes (tracked and untracked) as a patch next to its result."""
    _quiet(runner, ["git", "-C", workdir, "add", "-A"])
    proc = _quiet(runner, ["git", "-C", workdir, "diff", "--cached", "--binary"])
    patch = _text(proc.stdout)
    if proc.returncode != 0 or not patch:
        return None
    diff_rel = out_rel[:-len(".json")] + ".diff"
    metrics_export.write_text_atomic(os.path.join(out_dir, diff_rel), patch)
    return diff_rel


def _run_one(case, entry, *, runner, workdir_factory, out_dir, timeout, check_timeout, keep_diff,
             clock, now) -> dict:
    result = {
        "baseline_version": RESULT_VERSION,
        "case": entry["case"], "arm": entry["arm"], "run": entry["run"],
        "repo": entry["repo"], "rev": entry["rev"], "argv": entry["argv"],
        "workdir": None, "started_at": None, "ended_at": None, "wall_seconds": None,
        "exit_code": None, "timed_out": False, "headless": None, "checks": [],
        "success": False, "error": None, "stderr_tail": None, "diff_path": None,
    }
    try:
        with workdir_factory(case, runner=runner) as workdir:
            result["workdir"] = workdir
            result["started_at"] = _iso(now())
            started = clock()
            stdout = None
            try:
                proc = _quiet(runner, entry["argv"], cwd=workdir, timeout=timeout)
                result["exit_code"] = proc.returncode
                result["stderr_tail"] = _tail(proc.stderr)
                stdout = proc.stdout
            except subprocess.TimeoutExpired as exc:
                result["timed_out"] = True
                stdout = exc.stdout
            result["wall_seconds"] = round(clock() - started, 3)
            result["ended_at"] = _iso(now())
            try:
                result["headless"] = telemetry.read_headless_result(json.loads(_text(stdout)))
            except (ValueError, TypeError):
                result["error"] = "claude output is not a `--output-format json` result"
            result["checks"] = _run_checks(entry["checks"], workdir, runner, check_timeout)
            if keep_diff:
                result["diff_path"] = _save_diff(workdir, runner, out_dir, entry["out"])
    except Exception as exc:  # noqa: BLE001 -- recorded in the result; the matrix goes on
        result["error"] = f"{type(exc).__name__}: {exc}"
    headless = result["headless"]
    result["success"] = bool(
        result["error"] is None and not result["timed_out"] and result["exit_code"] == 0
        and headless is not None and headless.get("is_error") is False
        and all(check["passed"] for check in result["checks"]))
    return result


def run(cases, *, arms, runs, max_budget_usd, out_dir, confirm, runner=None, workdir_factory=None,
        model: str | None = None, claude: str = "claude", timeout: float = DEFAULT_TIMEOUT_SECONDS,
        check_timeout: float = DEFAULT_CHECK_TIMEOUT_SECONDS, keep_diff: bool = True,
        clock=None, now=None) -> dict:
    """Execute the plan and write one result JSON per run. SPENDS MONEY.

    confirm          must be True, else ConfirmationRequired (nothing runs)
    runner           callable(argv, **kwargs) like subprocess.run (default)
    workdir_factory  callable(case, runner=...) -> context manager yielding
                     the working directory (default: `git_worktree`)
    timeout          seconds for each claude run; check_timeout per check
    keep_diff        save each run's changes as <case>/<arm>-<n>.diff
    clock / now      monotonic seconds / aware-datetime providers (tests)

    Returns {"out_dir", "total_runs", "worst_case_budget_usd", "results",
    "summary"}; a failing run is recorded, never raised.
    """
    the_plan = plan(cases, arms, runs, max_budget_usd, model=model, claude=claude)
    if confirm is not True:
        raise ConfirmationRequired(the_plan)
    runner = runner or subprocess.run
    workdir_factory = workdir_factory or git_worktree
    clock = clock or time.monotonic
    now = now or _utcnow
    by_id = {case["id"]: case for case in cases}
    results = []
    for entry in the_plan["matrix"]:
        result = _run_one(by_id[entry["case"]], entry, runner=runner, workdir_factory=workdir_factory,
                          out_dir=out_dir, timeout=timeout, check_timeout=check_timeout, keep_diff=keep_diff,
                          clock=clock, now=now)
        metrics_export.write_text_atomic(os.path.join(out_dir, entry["out"]),
                                         json.dumps(result, indent=2, sort_keys=True) + "\n")
        results.append(result)
    return {"out_dir": out_dir, "total_runs": the_plan["total_runs"],
            "worst_case_budget_usd": the_plan["worst_case_budget_usd"], "results": results,
            "summary": summarize(results)}


def load_results(out_dir: str) -> list[dict]:
    """Read back every `<case>/<arm>-<n>.json` result under out_dir (sorted)."""
    results = []
    for path in glob.glob(os.path.join(glob.escape(out_dir), "*", "*.json")):
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and {"case", "arm", "run"} <= set(data):
            results.append(data)
    return sorted(results, key=lambda r: (str(r["case"]), str(r["arm"]), r["run"]))


# ---------------------------------------------------------------------- summary

def _numbers(values) -> list[float]:
    return [float(v) for v in values
            if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)]


def _median(values):
    numbers = _numbers(values)
    return round(statistics.median(numbers), 6) if numbers else None


def _cv(values):
    """Sample coefficient of variation (stdev / mean); None with < 2 values or mean 0."""
    numbers = _numbers(values)
    if len(numbers) < 2:
        return None
    mean = statistics.fmean(numbers)
    return round(statistics.stdev(numbers) / mean, 4) if mean else None


def _ratio(value, reference):
    if value is None or not reference:
        return None
    return round(value / reference, 4)


def summarize(results) -> dict:
    """Per case x arm: medians, cost CV and success rate; per case: overhead vs "direct".

    Medians use every run with a parsed headless result (a failed run still
    cost money); success_rate counts all runs. overhead_vs_direct[arm] =
    median(arm) / median(direct) for cost, total tokens and host duration,
    present only when the case has an arm named "direct".
    """
    grouped: dict[str, dict[str, list[dict]]] = {}
    for result in results:
        grouped.setdefault(str(result["case"]), {}).setdefault(str(result["arm"]), []).append(result)
    cases = {}
    for case_id in sorted(grouped):
        arms_summary = {}
        for arm in sorted(grouped[case_id]):
            runs = grouped[case_id][arm]
            measured = [r["headless"] for r in runs if isinstance(r.get("headless"), dict)]
            successes = sum(1 for r in runs if r.get("success") is True)
            costs = [h.get("cost_usd") for h in measured]
            stats = {
                "runs": len(runs),
                "measured_runs": len(measured),
                "successes": successes,
                "success_rate": round(successes / len(runs), 4),
                "median_cost_usd": _median(costs),
                "cv_cost": _cv(costs),
            }
            for key in _TOKEN_KEYS:
                stats[f"median_{key}"] = _median(h.get(key) for h in measured)
            stats["median_turns"] = _median(h.get("turns") for h in measured)
            stats["median_duration_ms"] = _median(h.get("duration_ms") for h in measured)
            stats["median_wall_seconds"] = _median(r.get("wall_seconds") for r in runs)
            arms_summary[arm] = stats
        entry = {"arms": arms_summary}
        direct = arms_summary.get(DIRECT_ARM)
        if direct is not None:
            entry["overhead_vs_direct"] = {
                arm: {
                    "cost_usd": _ratio(stats["median_cost_usd"], direct["median_cost_usd"]),
                    "total_tokens": _ratio(stats["median_total_tokens"], direct["median_total_tokens"]),
                    "duration_ms": _ratio(stats["median_duration_ms"], direct["median_duration_ms"]),
                }
                for arm, stats in arms_summary.items() if arm != DIRECT_ARM
            }
        cases[case_id] = entry
    return {"reference_arm": DIRECT_ARM, "cases": cases}
