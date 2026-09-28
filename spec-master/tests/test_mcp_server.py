import _pathfix  # noqa: F401

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MCP_DIR = Path(__file__).resolve().parent.parent / "mcp"
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

import hooks  # noqa: E402
import spec_master_mcp as mcp  # noqa: E402

SERVER_SCRIPT = MCP_DIR / "spec_master_mcp.py"


def _request(msg_id, method, params=None):
    message = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


class _ServerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.server = mcp.Server(project_root=cls._tmp.name, timeout=30)
        cls.tools = {t["name"]: t for t in cls.server.list_tools()["tools"]}

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def props(self, tool_name):
        return self.tools[tool_name]["inputSchema"]["properties"]


class ProtocolTest(_ServerCase):
    def test_initialize_echoes_a_supported_version(self):
        response = self.server.handle(_request(1, "initialize", {
            "protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}))
        result = response["result"]
        self.assertEqual(response["id"], 1)
        self.assertEqual(result["protocolVersion"], "2025-03-26")
        self.assertEqual(result["capabilities"], {"tools": {"listChanged": False}})
        self.assertEqual(result["serverInfo"]["name"], "spec-master")
        self.assertIn("version", result["serverInfo"])
        self.assertIn(self.server.project_root, result["instructions"])

    def test_initialize_falls_back_to_latest_for_unknown_version(self):
        result = self.server.handle(_request("a", "initialize", {"protocolVersion": "1999-01-01"}))["result"]
        self.assertEqual(result["protocolVersion"], mcp.LATEST_PROTOCOL_VERSION)

    def test_ping(self):
        self.assertEqual(self.server.handle(_request(7, "ping")), {"jsonrpc": "2.0", "id": 7, "result": {}})

    def test_notifications_get_no_reply(self):
        self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "method": "notifications/cancelled",
                                              "params": {"requestId": 3}}))
        self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "method": "no/such/method"}))

    def test_client_responses_are_ignored(self):
        self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "id": 5, "result": {}}))

    def test_unknown_method(self):
        response = self.server.handle(_request(2, "resources/list"))
        self.assertEqual(response["error"]["code"], mcp.METHOD_NOT_FOUND)
        self.assertEqual(response["id"], 2)

    def test_invalid_requests(self):
        self.assertEqual(self.server.handle({"id": 1, "method": "ping"})["error"]["code"], mcp.INVALID_REQUEST)
        self.assertEqual(self.server.handle("ping")["error"]["code"], mcp.INVALID_REQUEST)
        bad_id = self.server.handle({"jsonrpc": "2.0", "id": True, "method": "ping"})
        self.assertEqual(bad_id["error"]["code"], mcp.INVALID_REQUEST)
        self.assertIsNone(bad_id["id"])

    def test_invalid_params(self):
        self.assertEqual(self.server.handle(_request(3, "tools/list", [1]))["error"]["code"], mcp.INVALID_PARAMS)
        self.assertEqual(self.server.handle(_request(4, "tools/call", {"arguments": {}}))["error"]["code"],
                         mcp.INVALID_PARAMS)
        bad_args = self.server.handle(_request(5, "tools/call", {"name": "state_show", "arguments": [1]}))
        self.assertEqual(bad_args["error"]["code"], mcp.INVALID_PARAMS)

    def test_parse_error(self):
        response = self.server.handle_line("{not json")
        self.assertEqual(response["error"]["code"], mcp.PARSE_ERROR)
        self.assertIsNone(response["id"])

    def test_batches(self):
        responses = self.server.handle([
            _request(1, "ping"),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            _request(2, "nope"),
        ])
        self.assertEqual([r["id"] for r in responses], [1, 2])
        self.assertEqual(responses[1]["error"]["code"], mcp.METHOD_NOT_FOUND)
        self.assertIsNone(self.server.handle([{"jsonrpc": "2.0", "method": "notifications/initialized"}]))
        self.assertEqual(self.server.handle([])["error"]["code"], mcp.INVALID_REQUEST)

    def test_unknown_tool_is_a_tool_error_not_a_protocol_error(self):
        response = self.server.handle(_request(9, "tools/call", {"name": "no_such_tool", "arguments": {}}))
        self.assertTrue(response["result"]["isError"])
        self.assertIn("unknown tool", response["result"]["content"][0]["text"])

    def test_unknown_argument_is_a_tool_error(self):
        response = self.server.handle(_request(10, "tools/call", {
            "name": "state_show", "arguments": {"bogus": 1}}))
        self.assertTrue(response["result"]["isError"])
        self.assertIn("bogus", response["result"]["content"][0]["text"])

    def test_module_level_handle(self):
        self.assertEqual(mcp.handle(_request(1, "ping"))["result"], {})

    def test_timeout_is_a_tool_error(self):
        server = mcp.Server(project_root=self._tmp.name, timeout=0.001)
        result = server.call_tool("team_roles", {})
        self.assertTrue(result["isError"])
        self.assertIn("timed out", result["content"][0]["text"])

    def test_timeout_env(self):
        with mock.patch.dict("os.environ", {"SPEC_MASTER_MCP_TIMEOUT": "7.5"}):
            self.assertEqual(mcp.Server(project_root=self._tmp.name).timeout, 7.5)
        with mock.patch.dict("os.environ", {"SPEC_MASTER_MCP_TIMEOUT": "soon"}):
            self.assertEqual(mcp.Server(project_root=self._tmp.name).timeout, mcp.DEFAULT_TIMEOUT)

    def test_unloadable_cli_still_serves_the_protocol(self):
        def broken():
            raise ImportError("boom")

        server = mcp.Server(project_root=self._tmp.name, parser_factory=broken)
        self.assertEqual(server.list_tools(), {"tools": []})
        self.assertIn("boom", server.initialize({})["instructions"])
        result = server.call_tool("state_show", {})
        self.assertTrue(result["isError"])
        self.assertIn("boom", result["content"][0]["text"])


