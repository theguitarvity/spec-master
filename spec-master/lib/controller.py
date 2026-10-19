#!/usr/bin/env python3
"""Deterministic guarded-mode controller CLI.

Drives phase_runner.py through the Spec Kit phase sequence one isolated
attempt at a time, validating artifacts before promoting any phase
(docs/spec-master/guarded-mode-spec.md; specs/001-guarded-mode-controller/).

    python3 controller.py run --project . --context context.md --mode guarded --integration opencode --model <id>
    python3 controller.py resume --project .
    python3 controller.py status --project .

`--mode native` is accepted (never rejected as an unknown flag value —
GM-001) but the controller refuses to drive it: native mode means the
agent runs PROTOCOL.md directly, with no controller involved at all
(see specs/001-guarded-mode-controller/research.md item 2).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import execution_mode  # noqa: E402
import fingerprint  # noqa: E402
import hooks  # noqa: E402
import phase_contracts  # noqa: E402
import phase_runner  # noqa: E402
import risk_profile  # noqa: E402
import state as state_mod  # noqa: E402

PHASES = ("constitution", "specify", "clarify", "plan", "tasks", "analyze", "implement", "validate")

DEFAULT_MAX_ATTEMPTS = 2
DEFAULT_PHASE_TIMEOUT = 600

LOCK_RELATIVE_PATH = ".spec-master/run.lock"
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _print_json(payload) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False))


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime(TIMESTAMP_FORMAT)


def _state_path(project: Path) -> Path:
    return project / ".spec-master" / "state.json"


def _lock_path(project: Path) -> Path:
    return project / LOCK_RELATIVE_PATH


def _emit(project: Path, event_type: str, payload: dict) -> None:
    """Hook events are advisory: a broken hooks.json never stops a run."""
    hooks.safe_emit(project, event_type, payload)


def _emit_gate_results(project: Path, feature_id: str | None, gates) -> None:
    for gate in gates or []:
        if isinstance(gate, dict) and gate.get("result"):
            _emit(project, "gate.result", {
                "gate": gate.get("name"), "category": gate.get("category"), "tool": gate.get("tool"),
                "result": gate.get("result"), "blocking": bool(gate.get("blocking")), "feature": feature_id,
            })


class ControllerError(Exception):
    pass


def _load_or_init_state(project: Path, context: str, mode: str, integration: str,
                         model: str, max_attempts: int, phase_timeout: int) -> dict:
    path = _state_path(project)
    if path.exists():
        state = state_mod.load(str(path))
    else:
        state = state_mod.default_state(context)
        state_mod.save(str(path), state)
    if "execution" not in state:
        execution_mode.init_execution(state, mode, integration, model)
        state["execution"]["max_attempts_per_phase"] = max_attempts
        state["execution"]["phase_timeout_seconds"] = phase_timeout
        state_mod.save(str(path), state)
    state.setdefault("attempts", {})
    return state


def _check_and_clear_lock(project: Path, phase_timeout: int) -> None:
    lock = _lock_path(project)
    if not lock.exists():
        return
    try:
        info = json.loads(lock.read_text(encoding="utf-8"))
        started_at = dt.datetime.strptime(info["started_at"], TIMESTAMP_FORMAT).replace(tzinfo=dt.timezone.utc)
    except (OSError, ValueError, KeyError):
        lock.unlink(missing_ok=True)
        return
    age = (dt.datetime.now(dt.timezone.utc) - started_at).total_seconds()
    if age > phase_timeout:
        lock.unlink(missing_ok=True)
        print(f"[Spec Master] stale run.lock removed (age {int(age)}s > timeout {phase_timeout}s).")
        return
    raise ControllerError("run already in progress (lock held)")


def _acquire_lock(project: Path, phase: str) -> None:
    lock = _lock_path(project)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(
        json.dumps({"phase": phase, "pid": os.getpid(), "started_at": _now_iso()}),
        encoding="utf-8",
    )


def _release_lock(project: Path) -> None:
    _lock_path(project).unlink(missing_ok=True)


def _preserve_failed_attempt(project: Path, phase: str, last_attempt: dict,
                             feature_id: str | None = None) -> None:
    dest_dir = project / ".spec-master" / "failed-attempts"
    dest_dir = (dest_dir / feature_id / phase) if feature_id and phase in state_mod.FEATURE_PHASES else dest_dir / phase
    dest_dir.mkdir(parents=True, exist_ok=True)
    transcript = Path(last_attempt["transcript"])
    if transcript.exists():
        shutil.copy2(transcript, dest_dir / transcript.name)


def _feature_dir_hint(phase: str, feature_dir: str | None) -> str:
    """For `specify`, tell Spec Kit which directory the harness allocated
    (create-new-feature.sh takes `--number` and `--short-name`)."""
    if phase != "specify" or not feature_dir:
        return ""
    name = Path(feature_dir).name
    number, _, short_name = name.partition("-")
    if not number.isdigit() or not short_name:
        return f" Create the feature in {feature_dir}."
    return (f" Create the feature in {feature_dir} (create-new-feature: "
            f"--number {int(number)} --short-name {short_name}).")


def _render_prompt(phase: str, attempt_number: int, last_attempt: dict | None,
                    allowed_writes: tuple, expected_artifacts: tuple, feature_dir: str | None = None) -> str:
    if attempt_number == 1 or last_attempt is None:
        return (
            f"Execute /speckit.{phase} for this project. Follow the installed Spec Kit "
            f"command for this phase exactly; never print a tool call as plain text; "
            f"you may only write to: {', '.join(allowed_writes)}."
            + _feature_dir_hint(phase, feature_dir)
        )
    # FR-013: a retry gets only the objective failure cause, the allowlist,
    # and the expected artifacts — never the previous attempt's transcript.
    return (
        f"Your previous attempt at /speckit.{phase} failed: {last_attempt.get('reason')}. "
        f"You may only write to: {', '.join(allowed_writes)}. "
        f"Required artifact(s): {', '.join(expected_artifacts)}. "
        f"Fix this and retry — do not repeat the same mistake."
    )


def _context_hash(project: Path, context: str) -> str | None:
    context_path = project / context
    if not context_path.is_file():
        context_path = Path(context)
    if not context_path.is_file():
        return None
    return fingerprint.compute_file_hash(str(context_path))


def _consumed_attempts(attempts: list[dict]) -> int:
    # A user_decision_required record is preserved for audit (FR-011) but
    # never counts against the attempt budget (spec.md §10/§16 item 2).
    return len([a for a in attempts if a.get("reason") != "user_decision_required"])


def _attempt_key(feature_id: str | None, phase: str) -> str:
    """Attempts are recorded per feature and phase, so a second feature never
    inherits the first one's attempts (or its PASSED). The constitution and
    standalone runs (no feature) keep the historical per-phase key."""
    if feature_id and phase in state_mod.FEATURE_PHASES:
        return f"{feature_id}/{phase}"
    return phase


def _attempts_for(state: dict, feature_id: str | None, phase: str) -> list[dict]:
    attempts = state.setdefault("attempts", {})
    key = _attempt_key(feature_id, phase)
    if key not in attempts and key != phase and phase in attempts:
        # A state written before attempts were keyed per feature: adopt the
        # per-phase history only when this is the state's single feature, so
        # it can only have come from this feature's own runs.
        feature_ids = [f.get("id") for f in state.get("features", [])]
        if feature_ids == [feature_id]:
            attempts[key] = list(attempts[phase])
    return attempts.setdefault(key, [])


def _feature_dir(state: dict, feature_id: str | None) -> str | None:
    """The feature's recorded spec directory, which scopes the phase contract
    (only when the orchestrator recorded one; otherwise the historical
    project-wide contract applies)."""
    if not feature_id:
        return None
    try:
        feature = state_mod.find_feature(state, feature_id)
    except state_mod.StateError:
        return None
    spec_dir = feature.get("spec_directory")
    return spec_dir if isinstance(spec_dir, str) and spec_dir.strip() else None


def _record_discovered_feature_dir(state: dict, project: Path, feature_id: str | None) -> None:
    """After `specify`, remember the directory Spec Kit created when the
    feature had none recorded, so later phases are scoped to it."""
    if not feature_id or _feature_dir(state, feature_id):
        return
    try:
        resolved = phase_contracts.resolve_active_feature_dir(project)
        feature = state_mod.find_feature(state, feature_id)
    except (phase_contracts.ActiveFeatureUnresolved, state_mod.StateError):
        return
    if resolved.is_dir():
        feature["spec_directory"] = resolved.relative_to(project.resolve()).as_posix()


def _phase_status(state: dict, phase: str, feature_id: str | None = None) -> str:
    attempts = state.get("attempts", {}).get(_attempt_key(feature_id, phase), [])
    if not attempts:
        return "PENDING"
    if attempts[-1]["status"] == "PASSED":
        return "PASSED"
    if attempts[-1].get("reason") == "user_decision_required":
        return "PAUSED"
    max_attempts = state.get("execution", {}).get("max_attempts_per_phase", DEFAULT_MAX_ATTEMPTS)
    if _consumed_attempts(attempts) >= max_attempts:
        return "BLOCKED"
    return "FAILED"


def _promote_feature_phase(state: dict, feature_id: str | None, phase: str) -> None:
    if not feature_id or phase not in state_mod.FEATURE_PHASES:
        return
    try:
        state_mod.transition_phase(state, feature_id, phase, "PASSED")
    except state_mod.StateError:
        pass  # no matching feature/phase in the per-feature loop — standalone run


def _skip_by_risk_profile(state: dict, feature_id: str | None, phase: str) -> bool:
    """Roadmap item 15: honor a recorded `SKIPPED` for a skippable phase, or record
    one when the feature's saved risk tier (`risk classify --save`) makes the
    phase skippable. Only `state_mod.SKIPPABLE_PHASES` (clarify) is ever skipped;
    any doubt (no feature, no tier, refused transition) means "run the phase".
    """
    if not feature_id or phase not in state_mod.SKIPPABLE_PHASES:
        return False
    try:
        feature = state_mod.find_feature(state, feature_id)
    except state_mod.StateError:
        return False
    if feature["phases"].get(phase) == "SKIPPED":
        return True
    risk = feature.get("risk")
    try:
        profile = risk_profile.profile_for(risk.get("tier") if isinstance(risk, dict) else None)
    except ValueError:
        return False
    if profile.get(phase) != "skippable":
        return False
    try:
        state_mod.transition_phase(state, feature_id, phase, "SKIPPED")
    except state_mod.StateError:
        return False
    return True


def _try_contract_revalidation(project: Path, phase: str, attempts: list[dict],
                                context_hash: str | None, feature_dir: str | None = None) -> dict | None:
    """NPV-010 / spec.md §11: a cheap, no-subprocess re-check of a
    previously-blocked attempt under the *current* phase contract. Returns
    a ready-to-append `PhaseAttempt` dict on success, or `None` when any of
    the four gate conditions fails — the caller then falls through to a
    normal, live attempt (research.md item 6).
    """
    last_attempt = attempts[-1]
    if last_attempt.get("contract_version", 1) >= phase_contracts.PHASE_CONTRACT_VERSION:
        return None
    if last_attempt.get("reason") not in ("missing_artifact", "unchanged_artifact"):
        return None
    if phase_contracts.validate_artifacts(project, phase, feature_dir):
        return None
    if last_attempt.get("context_hash") != context_hash:
        return None

    transcript_path = Path(last_attempt.get("transcript", ""))
    transcript_text = ""
    if transcript_path.is_file():
        transcript_text = transcript_path.read_text(encoding="utf-8", errors="replace")

    # History for a produce-or-update trust check excludes the attempt being
    # revalidated itself (research.md item 2 — every *prior* attempt).
    prior_history = attempts[:-1]
    revalidated = phase_runner.revalidate_from_transcript(project, phase, transcript_text, prior_history,
                                                          feature_dir=feature_dir)
    if revalidated is None:
        return None

    now = _now_iso()
    return {
        "status": "PASSED",
        "reason": "valid_noop",
        "outcome": revalidated["outcome"],
        "policy": revalidated["policy"],
        "contract_version": phase_contracts.PHASE_CONTRACT_VERSION,
        "active_artifacts": revalidated["active_artifacts"],
        "structured_result": revalidated["structured_result"],
        "events": [],
        "transcript": last_attempt.get("transcript"),
        "changed_paths": [],
        "forbidden_writes": [],
        "quality_gates": None,
        "started_at": now,
        "finished_at": now,
        "context_hash": context_hash,
        "source": "contract_revalidation",
    }


def _run_phase_with_attempts(state: dict, project: Path, phase: str, feature_id: str | None) -> str:
    execution = state["execution"]
    max_attempts = execution.get("max_attempts_per_phase", DEFAULT_MAX_ATTEMPTS)
    phase_timeout = execution.get("phase_timeout_seconds", DEFAULT_PHASE_TIMEOUT)
    attempts = _attempts_for(state, feature_id, phase)
    feature_dir = _feature_dir(state, feature_id)
    allowed_writes = phase_contracts.scoped_patterns(
        phase_contracts.PHASE_ALLOWED_WRITES[phase], feature_dir, keep_feature_json=True)
    expected_artifacts = phase_contracts.phase_artifacts(phase, feature_dir)
    context = state["context"]
    context_hash = _context_hash(project, context)

    if attempts and attempts[-1]["status"] == "PASSED":
        if attempts[-1].get("context_hash") == context_hash:
            print(f"[Spec Master] {phase} already PASSED (fingerprint unchanged) — skipping.")
            return "PASSED"

    if attempts and attempts[-1]["status"] != "PASSED":
        revalidated = _try_contract_revalidation(project, phase, attempts, context_hash, feature_dir)
        if revalidated is not None:
            revalidated["number"] = len(attempts) + 1
            attempts.append(revalidated)
            state_mod.save(str(_state_path(project)), state)
            print(f"[Spec Master] {phase} revalidated under contract v"
                  f"{phase_contracts.PHASE_CONTRACT_VERSION} — passed without a new attempt.")
            if phase == "constitution":
                state["constitution"] = {"status": "VALIDATED", "path": expected_artifacts[0]}
            _promote_feature_phase(state, feature_id, phase)
            state_mod.save(str(_state_path(project)), state)
            _emit(project, "phase.transition", {"feature": feature_id, "phase": phase, "status": "PASSED",
                                                "source": "contract_revalidation"})
            return "PASSED"

    # Every call grants a fresh budget of up to `max_attempts` *new*
    # attempts (matching Feature 1's behavior: resuming a phase that
    # exhausted a prior budget still gets to try again) — only attempts
    # made *during this call* count against it, not the phase's full
    # cumulative history.
    consumed_before_this_call = _consumed_attempts(attempts)
    while _consumed_attempts(attempts) - consumed_before_this_call < max_attempts:
        attempt_number = len(attempts) + 1
        used = _consumed_attempts(attempts) - consumed_before_this_call
        _check_and_clear_lock(project, phase_timeout)
        _acquire_lock(project, phase)
        started_at = _now_iso()
        print(f"[Spec Master] {phase} attempt {used + 1}/{max_attempts} started ({execution['active_mode']}).")
        _emit(project, "phase.started", {"feature": feature_id, "phase": phase, "attempt": attempt_number})
        last_attempt = attempts[-1] if attempts else None
        prompt = _render_prompt(phase, attempt_number, last_attempt, allowed_writes, expected_artifacts,
                                feature_dir)
        try:
            result = phase_runner.run_phase(
                project, phase, execution["integration"], execution["model"],
                prompt, phase_timeout, agent="spec-phase", history=list(attempts),
                feature_dir=feature_dir,
            )
        finally:
            _release_lock(project)
        finished_at = _now_iso()

        record = {
            "number": attempt_number,
            "status": result["status"],
            "reason": result["reason"],
            "outcome": result.get("outcome"),
            "policy": result.get("policy"),
            "contract_version": result.get("contract_version"),
            "active_artifacts": result.get("active_artifacts") or [],
            "structured_result": result.get("structured_result"),
            "events": result["events"],
            "transcript": result["transcript"],
            "changed_paths": result["changed_paths"],
            "forbidden_writes": result["forbidden_writes"],
            "quality_gates": result.get("quality_gates"),
            "started_at": started_at,
            "finished_at": finished_at,
            "context_hash": context_hash,
        }
        attempts.append(record)
        state_mod.save(str(_state_path(project)), state)
        _emit_gate_results(project, feature_id, record.get("quality_gates"))

        if result["reason"] == "user_decision_required":
            try:
                state_mod.transition_workflow_status(state, "PAUSED")
            except state_mod.InvalidTransitionError:
                pass
            state_mod.save(str(_state_path(project)), state)
            print(f"[Spec Master] {phase} paused: user decision required.")
            _emit(project, "phase.transition", {"feature": feature_id, "phase": phase, "status": "PAUSED"})
            checks = (record.get("structured_result") or {}).get("checks")
            if checks:
                print(f"[Spec Master] {phase} checks: {checks}")
            return "PAUSED"

        if execution["active_mode"] == "native":
            for event in result["events"]:
                execution_mode.maybe_migrate(state, event, finished_at, reason=event)
            state_mod.save(str(_state_path(project)), state)

        if result["status"] == "PASSED":
            print(f"[Spec Master] {phase} attempt {used + 1}/{max_attempts} passed "
                  f"({result['reason'] or 'artifact_updated'}).")
            if phase == "constitution":
                state["constitution"] = {"status": "VALIDATED", "path": expected_artifacts[0]}
            if phase == "specify":
                _record_discovered_feature_dir(state, project, feature_id)
            _promote_feature_phase(state, feature_id, phase)
            state_mod.save(str(_state_path(project)), state)
            _emit(project, "phase.transition", {"feature": feature_id, "phase": phase, "status": "PASSED"})
            return "PASSED"

        print(f"[Spec Master] {phase} failed: {result['reason']}.")

    _preserve_failed_attempt(project, phase, attempts[-1], feature_id)
    print(f"[Spec Master] {phase} attempts exhausted ({max_attempts}/{max_attempts}) — BLOCKED.")
    _emit(project, "phase.transition", {"feature": feature_id, "phase": phase, "status": "BLOCKED",
                                        "reason": attempts[-1].get("reason")})
    return "BLOCKED"


def _drive_workflow(state: dict, project: Path, feature_id: str | None) -> int:
    phase_timeout = state["execution"].get("phase_timeout_seconds", DEFAULT_PHASE_TIMEOUT)
    try:
        _check_and_clear_lock(project, phase_timeout)
    except ControllerError as exc:
        _print_json({"status": "REJECTED", "reason": str(exc)})
        return 2

    blocked_phase = None
    paused_phase = None
    skipped_phases = []
    for phase in PHASES:
        if _skip_by_risk_profile(state, feature_id, phase):
            skipped_phases.append(phase)
            state_mod.save(str(_state_path(project)), state)
            print(f"[Spec Master] {phase} SKIPPED — the feature's risk tier makes it skippable.")
            _emit(project, "phase.transition", {"feature": feature_id, "phase": phase, "status": "SKIPPED",
                                                "source": "risk_profile"})
            continue
        status = _run_phase_with_attempts(state, project, phase, feature_id)
        if status == "BLOCKED":
            blocked_phase = phase
            break
        if status == "PAUSED":
            paused_phase = phase
            break

    if paused_phase:
        workflow_status = "PAUSED"
    elif blocked_phase:
        workflow_status = "BLOCKED"
    else:
        workflow_status = "COMPLETED"

    if workflow_status != "PAUSED":
        # _run_phase_with_attempts already set state["status"] = "PAUSED"
        # itself (and saved) — don't overwrite it here.
        try:
            state_mod.transition_workflow_status(state, workflow_status)
            state_mod.save(str(_state_path(project)), state)
        except state_mod.InvalidTransitionError:
            pass

    _emit(project, "workflow.status", {"status": workflow_status, "feature": feature_id,
                                       "blocked_phase": blocked_phase, "paused_phase": paused_phase})

    phases_summary = {phase: "SKIPPED" if phase in skipped_phases else _phase_status(state, phase, feature_id)
                      for phase in PHASES}
    recorded = {phase: state["attempts"][_attempt_key(feature_id, phase)]
                for phase in PHASES if _attempt_key(feature_id, phase) in state["attempts"]}
    attempts_summary = {phase: len(attempts) for phase, attempts in recorded.items()}
    outcomes = {
        phase: (attempts[-1].get("outcome") if attempts else None)
        for phase, attempts in recorded.items()
    }
    validate_attempts = recorded.get("validate", [])
    quality_gates = (validate_attempts[-1].get("quality_gates") if validate_attempts else None) or []

    report = {
        "workflow_status": workflow_status,
        "active_mode": state["execution"]["active_mode"],
        "mode_transitions": state["execution"]["mode_transitions"],
        "phases": phases_summary,
        "blocked_phase": blocked_phase,
        "paused_phase": paused_phase,
        "attempts_summary": attempts_summary,
        "outcomes": outcomes,
        "quality_gates": quality_gates,
    }
    _print_json(report)
    return 0 if workflow_status == "COMPLETED" else 1


def cmd_run(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    if not project.is_dir():
        _print_json({"status": "REJECTED", "reason": f"project directory not found: {project}"})
        return 2
    if not (project / args.context).is_file() and not Path(args.context).is_file():
        _print_json({"status": "REJECTED", "reason": f"context file not found: {args.context}"})
        return 2

    try:
        mode = execution_mode.parse_mode(args.mode)
    except execution_mode.ExecutionModeError as exc:
        _print_json({"status": "REJECTED", "reason": str(exc)})
        return 2

    if mode == "native":
        _print_json({
            "status": "REJECTED",
            "reason": "native mode does not use this controller; run the agent-driven "
                      "/spec-master protocol directly",
        })
        return 2

    if args.integration not in phase_runner.INTEGRATIONS:
        _print_json({
            "status": "REJECTED",
            "reason": f"integration {args.integration!r} is not supported in guarded mode yet",
        })
        return 2

    state = _load_or_init_state(
        project, args.context, mode, args.integration, args.model,
        args.max_attempts, args.phase_timeout,
    )
    return _drive_workflow(state, project, args.feature)


def cmd_resume(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    path = _state_path(project)
    if not path.exists():
        _print_json({"status": "REJECTED", "reason": "no guarded/auto run to resume"})
        return 2
    state = state_mod.load(str(path))
    if "execution" not in state:
        _print_json({"status": "REJECTED", "reason": "no guarded/auto run to resume"})
        return 2
    state.setdefault("attempts", {})
    return _drive_workflow(state, project, args.feature)


def cmd_status(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    path = _state_path(project)
    if not path.exists() or "execution" not in state_mod.load(str(path)):
        _print_json({"execution": None, "phases": {}, "attempts_summary": {}, "blocked_phase": None})
        return 0
    state = state_mod.load(str(path))
    feature_id = getattr(args, "feature", None)
    attempts = state.get("attempts", {})
    phases_summary = {phase: _phase_status(state, phase, feature_id) for phase in PHASES}
    blocked_phase = next((phase for phase, status in phases_summary.items() if status == "BLOCKED"), None)
    if feature_id:
        attempts_summary = {phase: len(attempts[_attempt_key(feature_id, phase)])
                            for phase in PHASES if _attempt_key(feature_id, phase) in attempts}
    else:
        attempts_summary = {phase: len(records) for phase, records in attempts.items()}
    _print_json({
        "execution": state.get("execution"),
        "phases": phases_summary,
        "attempts_summary": attempts_summary,
        "blocked_phase": blocked_phase,
    })
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spec-master-controller")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run")
    p_run.add_argument("--project", required=True)
    p_run.add_argument("--context", required=True)
    p_run.add_argument("--mode", choices=execution_mode.MODES, default=None)
    p_run.add_argument("--integration", default="opencode")
    p_run.add_argument("--model", required=True)
    p_run.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    p_run.add_argument("--phase-timeout", type=int, default=DEFAULT_PHASE_TIMEOUT)
    p_run.add_argument("--feature", default=None)
    p_run.set_defaults(func=cmd_run)

    p_resume = sub.add_parser("resume")
    p_resume.add_argument("--project", required=True)
    p_resume.add_argument("--feature", default=None)
    p_resume.set_defaults(func=cmd_resume)

    p_status = sub.add_parser("status")
    p_status.add_argument("--project", required=True)
    p_status.add_argument("--feature", default=None,
                          help="report this feature's attempts (attempts are recorded per feature and phase)")
    p_status.set_defaults(func=cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
