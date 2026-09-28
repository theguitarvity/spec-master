#!/usr/bin/env python3
"""spec-master orchestration core CLI.

Model-agnostic entrypoint: any adapter (Claude Code, Copilot, Codex, Qwen-compatible shells) shells
out to this CLI for every *structural* decision, so the same tested logic
backs every platform. Semantic work (writing specs, resolving ambiguity)
stays in the calling agent's prompt.

    python3 cli.py <command> <subcommand> [options]

All output is compact JSON on stdout (`--pretty`, or SPEC_MASTER_PRETTY=1,
indents it) unless the subcommand renders Markdown (`traceability render`),
in which case Markdown is printed directly.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from graph import ontology as graph_ontology
from graph import maps as graph_maps
from graph import health as graph_health
from graph.store import FileGraphStore, graph_from_dict
from graph.validation import validate_graph

from knowledge.manifest import KnowledgeManifest
from knowledge.router import KnowledgeRouter
from knowledge.validation import validate_manifest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import calibration  # noqa: E402
import constitution_diff  # noqa: E402
import context_budget  # noqa: E402
import context_delta  # noqa: E402
import dashboard  # noqa: E402
import decision_memory  # noqa: E402
import discovery  # noqa: E402
import ears  # noqa: E402
import evals  # noqa: E402
import evidence  # noqa: E402
import feature_model  # noqa: E402
import fingerprint  # noqa: E402
import git_strategy  # noqa: E402
import hooks  # noqa: E402
import metrics  # noqa: E402
import metrics_export  # noqa: E402
import pr_step  # noqa: E402
import quality_gates  # noqa: E402
import risk_profile  # noqa: E402
import state as state_mod  # noqa: E402
import team_model  # noqa: E402
import team_workstreams  # noqa: E402
import telemetry  # noqa: E402
import tool_policy  # noqa: E402
import traceability  # noqa: E402
import tracker_orchestration  # noqa: E402
import web_bundle  # noqa: E402
import runtime_contract  # noqa: E402
import worktree  # noqa: E402


# Output is compact JSON by default: every byte printed here lands in the
# calling agent's context. `--pretty` (anywhere on the command line) or
# SPEC_MASTER_PRETTY=1 restores the indented format for humans.
PRETTY = False


def _print_json(payload) -> None:
    if PRETTY:
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False))
    else:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=False, separators=(",", ":")))


class EvidenceMissing(state_mod.InvalidTransitionError):
    """A phase promotion without the evidence Principle IV requires."""

    def __init__(self, result: dict):
        failed = [c["detail"] for c in result["checks"] if not c["ok"]]
        super().__init__(
            f"cannot promote '{result['phase']}' of '{result['feature']}' to PASSED without evidence: "
            + "; ".join(failed)
        )
        self.payload = {"evidence": result}


def _load_json_file(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _save_json_file(path: str, payload) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, sort_keys=False)
        fh.write("\n")


def _transition_ack(feature: dict, args: argparse.Namespace, previous: str, evidence_entry: dict | None,
                    feature_status_changed: bool) -> dict:
    ack = {"feature": args.feature, "phase": args.phase, "status": args.status, "previous": previous}
    if evidence_entry is not None:
        ack["evidence"] = {"verified": evidence_entry["verified"],
                           "artifacts": len(evidence_entry.get("artifacts") or [])}
    if feature_status_changed:
        ack["feature_status"] = feature.get("status")
    return ack


def cmd_state(args: argparse.Namespace) -> int:
    if args.state_action == "init":
        with state_mod.locked(args.path):
            s = state_mod.init(args.path, context=args.context, workflow=args.workflow)
            # New states keep traceability per feature from the start (nothing to migrate yet).
            traceability.migrate_from_state(s, args.path)
            state_mod.save(args.path, s)
        _print_json(s)
        return 0
    if args.state_action == "show":
        s = state_mod.load(args.path)
        _print_json(state_mod.summarize(s) if args.summary else s)
        return 0
    if args.state_action == "set-workflow":
        with state_mod.transaction(args.path) as s:
            state_mod.set_workflow(s, args.workflow)
        _print_json(s)
        return 0
    if args.state_action == "set-status":
        with state_mod.transaction(args.path) as s:
            state_mod.transition_workflow_status(s, args.status)
        _print_json(s)
        return 0
    if args.state_action == "upsert-feature":
        feature = _load_json_file(args.feature_file) if args.feature_file else json.loads(args.feature_json)
        if args.import_unverified and not (args.reason or "").strip():
            raise state_mod.StateError("--import-unverified requires --reason")
        with state_mod.transaction(args.path) as s:
            f, info = state_mod.upsert_feature_metadata(s, feature, allow_unverified=args.import_unverified)
            for phase in info["imported_phases"]:
                evidence.record_unverified(f, phase, args.reason)
        payload = dict(f)
        if args.import_unverified:
            payload["imported_unverified"] = info
        _print_json(payload)
        return 0
    if args.state_action == "transition":
        if args.import_unverified and not (args.reason or "").strip():
            raise state_mod.StateError("--import-unverified requires --reason")
        root = hooks.project_root_for_state(args.path)
        with state_mod.transaction(args.path) as s:
            feature = state_mod.find_feature(s, args.feature)
            previous = feature["phases"].get(args.phase, "PENDING")
            state_status = feature.get("status")
            f = state_mod.transition_phase(s, args.feature, args.phase, args.status)
            evidence_entry = None
            if args.status == "PASSED":
                if args.import_unverified:
                    evidence_entry = evidence.record_unverified(f, args.phase, args.reason)
                else:
                    rows = (traceability.load_rows(s, args.path, feature=args.feature)
                            if args.phase == "validate" else None)
                    result = evidence.check(root, f, args.phase, traceability_rows=rows)
                    if not result["ok"]:
                        raise EvidenceMissing(result)
                    evidence_entry = evidence.record(f, result)
                if args.phase == state_mod.FEATURE_PHASES[-1]:
                    f["status"] = "COMPLETED"
        fired = None if args.no_hooks else hooks.safe_emit(
            root, "phase.transition",
            {"feature": args.feature, "phase": args.phase, "status": args.status, "previous": previous},
        )
        payload = dict(f) if args.full else _transition_ack(
            f, args, previous, evidence_entry, f.get("status") != state_status)
        if fired and fired["directives"]:
            payload["hook_directives"] = fired["directives"]
        _print_json(payload)
        return 0
    if args.state_action == "analyze-cycle":
        with state_mod.transaction(args.path) as s:
            result = state_mod.analyze_cycle(s, args.feature, args.action)
        _print_json(result)
        return 0
    if args.state_action == "evidence":
        s = state_mod.load(args.path)
        root = hooks.project_root_for_state(args.path)
        feature = state_mod.find_feature(s, args.feature)
        if args.phase:
            rows = traceability.load_rows(s, args.path, feature=args.feature) if args.phase == "validate" else None
            _print_json(evidence.check(root, feature, args.phase, traceability_rows=rows))
        else:
            _print_json({"feature": args.feature, "phases": evidence.summary(feature),
                         "evidence": feature.get("evidence") or {}})
        return 0
    raise SystemExit(f"unknown state action: {args.state_action}")


def cmd_fingerprint(args: argparse.Namespace) -> int:
    if args.fp_action == "compute":
        files = args.files.split(",") if args.files else []
        _print_json(fingerprint.compute(files))
        return 0
    if args.fp_action == "compare":
        previous = _load_json_file(args.previous)
        current = _load_json_file(args.current)
        _print_json(fingerprint.compare(previous, current))
        return 0
    raise SystemExit(f"unknown fingerprint action: {args.fp_action}")


def cmd_discovery(args: argparse.Namespace) -> int:
    _print_json(discovery.scan(args.path))
    return 0


def cmd_features(args: argparse.Namespace) -> int:
    if args.features_action == "order":
        features = _load_json_file(args.file)
        try:
            order = feature_model.order_features(features)
        except feature_model.CycleError as exc:
            _print_json({"error": str(exc), "cycle": exc.cycle})
            return 1
        _print_json({"order": order})
        return 0
    raise SystemExit(f"unknown features action: {args.features_action}")


def cmd_git_strategy(args: argparse.Namespace) -> int:
    if args.gs_action == "plan":
        result = git_strategy.plan(
            strategy=args.strategy,
            feature_name=args.feature_name,
            issue_id=args.issue_id,
            git_extension_installed=args.git_extension_installed,
            spec_kit_present=args.spec_kit_present,
        )
        _print_json(result)
        return 0
    raise SystemExit(f"unknown git-strategy action: {args.gs_action}")


def cmd_gates(args: argparse.Namespace) -> int:
    _print_json(quality_gates.detect(args.path))
    return 0


def cmd_worktree(args: argparse.Namespace) -> int:
    if args.worktree_action == "waves":
        features = _load_json_file(args.features)
        _print_json(worktree.compute_waves(features))
        return 0
    if args.worktree_action == "plan":
        handle = worktree.plan_worktree(
            feature_id=args.feature_id,
            project_root=args.project_root,
            strategy=args.strategy,
            wave_size=args.wave_size,
            is_git_repo=not args.not_git_repo,
        )
        _print_json(handle)
        return 0
    if args.worktree_action == "conflicts":
        _print_json(worktree.conflicts(args.path_a, args.path_b))
        return 0
    if args.worktree_action == "aggregate":
        handles = _load_json_file(args.handles)
        _print_json(worktree.aggregate(args.wave_index, handles))
        return 0
    raise SystemExit(f"unknown worktree action: {args.worktree_action}")


def cmd_constitution(args: argparse.Namespace) -> int:
    if args.const_action == "diff":
        result = constitution_diff.diff_files(args.existing, args.proposed)
        _print_json(result)
        return 0
    raise SystemExit(f"unknown constitution action: {args.const_action}")


def cmd_traceability(args: argparse.Namespace) -> int:
    if args.trace_action == "add":
        row = _load_json_file(args.row_file) if args.row_file else json.loads(args.row_json)
        with state_mod.transaction(args.path) as s:
            written = traceability.record(s, args.path, row)
        _print_json(written)
        return 0
    if args.trace_action == "render":
        s = state_mod.load(args.path)
        rows = traceability.load_rows(s, args.path, feature=args.feature)
        title = f"Requirement Traceability — {args.feature}" if args.feature else "Requirement Traceability"
        markdown = traceability.render_rows(rows, title=title)
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(markdown, encoding="utf-8")
            _print_json({"output": args.output, "rows": len(rows)})
        else:
            print(markdown)
        return 0
    if args.trace_action == "migrate":
        with state_mod.transaction(args.path) as s:
            summary = traceability.migrate_from_state(s, args.path)
        _print_json(summary)
        return 0
    raise SystemExit(f"unknown traceability action: {args.trace_action}")


def _load_state_optional(path: str) -> dict | None:
    try:
        return state_mod.load(path)
    except (OSError, state_mod.StateError, ValueError):
        return None


def cmd_delta(args: argparse.Namespace) -> int:
    state = _load_state_optional(args.state)
    if args.delta_action == "snapshot":
        snap = context_delta.snapshot(args.path, state)
        path = context_delta.save_snapshot(args.path, snap)
        _print_json({"snapshot": path, "artifacts": len(snap["artifacts"]), "taken_at": snap["taken_at"]})
        return 0
    if args.delta_action == "report":
        result = context_delta.report(args.path, state)
        if args.format == "markdown":
            markdown = context_delta.render(result)
            if args.output:
                Path(args.output).parent.mkdir(parents=True, exist_ok=True)
                Path(args.output).write_text(markdown, encoding="utf-8")
                _print_json({"output": args.output, "summary": result.get("summary", {})})
            else:
                print(markdown)
        else:
            _print_json(result)
        return 0
    raise SystemExit(f"unknown delta action: {args.delta_action}")


def cmd_dashboard(args: argparse.Namespace) -> int:
    if args.dashboard_action == "render":
        _print_json(dashboard.write_summary(args.path, output=args.output, refresh=args.refresh))
        return 0
    if args.dashboard_action == "model":
        _print_json(dashboard.build_model(args.path))
        return 0
    raise SystemExit(f"unknown dashboard action: {args.dashboard_action}")


def cmd_hooks(args: argparse.Namespace) -> int:
    if args.hooks_action == "init":
        _print_json(hooks.init_config(args.path, force=args.force))
        return 0
    if args.hooks_action == "list":
        _print_json({"hooks": hooks.load_hooks(args.path), "events": list(hooks.EVENT_TYPES)})
        return 0
    if args.hooks_action == "validate":
        config = _load_json_file(args.file) if args.file else hooks._read_config(args.path)
        errors = hooks.validate_hooks(hooks.effective_hooks(config))
        _print_json({"valid": not errors, "errors": errors})
        return 0 if not errors else 1
    if args.hooks_action == "emit":
        payload = json.loads(args.payload_json) if args.payload_json else {}
        _print_json(hooks.emit(args.path, args.event, payload, execute_internal=not args.no_internal))
        return 0
    if args.hooks_action == "firings":
        _print_json({"firings": hooks.read_firings(args.path, limit=args.limit, event_type=args.event)})
        return 0
    raise SystemExit(f"unknown hooks action: {args.hooks_action}")


def _risk_state_path(args: argparse.Namespace) -> str:
    return args.state or str(Path(args.path) / ".spec-master" / "state.json")


def cmd_risk(args: argparse.Namespace) -> int:
    if args.risk_action == "classify":
        state_path = _risk_state_path(args)
        s = state_mod.load(state_path)
        paths = [p.strip() for p in (args.paths or "").split(",") if p.strip()] or None
        result = risk_profile.classify(args.path, s, args.feature, args.stage, paths=paths)
        if args.save:
            with state_mod.transaction(state_path) as locked_state:
                result["saved_risk"] = risk_profile.save_classification(locked_state, args.feature, result)
            s = locked_state
            emitted = risk_profile.emit_event(args.path, s, args.feature, args.stage, paths=paths)
            result["hook_directives"] = (emitted or {}).get("directives", [])
        _print_json(result)
        return 0
    if args.risk_action == "override":
        state_path = _risk_state_path(args)
        with state_mod.transaction(state_path) as s:
            result = risk_profile.override(args.path, s, args.feature, args.tier, args.reason, by=args.by)
        _print_json(result)
        return 0
    if args.risk_action == "profiles":
        _print_json({
            "tiers": list(risk_profile.TIER_ORDER),
            "profiles": risk_profile.CEREMONY_PROFILES,
            "adr_sensitive_categories": list(risk_profile.ADR_SENSITIVE_CATEGORIES),
            "work_package_template": list(risk_profile.WORK_PACKAGE_TEMPLATE),
            "thresholds": risk_profile.load_thresholds(args.path),
        })
        return 0
    if args.risk_action == "work-packages":
        _print_json({"feature": args.feature, "tier": args.tier,
                     "packages": risk_profile.work_packages(args.feature, args.tier)})
        return 0
    raise SystemExit(f"unknown risk action: {args.risk_action}")


def cmd_tracker(args: argparse.Namespace) -> int:
    if args.tracker_action == "orchestrate":
        _print_json(tracker_orchestration.orchestrate(args.path))
        return 0
    raise SystemExit(f"unknown tracker action: {args.tracker_action}")


def cmd_pr(args: argparse.Namespace) -> int:
    if args.pr_action == "plan":
        state_path = args.state or str(Path(args.path) / ".spec-master" / "state.json")
        s = state_mod.load(state_path)
        _print_json(pr_step.plan_pr(
            args.path, s, state_path, args.feature,
            confirm=args.confirm, base=args.base, remote_url=args.remote_url, draft=args.draft,
        ))
        return 0
    raise SystemExit(f"unknown pr action: {args.pr_action}")


def cmd_ears(args: argparse.Namespace) -> int:
    if args.ears_action == "check":
        if args.text:
            result = ears.validate(args.text, strict=args.strict)
        else:
            state_path = ears.resolve_state_path(args.path)
            result = {"state": state_path,
                      **ears.check_state(state_mod.load(state_path), feature_id=args.feature,
                                         strict=args.strict)}
        _print_json(result)
        return 1 if args.strict and not result["valid"] else 0
    raise SystemExit(f"unknown ears action: {args.ears_action}")


def cmd_team(args: argparse.Namespace) -> int:
    if args.team_action == "roles":
        _print_json({"roles": team_model.roles()})
        return 0
    if args.team_action == "intake":
        _print_json(team_model.guided_intake())
        return 0
    if args.team_action == "adopt":
        _print_json(team_model.adoption_plan())
        return 0
    if args.team_action == "workstreams":
        features = _load_json_file(args.file)
        _print_json(team_model.build_workstreams(features))
        return 0
    if args.team_action == "escalate":
        route = team_model.escalation_route(args.kind, decision_memory.canonical_role(args.raised_by))
        payload = {"kind": args.kind, "raised_by": route["raised_by"], "feature": args.feature,
                   "summary": args.summary}
        fired = hooks.safe_emit(args.path, "escalation.raised", {k: v for k, v in payload.items() if v})
        _print_json({"route": route, "hooks": fired})
        return 0
    if args.team_action == "resolve":
        payload = {
            "kind": args.kind, "raised_by": args.raised_by, "decided_by": args.decided_by,
            "decision": args.decision, "rationale": args.rationale, "feature": args.feature,
            "alternatives": args.alternative or None, "adr_triggers": args.adr_trigger or None,
            "title": args.title,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        fired = hooks.safe_emit(args.path, "escalation.resolved", payload)
        recorded = next((entry["result"] for entry in (fired or {}).get("fired", [])
                         if entry["action"] == "record_decision" and entry["result"].get("executed")), None)
        if recorded is None:
            # No enabled hook recorded it (or it failed): record directly so a
            # resolution is never lost; errors surface to the caller here.
            recorded = decision_memory.record_from_event(args.path, payload)
        _print_json({"recorded": recorded, "hooks": fired})
        return 0
    if args.team_action == "decisions":
        if args.role:
            decisions = decision_memory.decisions_for_role(args.path, args.role, limit=args.limit)
        elif args.feature:
            decisions = decision_memory.decisions_for_feature(args.path, args.feature, limit=args.limit)
        else:
            decisions = decision_memory.all_decisions(args.path)[: args.limit or None]
        _print_json({"decisions": decisions})
        return 0
    if args.team_action == "routes":
        _print_json({"routes": team_model.ESCALATION_ROUTES, "adr_triggers": decision_memory.ADR_TRIGGERS})
        return 0
    raise SystemExit(f"unknown team action: {args.team_action}")


def cmd_workstreams(args: argparse.Namespace) -> int:
    if args.workstreams_action == "review":
        doc = _load_json_file(args.file)
        team_workstreams.record_review_verdict(
            doc["packages"], args.package, reviewer_agent=args.reviewer,
            status=args.status, reason=args.reason,
        )
        _save_json_file(args.file, doc)
        _print_json(next(p for p in doc["packages"] if p["id"] == args.package))
        return 0
    if args.workstreams_action == "integrate":
        doc = _load_json_file(args.file)
        team_workstreams.record_integration_verdict(
            doc["packages"], args.package, status=args.status, reason=args.reason,
        )
        _save_json_file(args.file, doc)
        _print_json(next(p for p in doc["packages"] if p["id"] == args.package))
        return 0
    if args.workstreams_action == "aggregate":
        handles = _load_json_file(args.handles)
        doc = _load_json_file(args.packages)
        _print_json(team_workstreams.aggregate_with_verdicts(args.wave_index, handles, doc["packages"]))
        return 0
    raise SystemExit(f"unknown workstreams action: {args.workstreams_action}")


def _append_round(rounds_path: str, row: dict) -> dict:
    """Append one row to rounds.json: validated first, then written
    atomically under the file's lock (rounds.json is core-owned)."""
    report = metrics_export.validate_rounds([row])
    if not report["valid"]:
        raise ValueError("refusing to append an invalid round: "
                         + "; ".join(f"{e['path'] or '/'}: {e['message']}" for e in report["errors"]))
    with state_mod.locked(rounds_path):
        rounds = []
        if os.path.exists(rounds_path):
            rounds = _load_json_file(rounds_path)
            if not isinstance(rounds, list):
                raise ValueError(f"{rounds_path} is not a JSON array; fix it before appending")
        rounds.append(row)
        state_mod.save(rounds_path, rounds)
    return {"appended": row["round_id"], "rounds_file": rounds_path, "rounds": len(rounds)}


