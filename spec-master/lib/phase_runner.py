"""Integration-agnostic phase execution.

Resolves paths, invokes the chosen adapter subprocess, runs quality gates
for the `validate` phase, and classifies findings into `execution_mode`
event-type strings (docs/spec-master/guarded-mode-spec.md §5, §7, §9;
research.md item 4; data-model.md "Producibility this increment").
"""
from __future__ import annotations

import datetime as dt
import fnmatch
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import phase_contracts  # noqa: E402
import quality_gates  # noqa: E402

SOURCE_LIKE_EXTENSIONS = frozenset((
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".php", ".sh", ".swift",
    ".kt", ".scala",
))

# Phases before `implement`; a source-looking forbidden write here is
# `early_implementation` (critical), not merely `wrong_path` (recoverable).
PRE_IMPLEMENT_PHASES = ("constitution", "specify", "clarify", "plan", "tasks", "analyze")


class UnsupportedIntegrationError(Exception):
    pass


def _looks_like_source(path: str) -> bool:
    return Path(path).suffix in SOURCE_LIKE_EXTENSIONS


def _symlink_escapes_project(project: Path, relative: str) -> bool:
    """A path inside the project tree whose *resolved* target escapes it.

    `phase_contracts.snapshot()` only ever walks inside `project`, so it can
    never itself see a write to an unrelated absolute path elsewhere on
    disk — the one way a project-relative path can still resolve outside
    the project root is a symlink. This is the literal, checkable meaning
    of FR-014 ("reject any modified path that resolves outside the project
    directory").
    """
    target = project / relative
    try:
        resolved = target.resolve()
        project_resolved = project.resolve()
    except OSError:
        return False
    try:
        resolved.relative_to(project_resolved)
        return False
    except ValueError:
        return True


def _run_quality_gates(project: Path) -> list[dict]:
    gates = quality_gates.detect(str(project))
    results = []
    for gate in gates:
        try:
            completed = subprocess.run(
                gate["command"], shell=True, cwd=project, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            result = "PASSED" if completed.returncode == 0 else "FAILED"
            exit_code = completed.returncode
        except OSError as exc:
            result = "FAILED"
            exit_code = None
            gate = {**gate, "error": str(exc)}
        results.append({**gate, "result": result, "exit_code": exit_code})

    report_path = project / ".spec-master" / "reports" / "quality-gates.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Quality Gates", ""]
    if not results:
        lines.append("No quality gates detected for this project.")
    for gate in results:
        lines.append(f"- **{gate['name']}** (`{gate['command']}`): {gate['result']} "
                      f"(exit {gate['exit_code']}, blocking={gate['blocking']})")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return results


def _run_opencode(project: Path, phase: str, prompt_text: str, model: str,
                   agent: str, timeout_seconds: int) -> dict:
    log_dir = project / ".spec-master" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    transcript_path = log_dir / f"{stamp}-{phase}.jsonl"
    command = [
        "opencode", "run", "--pure", "--format", "json",
        "--dir", str(project), "--agent", agent,
        "--model", model, "--command", f"speckit.{phase}",
        prompt_text,
    ]
    timed_out = False
    try:
        completed = subprocess.run(
            command, cwd=project, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout_seconds, check=False,
        )
        stdout = completed.stdout
        exit_code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        exit_code = None
    transcript_path.write_text(stdout or "", encoding="utf-8")
    return {
        "stdout": stdout or "",
        "exit_code": exit_code,
        "timed_out": timed_out,
        "transcript": str(transcript_path),
    }


INTEGRATIONS = {"opencode": _run_opencode}


def classify_events(phase: str, findings: dict) -> list[str]:
    """Turn phase_contracts-level findings into execution_mode event types."""
    events: list[str] = []

    for path in findings["symlink_escapes"]:
        events.append("out_of_project_write")

    for path in findings["forbidden_writes"]:
        if path in findings["symlink_escapes"]:
            continue  # already classified as the stronger out_of_project_write
        if path in findings["artifact_wrong_location"]:
            continue  # already classified as the more specific artifact_wrong_location
        if phase in PRE_IMPLEMENT_PHASES and _looks_like_source(path):
            events.append("early_implementation")
        else:
            events.append("wrong_path")

    if findings["fake_tool_markers"]:
        events.append("simulated_tool_call")

    if findings["exit_code"] == 0 and findings["missing_artifacts"] and not findings["forbidden_writes"]:
        events.append("false_phase_completion")

    if findings["placeholder_artifacts"]:
        events.append("placeholder_not_removed")

    if findings["artifact_wrong_location"]:
        events.append("artifact_wrong_location")

    if (
        findings["exit_code"] not in (0, None)
        and not findings["timed_out"]
        and not findings["fake_tool_markers"]
        and not findings["forbidden_writes"]
    ):
        events.append("recoverable_tool_error")

    if findings["timed_out"]:
        events.append("timeout")

    return events


