"""`doctor`: the harness's self-checks, run in CI instead of in every workflow.

Each check is deterministic and cheap. `error` checks fail the command
(exit 1); `warn` and `info` are reported only.

- protocol_conformance: every CLI invocation the agent-facing docs show
  exists in the parser (group, action and flags).
- kernel_budget / hook_path_budget / step_path_budget: lines of code in the
  kernel and in what the hooks and the step API import — the guard against
  the harness itself growing into the overengineering it removes.
- cards: the router card stays under 5 KB and every other card under 3 KB.
- speckit_version: the installed Spec Kit is inside the supported range.
- evidence / metrics / policy / gates / hooks: the project's own records.
"""
from __future__ import annotations

import argparse
import json
import modulefinder
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

LIB = Path(__file__).resolve().parents[1]
ENGINE = LIB.parent
KERNEL = LIB / "kernel"

KERNEL_LOC_BUDGET = 2500
HOOK_PATH_LOC_BUDGET = 1500
HOOK_P50_MS = 100  # the proposal's p95 target is 50 ms; CI machines get headroom
STEP_PATH_LOC_TARGET = 4500
ROUTER_CARD_BYTES = 5 * 1024
CARD_BYTES = 3 * 1024
SPEC_KIT_RANGE = ((0, 16, 4), (1, 1, 0))  # >=0.16.4,<1.1

GLOBAL_FLAGS = {"--pretty", "--help", "-h"}
_CODE_RE = re.compile(r"```[^\n]*\n(.*?)```|`([^`]+)`", re.DOTALL)
_FLAG_RE = re.compile(r"(?<![\w-])(--[a-z][a-z0-9-]*)")
_WORD_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def _check(name: str, ok: bool, level: str, detail: str, **extra) -> dict:
    return {"name": name, "ok": ok, "level": level, "detail": detail, **extra}


# --------------------------------------------------------------------------- conformance

def agent_facing_docs(repo: Path) -> list[Path]:
    engine = repo / "spec-master"
    docs = [engine / "PROTOCOL.md", *sorted((engine / "docs").glob("*.md")),
            *sorted((engine / "adapters").glob("*.md")), *sorted((engine / "templates").rglob("*.md")),
            *sorted((engine / "cards").rglob("*.md")), *sorted((engine / "knowledge" / "playbooks").glob("*.md")),
            *sorted((engine / "skills").rglob("*.md")),
            repo / ".claude" / "commands" / "spec-master.md", repo / ".claude" / "skills" / "spec-master" / "SKILL.md",
            repo / ".github" / "skills" / "spec-master" / "SKILL.md",
            repo / ".agents" / "skills" / "spec-master" / "SKILL.md",
            repo / ".agents" / "agents" / "spec-master" / "agent.md", repo / ".qwen" / "commands" / "spec-master.md",
            repo / "README.md", repo / "docs" / "spec-master" / "README.md"]
    return [path for path in docs if path.is_file()]


def parser_catalog(parser: argparse.ArgumentParser) -> dict:
    groups = {}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for group, group_parser in action.choices.items():
                actions = {}
                for sub in group_parser._actions:
                    if isinstance(sub, argparse._SubParsersAction):
                        for name, action_parser in sub.choices.items():
                            actions[name] = {opt for a in action_parser._actions for opt in a.option_strings}
                groups[group] = actions
    return groups


def code_fragments(text: str):
    for match in _CODE_RE.finditer(text):
        block = (match.group(1) if match.group(1) is not None else match.group(2)).replace("\\\n", " ")
        if match.group(1) is not None:
            yield from block.splitlines()
        else:
            yield " ".join(block.split())  # a code span may wrap across lines


def invocations(fragment: str, catalog: dict):
    """(group, action_or_None, flags): a group right after `cli.py` is always an
    invocation (an unknown one is reported); so is a span starting with one."""
    tokens = fragment.replace("cli.py", " cli.py ").split()
    command_line = bool(tokens) and (tokens[0] in ("python", "python3") or tokens[0].endswith("cli.py"))
    for index, token in enumerate(tokens):
        prefixed = index > 0 and tokens[index - 1].endswith("cli.py")
        if prefixed and token not in catalog:
            if command_line and _WORD_RE.match(token):
                yield token, None, []
            continue
        if token not in catalog or not (prefixed or index == 0):
            continue
        action = tokens[index + 1] if index + 1 < len(tokens) else None
        rest = " ".join(tokens[index + 2:]).split("cli.py")[0]
        yield token, action, _FLAG_RE.findall(rest)