class ToolListTest(_ServerCase):
    def test_tools_list_via_handle(self):
        names = {t["name"] for t in self.server.handle(_request(1, "tools/list"))["result"]["tools"]}
        for expected in ("state_show", "state_init", "graph_stats", "traceability_render", "hooks_emit",
                         "git_strategy_plan", "team_decisions", "knowledge_for_role", "evals_run"):
            self.assertIn(expected, names)

    def test_every_tool_is_well_formed(self):
        for name, tool in self.tools.items():
            self.assertRegex(name, r"^[A-Za-z0-9_.-]{1,128}$")
            self.assertTrue(tool["description"])
            schema = tool["inputSchema"]
            self.assertEqual(schema["type"], "object")
            self.assertIs(schema["additionalProperties"], False)
            self.assertNotIn("help", schema["properties"])
            for required in schema.get("required", []):
                self.assertIn(required, schema["properties"])
            self.assertIsInstance(tool["annotations"]["readOnlyHint"], bool)

    def test_hooks_emit_schema(self):
        tool = self.tools["hooks_emit"]
        props = tool["inputSchema"]["properties"]
        self.assertEqual(props["event"]["enum"], list(hooks.EVENT_TYPES))
        self.assertEqual(props["no_internal"]["type"], "boolean")
        self.assertIn("description", props["no_internal"])
        self.assertEqual(props["path"], {"type": "string", "default": "."})
        self.assertEqual(tool["inputSchema"]["required"], ["event"])
        self.assertFalse(tool["annotations"]["readOnlyHint"])

    def test_types_required_and_positionals(self):
        self.assertEqual(self.props("hooks_firings")["limit"]["type"], "integer")
        self.assertEqual(self.props("worktree_plan")["wave_size"], {
            "description": "feature count in this feature's wave (FR-004)", "type": "integer", "default": 2})
        self.assertEqual(self.props("state_show")["summary"]["type"], "boolean")
        self.assertEqual(self.props("state_init")["workflow"]["enum"], ["git-flow", "trunk"])
        self.assertEqual(self.tools["state_init"]["inputSchema"]["required"], ["context"])
        self.assertEqual(self.tools["graph_neighbors"]["inputSchema"]["required"], ["node_id"])
        self.assertEqual(self.props("policy_preflight")["command"],
                         {"type": "array", "items": {"type": "string"}, "minItems": 1})
        self.assertEqual(self.props("team_resolve")["alternative"]["type"], "array")
        self.assertNotIn("required", self.tools["team_roles"]["inputSchema"])
        self.assertIn("record the decision", self.tools["team_resolve"]["description"])

    def test_read_only_annotations_are_conservative(self):
        for name in ("state_show", "graph_stats", "graph_neighbors", "hooks_list", "team_decisions",
                     "gates_detect", "git_strategy_plan", "telemetry_locate", "baseline_plan", "lane_triage",
                     "step_next"):
            self.assertTrue(self.tools[name]["annotations"]["readOnlyHint"], name)
        for name in ("state_init", "state_transition", "traceability_render", "hooks_init", "hooks_emit",
                     "worktree_plan", "graph_health", "graph_snapshot", "delta_report", "team_resolve",
                     "metrics_record_round", "telemetry_ingest", "baseline_run", "step_begin", "step_end",
                     "harness_install_hooks", "harness_mode"):
            self.assertFalse(self.tools[name]["annotations"]["readOnlyHint"], name)