def _emit_round(args: argparse.Namespace, row: dict) -> None:
    if args.append:
        _print_json({**_append_round(args.rounds or metrics_export.default_rounds_path(args.path), row), "row": row})
    else:
        _print_json(row)


def cmd_metrics(args: argparse.Namespace) -> int:
    if args.metrics_action == "record-round":
        row = metrics.record_round(
            round_id=args.round_id,
            phase=args.phase,
            started_at=args.started_at,
            ended_at=args.ended_at,
            input_tokens=args.input_tokens,
            output_tokens=args.output_tokens,
            work_packages_completed=args.work_packages_completed,
            features_completed=args.features_completed,
            notes=args.notes,
            feature_id=args.feature_id,
            tier=args.tier,
            source=args.source,
        )
        _emit_round(args, row)
        return 0
    if args.metrics_action == "summarize":
        rounds = _load_json_file(args.file)
        _print_json(metrics.summarize(rounds))
        return 0
    if args.metrics_action in ("export", "validate"):
        rounds_path = args.rounds or metrics_export.default_rounds_path(args.path)
        rounds = metrics_export.load_rounds(rounds_path)
        report = metrics_export.validate_rounds(rounds)
        if args.metrics_action == "validate":
            _print_json({"rounds_file": rounds_path, "rounds": len(rounds) if isinstance(rounds, list) else None,
                         **report})
            return 0 if report["valid"] else 1
        if not report["valid"]:
            _print_json({"error": "rounds do not match schemas/metrics-round.schema.json; nothing exported",
                         "rounds_file": rounds_path, **report})
            return 1
        text = metrics_export.export(rounds, fmt=args.format, validate_first=False)
        if args.output:
            output = metrics_export.write_text_atomic(args.output, text)
            _print_json({"output": output, "format": args.format, "rounds": len(rounds)})
        else:
            print(text, end="")
        return 0
    if args.metrics_action == "calibrate":
        rounds_path = args.rounds or str(Path(args.path) / ".spec-master" / "metrics" / "rounds.json")
        s = _load_state_optional(args.state or str(Path(args.path) / ".spec-master" / "state.json"))
        result = calibration.calibrate(
            calibration.load_rounds(rounds_path),
            overrides=risk_profile.read_overrides(args.path),
            thresholds=risk_profile.load_thresholds(args.path),
            window=args.window,
            risk=calibration.risk_from_state(s),
            since=calibration.consumed_until(args.path),
            require_measured=True if args.require_measured else None,
        )
        result["rounds_file"] = rounds_path
        if args.apply:
            result["apply"] = calibration.apply(args.path, result)
        _print_json(result)
        return 0
    raise SystemExit(f"unknown metrics action: {args.metrics_action}")


