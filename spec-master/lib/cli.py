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

from graph import ontology as graph_ontology
from graph import maps as graph_maps
from graph import health as graph_health
from graph.store import FileGraphStore, graph_from_dict
from graph.validation import validate_graph

from knowledge.manifest import KnowledgeManifest
from knowledge.router import KnowledgeRouter
from knowledge.validation import validate_manifest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import constitution_diff  # noqa: E402
import context_budget  # noqa: E402
import discovery  # noqa: E402
import evals  # noqa: E402
import feature_model  # noqa: E402
import fingerprint  # noqa: E402
import git_strategy  # noqa: E402
import metrics  # noqa: E402
import quality_gates  # noqa: E402
import state as state_mod  # noqa: E402
import team_model  # noqa: E402
import tool_policy  # noqa: E402
import traceability  # noqa: E402
import runtime_contract  # noqa: E402


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
            p = Path(path)
            items.append({"id": str(p), "content": p.read_text(encoding="utf-8") if p.exists() else ""})
        _print_json(context_budget.budget_items(items, token_budget=args.token_budget))
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
        _print_json({
            "modules": [m.to_dict() for m in modules],
            "budget": router.budget_summary(modules),
        })
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

    p_runtime = sub.add_parser("runtime")
    p_runtime.set_defaults(func=cmd_runtime)
    runtime_sub = p_runtime.add_subparsers(dest="runtime_action", required=True)
    runtime_contract_parser = runtime_sub.add_parser("contract")
    runtime_contract_parser.add_argument("--runtime-type", choices=["hosted", "hybrid"], default="hybrid")

    p_evals = sub.add_parser("evals")
    p_evals.set_defaults(func=cmd_evals)
    evals_sub = p_evals.add_subparsers(dest="evals_action", required=True)
    evals_sub.add_parser("run")

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
