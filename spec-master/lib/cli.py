#!/usr/bin/env python3
"""spec-master orchestration core CLI.

Model-agnostic entrypoint: any adapter (Claude Code, Copilot, Codex, Qwen-compatible shells) shells
out to this CLI for every *structural* decision, so the same tested logic
backs every platform. Semantic work (writing specs, resolving ambiguity)
stays in the calling agent's prompt.

    python3 cli.py <command> <subcommand> [options]

All output is JSON on stdout unless the subcommand renders Markdown
(`traceability render`), in which case Markdown is printed directly.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import constitution_diff  # noqa: E402
import discovery  # noqa: E402
import feature_model  # noqa: E402
import fingerprint  # noqa: E402
import git_strategy  # noqa: E402
import metrics  # noqa: E402
import quality_gates  # noqa: E402
import state as state_mod  # noqa: E402
import team_model  # noqa: E402
import traceability  # noqa: E402


def _print_json(payload) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False))


def _load_json_file(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def cmd_state(args: argparse.Namespace) -> int:
    if args.state_action == "init":
        s = state_mod.init(args.path, context=args.context, workflow=args.workflow)
        _print_json(s)
        return 0
    if args.state_action == "show":
        s = state_mod.load(args.path)
        _print_json(state_mod.summarize(s) if args.summary else s)
        return 0
    if args.state_action == "set-workflow":
        s = state_mod.load(args.path)
        state_mod.set_workflow(s, args.workflow)
        state_mod.save(args.path, s)
        _print_json(s)
        return 0
    if args.state_action == "set-status":
        s = state_mod.load(args.path)
        state_mod.transition_workflow_status(s, args.status)
        state_mod.save(args.path, s)
        _print_json(s)
        return 0
    if args.state_action == "upsert-feature":
        s = state_mod.load(args.path)
        feature = _load_json_file(args.feature_file) if args.feature_file else json.loads(args.feature_json)
        f = state_mod.upsert_feature(s, feature)
        state_mod.save(args.path, s)
        _print_json(f)
        return 0
    if args.state_action == "transition":
        s = state_mod.load(args.path)
        f = state_mod.transition_phase(s, args.feature, args.phase, args.status)
        state_mod.save(args.path, s)
        _print_json(f)
        return 0
    if args.state_action == "analyze-cycle":
        s = state_mod.load(args.path)
        result = state_mod.analyze_cycle(s, args.feature, args.action)
        state_mod.save(args.path, s)
        _print_json(result)
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


def cmd_constitution(args: argparse.Namespace) -> int:
    if args.const_action == "diff":
        result = constitution_diff.diff_files(args.existing, args.proposed)
        _print_json(result)
        return 0
    raise SystemExit(f"unknown constitution action: {args.const_action}")


def cmd_traceability(args: argparse.Namespace) -> int:
    if args.trace_action == "add":
        s = state_mod.load(args.path)
        row = _load_json_file(args.row_file) if args.row_file else json.loads(args.row_json)
        traceability.add_row(s, row)
        state_mod.save(args.path, s)
        _print_json(row)
        return 0
    if args.trace_action == "render":
        s = state_mod.load(args.path)
        print(traceability.render(s))
        return 0
    raise SystemExit(f"unknown traceability action: {args.trace_action}")


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
    raise SystemExit(f"unknown team action: {args.team_action}")


def cmd_metrics(args: argparse.Namespace) -> int:
    if args.metrics_action == "record-round":
        _print_json(
            metrics.record_round(
                round_id=args.round_id,
                phase=args.phase,
                started_at=args.started_at,
                ended_at=args.ended_at,
                input_tokens=args.input_tokens,
                output_tokens=args.output_tokens,
                work_packages_completed=args.work_packages_completed,
                features_completed=args.features_completed,
                notes=args.notes,
            )
        )
        return 0
    if args.metrics_action == "summarize":
        rounds = _load_json_file(args.file)
        _print_json(metrics.summarize(rounds))
        return 0
    raise SystemExit(f"unknown metrics action: {args.metrics_action}")


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

    s_upsert = state_sub.add_parser("upsert-feature")
    s_upsert.add_argument("--path", default=".spec-master/state.json")
    s_upsert.add_argument("--feature-file", dest="feature_file", default=None)
    s_upsert.add_argument("--feature-json", dest="feature_json", default=None)

    s_trans = state_sub.add_parser("transition")
    s_trans.add_argument("--path", default=".spec-master/state.json")
    s_trans.add_argument("--feature", required=True)
    s_trans.add_argument("--phase", required=True)
    s_trans.add_argument("--status", required=True)

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

    p_team = sub.add_parser("team")
    p_team.set_defaults(func=cmd_team)
    team_sub = p_team.add_subparsers(dest="team_action", required=True)
    team_sub.add_parser("roles")
    team_sub.add_parser("intake")
    team_sub.add_parser("adopt")
    team_workstreams = team_sub.add_parser("workstreams")
    team_workstreams.add_argument("--file", required=True, help="JSON file: feature objects with optional tasks")

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
    metrics_summary = metrics_sub.add_parser("summarize")
    metrics_summary.add_argument("--file", required=True, help="JSON file: list of round metrics")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (state_mod.StateError, ValueError) as exc:
        _print_json({"error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