def cmd_telemetry(args: argparse.Namespace) -> int:
    if args.telemetry_action == "locate":
        found = telemetry.locate_transcripts(args.path, include_subagents=args.include_subagents)
        _print_json({"project": os.path.abspath(args.path), "transcripts": found})
        return 0
    if args.telemetry_action == "ingest":
        if args.headless_json:
            usage = telemetry.read_headless_result(args.headless_json)
        else:
            files = list(args.transcript or [])
            if args.latest:
                found = telemetry.locate_transcripts(args.path)
                if not found:
                    _print_json({"error": "no Claude Code transcript found for this project",
                                 "project": os.path.abspath(args.path)})
                    return 1
                files = [found[0]]
            if not args.main_only:  # a session's usage includes its subagents
                files = [path for session in files for path in telemetry.session_transcripts(session)]
            usage = telemetry.read_transcript_usage(files, since=args.since, until=args.until)
        row = telemetry.to_round(
            usage, round_id=args.round_id, phase=args.phase, source=usage["source"],
            feature_id=args.feature_id, tier=args.tier, lane=args.lane, notes=args.notes,
            started_at=args.started_at, ended_at=args.ended_at,
            work_packages_completed=args.work_packages_completed, features_completed=args.features_completed,
        )
        _emit_round(args, row)
        return 0
    raise SystemExit(f"unknown telemetry action: {args.telemetry_action}")


def cmd_baseline(args: argparse.Namespace) -> int:
    import baseline
    cases = baseline.load_cases(args.cases) if args.baseline_action in ("plan", "run") else None
    if args.baseline_action == "plan":
        _print_json(baseline.plan(cases, _csv(args.arms), args.runs, args.max_budget_usd,
                                  model=args.model, claude=args.claude))
        return 0
    if args.baseline_action == "run":
        try:
            result = baseline.run(cases, arms=_csv(args.arms), runs=args.runs, max_budget_usd=args.max_budget_usd,
                                  out_dir=args.out, confirm=args.yes, model=args.model, claude=args.claude,
                                  timeout=args.timeout)
        except baseline.ConfirmationRequired as exc:
            _print_json({"error": "a baseline run spends real money: show the plan to the user and re-run with "
                                  "--yes only after their explicit agreement",
                         "total_runs": exc.plan["total_runs"],
                         "worst_case_budget_usd": exc.plan["worst_case_budget_usd"]})
            return 2
        _print_json({key: result[key] for key in ("out_dir", "total_runs", "worst_case_budget_usd", "summary")})
        return 0
    if args.baseline_action == "summarize":
        _print_json(baseline.summarize(baseline.load_results(args.out)))
        return 0
    raise SystemExit(f"unknown baseline action: {args.baseline_action}")


def cmd_bundle(args: argparse.Namespace) -> int:
    if args.bundle_action == "build":
        state_path = args.state or str(Path(args.path) / ".spec-master" / "state.json")
        state = _load_state_optional(state_path)
        if state is None:
            _print_json({"error": f"cannot load state: {state_path}"})
            return 1
        result = web_bundle.build(
            args.path, state, args.feature, phase=args.phase, token_budget=args.budget,
            generated_at=None if args.no_timestamp else web_bundle.now_iso(),
        )
        if args.stdout:
            print(result["markdown"], end="")
            return 0
        output = web_bundle.write(args.path, result, args.output)
        _print_json({
            "output": output,
            "feature": result["feature"],
            "phase": result["phase"],
            "tokens": result["tokens"],
            "token_budget": result["token_budget"],
            "over_budget": result["over_budget"],
            "included": result["included"],
            "omitted": result["omitted"],
            "missing": result["missing"],
            "unresolved_placeholders": result["unresolved_placeholders"],
            "warnings": result["warnings"],
        })
        return 0
    raise SystemExit(f"unknown bundle action: {args.bundle_action}")


