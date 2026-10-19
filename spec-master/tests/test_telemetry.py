import _pathfix  # noqa: F401

import datetime as dt
import json
import os
import shutil
import tempfile
import unittest

import metrics_export
import telemetry

SESSION = "11111111-2222-3333-4444-555555555555"
MODEL = "claude-test-model"
SECRET = "SECRET-CONTENT-MARKER"


def _ts(clock: str) -> str:
    return f"2026-09-27T{clock}Z"


def _base(kind, clock, **extra):
    line = {"type": kind, "sessionId": SESSION, "uuid": f"u-{kind}-{clock}", "parentUuid": None,
            "userType": "external", "cwd": "/work/app", "version": "2.1.283", "gitBranch": "main",
            "isSidechain": False, "timestamp": _ts(clock)}
    line.update(extra)
    return line


def _usage(inp, out, read, create):
    return {"input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": read,
            "cache_creation_input_tokens": create, "service_tier": "standard",
            "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": create}}


def _assistant(clock, msg_id, usage, *, stop="tool_use", block=0, model=MODEL, **extra):
    """One content-block line of an API response (the host writes one per block)."""
    return _base("assistant", clock, requestId=f"req-{msg_id}", apiBlockIndex=block, message={
        "id": msg_id, "type": "message", "role": "assistant", "model": model,
        "content": [{"type": "text", "text": f"{SECRET} reply"}],
        "stop_reason": stop, "stop_sequence": None, "usage": usage}, **extra)


def _human(clock, text=f"{SECRET} please fix the bug"):
    return _base("user", clock, origin={"kind": "human"}, turnOrigin="human", promptSource="sdk",
                 promptId="p-1", message={"role": "user", "content": text})


def _tool_result(clock):
    return _base("user", clock, toolUseResult={"stdout": SECRET}, sourceToolAssistantUUID="u-a",
                 message={"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1",
                                                       "content": f"{SECRET} tool output"}]})


def _main_session_lines():
    usage_a = _usage(10, 500, 1000, 200)
    return [
        {"type": "queue-operation", "operation": "enqueue", "sessionId": SESSION, "timestamp": _ts("10:00:00.000"),
         "content": SECRET},
        _human("10:00:00.100"),
        _assistant("10:00:05.000", "msg_A", usage_a, block=0),   # one response, three lines,
        _assistant("10:00:05.010", "msg_A", usage_a, block=1),   # same id and the same usage
        _assistant("10:00:05.020", "msg_A", usage_a, block=2),
        _tool_result("10:00:06.000"),
        _assistant("10:00:10.000", "msg_B", _usage(5, 100, 2000, 0), stop="end_turn"),
        _base("system", "10:00:10.500", subtype="stop_hook_summary", hookCount=1),
        {"type": "mode", "mode": "normal", "sessionId": SESSION},
        '{"type": "assistant", "message": {',                    # malformed (truncated write)
        "[1, 2, 3]",                                             # JSON, but not an object
        _base("user", "10:30:00.000", origin={"kind": "task-notification"}, turnOrigin="task_notification",
              promptSource="system", message={"role": "user", "content": SECRET}),
        _assistant("10:30:05.000", "msg_C", _usage(3, 50, 3000, 100), stop="end_turn"),
        _base("user", "10:30:06.000", isMeta=True, message={"role": "user", "content": SECRET}),
        _base("user", "10:30:07.000", message={"role": "user", "content": [{"type": "text", "text": SECRET}]}),
        _assistant("10:30:08.000", "synthetic-1", _usage(0, 0, 0, 0), stop="stop_sequence", model="<synthetic>"),
        _human("11:00:08.000"),
        # streaming-start snapshot first, final usage second: per-field max wins
        _assistant("11:00:10.000", "msg_D", _usage(1, 7, 4000, 50), stop=None, block=0),
        _assistant("11:00:10.050", "msg_D", _usage(1, 900, 4000, 50), stop="end_turn", block=1),
        {"type": "cost-state", "sessionId": SESSION, "totalCostUSD": 1.5, "modelUsage": {}},
        # older layout: a sidechain interleaved in the main file
        _base("user", "11:00:19.000", isSidechain=True, agentId="agent-old",
              message={"role": "user", "content": SECRET}),
        _assistant("11:00:20.000", "msg_S1", _usage(7, 70, 700, 70), stop="end_turn", isSidechain=True,
                   agentId="agent-old"),
    ]