def _artifact_wrong_location(project: Path, phase: str, changed: list[str]) -> list[str]:
    """A required artifact's basename appears at an unexpected path."""
    if not phase_contracts.validate_artifacts(project, phase):
        return []  # required artifacts are all present at their canonical location
    expected_basenames = {
        Path(pattern).name for pattern in phase_contracts.PHASE_ARTIFACTS[phase]
    }
    misplaced = [
        path for path in changed
        if Path(path).name in expected_basenames
        and not any(fnmatch.fnmatch(path, pattern) for pattern in phase_contracts.PHASE_ARTIFACTS[phase])
    ]
    return sorted(misplaced)


def run_phase(project, phase: str, integration: str, model: str, prompt_text: str,
              timeout_seconds: int, agent: str = "spec-phase") -> dict:
    if integration not in INTEGRATIONS:
        raise UnsupportedIntegrationError(
            f"integration {integration!r} is not supported in guarded mode yet "
            f"(only {sorted(INTEGRATIONS)} implemented this increment)"
        )
    project = Path(project).resolve()
    adapter = INTEGRATIONS[integration]

    quality_gate_results = None
    if phase == "validate":
        quality_gate_results = _run_quality_gates(project)

    before = phase_contracts.snapshot(project)
    invocation = adapter(project, phase, prompt_text, model, agent, timeout_seconds)
    after = phase_contracts.snapshot(project)
    changed = phase_contracts.changed_paths(before, after)

    findings = {
        "exit_code": invocation["exit_code"],
        "timed_out": invocation["timed_out"],
        "changed_paths": changed,
        "symlink_escapes": [p for p in changed if _symlink_escapes_project(project, p)],
        "fake_tool_markers": phase_contracts.validate_transcript(invocation["stdout"]),
        "missing_artifacts": phase_contracts.validate_artifacts(project, phase),
        "placeholder_artifacts": phase_contracts.placeholder_artifacts(project, phase),
        "forbidden_writes": phase_contracts.forbidden_writes(changed, phase),
        "artifact_wrong_location": _artifact_wrong_location(project, phase, changed),
    }
    required_changed = any(
        any(fnmatch.fnmatch(path, pattern) for path in changed)
        for pattern in phase_contracts.PHASE_ARTIFACTS[phase]
    )
    blocking_gate_failed = bool(quality_gate_results) and any(
        g["blocking"] and g["result"] == "FAILED" for g in quality_gate_results
    )

    events = classify_events(phase, findings)

    passed = (
        not findings["timed_out"]
        and findings["exit_code"] == 0
        and not findings["fake_tool_markers"]
        and not findings["missing_artifacts"]
        and not findings["placeholder_artifacts"]
        and not findings["forbidden_writes"]
        and not findings["artifact_wrong_location"]
        and required_changed
        and not blocking_gate_failed
    )

    if passed:
        reason = None
    elif findings["timed_out"]:
        reason = "timeout"
    elif blocking_gate_failed:
        reason = "blocking_quality_gate_failed"
    elif findings["fake_tool_markers"]:
        reason = "fake_tool_marker"
    elif findings["forbidden_writes"] or findings["artifact_wrong_location"]:
        reason = "forbidden_write"
    elif findings["placeholder_artifacts"]:
        reason = "placeholder_artifact"
    elif findings["exit_code"] != 0:
        reason = "exit_nonzero"
    else:
        reason = "missing_artifact"

    return {
        "status": "PASSED" if passed else "FAILED",
        "phase": phase,
        "reason": reason,
        "events": events,
        "exit_code": findings["exit_code"],
        "changed_paths": changed,
        "forbidden_writes": findings["forbidden_writes"],
        "missing_artifacts": findings["missing_artifacts"],
        "placeholder_artifacts": findings["placeholder_artifacts"],
        "fake_tool_markers": findings["fake_tool_markers"],
        "quality_gates": quality_gate_results,
        "transcript": invocation["transcript"],
    }