def cmd_graph(args: argparse.Namespace) -> int:
    store = FileGraphStore(project_root=args.path)
    if args.graph_action == "validate":
        graph = store.load()
        report = validate_graph(graph)
        _print_json(report)
        return 0
    if args.graph_action == "stats":
        graph = store.load()
        _print_json(graph.stats())
        return 0
    if args.graph_action == "neighbors":
        graph = store.load()
        rels = args.relations.split(",") if args.relations else None
        edges = graph.neighbors(args.node_id, relations=rels, direction="both")
        _print_json([e.to_dict() for e in edges])
        return 0
    if args.graph_action == "stale":
        graph = store.load()
        from graph.validation import find_stale_nodes
        stale = find_stale_nodes(graph)
        _print_json({"stale_nodes": stale})
        return 0
    if args.graph_action == "rebuild":
        stats = store.rebuild_manifest()
        _print_json(stats)
        return 0
    if args.graph_action == "enrich-discovery":
        from graph.enrichment import enrich_from_discovery
        info = discovery.scan(args.path)
        nodes, edges = enrich_from_discovery(info, project_root=args.path)
        for node in nodes:
            store.save_node(node)
        for edge in edges:
            store.save_edge(edge)
        _print_json({"nodes_saved": len(nodes), "edges_saved": len(edges), "stats": store.load().stats()})
        return 0
    if args.graph_action == "snapshot":
        _print_json(store.snapshot(args.name))
        return 0
    if args.graph_action == "drift":
        from graph import drift
        previous = graph_from_dict(_load_json_file(args.previous))
        current = store.load()
        _print_json(drift.detect_structural_drift(previous, current))
        return 0
    if args.graph_action == "health":
        graph = store.load()
        report = graph_health.compute_health(graph)
        md = graph_health.render_health_report(report)
        health_path = Path(args.path) / ".spec-master" / "reports" / "graph-health.md"
        health_path.parent.mkdir(parents=True, exist_ok=True)
        health_path.write_text(md, encoding="utf-8")
        _print_json({"path": str(health_path), "score": report["score"], "grade": report["grade"]})
        return 0
    if args.graph_action == "maps":
        graph = store.load()
        if args.map_type == "system":
            print(graph_maps.render_system_map(graph))
            return 0
        if args.map_type == "node":
            if not args.node_id:
                raise SystemExit("graph maps node requires --node-id")
            print(graph_maps.render_node_map(graph, args.node_id, depth=args.depth))
            return 0
        if args.map_type == "dependencies":
            print(graph_maps.render_dependency_map(graph, relation=args.relation))
            return 0
        raise SystemExit(f"unknown map type: {args.map_type}")
    raise SystemExit(f"unknown graph action: {args.graph_action}")


def cmd_policy(args: argparse.Namespace) -> int:
    if args.policy_action == "preflight":
        commands = args.command if isinstance(args.command, list) else [args.command]
        _print_json(tool_policy.preflight(commands))
        return 0
    raise SystemExit(f"unknown policy action: {args.policy_action}")


def cmd_budget(args: argparse.Namespace) -> int:
    if args.budget_action == "estimate":
        _print_json({"estimated_tokens": context_budget.estimate_tokens(args.text)})
        return 0
    if args.budget_action == "file":
        items = []
        for path in args.files.split(","):
            p = Path(path.strip())
            items.append({"id": str(p), "content": p.read_text(encoding="utf-8") if p.exists() else "",
                          "exists": p.exists()})
        result = context_budget.budget_items(items, token_budget=args.token_budget)
        # The caller reads the selected files itself; echoing them here put
        # every file in the context twice (omitted ones included).
        for key in ("selected", "omitted"):
            for entry in result[key]:
                if not (args.with_content and key == "selected"):
                    entry.pop("content", None)
        _print_json(result)
        return 0
    raise SystemExit(f"unknown budget action: {args.budget_action}")


def cmd_runtime(args: argparse.Namespace) -> int:
    _print_json(runtime_contract.describe(args.runtime_type))
    return 0


def cmd_evals(args: argparse.Namespace) -> int:
    _print_json(evals.run())
    return 0


def cmd_knowledge(args: argparse.Namespace) -> int:
    manifest = KnowledgeManifest(knowledge_root=args.knowledge_root)

    if args.knowledge_action == "list":
        modules = manifest.all_modules()
        if args.role:
            modules = [m for m in modules if m.is_applicable_to(args.role)]
        if args.category:
            modules = [m for m in modules if m.category == args.category]
        if args.tag:
            modules = [m for m in modules if args.tag in m.tags]
        _print_json([m.to_dict() for m in sorted(modules, key=lambda m: m.id)])
        return 0

    if args.knowledge_action == "get":
        module = manifest.get(args.id)
        if module is None:
            raise SystemExit(f"unknown knowledge module: {args.id}")
        payload = module.to_dict()
        payload["content"] = module.content
        _print_json(payload)
        return 0

    if args.knowledge_action == "search":
        results = manifest.search(args.query)
        _print_json([m.to_dict() for m in results])
        return 0

    if args.knowledge_action == "for-role":
        router = KnowledgeRouter(manifest)
        modules = router.for_role(args.role, limit=args.limit)
        payload = {
            "modules": [m.to_dict() for m in modules],
            "budget": router.budget_summary(modules),
        }
        if args.path:
            payload["decisions"] = decision_memory.decisions_for_role(args.path, args.role,
                                                                      limit=args.decision_limit)
        _print_json(payload)
        return 0

    if args.knowledge_action == "route":
        router = KnowledgeRouter(manifest)
        keywords = args.keywords.split(",") if args.keywords else None
        tech_stacks = args.tech_stacks.split(",") if args.tech_stacks else None
        modules = router.for_context(args.role, keywords=keywords,
                                      tech_stacks=tech_stacks, limit=args.limit)
        _print_json({
            "modules": [m.to_dict() for m in modules],
            "budget": router.budget_summary(modules),
        })
        return 0

    if args.knowledge_action == "stats":
        _print_json(manifest.stats())
        return 0

    if args.knowledge_action == "validate":
        _print_json(validate_manifest(manifest))
        return 0

    raise SystemExit(f"unknown knowledge action: {args.knowledge_action}")


def _csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def cmd_lane(args: argparse.Namespace) -> int:
    from kernel import lanes
    if args.lane_action == "triage":
        _print_json(lanes.triage(args.path, intent=args.intent, paths=_csv(args.paths),
                                 confirmed=args.confirm or (), denied=args.deny or (),
                                 unresolved=args.unresolved, requested=args.lane))
        return 0
    raise SystemExit(f"unknown lane action: {args.lane_action}")


def cmd_step(args: argparse.Namespace) -> int:
    from kernel import changes, step
    try:
        if args.step_action == "next":
            result = step.next_step(args.path)
        elif args.step_action == "begin":
            result = step.begin(args.path, intent=args.intent, paths=_csv(args.paths), lane=args.lane,
                                kind=args.kind, confirmed=args.confirm or (), denied=args.deny or (),
                                unresolved=args.unresolved, regression_test=args.regression_test,
                                test_command=args.test_command)
        elif args.step_action == "end":
            result = step.end(args.path, change_id=args.change, run_gates=not args.no_gates, dry_run=args.dry_run)
        elif args.step_action == "widen":
            result = step.widen(args.path, paths=_csv(args.paths), change_id=args.change)
        elif args.step_action == "pause":
            result = step.pause(args.path, change_id=args.change, reason=args.reason or "")
        elif args.step_action == "resume":
            result = step.resume(args.path, change_id=args.change)
        else:
            raise SystemExit(f"unknown step action: {args.step_action}")
    except changes.ChangeError as exc:
        _print_json({"error": str(exc)})
        return 1
    _print_json(result)
    return 0 if result.get("status") not in ("QUESTIONS",) and result.get("ok", True) else 2


def cmd_doctor(args: argparse.Namespace) -> int:
    from kernel import doctor
    report = doctor.run(args.path, build_parser())
    if args.errors_only:
        report["checks"] = [c for c in report["checks"] if not c["ok"]]
    _print_json(report)
    return 0 if report["ok"] else 1


def cmd_harness(args: argparse.Namespace) -> int:
    from kernel import install
    if args.harness_action == "install-hooks":
        _print_json(install.install_hooks(args.project, engine=args.engine, mode=args.mode, dry_run=args.dry_run))
        return 0
    if args.harness_action == "mode":
        _print_json(install.set_mode(args.project, args.mode, dry_run=args.dry_run))
        return 0
    raise SystemExit(f"unknown harness action: {args.harness_action}")