def _subagent_lines(agent_id, responses):
    lines = [_base("user", "10:00:07.000", isSidechain=True, agentId=agent_id,
                   message={"role": "user", "content": SECRET})]
    for clock, msg_id, usage in responses:
        # subagent lines carry the streaming-start usage: stop_reason is null
        lines.append(_assistant(clock, msg_id, usage, stop=None, isSidechain=True, agentId=agent_id))
    return lines


def _write_jsonl(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for line in lines:
            fh.write((line if isinstance(line, str) else json.dumps(line)) + "\n")
    return path


class _TranscriptCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.project = os.path.join(self.tmp, "projects", "-work-app")
        self.main = _write_jsonl(os.path.join(self.project, f"{SESSION}.jsonl"), _main_session_lines())
        sub = os.path.join(self.project, SESSION, "subagents")
        x_usage = _usage(4, 3, 5000, 400)
        self.agent = _write_jsonl(os.path.join(sub, "agent-abc.jsonl"), _subagent_lines("abc", [
            ("10:00:08.000", "msg_X", x_usage), ("10:00:08.010", "msg_X", x_usage),
            ("10:00:09.000", "msg_Y", _usage(2, 5, 6000, 0))]))
        self.workflow_agent = _write_jsonl(os.path.join(sub, "workflows", "wf_1", "agent-wf1.jsonl"),
                                           _subagent_lines("wf1", [("10:10:00.000", "msg_W", _usage(1, 2, 10, 0))]))
        _write_jsonl(os.path.join(sub, "workflows", "wf_1", "journal.jsonl"),
                     [{"type": "started", "agentId": "wf1", "label": SECRET}])
        with open(os.path.join(sub, "agent-abc.meta.json"), "w", encoding="utf-8") as fh:
            json.dump({"agentType": "general-purpose", "description": SECRET}, fh)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class ReadTranscriptUsageTests(_TranscriptCase):
    def test_main_file_dedupes_responses_and_splits_sidechain(self):
        usage = telemetry.read_transcript_usage(self.main)
        self.assertEqual(usage["source"], "host-transcript")
        self.assertEqual(usage["main"], {"input_tokens": 19, "output_tokens": 1550, "cache_read_input_tokens": 10000,
                                         "cache_creation_input_tokens": 350, "turns": 4, "incomplete_responses": 0})
        self.assertEqual(usage["sidechain"], {"input_tokens": 7, "output_tokens": 70, "cache_read_input_tokens": 700,
                                              "cache_creation_input_tokens": 70, "turns": 1,
                                              "incomplete_responses": 0})
        self.assertEqual((usage["input_tokens"], usage["output_tokens"], usage["total_tokens"], usage["turns"]),
                         (26, 1620, 1646, 5))
        self.assertEqual((usage["cache_read_input_tokens"], usage["cache_creation_input_tokens"]), (10700, 420))
        self.assertTrue(usage["output_tokens_complete"])
        self.assertEqual(usage["models"], {MODEL: 5})  # the <synthetic> message is not an API response
        self.assertEqual(usage["subagents"], 1)

    def test_metadata_bounds_session_and_skipped_lines(self):
        usage = telemetry.read_transcript_usage(self.main)
        self.assertEqual(usage["started_at"], "2026-09-27T10:00:00.000Z")
        self.assertEqual(usage["ended_at"], "2026-09-27T11:00:20.000Z")
        self.assertEqual(usage["duration_seconds"], 3620.0)
        self.assertEqual((usage["session_id"], usage["session_ids"]), (SESSION, [SESSION]))
        self.assertEqual(usage["skipped_lines"], 2)
        self.assertEqual(usage["lines"], len(_main_session_lines()))
        self.assertEqual(usage["transcripts"], [self.main])

    def test_human_wait_counts_only_genuine_prompts(self):
        usage = telemetry.read_transcript_usage(self.main)
        # prompt 2 (11:00:08) waited since the last activity (the 10:30:08 message); the
        # 10:00:10 -> 10:30:00 idle gap ended in a task notification, not a human prompt,
        # and the isMeta / unstamped / tool-result user lines are not prompts either.
        self.assertEqual(usage["human_prompts"], 2)
        self.assertEqual(usage["human_wait_seconds"], 1800.0)

    def test_full_session_includes_subagent_files_and_flags_lower_bound(self):
        files = telemetry.session_transcripts(self.main)
        self.assertEqual(files, [self.main, self.agent, self.workflow_agent])  # journal/meta excluded
        usage = telemetry.read_transcript_usage(files)
        self.assertEqual(usage["sidechain"], {"input_tokens": 14, "output_tokens": 80, "cache_read_input_tokens": 11710,
                                              "cache_creation_input_tokens": 470, "turns": 4,
                                              "incomplete_responses": 3})
        self.assertEqual((usage["turns"], usage["incomplete_responses"], usage["total_tokens"]), (8, 3, 1663))
        self.assertFalse(usage["output_tokens_complete"])
        self.assertEqual(usage["subagents"], 3)
        self.assertEqual(usage["session_id"], SESSION)  # subagents carry the parent session id

    def test_responses_are_deduplicated_across_files(self):
        once = telemetry.read_transcript_usage(self.main)
        twice = telemetry.read_transcript_usage([self.main, self.main])
        for key in telemetry.TOKEN_FIELDS + ("turns",):
            self.assertEqual(twice[key], once[key], key)

    def test_window_filters_responses_by_first_line(self):
        usage = telemetry.read_transcript_usage(telemetry.session_transcripts(self.main),
                                                since="2026-09-27T10:00:00Z", until="2026-09-27T10:00:30Z")
        self.assertEqual((usage["input_tokens"], usage["output_tokens"], usage["turns"]), (21, 608, 4))
        self.assertEqual(usage["incomplete_responses"], 2)
        self.assertEqual((usage["human_prompts"], usage["human_wait_seconds"]), (1, 0.0))
        self.assertEqual(usage["ended_at"], "2026-09-27T10:00:10.500Z")
        self.assertEqual(usage["window"], {"since": "2026-09-27T10:00:00.000Z", "until": "2026-09-27T10:00:30.000Z"})

    def test_window_clips_human_wait(self):
        usage = telemetry.read_transcript_usage(self.main, since=dt.datetime(2026, 9, 27, 10, 45),  # naive = UTC
                                                until="2026-09-27T11:30:00+00:00")
        self.assertEqual(usage["human_wait_seconds"], 908.0)  # 10:45:00 -> 11:00:08
        self.assertEqual((usage["human_prompts"], usage["turns"]), (1, 2))
        self.assertEqual((usage["started_at"], usage["ended_at"]), ("2026-09-27T11:00:08.000Z",
                                                                    "2026-09-27T11:00:20.000Z"))

    def test_empty_window(self):
        usage = telemetry.read_transcript_usage(self.main, since="2030-01-01T00:00:00Z")
        self.assertEqual((usage["total_tokens"], usage["turns"], usage["started_at"], usage["session_id"]),
                         (0, 0, None, None))

    def test_invalid_window_bound_raises(self):
        with self.assertRaises(ValueError):
            telemetry.read_transcript_usage(self.main, since="yesterday")

    def test_never_returns_message_content(self):
        usage = telemetry.read_transcript_usage(telemetry.session_transcripts(self.main))
        self.assertNotIn(SECRET, json.dumps(usage))

    def test_legacy_transcript_without_origin_metadata(self):
        path = _write_jsonl(os.path.join(self.tmp, "legacy.jsonl"), [
            _base("user", "09:00:00.000", message={"role": "user", "content": "old prompt"}),
            _assistant("09:00:05.000", "msg_L1", _usage(1, 10, 0, 0), stop="tool_use"),
            # a tool result recognisable only by its block type
            _base("user", "09:00:06.000", message={"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t", "content": "x"}]}),
            _assistant("09:00:07.000", "msg_L2", _usage(1, 10, 0, 0), stop="end_turn"),
            _base("user", "09:00:08.000", sourceToolUseID="t", message={"role": "user", "content": "skill"}),
            _base("user", "09:10:07.000", message={"role": "user", "content": "next prompt"}),
        ])
        usage = telemetry.read_transcript_usage(path)
        self.assertEqual((usage["human_prompts"], usage["human_wait_seconds"]), (2, 600.0))
        self.assertEqual(usage["turns"], 2)


class LocateTranscriptsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.home = os.path.join(self.tmp, "home")
        self.project = os.path.join(self.tmp, "work", "my_app.v2")
        os.makedirs(self.project)
        self.dir = os.path.join(self.home, ".claude", "projects",
                                telemetry.project_dir_name(os.path.realpath(self.project)))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _touch(self, rel, mtime=None):
        path = _write_jsonl(os.path.join(self.dir, rel), [{"type": "mode"}])
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return path

    def test_newest_first_and_only_transcripts(self):
        old = self._touch("aaa.jsonl", 1_000_000)
        new = self._touch("bbb.jsonl", 2_000_000)
        with open(os.path.join(self.dir, "notes.txt"), "w", encoding="utf-8") as fh:
            fh.write("x")
        agent = self._touch(os.path.join("bbb", "subagents", "agent-1.jsonl"), 1_500_000)
        wf_agent = self._touch(os.path.join("bbb", "subagents", "workflows", "wf", "agent-2.jsonl"), 1_200_000)
        self._touch(os.path.join("bbb", "subagents", "workflows", "wf", "journal.jsonl"))
        self.assertEqual(telemetry.locate_transcripts(self.project, home=self.home), [new, old])
        self.assertEqual(telemetry.locate_transcripts(self.project, home=self.home, include_subagents=True),
                         [new, agent, wf_agent, old])
        self.assertTrue(os.path.basename(self.dir).startswith("-"))
        self.assertIn("-work-my-app-v2", self.dir)

    def test_missing_directory(self):
        self.assertEqual(telemetry.locate_transcripts(os.path.join(self.tmp, "nowhere"), home=self.home), [])

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unsupported")
    def test_symlinked_project_resolves_to_the_real_path(self):
        link = os.path.join(self.tmp, "link")
        try:
            os.symlink(self.project, link)
        except OSError:
            self.skipTest("cannot create symlinks here")
        path = self._touch("ccc.jsonl")
        self.assertEqual(telemetry.locate_transcripts(link, home=self.home), [path])

    def test_config_dir_and_project_dir_name_overrides(self):
        config = os.path.join(self.tmp, "cfg")
        named = _write_jsonl(os.path.join(config, "projects", "custom_name", "s.jsonl"), [{"type": "mode"}])
        env = {"CLAUDE_CONFIG_DIR": config, "CLAUDE_CODE_PROJECT_DIR_NAME": "custom_name"}
        self.assertEqual(telemetry.locate_transcripts(self.project, env=env), [named])
        self.assertEqual(telemetry.claude_config_dir(env=env), config)
        for bad in ("../escape", "con", ""):
            dirs = telemetry.project_transcript_dirs(self.project, env=dict(env, CLAUDE_CODE_PROJECT_DIR_NAME=bad))
            self.assertNotIn(os.path.join(config, "projects", bad), dirs)
        # the override needs CLAUDE_CONFIG_DIR, and an explicit home wins over both
        self.assertEqual(telemetry.locate_transcripts(self.project, home=self.home, env=env), [])
        self.assertEqual(telemetry.claude_config_dir(home=self.home, env=env), os.path.join(self.home, ".claude"))


