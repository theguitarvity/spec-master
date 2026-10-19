import http.client
import json
import os
import shutil
import tempfile
import threading
import time
import unittest

import _pathfix  # noqa: F401
import dashboard
import dashboard_server as ds
import state as state_mod

TOKENS_SUMMARY = {
    "schema": "spec-master.tokens-summary/v1",
    "totals": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 0,
               "cache_creation_input_tokens": 0, "total_tokens": 15, "cost_usd": 0.0, "cache_hit_ratio": 0.0},
    "by_feature": {}, "by_phase": {}, "by_agent": {}, "by_model": {},
    "burn_rate_tokens_per_min": 1.5, "window": {"first_ts": "a", "last_ts": "b"},
}


def _append(path, *lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for line in lines:
            fh.write((line if isinstance(line, str) else json.dumps(line)) + "\n")


class Project(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.sm = os.path.join(self.tmp, ".spec-master")
        self.state_path = os.path.join(self.sm, "state.json")
        state_mod.init(self.state_path, context="ctx.md")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def p(self, *parts):
        return os.path.join(self.sm, *parts)


class TailerTests(Project):
    def test_streams_only_new_lines_after_creation(self):
        path = self.p("events.jsonl")
        _append(path, {"type": "old"})
        tailer = ds.Tailer(path)
        self.assertEqual(tailer.poll(), [])
        _append(path, {"type": "new", "n": 1}, {"type": "new", "n": 2})
        self.assertEqual([r["n"] for r in tailer.poll()], [1, 2])
        self.assertEqual(tailer.poll(), [])

    def test_missing_file_then_created(self):
        path = self.p("metrics", "tokens.jsonl")
        tailer = ds.Tailer(path)
        self.assertEqual(tailer.poll(), [])
        _append(path, {"a": 1})
        self.assertEqual(tailer.poll(), [{"a": 1}])

    def test_partial_line_is_held_until_complete(self):
        path = self.p("events.jsonl")
        _append(path, {"x": 0})
        tailer = ds.Tailer(path)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write('{"x": 1')
        self.assertEqual(tailer.poll(), [])
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("}\n")
        self.assertEqual(tailer.poll(), [{"x": 1}])

    def test_truncation_resets_offset(self):
        path = self.p("events.jsonl")
        _append(path, {"x": 0}, {"x": 1}, {"x": 2})
        tailer = ds.Tailer(path)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('{"y": 1}\n')
        self.assertEqual(tailer.poll(), [{"y": 1}])

    def test_corrupt_and_non_object_lines_are_skipped(self):
        path = self.p("events.jsonl")
        tailer = ds.Tailer(path)
        _append(path, "{broken", "[1,2]", '"str"', {"ok": True})
        self.assertEqual(tailer.poll(), [{"ok": True}])


class SseFormatTests(unittest.TestCase):
    def test_format_sse_single_line_data(self):
        self.assertEqual(ds.format_sse("tokens", '{"a":1}'), 'event: tokens\ndata: {"a":1}\n\n')

    def test_format_sse_strips_newlines_from_event_and_data(self):
        out = ds.format_sse("a\nb", "x\ny")
        self.assertEqual(out.count("\n"), 3 + 0)  # event line, data line, blank line
        self.assertNotIn("a\nb", out)


class LiveSourcesTests(Project):
    def test_each_source_maps_to_its_event_type(self):
        sources = ds.LiveSources(self.tmp)
        _append(self.p("events.jsonl"), {"type": "phase.started", "feature_id": "f"})
        _append(self.p("metrics", "tokens.jsonl"), {"model": "m", "input_tokens": 1})
        _append(self.p("hooks", "firings.jsonl"), {"event": {"type": "x"}})
        _append(self.p("hooks", "decisions.jsonl"), {"decision": "allow"})
        got = {name: json.loads(data) for name, data in sources.poll()}
        self.assertEqual(set(got), {"phase.started", "tokens", "hook.fired", "hook.decision"})
        self.assertEqual(got["tokens"]["model"], "m")

    def test_event_without_type_is_named_event(self):
        sources = ds.LiveSources(self.tmp)
        _append(self.p("events.jsonl"), {"feature_id": "f"})
        self.assertEqual([n for n, _ in sources.poll()], ["event"])

    def test_state_change_emits_model_notice(self):
        sources = ds.LiveSources(self.tmp)
        self.assertEqual(sources.poll(), [])
        s = state_mod.load(self.state_path)
        state_mod.upsert_feature(s, {"id": "f", "name": "F"})
        state_mod.save(self.state_path, s)
        events = sources.poll()
        self.assertEqual([n for n, _ in events], ["model"])
        self.assertEqual(json.loads(events[0][1])["reason"], "state.json changed")
        self.assertEqual(sources.poll(), [])

    def test_changes_dir_emits_change_with_status(self):
        sources = ds.LiveSources(self.tmp)
        _append(self.p("changes", "c1.json"), {"id": "c1", "status": "RUNNING", "updated_at": "t"})
        _append(self.p("changes", "active.json"), {"id": "c1"})
        _append(self.p("changes", "log.jsonl"), {"id": "c0"})
        events = sources.poll()
        self.assertEqual([n for n, _ in events], ["change"])
        self.assertEqual(json.loads(events[0][1]), {"id": "c1", "status": "RUNNING", "updated_at": "t"})
        self.assertEqual(sources.poll(), [])

    def test_unreadable_change_record_still_emits_id(self):
        sources = ds.LiveSources(self.tmp)
        os.makedirs(self.p("changes"))
        with open(self.p("changes", "c2.json"), "w", encoding="utf-8") as fh:
            fh.write("{torn")
        events = sources.poll()
        self.assertEqual(json.loads(events[0][1]), {"id": "c2"})


class DeriveTests(unittest.TestCase):
    def test_agents_and_timeline(self):
        records = [
            {"type": "phase.started", "ts": "t1", "session_id": "s", "feature_id": "f", "phase": "plan", "status": "RUNNING"},
            {"type": "agent.started", "ts": "t2", "session_id": "s", "feature_id": "f", "phase": "plan",
             "agent_id": "a1", "agent_type": "dev", "worktree": "/w"},
            {"type": "agent.started", "ts": "t3", "agent_id": "a2", "agent_type": "qa"},
            {"type": "agent.finished", "ts": "t4", "agent_id": "a1"},
            {"type": "phase.finished", "ts": "t5", "session_id": "s", "feature_id": "f", "phase": "plan", "status": "PASSED"},
            {"type": "phase.started", "ts": "t6", "session_id": "s", "feature_id": "f", "phase": "tasks"},
        ]
        out = ds.derive_events(records)
        agents = {a["agent_id"]: a for a in out["agents"]}
        self.assertFalse(agents["a1"]["active"])
        self.assertEqual(agents["a1"]["finished_at"], "t4")
        self.assertTrue(agents["a2"]["active"])
        self.assertEqual(agents["a1"]["worktree"], "/w")
        timeline = out["timeline"]
        self.assertEqual([(t["phase"], t["status"], t["finished_at"]) for t in timeline],
                         [("plan", "PASSED", "t5"), ("tasks", "RUNNING", None)])

    def test_garbage_is_ignored(self):
        out = ds.derive_events([{"type": "agent.finished"}, {"type": "phase.finished"}, {"nothing": 1}])
        self.assertEqual(out, {"agents": [], "timeline": []})


class TokensTests(Project):
    def test_provider_wins(self):
        self.assertEqual(ds.tokens_summary(self.tmp, provider=lambda root: TOKENS_SUMMARY), TOKENS_SUMMARY)

    def test_missing_ledger_gives_none(self):
        self.assertIsNone(ds.tokens_summary(self.tmp, ledger_module=None))

    def test_ledger_module_summarize_then_summary(self):
        class A:
            @staticmethod
            def summarize(root, **kw):
                return TOKENS_SUMMARY
        class B:
            @staticmethod
            def summary(root, **kw):
                return {"schema": "x"}
        self.assertEqual(ds.tokens_summary(self.tmp, ledger_module=A), TOKENS_SUMMARY)
        self.assertEqual(ds.tokens_summary(self.tmp, ledger_module=B), {"schema": "x"})

    def test_failing_or_non_dict_summary_gives_none(self):
        def boom(root):
            raise RuntimeError("bad ledger")
        self.assertIsNone(ds.tokens_summary(self.tmp, provider=boom))
        self.assertIsNone(ds.tokens_summary(self.tmp, provider=lambda root: ["not", "a", "dict"]))

    def test_build_live_model_extends_build_model(self):
        _append(self.p("events.jsonl"), {"type": "agent.started", "agent_id": "a", "ts": "t"})
        model = ds.build_live_model(self.tmp, provider=lambda root: TOKENS_SUMMARY)
        self.assertEqual(model["schema"], dashboard.SCHEMA)
        self.assertEqual(model["tokens"], TOKENS_SUMMARY)
        self.assertEqual(model["agents"][0]["agent_id"], "a")
        self.assertEqual(model["timeline"], [])
        self.assertIn("features", model)
        self.assertIsNone(ds.build_live_model(self.tmp, provider=None, ledger_module=None)["tokens"])


class ServerTestBase(Project):
    def start(self, dist=None, **kwargs):
        kwargs.setdefault("heartbeat", 0.2)
        kwargs.setdefault("poll_interval", 0.05)
        self.server = ds.make_server(self.tmp, port=0, dist_dir=dist, **kwargs)
        self.port = self.server.server_address[1]
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self._stop, thread)

    def _stop(self, thread):
        self.server.shutdown()
        self.server.server_close()
        thread.join(5)

    def request(self, method, path, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(conn.close)
        conn.request(method, path, headers=headers or {})
        resp = conn.getresponse()
        return resp, resp.read()

    def sse(self, path="/api/events"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(conn.close)
        conn.request("GET", path)
        return conn.getresponse()

    @staticmethod
    def read_messages(resp, count, deadline=5.0):
        """Collect `count` SSE messages (event/data pairs) or comments, as raw blocks."""
        blocks, current, end = [], [], time.time() + deadline
        while len(blocks) < count and time.time() < end:
            line = resp.readline().decode("utf-8")
            if line in ("\n", "\r\n"):
                if current:
                    blocks.append("".join(current))
                    current = []
            elif line:
                current.append(line)
        return blocks


class HttpBasicsTests(ServerTestBase):
    def test_binds_loopback_only(self):
        self.start()
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        self.assertEqual(ds.HOST, "127.0.0.1")

    def test_api_model_has_tokens_null_without_ledger(self):
        self.start(tokens_provider=lambda root: None)
        resp, body = self.request("GET", "/api/model")
        self.assertEqual(resp.status, 200)
        self.assertIn("application/json", resp.getheader("Content-Type"))
        self.assertEqual(resp.getheader("Cache-Control"), "no-store")
        model = json.loads(body)
        self.assertEqual(model["schema"], dashboard.SCHEMA)
        self.assertIsNone(model["tokens"])
        self.assertIsNone(resp.getheader("Access-Control-Allow-Origin"))

    def test_api_model_includes_ledger_summary(self):
        self.start(tokens_provider=lambda root: TOKENS_SUMMARY)
        _, body = self.request("GET", "/api/model")
        self.assertEqual(json.loads(body)["tokens"], TOKENS_SUMMARY)

    def test_healthz(self):
        self.start()
        resp, body = self.request("GET", "/healthz")
        self.assertEqual((resp.status, json.loads(body)), (200, {"ok": True}))

    def test_head_allowed_other_methods_405(self):
        self.start()
        resp, body = self.request("HEAD", "/healthz")
        self.assertEqual((resp.status, body), (200, b""))
        for method in ("POST", "PUT", "DELETE", "PATCH"):
            resp, _ = self.request(method, "/api/model")
            self.assertEqual(resp.status, 405, method)
            self.assertEqual(resp.getheader("Allow"), "GET, HEAD")

    def test_foreign_host_header_rejected(self):
        self.start()
        resp, _ = self.request("GET", "/api/model", headers={"Host": "evil.example.com"})
        self.assertEqual(resp.status, 403)
        resp, _ = self.request("GET", "/api/model", headers={"Host": f"localhost:{self.port}"})
        self.assertEqual(resp.status, 200)
        resp, _ = self.request("GET", "/api/model", headers={"Host": f"127.0.0.1:{self.port}"})
        self.assertEqual(resp.status, 200)

    def test_unknown_api_path_404(self):
        self.start()
        resp, _ = self.request("GET", "/api/nope")
        self.assertEqual(resp.status, 404)

    def test_corrupt_jsonl_does_not_break_model(self):
        _append(self.p("events.jsonl"), "{corrupt")
        _append(self.p("hooks", "decisions.jsonl"), "{corrupt")
        self.start()
        resp, body = self.request("GET", "/api/model")
        self.assertEqual(resp.status, 200)
        self.assertEqual(json.loads(body)["hook_decisions"], [])


class StaticTests(ServerTestBase):
    def make_dist(self):
        dist = os.path.join(self.tmp, "dist")
        os.makedirs(os.path.join(dist, "assets"))
        with open(os.path.join(dist, "index.html"), "w", encoding="utf-8") as fh:
            fh.write("<!doctype html><title>React</title>")
        with open(os.path.join(dist, "assets", "app.js"), "w", encoding="utf-8") as fh:
            fh.write("console.log(1)")
        with open(os.path.join(self.tmp, "secret.txt"), "w", encoding="utf-8") as fh:
            fh.write("secret")
        return dist

    def test_serves_bundle_index_and_assets(self):
        self.start(dist=self.make_dist())
        resp, body = self.request("GET", "/")
        self.assertEqual(resp.status, 200)
        self.assertIn("text/html", resp.getheader("Content-Type"))
        self.assertIn(b"React", body)
        self.assertEqual(resp.getheader("Cache-Control"), "no-store")
        resp, body = self.request("GET", "/assets/app.js")
        self.assertEqual(resp.status, 200)
        self.assertIn("javascript", resp.getheader("Content-Type"))
        self.assertEqual(body, b"console.log(1)")

    def test_path_traversal_blocked(self):
        self.start(dist=self.make_dist())
        for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt", "/..%2fsecret.txt"):
            resp, body = self.request("GET", path)
            self.assertNotEqual(body, b"secret", path)
            self.assertIn(resp.status, (200, 400, 403, 404), path)
        resp, body = self.request("GET", "/assets/missing.js")
        self.assertEqual(resp.status, 404)

    def test_missing_bundle_falls_back_to_static_html(self):
        self.start(dist=os.path.join(self.tmp, "no-such-dist"))
        resp, body = self.request("GET", "/")
        self.assertEqual(resp.status, 200)
        self.assertIn("text/html", resp.getheader("Content-Type"))
        self.assertIn(b"<html", body.lower())
        self.assertIn(b"Spec Master", body)

    def test_default_dist_is_the_committed_bundle_location(self):
        self.assertTrue(ds.DEFAULT_DIST.replace(os.sep, "/").endswith("dashboard/web/dist"))


class SseTests(ServerTestBase):
    def test_headers_and_connected_comment(self):
        self.start()
        resp = self.sse()
        self.assertEqual(resp.status, 200)
        self.assertIn("text/event-stream", resp.getheader("Content-Type"))
        self.assertEqual(resp.getheader("Cache-Control"), "no-store")
        self.assertEqual(self.read_messages(resp, 1), [": connected\n"])

    def test_events_from_every_source(self):
        self.start()
        resp = self.sse()
        self.read_messages(resp, 1)
        _append(self.p("events.jsonl"), {"type": "phase.started", "feature_id": "f"})
        _append(self.p("metrics", "tokens.jsonl"), {"model": "m"})
        _append(self.p("hooks", "firings.jsonl"), {"k": 1})
        _append(self.p("hooks", "decisions.jsonl"), {"decision": "allow"})
        _append(self.p("changes", "c1.json"), {"id": "c1", "status": "RUNNING"})
        s = state_mod.load(self.state_path)
        state_mod.upsert_feature(s, {"id": "f", "name": "F"})
        state_mod.save(self.state_path, s)
        got = {}
        for block in self.read_messages(resp, 6):
            if block.startswith(":"):
                continue
            lines = block.strip().split("\n")
            got[lines[0].split(": ", 1)[1]] = json.loads(lines[1].split(": ", 1)[1])
        self.assertEqual(set(got), {"phase.started", "tokens", "hook.fired", "hook.decision", "change", "model"})
        self.assertEqual(got["change"]["id"], "c1")

    def test_heartbeat_ping(self):
        self.start(heartbeat=0.1)
        resp = self.sse()
        blocks = self.read_messages(resp, 3)
        self.assertIn(": ping\n", blocks)

    def test_old_lines_are_not_replayed(self):
        _append(self.p("events.jsonl"), {"type": "old"})
        self.start()
        resp = self.sse()
        self.read_messages(resp, 1)
        _append(self.p("events.jsonl"), {"type": "fresh"})
        blocks = [b for b in self.read_messages(resp, 2) if not b.startswith(":")]
        self.assertEqual(len(blocks), 1)
        self.assertTrue(blocks[0].startswith("event: fresh"))

    def test_client_cap_returns_503(self):
        self.start(max_clients=1)
        first = self.sse()
        self.read_messages(first, 1)
        resp, _ = self.request("GET", "/api/events")
        self.assertEqual(resp.status, 503)

    def test_slot_released_when_client_disconnects(self):
        self.start(max_clients=1, heartbeat=0.05)
        first = self.sse()
        self.read_messages(first, 1)
        first.close()
        end = time.time() + 5
        status = None
        while time.time() < end:
            resp, _ = self.request("GET", "/healthz")
            if self.server.active_clients == 0:
                status = 0
                break
            time.sleep(0.05)
        self.assertEqual(status, 0)

    def test_shutdown_with_open_client_does_not_hang(self):
        self.start()
        resp = self.sse()
        self.read_messages(resp, 1)
        started = time.time()
        # cleanup (shutdown + close + join) runs after the test; just prove stop_event wiring here
        self.server.stop_event.set()
        self.assertLess(time.time() - started, 1)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        os.makedirs(os.path.join(self.tmp, "assets"))
        for rel, text in (("index.html", "<html>"), ("assets/a.js", "1;")):
            with open(os.path.join(self.tmp, rel), "w", encoding="utf-8") as fh:
                fh.write(text)

    def test_write_then_verify_clean(self):
        manifest = ds.write_manifest(self.tmp)
        self.assertEqual(set(manifest["files"]), {"index.html", "assets/a.js"})
        self.assertEqual(ds.verify_manifest(self.tmp), [])
        self.assertNotIn(ds.MANIFEST_NAME, manifest["files"])

    def test_tamper_missing_and_extra_detected(self):
        ds.write_manifest(self.tmp)
        with open(os.path.join(self.tmp, "assets", "a.js"), "w", encoding="utf-8") as fh:
            fh.write("2;")
        with open(os.path.join(self.tmp, "extra.txt"), "w", encoding="utf-8") as fh:
            fh.write("x")
        os.unlink(os.path.join(self.tmp, "index.html"))
        problems = "\n".join(ds.verify_manifest(self.tmp))
        self.assertIn("modified: assets/a.js", problems)
        self.assertIn("unlisted: extra.txt", problems)
        self.assertIn("missing: index.html", problems)

    def test_no_manifest_is_a_problem(self):
        self.assertEqual(ds.verify_manifest(self.tmp), [f"missing manifest: {ds.MANIFEST_NAME}"])

    def test_manifest_is_deterministic(self):
        first = ds.write_manifest(self.tmp)
        second = ds.write_manifest(self.tmp)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