def conformance(repo: Path, parser: argparse.ArgumentParser) -> tuple[int, list[str]]:
    catalog = parser_catalog(parser)
    problems, checked = [], 0
    for path in agent_facing_docs(repo):
        for fragment in code_fragments(path.read_text(encoding="utf-8")):
            for group, action, flags in invocations(fragment, catalog):
                where = f"{path.relative_to(repo)}: `{fragment.strip()[:90]}`"
                if group not in catalog:
                    problems.append(f"{where} — unknown command group `{group}`")
                    continue
                if action is None or action.startswith(("-", "<", "[")) or action == "...":
                    continue
                names = action.replace("\\", "").strip("`").split("|")
                if not all(_WORD_RE.match(name) for name in names):
                    continue  # prose that starts with a group name
                for name in names:
                    checked += 1
                    if name not in catalog[group]:
                        problems.append(f"{where} — unknown action `{group} {name}`")
                        continue
                    known = catalog[group][name] | GLOBAL_FLAGS
                    problems.extend(f"{where} — `{group} {name}` has no flag `{flag}`"
                                    for flag in flags if flag not in known)
    return checked, problems


# --------------------------------------------------------------------------- budgets

def loc(path: Path) -> int:
    count = 0
    in_doc = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(('"""', "'''")):
            quotes = stripped[:3]
            if not (in_doc is False and stripped.count(quotes) >= 2 and len(stripped) > 3):
                in_doc = not in_doc
            continue
        if in_doc or not stripped or stripped.startswith("#"):
            continue
        count += 1
    return count


def import_closure(script: Path) -> list[Path]:
    """Engine modules a script can import (static, lazy imports included)."""
    finder = modulefinder.ModuleFinder(path=[str(LIB)] + list(sys.path))
    finder.run_script(str(script))
    found = {Path(module.__file__).resolve() for module in finder.modules.values()
             if getattr(module, "__file__", None)}
    return sorted(p for p in found if LIB in p.parents)