class ProjectDirNameTests(unittest.TestCase):
    # Reference values produced by the sanitizer extracted from Claude Code 2.1.283, run under node.
    VECTORS = {
        "/home/user/spec-master": "-home-user-spec-master",
        "/home/user/spec-master/.claude/worktrees/agent-aedb9d11a608e2961":
            "-home-user-spec-master--claude-worktrees-agent-aedb9d11a608e2961",
        "/home/user/my_project.v2": "-home-user-my-project-v2",
        "C:\\Users\\dev\\repo": "C--Users-dev-repo",
        "/tmp/caf\u00e9": "-tmp-caf-",
        "/tmp/rocket-\U0001F680": "-tmp-rocket---",  # one astral char = two UTF-16 units
        "/" + "a" * 250: "-" + "a" * 199 + "-feo44x",
        "/srv/" + "deep/" * 45 + "repo": "-srv" + "-deep" * 39 + "--3g0dfy",
    }

    def test_matches_host_vectors(self):
        for path, expected in self.VECTORS.items():
            self.assertEqual(telemetry.project_dir_name(path), expected, path[:40])

    def test_hash_is_java_style_signed_32_bit(self):
        self.assertEqual(telemetry._java_string_hash(telemetry._utf16_units("/home/user/spec-master")), -640680239)
        self.assertEqual(telemetry._java_string_hash(telemetry._utf16_units("C:\\Users\\dev\\repo")), 1137412210)
        self.assertEqual(telemetry._base36(0), "0")