class IntrospectionTest(unittest.TestCase):
    """build_tools() is generic: new CLI groups/shapes must map without code changes."""

    def setUp(self):
        parser = argparse.ArgumentParser(prog="x")
        parser.add_argument("--verbose", action="store_true")
        sub = parser.add_subparsers(dest="command", required=True)
        solo = sub.add_parser("solo", help="a group with no actions")
        solo.add_argument("--ratio", type=float, default=0.5)
        grp = sub.add_parser("risk-map")
        grp_sub = grp.add_subparsers(dest="risk_action", required=True)
        score = grp_sub.add_parser("score", aliases=["sc"], help="score risks")
        score.add_argument("target")
        score.add_argument("--level", type=int, choices=[1, 2, 3], required=True)
        score.add_argument("--limit", type=int, default=5, help="max items (default: %(default)s)")
        score.add_argument("-v", "--verbosity", action="count")
        score.add_argument("--no-color", dest="color", action="store_false")
        score.add_argument("--color-mode", action=argparse.BooleanOptionalAction, default=True)
        score.add_argument("--pair", nargs=2)
        score.add_argument("--tag", action="append")
        deep = grp_sub.add_parser("deep")
        deep_sub = deep.add_subparsers(dest="deep_action", required=True)
        deep_sub.add_parser("list")
        self.parser = parser
        self.tools = {t.name: t for t in mcp.build_tools(parser)}

    def test_names_groups_aliases_and_nesting(self):
        self.assertEqual(sorted(self.tools), ["risk_map_deep_list", "risk_map_score", "solo"])
        self.assertEqual(self.tools["solo"].to_mcp()["description"],
                         "a group with no actions (Spec Master CLI: `solo`).")
        self.assertEqual(self.tools["risk_map_score"].tokens, ["risk-map", "score"])
        self.assertTrue(self.tools["risk_map_deep_list"].read_only)
        self.assertFalse(self.tools["risk_map_score"].read_only)

    def test_schema_mapping(self):
        schema = self.tools["risk_map_score"].input_schema()
        props = schema["properties"]
        self.assertEqual(sorted(schema["required"]), ["level", "target"])
        self.assertEqual(props["level"], {"type": "integer", "enum": [1, 2, 3]})
        self.assertEqual(props["limit"]["description"], "max items (default: 5)")
        self.assertEqual(props["verbosity"], {"type": "integer", "minimum": 0})
        self.assertEqual(props["no_color"]["type"], "boolean")
        self.assertEqual(props["color_mode"], {"type": "boolean", "default": True})
        self.assertEqual(props["pair"]["minItems"], 2)
        self.assertEqual(props["tag"]["type"], "array")
        self.assertEqual(props["verbose"]["type"], "boolean")  # root-level option is inherited
        self.assertEqual(self.tools["solo"].input_schema()["properties"]["ratio"],
                         {"type": "number", "default": 0.5})

    def test_argv_interleaves_levels(self):
        argv = mcp.build_argv(self.tools["risk_map_score"], {
            "verbose": True, "target": "-weird", "level": "2", "verbosity": 2, "no_color": True,
            "color_mode": False, "pair": ["a", "b"], "tag": ["t1", "t2"]})
        self.assertEqual(argv, ["--verbose", "risk-map", "score", "--level=2", "--verbosity", "--verbosity", "--no-color",
                                "--no-color-mode", "--pair", "a", "b", "--tag=t1", "--tag=t2", "--", "-weird"])
        ns = self.parser.parse_args(argv)  # the argv round-trips through argparse
        self.assertEqual((ns.verbose, ns.target, ns.level, ns.verbosity, ns.color, ns.color_mode),
                         (True, "-weird", 2, 2, False, False))
        self.assertEqual((ns.pair, ns.tag, ns.limit), (["a", "b"], ["t1", "t2"], 5))


