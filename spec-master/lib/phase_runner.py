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
import phase_result  # noqa: E402
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
        if gate.get("execution") == "ci" or not gate.get("command"):
            # CI-only scanner (e.g. CodeQL): nothing to run locally; the
            # orchestrator confirms the CI check before declaring SUCCESS.
            results.append({**gate, "result": "DEFERRED_TO_CI", "exit_code": None})
            continue
        # A declared gate may set a repository-relative `cwd` (quality_gates
        # rejects one that leaves the project) and a `timeout_seconds`.
        cwd = project / gate["cwd"] if gate.get("cwd") else project
        try:
            completed = subprocess.run(
                gate["command"], shell=True, cwd=cwd, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
                timeout=gate.get("timeout_seconds"),
            )
            result = "PASSED" if completed.returncode == 0 else "FAILED"
            exit_code = completed.returncode
        except subprocess.TimeoutExpired:
            result = "FAILED"
            exit_code = None
            gate = {**gate, "timed_out": True, "error": f"timed out after {gate['timeout_seconds']}s"}
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
        where = f"`{gate['command']}`" if gate.get("command") else \
            "CI: " + ", ".join(gate.get("evidence") or [])
        lines.append(f"- **{gate['name']}** ({where}): {gate['result']} "
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


def _artifact_wrong_location(project: Path, phase: str, changed: list[str],
                             feature_dir: str | None = None) -> list[str]:
    """A required artifact's basename appears at an unexpected path."""
    if not phase_contracts.validate_artifacts(project, phase, feature_dir):
        return []  # required artifacts are all present at their canonical location
    patterns = phase_contracts.phase_artifacts(phase, feature_dir)
    expected_basenames = {Path(pattern).name for pattern in patterns}
    misplaced = [
        path for path in changed
        if Path(path).name in expected_basenames
        and not any(fnmatch.fnmatch(path, pattern) for pattern in patterns)
    ]
    return sorted(misplaced)


def _reason_for_hard_fail(findings: dict, blocking_gate_failed: bool) -> str:
    if findings["timed_out"]:
        return "timeout"
    if blocking_gate_failed:
        return "blocking_quality_gate_failed"
    if findings["fake_tool_markers"]:
        return "fake_tool_marker"
    if findings["forbidden_writes"] or findings["artifact_wrong_location"]:
        return "forbidden_write"
    return "exit_nonzero"


def _evaluate_inspect_noop(project: Path, phase: str, structured_result: dict | None,
                            outcome: str | None,
                            feature_dir: str | None = None) -> tuple[str, str, str | None, list[str]]:
    """`inspect-or-update` no-op decision (clarify/analyze) — specs/002-
    guarded-noop-phase-validation/spec.md §5, §8. Relies only on the
    active-feature-scoped predicate, never the generic glob-based
    `missing_artifacts`/`placeholder_artifacts` findings, since those can
    be satisfied or tripped by an unrelated feature directory in a
    multi-feature project (research.md item 4's active-feature scoping
    applies here specifically to avoid that false signal).
    """
    if outcome != "no_changes_required":
        reason = "phase_result_missing" if structured_result is None else "phase_result_invalid"
        return "FAILED", reason, outcome, []

    predicate = phase_contracts.clarify_result_ok if phase == "clarify" else phase_contracts.analyze_result_ok
    names = ("spec.md",) if phase == "clarify" else ("spec.md", "plan.md", "tasks.md")
    try:
        ok = predicate(project, structured_result, feature_dir)
        resolved_dir = phase_contracts.feature_dir_path(project, feature_dir)
        active_artifacts = [str((resolved_dir / name).relative_to(project)) for name in names]
    except phase_contracts.ActiveFeatureUnresolved:
        return "FAILED", "active_feature_unresolved", outcome, []

    if ok:
        return "PASSED", "valid_noop", "no_changes_required", active_artifacts
    return "FAILED", "phase_result_invalid", outcome, active_artifacts


def _evaluate_producer_retry(findings: dict, history: list) -> tuple[str, str, str | None]:
    """`produce-or-update` retry-trust decision — spec.md §9, research.md item 2.

    Never eligible on a phase's very first attempt (`history` empty); a
    single historical forbidden write or out-of-project write anywhere in
    `history` permanently disqualifies trusting the existing artifact.
    """
    trustworthy = bool(history) and not any(
        record.get("forbidden_writes") or "out_of_project_write" in (record.get("events") or [])
        for record in history
    )
    if trustworthy and not findings["missing_artifacts"] and not findings["placeholder_artifacts"]:
        return "PASSED", "valid_noop", "no_changes_required"
    if findings["missing_artifacts"]:
        return "FAILED", "missing_artifact", None
    if findings["placeholder_artifacts"]:
        return "FAILED", "placeholder_artifact", None
    return "FAILED", "unchanged_artifact", None


def revalidate_from_transcript(project, phase: str, transcript_text: str, history: list,
                               feature_dir: str | None = None) -> dict | None:
    """Re-evaluate a previously-blocked attempt under the *current* contract
    without spawning a new subprocess (controller.py's contract-revalidation,
    specs/002-guarded-noop-phase-validation/spec.md §11, research.md item 6).

    For `inspect-or-update` phases, re-parses `transcript_text` (the old
    attempt's preserved transcript) for a structured result and evaluates it
    against the filesystem *as it stands now*. For `produce-or-update`
    phases, no transcript is needed at all — the same retry-trust check
    `run_phase` itself uses is re-run against `history` (every attempt
    *before* the one being revalidated) and the current filesystem state.
    Returns `None` (not a dict) when revalidation doesn't apply or doesn't
    pass — the caller then falls back to a genuine live attempt.
    """
    project = Path(project).resolve()
    policy = phase_contracts.PHASE_POLICY[phase]

    if policy == "inspect-or-update":
        structured_result = phase_result.parse_last_phase_result(transcript_text)
        outcome = structured_result.get("phase_result") if structured_result else None
        status, _reason, outcome, active_artifacts = _evaluate_inspect_noop(
            project, phase, structured_result, outcome, feature_dir
        )
        if status != "PASSED":
            return None
        return {
            "outcome": outcome,
            "policy": policy,
            "active_artifacts": active_artifacts,
            "structured_result": structured_result,
        }

    if policy == "produce-or-update":
        findings = {
            "missing_artifacts": phase_contracts.validate_artifacts(project, phase, feature_dir),
            "placeholder_artifacts": phase_contracts.placeholder_artifacts(project, phase, feature_dir),
        }
        status, _reason, outcome = _evaluate_producer_retry(findings, list(history))
        if status != "PASSED":
            return None
        return {"outcome": outcome, "policy": policy, "active_artifacts": [], "structured_result": None}

    return None  # "execute" (implement) has no revalidation-without-a-new-attempt path


def run_phase(project, phase: str, integration: str, model: str, prompt_text: str,
              timeout_seconds: int, agent: str = "spec-phase", history: list = (),
              feature_dir: str | None = None) -> dict:
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
        "missing_artifacts": phase_contracts.validate_artifacts(project, phase, feature_dir),
        "placeholder_artifacts": phase_contracts.placeholder_artifacts(project, phase, feature_dir),
        "forbidden_writes": phase_contracts.forbidden_writes(changed, phase, feature_dir),
        "artifact_wrong_location": _artifact_wrong_location(project, phase, changed, feature_dir),
    }
    required_changed = any(
        any(fnmatch.fnmatch(path, pattern) for path in changed)
        for pattern in phase_contracts.phase_artifacts(phase, feature_dir)
    )
    blocking_gate_failed = bool(quality_gate_results) and any(
        g["blocking"] and g["result"] == "FAILED" for g in quality_gate_results
    )

    events = classify_events(phase, findings)

    # Decision priority order fixed in specs/002-guarded-noop-phase-validation/
    # research.md item 7 (analyze finding C1): hard-fail checks always win;
    # `user_decision_required` wins next, even over an incidental file change;
    # only then does the ordinary "did it change what it should" path run,
    # followed by the two no-op paths policy adds.
    structured_result = phase_result.parse_last_phase_result(invocation["stdout"])
    outcome = structured_result.get("phase_result") if structured_result else None
    active_artifacts: list[str] = []
    policy = phase_contracts.PHASE_POLICY[phase]

    hard_fail = (
        findings["timed_out"] or findings["exit_code"] != 0 or findings["fake_tool_markers"]
        or findings["forbidden_writes"] or findings["artifact_wrong_location"] or blocking_gate_failed
    )

    if hard_fail:
        status, reason = "FAILED", _reason_for_hard_fail(findings, blocking_gate_failed)
    elif outcome == "user_decision_required":
        status, reason = "FAILED", "user_decision_required"
    elif required_changed:
        if findings["missing_artifacts"]:
            status, reason = "FAILED", "missing_artifact"
        elif findings["placeholder_artifacts"]:
            status, reason = "FAILED", "placeholder_artifact"
        else:
            status, reason = "PASSED", None
            outcome = outcome or "artifact_updated"
    elif policy == "inspect-or-update":
        status, reason, outcome, active_artifacts = _evaluate_inspect_noop(
            project, phase, structured_result, outcome, feature_dir
        )
    elif policy == "produce-or-update":
        status, reason, noop_outcome = _evaluate_producer_retry(findings, list(history))
        if noop_outcome:
            outcome = noop_outcome
    else:  # policy == "execute" (implement), no change this attempt
        if findings["missing_artifacts"]:
            status, reason = "FAILED", "missing_artifact"
        elif findings["placeholder_artifacts"]:
            status, reason = "FAILED", "placeholder_artifact"
        else:
            status, reason = "FAILED", "missing_artifact"

    return {
        "status": status,
        "phase": phase,
        "reason": reason,
        "outcome": outcome,
        "policy": policy,
        "contract_version": phase_contracts.PHASE_CONTRACT_VERSION,
        "active_artifacts": active_artifacts,
        "structured_result": structured_result,
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