def _headless(**overrides):
    result = {
        "type": "result", "subtype": "success", "is_error": False, "duration_ms": 45000, "duration_api_ms": 40000,
        "num_turns": 7, "result": f"{SECRET} final answer", "stop_reason": "end_turn",
        "session_id": "sess-h", "total_cost_usd": 0.1234, "uuid": "u-1",
        "usage": {"input_tokens": 30, "output_tokens": 900, "cache_read_input_tokens": 50000,
                  "cache_creation_input_tokens": 4000, "server_tool_use": {"web_search_requests": 0}},
        "modelUsage": {
            "claude-main": {"inputTokens": 30, "outputTokens": 900, "cacheReadInputTokens": 50000,
                            "cacheCreationInputTokens": 4000, "webSearchRequests": 0, "costUSD": 0.12,
                            "contextWindow": 200000, "maxOutputTokens": 32000},
            "claude-aux": {"inputTokens": 1000, "outputTokens": 40, "cacheReadInputTokens": 0,
                           "cacheCreationInputTokens": 0, "webSearchRequests": 0, "costUSD": 0.0034},
        },
        "permission_denials": [{"tool_name": "Bash", "tool_use_id": "t", "tool_input": {"command": SECRET}}],
    }
    result.update(overrides)
    return result


class ReadHeadlessResultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_totals_come_from_model_usage_and_main_from_usage(self):
        usage = telemetry.read_headless_result(_headless())
        self.assertEqual((usage["input_tokens"], usage["output_tokens"], usage["cache_read_input_tokens"],
                          usage["cache_creation_input_tokens"], usage["total_tokens"]), (1030, 940, 50000, 4000, 1970))
        self.assertEqual(usage["main"], {"input_tokens": 30, "output_tokens": 900, "cache_read_input_tokens": 50000,
                                         "cache_creation_input_tokens": 4000})
        self.assertEqual(usage["token_basis"], "modelUsage")
        self.assertEqual(usage["models"]["claude-aux"]["cost_usd"], 0.0034)
        self.assertEqual((usage["cost_usd"], usage["cost_basis"]), (0.1234, "measured"))
        self.assertEqual((usage["turns"], usage["duration_ms"], usage["duration_api_ms"], usage["duration_seconds"]),
                         (7, 45000, 40000, 45.0))
        self.assertEqual((usage["session_id"], usage["subtype"], usage["is_error"]), ("sess-h", "success", False))
        self.assertEqual((usage["permission_denials"], usage["errors"]), (1, 0))
        self.assertEqual((usage["started_at"], usage["ended_at"]), (None, None))
        self.assertNotIn(SECRET, json.dumps(usage))

    def test_reads_json_verbose_array_and_stream_json_files(self):
        plain = os.path.join(self.tmp, "r.json")
        with open(plain, "w", encoding="utf-8") as fh:
            json.dump(_headless(), fh)
        array = os.path.join(self.tmp, "verbose.json")
        with open(array, "w", encoding="utf-8") as fh:
            json.dump([{"type": "system", "subtype": "init"}, {"type": "assistant"}, _headless(num_turns=3)], fh)
        stream = _write_jsonl(os.path.join(self.tmp, "stream.jsonl"),
                              [{"type": "system", "subtype": "init"}, "not json", _headless(num_turns=4)])
        self.assertEqual(telemetry.read_headless_result(plain)["turns"], 7)
        self.assertEqual(telemetry.read_headless_result(array)["turns"], 3)
        self.assertEqual(telemetry.read_headless_result(stream)["turns"], 4)

    def test_tolerates_missing_fields(self):
        usage = telemetry.read_headless_result({"type": "result"})
        self.assertEqual((usage["total_tokens"], usage["turns"], usage["cost_usd"], usage["cost_basis"]),
                         (0, None, None, None))
        self.assertEqual((usage["is_error"], usage["token_basis"], usage["duration_seconds"]), (None, "usage", None))
        falls_back = telemetry.read_headless_result(_headless(modelUsage={}))
        self.assertEqual((falls_back["token_basis"], falls_back["input_tokens"]), ("usage", 30))

    def test_error_subtypes_and_bad_numbers(self):
        usage = telemetry.read_headless_result({"type": "result", "subtype": "error_max_budget_usd",
                                                "errors": [SECRET], "total_cost_usd": float("nan")})
        self.assertEqual((usage["is_error"], usage["errors"], usage["cost_usd"]), (True, 1, None))
        self.assertIsNone(telemetry.read_headless_result(_headless(total_cost_usd=-1))["cost_usd"])
        self.assertIsNone(telemetry.read_headless_result(_headless(total_cost_usd=True))["cost_usd"])

    def test_rejects_non_results(self):
        with self.assertRaises(ValueError):
            telemetry.read_headless_result({"type": "assistant"})
        with self.assertRaises(ValueError):
            telemetry.read_headless_result([{"type": "assistant"}])
        empty = _write_jsonl(os.path.join(self.tmp, "none.jsonl"), [{"type": "system"}])
        with self.assertRaises(ValueError):
            telemetry.read_headless_result(empty)
        with self.assertRaises(TypeError):
            telemetry.read_headless_result(42)