class BuildArgvTest(_ServerCase):
    def argv(self, tool, arguments):
        return mcp.build_argv(self.server.tools_by_name[tool], arguments)

    def test_booleans_emit_flag_only_when_true(self):
        self.assertEqual(
            self.argv("git_strategy_plan", {"strategy": "trunk", "feature_name": "f1",
                                            "git_extension_installed": True, "spec_kit_present": False}),
            ["git-strategy", "plan", "--strategy=trunk", "--feature-name=f1", "--git-extension-installed"])
        self.assertEqual(self.argv("state_show", {"summary": "true"}), ["state", "show", "--summary"])

    def test_arrays_repeat_the_flag(self):
        argv = self.argv("team_resolve", {"kind": "k", "raised_by": "dev", "decision": "d",
                                          "alternative": ["a", "b"], "adr_trigger": "x"})
        self.assertEqual(argv[-3:], ["--alternative=a", "--alternative=b", "--adr-trigger=x"])

    def test_integers_and_positionals(self):
        self.assertEqual(self.argv("graph_neighbors", {"node_id": "n.1", "depth": 3}),
                         ["graph", "neighbors", "--depth=3", "n.1"])
        self.assertEqual(self.argv("worktree_plan", {"feature_id": "f", "project_root": ".", "strategy": "trunk",
                                                     "wave_size": "4"})[-1], "--wave-size=4")
        self.assertEqual(self.argv("policy_preflight", {"command": ["-x", "ls"]}),
                         ["policy", "preflight", "--", "-x", "ls"])
        self.assertEqual(self.argv("budget_estimate", {"text": "--flag-like"}),
                         ["budget", "estimate", "--", "--flag-like"])

    def test_objects_for_string_params_are_json_encoded(self):
        argv = self.argv("hooks_emit", {"event": "gate.result", "payload_json": {"ok": True}})
        self.assertIn('--payload-json={"ok": true}', argv)

    def test_nulls_are_omitted(self):
        self.assertEqual(self.argv("state_show", {"path": None, "summary": None}), ["state", "show"])

    def test_rejections(self):
        cases = [
            ("state_show", {"bogus": 1}, "unknown argument"),
            ("state_init", {}, "missing required"),
            ("state_init", {"context": "c", "workflow": "waterfall"}, "not one of"),
            ("hooks_firings", {"limit": "many"}, "expected an integer"),
            ("hooks_firings", {"limit": True}, "expected an integer"),
            ("state_show", {"summary": "maybe"}, "expected a boolean"),
            ("state_init", {"context": True}, "expected a string"),
            ("state_init", {"context": "a\x00b"}, "NUL"),
            ("policy_preflight", {"command": []}, "at least 1"),
        ]
        for tool, arguments, message in cases:
            with self.subTest(tool=tool, arguments=arguments):
                with self.assertRaises(mcp.ArgumentError) as ctx:
                    self.argv(tool, arguments)
                self.assertIn(message, str(ctx.exception))


class StdioEndToEndTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def run_session(self, messages):
        payload = "".join(json.dumps(m) + "\n" for m in messages) + "not json\n"
        proc = subprocess.run([sys.executable, str(SERVER_SCRIPT), "--project", str(self.root)],
                              input=payload.encode(), capture_output=True, timeout=60, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode())
        lines = proc.stdout.decode().splitlines()
        responses = [json.loads(line) for line in lines]  # every stdout line is a JSON-RPC message
        return {r["id"]: r for r in responses}, proc.stderr.decode()

    def test_session(self):
        responses, stderr = self.run_session([
            _request(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                       "clientInfo": {"name": "test", "version": "0"}}),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            _request(2, "tools/call", {"name": "state_init", "arguments": {"context": "ctx.md", "workflow": "trunk"}}),
            _request(3, "tools/call", {"name": "state_show", "arguments": {"summary": True}}),
            _request(4, "tools/call", {"name": "state_show", "arguments": {"path": "missing/state.json"}}),
            _request(5, "tools/call", {"name": "graph_maps", "arguments": {"map_type": "node"}}),
            _request(6, "ping"),
        ])
        self.assertIn("serving", stderr)
        self.assertEqual(responses[1]["result"]["protocolVersion"], "2025-06-18")

        init = responses[2]["result"]
        self.assertFalse(init["isError"])
        self.assertEqual(init["structuredContent"]["context"], "ctx.md")
        self.assertTrue((self.root / ".spec-master" / "state.json").is_file())  # cwd = project root

        show = responses[3]["result"]
        self.assertFalse(show["isError"])
        self.assertEqual(show["structuredContent"], {"status": "INITIALIZED", "workflow": "trunk", "features": []})
        self.assertEqual(json.loads(show["content"][0]["text"]), show["structuredContent"])

        missing = responses[4]["result"]
        self.assertTrue(missing["isError"])
        self.assertIn("state file not found", missing["structuredContent"]["error"])

        maps = responses[5]["result"]
        self.assertTrue(maps["isError"])
        self.assertIn("requires --node-id", maps["content"][-1]["text"])

        self.assertEqual(responses[6]["result"], {})
        self.assertEqual(responses[None]["error"]["code"], mcp.PARSE_ERROR)

    def test_list_tools_flag(self):
        proc = subprocess.run([sys.executable, str(SERVER_SCRIPT), "--project", str(self.root), "--list-tools"],
                              capture_output=True, timeout=60, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode())
        names = {t["name"] for t in json.loads(proc.stdout)["tools"]}
        self.assertIn("traceability_render", names)

    def test_rejects_missing_project_dir(self):
        proc = subprocess.run([sys.executable, str(SERVER_SCRIPT), "--project", str(self.root / "nope")],
                              input=b"", capture_output=True, timeout=60, check=False)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, b"")


if __name__ == "__main__":
    unittest.main()