def _round_output_args(action_parser: argparse.ArgumentParser) -> None:
    if not any("--path" in a.option_strings for a in action_parser._actions):
        action_parser.add_argument("--path", default=".", help="project root")
    action_parser.add_argument("--append", action="store_true",
                               help="append the row to rounds.json (validated, atomic, locked)")
    action_parser.add_argument("--rounds", default=None,
                               help="rounds file (default: <path>/.spec-master/metrics/rounds.json)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spec-master-cli")
    sub = parser.add_subparsers(dest="command", required=True)

    p_state = sub.add_parser("state")
    p_state.set_defaults(func=cmd_state)
    state_sub = p_state.add_subparsers(dest="state_action", required=True)

    s_init = state_sub.add_parser("init")
    s_init.add_argument("--path", default=".spec-master/state.json")
    s_init.add_argument("--context", required=True)
    s_init.add_argument("--workflow", choices=["git-flow", "trunk"], default=None)

    s_show = state_sub.add_parser("show")
    s_show.add_argument("--path", default=".spec-master/state.json")
    s_show.add_argument("--summary", action="store_true")

    s_setwf = state_sub.add_parser("set-workflow")
    s_setwf.add_argument("--path", default=".spec-master/state.json")
    s_setwf.add_argument("--workflow", required=True, choices=["git-flow", "trunk"])

    s_setstatus = state_sub.add_parser("set-status")
    s_setstatus.add_argument("--path", default=".spec-master/state.json")
    s_setstatus.add_argument("--status", required=True)

    s_upsert = state_sub.add_parser("upsert-feature", help="record feature metadata (phases change only via transition)")
    s_upsert.add_argument("--path", default=".spec-master/state.json")
    s_upsert.add_argument("--feature-file", dest="feature_file", default=None)
    s_upsert.add_argument("--feature-json", dest="feature_json", default=None)
    s_upsert.add_argument("--import-unverified", dest="import_unverified", action="store_true",
                          help="accept phases/COMPLETED for history that never ran through Spec Master "
                               "(recorded as unverified evidence; requires --reason)")
    s_upsert.add_argument("--reason", default=None)

    s_trans = state_sub.add_parser("transition", help="move a feature phase; PASSED requires evidence")
    s_trans.add_argument("--path", default=".spec-master/state.json")
    s_trans.add_argument("--feature", required=True)
    s_trans.add_argument("--phase", required=True)
    s_trans.add_argument("--status", required=True)
    s_trans.add_argument("--no-hooks", dest="no_hooks", action="store_true",
                         help="do not emit the phase.transition hook event")
    s_trans.add_argument("--full", action="store_true", help="print the whole feature record instead of an ack")
    s_trans.add_argument("--import-unverified", dest="import_unverified", action="store_true",
                         help="promote without evidence, recorded as unverified (requires --reason)")
    s_trans.add_argument("--reason", default=None)

    s_evidence = state_sub.add_parser("evidence", help="check or show the evidence behind a feature's phases")
    s_evidence.add_argument("--path", default=".spec-master/state.json")
    s_evidence.add_argument("--feature", required=True)
    s_evidence.add_argument("--phase", default=None, choices=state_mod.FEATURE_PHASES,
                            help="dry-run the evidence check for this phase")

    s_cycle = state_sub.add_parser("analyze-cycle")
    s_cycle.add_argument("--path", default=".spec-master/state.json")
    s_cycle.add_argument("--feature", required=True)
    s_cycle.add_argument("--action", required=True, choices=["increment", "check"])

    p_fp = sub.add_parser("fingerprint")
    p_fp.set_defaults(func=cmd_fingerprint)
    fp_sub = p_fp.add_subparsers(dest="fp_action", required=True)
    fp_compute = fp_sub.add_parser("compute")
    fp_compute.add_argument("--files", required=True, help="comma-separated file paths")
    fp_compare = fp_sub.add_parser("compare")
    fp_compare.add_argument("--previous", required=True)
    fp_compare.add_argument("--current", required=True)

    p_disc = sub.add_parser("discovery")
    p_disc.set_defaults(func=cmd_discovery)
    disc_sub = p_disc.add_subparsers(dest="disc_action", required=True)
    disc_scan = disc_sub.add_parser("scan")
    disc_scan.add_argument("--path", default=".")

    p_feat = sub.add_parser("features")
    p_feat.set_defaults(func=cmd_features)
    feat_sub = p_feat.add_subparsers(dest="features_action", required=True)
    feat_order = feat_sub.add_parser("order")
    feat_order.add_argument("--file", required=True, help="JSON file: [{id, dependencies}]")

    p_gs = sub.add_parser("git-strategy")
    p_gs.set_defaults(func=cmd_git_strategy)
    gs_sub = p_gs.add_subparsers(dest="gs_action", required=True)
    gs_plan = gs_sub.add_parser("plan")
    gs_plan.add_argument("--strategy", required=True, choices=["git-flow", "trunk"])
    gs_plan.add_argument("--feature-name", required=True)
    gs_plan.add_argument("--issue-id", default=None)
    gs_plan.add_argument("--git-extension-installed", action="store_true")
    gs_plan.add_argument("--spec-kit-present", action="store_true")

    p_pr = sub.add_parser("pr", help="optional PR step at the end of a Git Flow feature (never automatic)")
    p_pr.set_defaults(func=cmd_pr)
    pr_sub = p_pr.add_subparsers(dest="pr_action", required=True)
    pr_plan = pr_sub.add_parser("plan", help="render the PR description and return a confirm/open directive")
    pr_plan.add_argument("--path", default=".", help="project root")
    pr_plan.add_argument("--feature", required=True)
    pr_plan.add_argument("--state", default=None, help="defaults to <path>/.spec-master/state.json")
    pr_plan.add_argument("--confirm", action="store_true",
                         help="the user explicitly confirmed: return the open_pr directive")
    pr_plan.add_argument("--base", default=None, help="target branch (default: develop/main/master from refs)")
    pr_plan.add_argument("--remote-url", dest="remote_url", default=None,
                         help="override the origin url read from .git/config")
    pr_plan.add_argument("--draft", action="store_true")

    p_ears = sub.add_parser("ears", help="optional EARS syntax check for acceptance criteria")
    p_ears.set_defaults(func=cmd_ears)
    ears_sub = p_ears.add_subparsers(dest="ears_action", required=True)
    ears_check = ears_sub.add_parser("check")
    ears_check.add_argument("--path", default=".", help="state.json path or project directory")
    ears_check.add_argument("--feature", default=None)
    ears_check.add_argument("--strict", action="store_true", help="non-EARS criteria fail (exit 1)")
    ears_check.add_argument("--text", action="append", default=None,
                            help="criterion to check (repeatable); bypasses state")

    p_wt = sub.add_parser("worktree")
    p_wt.set_defaults(func=cmd_worktree)
    wt_sub = p_wt.add_subparsers(dest="worktree_action", required=True)

    wt_waves = wt_sub.add_parser("waves")
    wt_waves.add_argument("--features", required=True, help="JSON file: [{id, dependencies}]")

    wt_plan = wt_sub.add_parser("plan")
    wt_plan.add_argument("--feature-id", required=True)
    wt_plan.add_argument("--project-root", required=True)
    wt_plan.add_argument("--strategy", required=True, choices=["git-flow", "trunk"])
    wt_plan.add_argument("--wave-size", type=int, default=2,
                          help="feature count in this feature's wave (FR-004)")
    wt_plan.add_argument("--not-git-repo", action="store_true", help="skip creation (FR-005)")

    wt_conflicts = wt_sub.add_parser("conflicts")
    wt_conflicts.add_argument("--path-a", required=True)
    wt_conflicts.add_argument("--path-b", required=True)

    wt_aggregate = wt_sub.add_parser("aggregate")
    wt_aggregate.add_argument("--wave-index", type=int, required=True)
    wt_aggregate.add_argument("--handles", required=True, help="JSON file: list of Worktree Handle")

    p_gates = sub.add_parser("gates")
    p_gates.set_defaults(func=cmd_gates)
    gates_sub = p_gates.add_subparsers(dest="gates_action", required=True)
    gates_detect = gates_sub.add_parser("detect")
    gates_detect.add_argument("--path", default=".")

    p_const = sub.add_parser("constitution")
    p_const.set_defaults(func=cmd_constitution)
    const_sub = p_const.add_subparsers(dest="const_action", required=True)
    const_diff = const_sub.add_parser("diff")
    const_diff.add_argument("--existing", required=True)
    const_diff.add_argument("--proposed", required=True)

    p_trace = sub.add_parser("traceability")
    p_trace.set_defaults(func=cmd_traceability)
    trace_sub = p_trace.add_subparsers(dest="trace_action", required=True)
    trace_add = trace_sub.add_parser("add")
    trace_add.add_argument("--path", default=".spec-master/state.json")
    trace_add.add_argument("--row-file", dest="row_file", default=None)
    trace_add.add_argument("--row-json", dest="row_json", default=None)
    trace_render = trace_sub.add_parser("render")
    trace_render.add_argument("--path", default=".spec-master/state.json")
    trace_render.add_argument("--feature", default=None, help="render only this feature's rows")
    trace_render.add_argument("--output", default=None,
                              help="write Markdown here (e.g. .spec-master/reports/traceability.md)")
    trace_migrate = trace_sub.add_parser("migrate",
                                         help="move inline rows to traceability/features/<id>.json")
    trace_migrate.add_argument("--path", default=".spec-master/state.json")

    p_delta = sub.add_parser("delta", help="ADDED/MODIFIED/REMOVED report for spec/plan/tasks between runs")
    p_delta.set_defaults(func=cmd_delta)
    delta_sub = p_delta.add_subparsers(dest="delta_action", required=True)
    delta_snapshot = delta_sub.add_parser("snapshot")
    delta_snapshot.add_argument("--path", default=".")
    delta_snapshot.add_argument("--state", default=".spec-master/state.json")
    delta_report = delta_sub.add_parser("report")
    delta_report.add_argument("--path", default=".")
    delta_report.add_argument("--state", default=".spec-master/state.json")
    delta_report.add_argument("--format", choices=["json", "markdown"], default="json")
    delta_report.add_argument("--output", default=None, help="with --format markdown: write here")

    p_dashboard = sub.add_parser("dashboard", help="Static local HTML dashboard (.spec-master/reports/dashboard.html)")
    p_dashboard.set_defaults(func=cmd_dashboard)
    dashboard_sub = p_dashboard.add_subparsers(dest="dashboard_action", required=True)
    dashboard_render = dashboard_sub.add_parser("render", help="build + atomically write the dashboard HTML")
    dashboard_render.add_argument("--path", default=".")
    dashboard_render.add_argument("--output", default=None,
                                  help="output file (default .spec-master/reports/dashboard.html; relative to --path)")
    dashboard_render.add_argument("--refresh", type=int, default=None,
                                  help="auto-refresh seconds while a run is active (default 5; 0 disables)")
    dashboard_model = dashboard_sub.add_parser("model", help="print the read-only dashboard model as JSON")
    dashboard_model.add_argument("--path", default=".")

    p_hooks = sub.add_parser("hooks", help="declarative event hooks (.spec-master/hooks.json)")
    p_hooks.set_defaults(func=cmd_hooks)
    hooks_sub = p_hooks.add_subparsers(dest="hooks_action", required=True)
    hooks_init = hooks_sub.add_parser("init")
    hooks_init.add_argument("--path", default=".")
    hooks_init.add_argument("--force", action="store_true")
    hooks_list = hooks_sub.add_parser("list")
    hooks_list.add_argument("--path", default=".")
    hooks_validate = hooks_sub.add_parser("validate")
    hooks_validate.add_argument("--path", default=".")
    hooks_validate.add_argument("--file", default=None, help="validate this hooks.json instead")
    hooks_emit = hooks_sub.add_parser("emit")
    hooks_emit.add_argument("--path", default=".")
    hooks_emit.add_argument("--event", required=True, choices=list(hooks.EVENT_TYPES))
    hooks_emit.add_argument("--payload-json", dest="payload_json", default=None)
    hooks_emit.add_argument("--no-internal", dest="no_internal", action="store_true",
                            help="return internal actions without executing them")
    hooks_firings = hooks_sub.add_parser("firings")
    hooks_firings.add_argument("--path", default=".")
    hooks_firings.add_argument("--limit", type=int, default=None)
    hooks_firings.add_argument("--event", default=None)

    p_tracker = sub.add_parser("tracker")
    p_tracker.set_defaults(func=cmd_tracker)
    tracker_sub = p_tracker.add_subparsers(dest="tracker_action", required=True)
    tracker_orchestrate = tracker_sub.add_parser("orchestrate")
    tracker_orchestrate.add_argument("--path", default=".")

    p_team = sub.add_parser("team")
    p_team.set_defaults(func=cmd_team)
    team_sub = p_team.add_subparsers(dest="team_action", required=True)
    team_sub.add_parser("roles")
    team_sub.add_parser("intake")
    team_sub.add_parser("adopt")
    team_workstreams_parser = team_sub.add_parser("workstreams")
    team_workstreams_parser.add_argument("--file", required=True, help="JSON file: feature objects with optional tasks")
    team_sub.add_parser("routes", help="escalation routing table and ADR triggers")
    team_escalate = team_sub.add_parser("escalate", help="route an escalation per the role playbooks")
    team_escalate.add_argument("--path", default=".")
    team_escalate.add_argument("--kind", required=True, choices=sorted(team_model.ESCALATION_ROUTES))
    team_escalate.add_argument("--raised-by", dest="raised_by", required=True)
    team_escalate.add_argument("--feature", default=None)
    team_escalate.add_argument("--summary", default=None)
    team_resolve = team_sub.add_parser("resolve", help="record the decision that resolved an escalation")
    team_resolve.add_argument("--path", default=".")
    team_resolve.add_argument("--kind", required=True)
    team_resolve.add_argument("--raised-by", dest="raised_by", required=True)
    team_resolve.add_argument("--decision", required=True)
    team_resolve.add_argument("--decided-by", dest="decided_by", default=None,
                              help="defaults to the first hop of the escalation route")
    team_resolve.add_argument("--rationale", default=None)
    team_resolve.add_argument("--feature", default=None)
    team_resolve.add_argument("--title", default=None)
    team_resolve.add_argument("--alternative", action="append", default=None,
                              help="a rejected alternative (repeatable)")
    team_resolve.add_argument("--adr-trigger", dest="adr_trigger", action="append", default=None,
                              help="ADR trigger id (repeatable); see `team routes`")
    team_decisions = team_sub.add_parser("decisions", help="past decisions from the knowledge graph")
    team_decisions.add_argument("--path", default=".")
    team_decisions.add_argument("--role", default=None)
    team_decisions.add_argument("--feature", default=None)
    team_decisions.add_argument("--limit", type=int, default=None)

    p_ws = sub.add_parser("workstreams")
    p_ws.set_defaults(func=cmd_workstreams)
    ws_sub = p_ws.add_subparsers(dest="workstreams_action", required=True)

    ws_review = ws_sub.add_parser("review")
    ws_review.add_argument("--file", required=True, help="workstreams.json (built by `team workstreams`)")
    ws_review.add_argument("--package", required=True)
    ws_review.add_argument("--reviewer", required=True, help="MUST match the package's own assigned reviewer_agent")
    ws_review.add_argument("--status", required=True, choices=["APPROVED", "REJECTED"])
    ws_review.add_argument("--reason", default=None, help="required when --status REJECTED")

    ws_integrate = ws_sub.add_parser("integrate")
    ws_integrate.add_argument("--file", required=True, help="workstreams.json (built by `team workstreams`)")
    ws_integrate.add_argument("--package", required=True)
    ws_integrate.add_argument("--status", required=True, choices=["APPROVED", "REJECTED"])
    ws_integrate.add_argument("--reason", default=None, help="required when --status REJECTED")

    ws_aggregate = ws_sub.add_parser("aggregate")
    ws_aggregate.add_argument("--wave-index", type=int, required=True)
    ws_aggregate.add_argument("--handles", required=True, help="JSON file: list of Worktree Handle")
    ws_aggregate.add_argument("--packages", required=True, help="workstreams.json (built by `team workstreams`)")

    p_risk = sub.add_parser("risk", help="risk-adaptive ceremony: tier = max(scope, sensitivity hooks, override)")
    p_risk.set_defaults(func=cmd_risk)
    risk_sub = p_risk.add_subparsers(dest="risk_action", required=True)
    risk_classify = risk_sub.add_parser("classify", help="classify a feature (intake or pre_implement)")
    risk_classify.add_argument("--path", default=".", help="project root")
    risk_classify.add_argument("--feature", required=True)
    risk_classify.add_argument("--stage", choices=list(risk_profile.STAGES), default="intake")
    risk_classify.add_argument("--state", default=None, help="state.json (default: <path>/.spec-master/state.json)")
    risk_classify.add_argument("--paths", default=None, help="comma-separated path hints (files the change touches)")
    risk_classify.add_argument("--save", action="store_true",
                               help="persist feature.risk in state and emit the feature.* hook event")
    risk_override = risk_sub.add_parser("override", help="force a HIGHER tier (logged as a calibration signal)")
    risk_override.add_argument("--path", default=".", help="project root")
    risk_override.add_argument("--feature", required=True)
    risk_override.add_argument("--tier", required=True, type=str.upper, choices=list(risk_profile.TIER_ORDER))
    risk_override.add_argument("--reason", required=True)
    risk_override.add_argument("--by", default="user")
    risk_override.add_argument("--state", default=None, help="state.json (default: <path>/.spec-master/state.json)")
    risk_profiles = risk_sub.add_parser("profiles", help="ceremony profiles + effective scope thresholds")
    risk_profiles.add_argument("--path", default=".", help="project root")
    risk_wp = risk_sub.add_parser("work-packages", help="role work packages for an L/XL feature")
    risk_wp.add_argument("--feature", required=True)
    risk_wp.add_argument("--tier", required=True, type=str.upper, choices=list(risk_profile.TIER_ORDER))

    p_metrics = sub.add_parser("metrics")
    p_metrics.set_defaults(func=cmd_metrics)
    metrics_sub = p_metrics.add_subparsers(dest="metrics_action", required=True)
    metrics_record = metrics_sub.add_parser("record-round")
    metrics_record.add_argument("--round-id", required=True)
    metrics_record.add_argument("--phase", required=True)
    metrics_record.add_argument("--started-at", required=True)
    metrics_record.add_argument("--ended-at", required=True)
    metrics_record.add_argument("--input-tokens", type=int, default=0)
    metrics_record.add_argument("--output-tokens", type=int, default=0)
    metrics_record.add_argument("--work-packages-completed", type=int, default=0)
    metrics_record.add_argument("--features-completed", type=int, default=0)
    metrics_record.add_argument("--notes", default=None)
    metrics_record.add_argument("--feature-id", default=None, help="attribute the round to a feature (calibration)")
    metrics_record.add_argument("--tier", default=None, type=str.upper, choices=list(metrics.TIERS),
                                help="ceremony tier of the feature (calibration)")
    metrics_record.add_argument("--source", default=None, choices=["manual", metrics.UNVERIFIED_SOURCE],
                                help="typed-in numbers (manual with 0 tokens is stored as manual-unverified); "
                                     "host-measured rows come from `telemetry ingest`")
    _round_output_args(metrics_record)
    metrics_summary = metrics_sub.add_parser("summarize")
    metrics_summary.add_argument("--file", required=True, help="JSON file: list of round metrics")
    metrics_calibrate = metrics_sub.add_parser("calibrate", help="per-tier estimated vs actual cost, drift, thresholds")
    metrics_calibrate.add_argument("--path", default=".", help="project root")
    metrics_calibrate.add_argument("--rounds", default=None,
                                   help="rounds JSON (default: <path>/.spec-master/metrics/rounds.json)")
    metrics_calibrate.add_argument("--state", default=None, help="state.json (default: <path>/.spec-master/state.json)")
    metrics_calibrate.add_argument("--window", type=int, default=calibration.DEFAULT_WINDOW,
                                   help="consecutive same-direction features that count as drift")
    metrics_calibrate.add_argument("--apply", action="store_true",
                                   help="write .spec-master/risk/thresholds.json and log the calibration")
    metrics_calibrate.add_argument("--require-measured", dest="require_measured", action="store_true",
                                   help="ignore every round without measured tokens, even in a v1-only file")
    metrics_export_p = metrics_sub.add_parser(
        "export", help="export rounds.json as OTLP/JSON metrics or JSONL (validates first)")
    metrics_export_p.add_argument("--path", default=".", help="project root")
    metrics_export_p.add_argument("--rounds", default=None,
                                  help="rounds file (default: <path>/.spec-master/metrics/rounds.json)")
    metrics_export_p.add_argument("--format", choices=metrics_export.FORMATS, default="otlp")
    metrics_export_p.add_argument("--output", default=None, help="write here instead of stdout")
    metrics_validate_p = metrics_sub.add_parser(
        "validate", help="validate rounds.json against schemas/metrics-round.schema.json")
    metrics_validate_p.add_argument("--path", default=".", help="project root")
    metrics_validate_p.add_argument("--rounds", default=None,
                                    help="rounds file (default: <path>/.spec-master/metrics/rounds.json)")

    p_telemetry = sub.add_parser("telemetry", help="host-measured usage (Claude Code transcripts, claude -p JSON)")
    p_telemetry.set_defaults(func=cmd_telemetry)
    telemetry_sub = p_telemetry.add_subparsers(dest="telemetry_action", required=True)
    telemetry_locate = telemetry_sub.add_parser("locate", help="this project's session transcripts, newest first")
    telemetry_locate.add_argument("--path", default=".", help="project root (where the host was launched)")
    telemetry_locate.add_argument("--include-subagents", dest="include_subagents", action="store_true")
    telemetry_ingest = telemetry_sub.add_parser(
        "ingest", help="build a round from host usage (never message content); --append writes it")
    telemetry_ingest.add_argument("--path", default=".", help="project root (where the host was launched)")
    ingest_from = telemetry_ingest.add_mutually_exclusive_group(required=True)
    ingest_from.add_argument("--latest", action="store_true", help="the newest session transcript of --path")
    ingest_from.add_argument("--transcript", action="append", help="a session transcript (repeatable)")
    ingest_from.add_argument("--headless-json", dest="headless_json",
                             help="a `claude -p --output-format json` result file")
    telemetry_ingest.add_argument("--main-only", dest="main_only", action="store_true",
                                  help="leave the session's subagent transcripts out")
    telemetry_ingest.add_argument("--since", default=None, help="window start (ISO 8601), e.g. the round start")
    telemetry_ingest.add_argument("--until", default=None, help="window end (ISO 8601)")
    telemetry_ingest.add_argument("--started-at", dest="started_at", default=None,
                                  help="round bounds; a headless result needs one of them")
    telemetry_ingest.add_argument("--ended-at", dest="ended_at", default=None)
    telemetry_ingest.add_argument("--round-id", dest="round_id", required=True)
    telemetry_ingest.add_argument("--phase", required=True)
    telemetry_ingest.add_argument("--feature-id", dest="feature_id", default=None)
    telemetry_ingest.add_argument("--tier", default=None, type=str.upper, choices=list(metrics.TIERS))
    telemetry_ingest.add_argument("--lane", default=None, choices=["patch", "standard", "critical"])
    telemetry_ingest.add_argument("--notes", default=None)
    telemetry_ingest.add_argument("--work-packages-completed", dest="work_packages_completed", type=int, default=0)
    telemetry_ingest.add_argument("--features-completed", dest="features_completed", type=int, default=0)
    _round_output_args(telemetry_ingest)

    p_baseline = sub.add_parser("baseline", help="measured baseline: Spec Master arm vs a direct agentic arm")
    p_baseline.set_defaults(func=cmd_baseline)
    baseline_sub = p_baseline.add_subparsers(dest="baseline_action", required=True)
    for action, text in (("plan", "the run matrix and worst-case spend; executes nothing"),
                         ("run", "execute the plan with claude -p (SPENDS MONEY: needs --yes)")):
        baseline_action = baseline_sub.add_parser(action, help=text)
        baseline_action.add_argument("--cases", required=True, help="cases JSON file (see lib/baseline.py)")
        baseline_action.add_argument("--arms", default="specmaster,direct", help="comma-separated arm names")
        baseline_action.add_argument("--runs", type=int, default=3)
        baseline_action.add_argument("--max-budget-usd", dest="max_budget_usd", type=float, required=True)
        baseline_action.add_argument("--model", default=None)
        baseline_action.add_argument("--claude", default="claude", help="the claude executable")
        if action == "run":
            baseline_action.add_argument("--out", required=True, help="results directory")
            baseline_action.add_argument("--timeout", type=float, default=3600.0, help="seconds per run")
            baseline_action.add_argument("--yes", action="store_true",
                                         help="the user explicitly agreed to spend the worst-case budget")
    baseline_summary = baseline_sub.add_parser("summarize", help="medians, cost CV, success and overhead vs direct")
    baseline_summary.add_argument("--out", required=True, help="results directory of a run")

    p_bundle = sub.add_parser("bundle", help="portable single-file bundles for chat UIs without tools")
    p_bundle.set_defaults(func=cmd_bundle)
    bundle_sub = p_bundle.add_subparsers(dest="bundle_action", required=True)
    bundle_build = bundle_sub.add_parser("build", help="build a pasteable Markdown bundle for one phase")
    bundle_build.add_argument("--path", default=".", help="project root")
    bundle_build.add_argument("--state", default=None, help="state file (default: <path>/.spec-master/state.json)")
    bundle_build.add_argument("--feature", default=None, help="feature id (optional only for --phase constitution)")
    bundle_build.add_argument("--phase", choices=web_bundle.PHASES, default=None,
                              help="default: the feature's first phase not PASSED/SKIPPED")
    bundle_build.add_argument("--budget", type=int, default=context_budget.DEFAULT_TOKEN_BUDGET,
                              help="estimated token budget for the bundle")
    bundle_build.add_argument("--output", default=None,
                              help="default: <path>/.spec-master/bundles/<feature>-<phase>.md")
    bundle_build.add_argument("--stdout", action="store_true", help="print the Markdown instead of writing it")
    bundle_build.add_argument("--no-timestamp", dest="no_timestamp", action="store_true",
                              help="omit the generated-at line (byte-for-byte reproducible output)")

    p_graph = sub.add_parser("graph")
    p_graph.set_defaults(func=cmd_graph)
    graph_sub = p_graph.add_subparsers(dest="graph_action", required=True)
    
    g_validate = graph_sub.add_parser("validate")
    g_validate.add_argument("--path", default=".")
    
    g_stats = graph_sub.add_parser("stats")
    g_stats.add_argument("--path", default=".")
    
    g_neighbors = graph_sub.add_parser("neighbors")
    g_neighbors.add_argument("node_id")
    g_neighbors.add_argument("--depth", type=int, default=2)
    g_neighbors.add_argument("--relations", default=None)
    g_neighbors.add_argument("--path", default=".")
    
    g_stale = graph_sub.add_parser("stale")
    g_stale.add_argument("--path", default=".")
    
    g_rebuild = graph_sub.add_parser("rebuild")
    g_rebuild.add_argument("--path", default=".")

    g_enrich = graph_sub.add_parser("enrich-discovery")
    g_enrich.add_argument("--path", default=".")

    g_snapshot = graph_sub.add_parser("snapshot")
    g_snapshot.add_argument("--path", default=".")
    g_snapshot.add_argument("--name", default="latest")

    g_drift = graph_sub.add_parser("drift")
    g_drift.add_argument("--path", default=".")
    g_drift.add_argument("--previous", required=True)
    
    g_health = graph_sub.add_parser("health")
    g_health.add_argument("--path", default=".")

    g_maps = graph_sub.add_parser("maps")
    g_maps.add_argument("--path", default=".")
    g_maps.add_argument("--map-type", dest="map_type", default="system",
                         choices=["system", "node", "dependencies"])
    g_maps.add_argument("--node-id", dest="node_id", default=None)
    g_maps.add_argument("--depth", type=int, default=2)
    g_maps.add_argument("--relation", default="DEPENDS_ON")

    p_knowledge = sub.add_parser("knowledge")
    p_knowledge.set_defaults(func=cmd_knowledge)
    knowledge_sub = p_knowledge.add_subparsers(dest="knowledge_action", required=True)

    k_list = knowledge_sub.add_parser("list")
    k_list.add_argument("--role", default=None)
    k_list.add_argument("--category", default=None)
    k_list.add_argument("--tag", default=None)
    k_list.add_argument("--knowledge-root", dest="knowledge_root", default=None)

    k_get = knowledge_sub.add_parser("get")
    k_get.add_argument("id")
    k_get.add_argument("--knowledge-root", dest="knowledge_root", default=None)

    k_search = knowledge_sub.add_parser("search")
    k_search.add_argument("query")
    k_search.add_argument("--knowledge-root", dest="knowledge_root", default=None)

    k_for_role = knowledge_sub.add_parser("for-role")
    k_for_role.add_argument("--role", required=True)
    k_for_role.add_argument("--limit", type=int, default=8)
    k_for_role.add_argument("--knowledge-root", dest="knowledge_root", default=None)
    k_for_role.add_argument("--path", default=None,
                            help="project root: also return past decisions involving this role")
    k_for_role.add_argument("--decision-limit", dest="decision_limit", type=int, default=5)

    k_route = knowledge_sub.add_parser("route")
    k_route.add_argument("--role", required=True)
    k_route.add_argument("--keywords", default=None, help="comma-separated")
    k_route.add_argument("--tech-stacks", dest="tech_stacks", default=None, help="comma-separated")
    k_route.add_argument("--limit", type=int, default=8)
    k_route.add_argument("--knowledge-root", dest="knowledge_root", default=None)

    k_stats = knowledge_sub.add_parser("stats")
    k_stats.add_argument("--knowledge-root", dest="knowledge_root", default=None)

    k_validate = knowledge_sub.add_parser("validate")
    k_validate.add_argument("--knowledge-root", dest="knowledge_root", default=None)

    p_policy = sub.add_parser("policy")
    p_policy.set_defaults(func=cmd_policy)
    policy_sub = p_policy.add_subparsers(dest="policy_action", required=True)
    policy_preflight = policy_sub.add_parser("preflight")
    policy_preflight.add_argument("command", nargs="+")

    p_budget = sub.add_parser("budget")
    p_budget.set_defaults(func=cmd_budget)
    budget_sub = p_budget.add_subparsers(dest="budget_action", required=True)
    budget_estimate = budget_sub.add_parser("estimate")
    budget_estimate.add_argument("text")
    budget_file = budget_sub.add_parser("file")
    budget_file.add_argument("--files", required=True, help="comma-separated paths")
    budget_file.add_argument("--token-budget", type=int, default=context_budget.DEFAULT_TOKEN_BUDGET)
    budget_file.add_argument("--with-content", dest="with_content", action="store_true",
                             help="also return the content of the selected files")

    p_runtime = sub.add_parser("runtime")
    p_runtime.set_defaults(func=cmd_runtime)
    runtime_sub = p_runtime.add_subparsers(dest="runtime_action", required=True)
    runtime_contract_parser = runtime_sub.add_parser("contract")
    runtime_contract_parser.add_argument("--runtime-type", choices=["hosted", "hybrid"], default="hybrid")

    p_lane = sub.add_parser("lane", help="lane triage: how much process a change needs (opt-in lane flow)")
    p_lane.set_defaults(func=cmd_lane)
    lane_sub = p_lane.add_subparsers(dest="lane_action", required=True)
    lane_triage = lane_sub.add_parser("triage", help="decide patch / standard / critical from paths and repo signals")
    lane_triage.add_argument("--path", default=".", help="project root")
    lane_triage.add_argument("--intent", required=True, help="the user's request, verbatim")
    lane_triage.add_argument("--paths", default="", help="comma-separated files the change will touch")
    lane_triage.add_argument("--confirm", action="append", help="a question's signal the user confirmed")
    lane_triage.add_argument("--deny", action="append", help="a question's signal the user denied")
    lane_triage.add_argument("--unresolved", type=int, default=0, help="open UNRESOLVED items")
    lane_triage.add_argument("--lane", choices=["patch", "standard", "critical"], default=None,
                             help="requested lane (can only raise)")

    p_step = sub.add_parser("step", help="lane flow steps: next, begin, end, widen, pause, resume")
    p_step.set_defaults(func=cmd_step)
    step_sub = p_step.add_subparsers(dest="step_action", required=True)
    step_next = step_sub.add_parser("next", help="the card for the current step")
    step_next.add_argument("--path", default=".")
    step_begin = step_sub.add_parser("begin", help="open a patch change (other lanes go to the full cycle)")
    step_begin.add_argument("--path", default=".")
    step_begin.add_argument("--intent", required=True, help="the user's request, verbatim")
    step_begin.add_argument("--paths", default="", help="comma-separated files the change will touch")
    step_begin.add_argument("--lane", choices=["patch", "standard", "critical"], default="patch")
    step_begin.add_argument("--kind", choices=["change", "bugfix"], default="change")
    step_begin.add_argument("--regression-test", dest="regression_test", default=None)
    step_begin.add_argument("--test-command", dest="test_command", default=None)
    step_begin.add_argument("--confirm", action="append")
    step_begin.add_argument("--deny", action="append")
    step_begin.add_argument("--unresolved", type=int, default=0)
    step_end = step_sub.add_parser("end", help="verify the change; PASSED only with evidence")
    step_end.add_argument("--path", default=".")
    step_end.add_argument("--change", default=None)
    step_end.add_argument("--dry-run", dest="dry_run", action="store_true", help="report without changing the record")
    step_end.add_argument("--no-gates", dest="no_gates", action="store_true",
                          help="skip running the gates for quick feedback (the change cannot pass this way)")
    step_widen = step_sub.add_parser("widen", help="add files to the change (re-triages; the lane may go up)")
    step_widen.add_argument("--path", default=".")
    step_widen.add_argument("--paths", required=True)
    step_widen.add_argument("--change", default=None)
    step_pause = step_sub.add_parser("pause", help="stop the running change on purpose")
    step_pause.add_argument("--path", default=".")
    step_pause.add_argument("--change", default=None)
    step_pause.add_argument("--reason", default=None)
    step_resume = step_sub.add_parser("resume", help="resume a paused change")
    step_resume.add_argument("--path", default=".")
    step_resume.add_argument("--change", required=True)

    p_doctor = sub.add_parser("doctor", help="harness self-checks for CI (conformance, budgets, records)")
    p_doctor.set_defaults(func=cmd_doctor)
    doctor_sub = p_doctor.add_subparsers(dest="doctor_action", required=True)
    doctor_run = doctor_sub.add_parser("run")
    doctor_run.add_argument("--path", default=".", help="project root")
    doctor_run.add_argument("--errors-only", dest="errors_only", action="store_true")

    p_harness = sub.add_parser("harness", help="wire the host (hooks) to the kernel")
    p_harness.set_defaults(func=cmd_harness)
    harness_sub = p_harness.add_subparsers(dest="harness_action", required=True)
    harness_hooks = harness_sub.add_parser("install-hooks", help="merge the hookd entries into .claude/settings.json")
    harness_hooks.add_argument("--project", default=".")
    harness_hooks.add_argument("--engine", default=None, help="engine directory (default: this one)")
    harness_hooks.add_argument("--mode", choices=["audit", "block"], default=None,
                               help="also write hooks_mode to .spec-master/policy.json")
    harness_hooks.add_argument("--dry-run", dest="dry_run", action="store_true")
    harness_mode = harness_sub.add_parser("mode", help="set hooks_mode only (hooks installed by the plugin)")
    harness_mode.add_argument("--project", default=".")
    harness_mode.add_argument("--mode", choices=["audit", "block"], required=True)
    harness_mode.add_argument("--dry-run", dest="dry_run", action="store_true")

    p_evals = sub.add_parser("evals")
    p_evals.set_defaults(func=cmd_evals)
    evals_sub = p_evals.add_subparsers(dest="evals_action", required=True)
    evals_sub.add_parser("run")

    return parser


def main(argv: list[str] | None = None) -> int:
    global PRETTY
    argv = list(sys.argv[1:] if argv is None else argv)
    PRETTY = "--pretty" in argv or os.environ.get("SPEC_MASTER_PRETTY", "") not in ("", "0")
    argv = [arg for arg in argv if arg != "--pretty"]
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (state_mod.StateError, ValueError) as exc:
        payload = {"error": str(exc)}
        payload.update(getattr(exc, "payload", None) or {})
        _print_json(payload)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