class ToRoundTests(_TranscriptCase):
    NOW = "2026-09-28T00:00:00Z"

    def test_transcript_round_is_a_valid_v2_row(self):
        usage = telemetry.read_transcript_usage(self.main)
        row = telemetry.to_round(usage, round_id="r1-implement-app", phase="implement", source="host-transcript",
                                 feature_id="app", tier="s", lane="standard", features_completed=1)
        self.assertEqual((row["input_tokens"], row["output_tokens"], row["total_tokens"]), (26, 1620, 1646))
        self.assertEqual((row["cache_read_input_tokens"], row["cache_creation_input_tokens"], row["turns"]),
                         (10700, 420, 5))
        self.assertEqual((row["started_at"], row["ended_at"], row["duration_seconds"]),
                         ("2026-09-27T10:00:00.000Z", "2026-09-27T11:00:20.000Z", 3620.0))
        self.assertEqual((row["source"], row["lane"], row["session_id"], row["tier"]),
                         ("host-transcript", "standard", SESSION, "S"))
        self.assertEqual(row["human_wait_seconds"], 1800.0)
        self.assertNotIn("cost_usd", row)  # a transcript carries no measured cost
        self.assertNotIn("notes", row)
        self.assertEqual(metrics_export.validate_rounds([row], now=self.NOW),
                         {"valid": True, "errors": [], "warnings": []})
        self.assertEqual(set(row) - set(metrics_export.load_schema()["properties"]), set())

    def test_lower_bound_is_noted(self):
        usage = telemetry.read_transcript_usage(telemetry.session_transcripts(self.main))
        row = telemetry.to_round(usage, round_id="r2", phase="implement", source="host-transcript", notes="pilot")
        self.assertEqual(row["notes"], "pilot; telemetry: output_tokens is a lower bound "
                                       "(3 response(s) recorded before their final usage)")

    def test_headless_round_needs_one_bound_and_keeps_measured_cost(self):
        usage = telemetry.read_headless_result(_headless())
        with self.assertRaises(ValueError):
            telemetry.to_round(usage, round_id="h1", phase="implement", source="host-headless")
        row = telemetry.to_round(usage, round_id="h1", phase="implement", source="host-headless",
                                 ended_at=dt.datetime(2026, 9, 27, 12, 0, 45, tzinfo=dt.timezone.utc))
        self.assertEqual((row["started_at"], row["ended_at"], row["duration_seconds"]),
                         ("2026-09-27T12:00:00.000Z", "2026-09-27T12:00:45.000Z", 45.0))
        self.assertEqual((row["cost_usd"], row["cost_basis"], row["turns"], row["total_tokens"]),
                         (0.1234, "measured", 7, 1970))
        self.assertNotIn("human_wait_seconds", row)
        self.assertTrue(metrics_export.validate_rounds([row], now=self.NOW)["valid"])

    def test_cost_is_written_only_when_measured(self):
        usage = dict(telemetry.read_headless_result(_headless()), cost_basis="estimated")
        row = telemetry.to_round(usage, round_id="h2", phase="plan", source="host-headless",
                                 started_at="2026-09-27T12:00:00Z")
        self.assertNotIn("cost_usd", row)
        self.assertNotIn("cost_basis", row)

    def test_refuses_mismatched_unknown_or_unmeasured_sources(self):
        usage = telemetry.read_transcript_usage(self.main)
        with self.assertRaises(ValueError):
            telemetry.to_round(usage, round_id="x", phase="plan", source="host-headless")
        with self.assertRaises(ValueError):
            telemetry.to_round(usage, round_id="x", phase="plan", source="telepathy")
        empty = telemetry.read_transcript_usage(self.main, since="2030-01-01T00:00:00Z")
        with self.assertRaises(ValueError):
            telemetry.to_round(empty, round_id="x", phase="plan", source="host-transcript",
                               started_at="2030-01-01T00:00:00Z", ended_at="2030-01-01T00:01:00Z")

    def test_manual_usage_without_tokens_becomes_unverified(self):
        row = telemetry.to_round({"input_tokens": 0, "output_tokens": 0}, round_id="m1", phase="plan",
                                 source="manual", started_at="2026-09-27T10:00:00Z", ended_at="2026-09-27T10:05:00Z")
        self.assertEqual(row["source"], "manual-unverified")


if __name__ == "__main__":
    unittest.main()
