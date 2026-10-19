"""`dispatch` command group: manifest, prepare, result, status, aggregate.

`register` imports only argparse's parser objects it is handed; the heavy
modules (`dispatch`, `worktree`) load inside `run`, so `cli.build_parser()` stays lazy.
"""
from __future__ import annotations

import json


def register(sub) -> None:
    p = sub.add_parser("dispatch", help="multi-agent dispatch: per-wave manifest for host subagents")
    p.set_defaults(func=run)
    actions = p.add_subparsers(dest="dispatch_action", required=True)

    def common(parser, wave=True):
        parser.add_argument("--feature", required=True)
        if wave:
            parser.add_argument("--wave", type=int, required=True)
        parser.add_argument("--path", default=".", help="project root (default: .)")

    manifest = actions.add_parser("manifest")
    common(manifest)
    for parser in (manifest, actions.add_parser("prepare")):
        if parser is not manifest:
            common(parser)
            parser.add_argument("--phase", choices=["implement", "review"], default="implement")
        parser.add_argument("--max-agents", type=int, default=None, help="agent cap per batch, 1..8 (default 4)")
        parser.add_argument("--lane", default="standard", help="standard (default), critical; patch is refused")
        parser.add_argument("--force-lane", default=None, help="reason to dispatch outside Standard/Critical")
    result = actions.add_parser("result")
    common(result)
    result.add_argument("--package", required=True)
    result.add_argument("--role", default="sm-implement", choices=["sm-spec", "sm-implement", "sm-review"])
    result.add_argument("--agent-key", default=None)
    result.add_argument("--agent-id", default=None)
    group = result.add_mutually_exclusive_group(required=True)
    group.add_argument("--text-file", help="file with the subagent's final message")
    group.add_argument("--text", help="the subagent's final message")
    common(actions.add_parser("status"))
    common(actions.add_parser("aggregate"))


def run(args) -> int:
    import dispatch
    action, root = args.dispatch_action, args.path
    if action == "manifest":
        out = dispatch.build_manifest(root, args.feature, args.wave, args.max_agents, lane=args.lane,
                                      force_lane=args.force_lane)
    elif action == "prepare":
        out = dispatch.prepare(root, args.feature, args.wave, args.phase, args.max_agents, lane=args.lane,
                               force_lane=args.force_lane)
    elif action == "result":
        if args.text_file:
            with open(args.text_file, "r", encoding="utf-8") as fh:
                text = fh.read()
        else:
            text = args.text
        out = dispatch.record_result(root, args.feature, args.wave, args.package, text, role=args.role,
                                     agent_key=args.agent_key, agent_id=args.agent_id)
    elif action == "status":
        out = dispatch.status(root, args.feature, args.wave)
    else:
        out = dispatch.aggregate(root, args.feature, args.wave)
    print(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    return 0