def hook_runtime(runs: int = 5) -> dict:
    """What a PreToolUse call really costs: engine modules imported at runtime
    (python -X importtime) and wall time, on a throwaway project."""
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git status"}})
    modules: set[str] = set()
    timings = []
    with tempfile.TemporaryDirectory() as project:
        env = {**os.environ, "CLAUDE_PROJECT_DIR": project}
        for index in range(runs):
            args = [sys.executable] + (["-X", "importtime"] if index == 0 else []) + \
                   [str(KERNEL / "hookd.py"), "pre-tool-use"]
            started = time.perf_counter()
            proc = subprocess.run(args, input=payload, capture_output=True, text=True, env=env, timeout=30)
            timings.append((time.perf_counter() - started) * 1000)
            if index == 0:
                for line in proc.stderr.splitlines():
                    if line.startswith("import time:") and line.count("|") == 2:
                        modules.add(line.rsplit("|", 1)[1].strip())
    files = [KERNEL / "hookd.py"]  # the script itself runs as __main__ and is not an import
    for name in sorted(modules):
        candidate = LIB.joinpath(*name.split("."))
        for path in (candidate.with_suffix(".py"), candidate / "__init__.py"):
            if path.is_file():
                if path not in files:
                    files.append(path)
                break
    timings = sorted(timings[1:])  # the first run pays -X importtime's own overhead
    return {"files": files, "p50_ms": round(timings[len(timings) // 2], 1), "max_ms": round(timings[-1], 1)}


def budgets() -> list[dict]:
    kernel_loc = sum(loc(p) for p in KERNEL.glob("*.py"))
    runtime = hook_runtime()
    hook_loc = sum(loc(p) for p in runtime["files"])
    step_modules = import_closure(KERNEL / "step.py")
    step_loc = sum(loc(p) for p in step_modules)
    return [
        _check("kernel_budget", kernel_loc <= KERNEL_LOC_BUDGET, "error",
               f"kernel/ has {kernel_loc} LOC (budget {KERNEL_LOC_BUDGET})", loc=kernel_loc),
        _check("hook_path_budget", hook_loc <= HOOK_PATH_LOC_BUDGET and runtime["p50_ms"] <= HOOK_P50_MS, "error",
               f"a PreToolUse call imports {len(runtime['files'])} engine modules ({hook_loc} LOC, budget "
               f"{HOOK_PATH_LOC_BUDGET}) and takes {runtime['p50_ms']} ms p50 / {runtime['max_ms']} ms max "
               f"(budget {HOOK_P50_MS} ms p50)",
               loc=hook_loc, p50_ms=runtime["p50_ms"], modules=[p.relative_to(LIB).as_posix() for p in runtime["files"]]),
        _check("step_path_budget", step_loc <= STEP_PATH_LOC_TARGET, "warn",
               f"the step API can import {len(step_modules)} engine modules, {step_loc} LOC "
               f"(target {STEP_PATH_LOC_TARGET} by wave 3)", loc=step_loc),
    ]


def cards() -> dict:
    oversized = []
    for card in sorted((ENGINE / "cards").glob("*.md")):
        limit = ROUTER_CARD_BYTES if card.name == "router.md" else CARD_BYTES
        size = card.stat().st_size
        if size > limit:
            oversized.append(f"{card.name}: {size} B > {limit} B")
    return _check("cards", not oversized, "error",
                  "every card within its size budget" if not oversized else "; ".join(oversized))


# --------------------------------------------------------------------------- project records

def _version_tuple(text: str):
    match = re.match(r"v?(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(part) for part in match.groups()) if match else None


def speckit_version(root: Path) -> dict:
    path = root / ".specify" / "integration.json"
    if not path.is_file():
        return _check("speckit_version", True, "info", "no .specify/integration.json (Spec Kit not installed here)")
    try:
        version = json.loads(path.read_text(encoding="utf-8")).get("version")
    except ValueError:
        return _check("speckit_version", False, "warn", ".specify/integration.json is not valid JSON")
    parsed = _version_tuple(str(version))
    low, high = SPEC_KIT_RANGE
    ok = parsed is not None and low <= parsed < high
    return _check("speckit_version", ok, "warn",
                  f"Spec Kit {version} {'inside' if ok else 'outside'} the supported range >=0.16.4,<1.1")


def evidence_check(root: Path) -> dict:
    import evidence
    state_path = root / ".spec-master" / "state.json"
    if not state_path.is_file():
        return _check("evidence", True, "info", "no state.json")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    missing = {}
    for feature in state.get("features") or []:
        gaps = [phase for phase, status in evidence.summary(feature).items() if status != "verified"]
        if gaps:
            missing[feature.get("id")] = gaps
    return _check("evidence", not missing, "warn",
                  "every PASSED phase has verified evidence" if not missing
                  else f"{len(missing)} feature(s) with PASSED phases lacking verified evidence", features=missing)


def metrics_check(root: Path) -> dict:
    import metrics_export
    path = root / ".spec-master" / "metrics" / "rounds.json"
    if not path.is_file():
        return _check("metrics", True, "info", "no rounds.json")
    report = metrics_export.validate_rounds(metrics_export.load_rounds(str(path)))
    return _check("metrics", report["valid"], "error",
                  f"{len(report['errors'])} error(s), {len(report['warnings'])} warning(s) in rounds.json",
                  errors=report["errors"][:10])


def policy_check(root: Path) -> dict:
    from kernel import lanes
    try:
        data = lanes.load_policy(str(root))
    except (ValueError, OSError) as exc:
        return _check("policy", False, "error", f".spec-master/policy.json: {exc}")
    return _check("policy", True, "info", f"hooks_mode={data.get('hooks_mode', 'audit')}, "
                                          f"min_lane={data.get('min_lane', 'patch')}")


def gates_check(root: Path) -> dict:
    from kernel import lanes
    ok = lanes.has_test_gate(str(root))
    return _check("gates", ok, "warn", "a test gate is detected or declared" if ok
                  else "no executable test gate — `step end` cannot verify anything here")


def hooks_check(root: Path) -> dict:
    settings = root / ".claude" / "settings.json"
    wired = False
    if settings.is_file():
        try:
            wired = "hookd.py" in settings.read_text(encoding="utf-8")
        except OSError:
            wired = False
    return _check("hooks", True, "info", "hookd wired in .claude/settings.json" if wired
                  else "hooks not wired in .claude/settings.json (install the plugin or `harness install-hooks`)")


def run(root: str, parser: argparse.ArgumentParser, *, repo: str | None = None) -> dict:
    root_path = Path(root).resolve()
    repo_path = Path(repo).resolve() if repo else ENGINE.parent
    checked, problems = conformance(repo_path, parser)
    checks = [_check("protocol_conformance", not problems, "error",
                     f"{checked} documented invocation(s) checked" if not problems
                     else f"{len(problems)} invocation(s) do not exist in the CLI", problems=problems[:20])]
    checks += budgets()
    checks.append(cards())
    for probe in (speckit_version, evidence_check, metrics_check, policy_check, gates_check, hooks_check):
        try:
            checks.append(probe(root_path))
        except Exception as exc:  # noqa: BLE001 - one broken record must not hide the others
            checks.append(_check(probe.__name__, False, "error", f"{type(exc).__name__}: {exc}"))
    errors = [c["name"] for c in checks if not c["ok"] and c["level"] == "error"]
    warnings = [c["name"] for c in checks if not c["ok"] and c["level"] == "warn"]
    return {"ok": not errors, "errors": errors, "warnings": warnings, "checks": checks}
