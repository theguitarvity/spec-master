import io
import json
import os
import shutil
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

import _pathfix  # noqa: F401
import cli
import dashboard
import state as state_mod


def _run_cli(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(list(argv))
    return code, buf.getvalue()


class DashboardCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmp, ".spec-master", "state.json")
        state_mod.init(self.state_path, context="ctx.md")
        s = state_mod.load(self.state_path)
        state_mod.upsert_feature(s, {"id": "f1", "name": "F1", "phases": {"specify": "PASSED", "clarify": "SKIPPED"}})
        state_mod.upsert_feature(s, {"id": "f2", "name": "F2"})
        state_mod.save(self.state_path, s)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _lock(self):
        with open(os.path.join(self.tmp, ".spec-master", "run.lock"), "w", encoding="utf-8") as fh:
            json.dump({"phase": "plan", "pid": 1,
                       "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, fh)

    def test_render_prints_summary_and_writes_default_output(self):
        code, out = _run_cli("dashboard", "render", "--path", self.tmp)
        self.assertEqual(code, 0)
        payload = json.loads(out)
        expected = os.path.join(os.path.abspath(self.tmp), ".spec-master", "reports", "dashboard.html")
        self.assertEqual(payload, {"output": expected, "features": 2, "completeness": 14.3, "active": False})
        self.assertTrue(os.path.isfile(expected))

    def test_render_active_run_with_output_and_refresh(self):
        self._lock()
        code, out = _run_cli("dashboard", "render", "--path", self.tmp, "--output", "live.html", "--refresh", "9")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["output"], os.path.join(os.path.abspath(self.tmp), "live.html"))
        self.assertTrue(payload["active"])
        with open(payload["output"], encoding="utf-8") as fh:
            self.assertIn('<meta http-equiv="refresh" content="9">', fh.read())

        code, out = _run_cli("dashboard", "render", "--path", self.tmp, "--refresh", "0")
        with open(json.loads(out)["output"], encoding="utf-8") as fh:
            self.assertNotIn('http-equiv="refresh"', fh.read())

    def test_render_negative_refresh_is_an_error(self):
        code, out = _run_cli("dashboard", "render", "--path", self.tmp, "--refresh", "-1")
        self.assertEqual(code, 1)
        self.assertIn("error", json.loads(out))

    def test_render_uninitialized_project(self):
        empty = tempfile.mkdtemp()
        try:
            code, out = _run_cli("dashboard", "render", "--path", empty)
            self.assertEqual(code, 0)
            payload = json.loads(out)
            self.assertEqual((payload["features"], payload["completeness"], payload["active"]), (0, 0.0, False))
            self.assertTrue(os.path.isfile(payload["output"]))
        finally:
            shutil.rmtree(empty, ignore_errors=True)

    def test_model_prints_the_model_without_writing(self):
        code, out = _run_cli("dashboard", "model", "--path", self.tmp)
        self.assertEqual(code, 0)
        model = json.loads(out)
        self.assertEqual(model["schema"], dashboard.SCHEMA)
        self.assertEqual([f["id"] for f in model["features"]], ["f1", "f2"])
        self.assertEqual(model["completeness"]["percent"], 14.3)
        self.assertIn(model["run"]["state"], ("settling", "idle"))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".spec-master", "reports")))


class DashboardServeCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_serve_parses_flags_and_delegates(self):
        import dashboard_server
        with mock.patch.object(dashboard_server, "serve", return_value=0) as served:
            code, _ = _run_cli("dashboard", "serve", "--port", "0", "--path", self.tmp, "--open")
        self.assertEqual(code, 0)
        served.assert_called_once_with(os.path.abspath(self.tmp), port=0, open_browser=True)

    def test_serve_defaults(self):
        import dashboard_server
        with mock.patch.object(dashboard_server, "serve", return_value=0) as served:
            _run_cli("dashboard", "serve")
        served.assert_called_once_with(os.path.abspath("."), port=8765, open_browser=False)

    def test_serve_end_to_end_prints_url_and_answers(self):
        import dashboard_server
        import http.client
        import threading
        seen = {}

        def ready(server):
            seen["port"] = server.server_address[1]

            def probe():  # serve_forever starts after `ready` returns, so probe from a thread
                conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
                conn.request("GET", "/healthz")
                seen["status"] = conn.getresponse().status
                conn.close()
                server.shutdown()

            threading.Thread(target=probe, daemon=True).start()

        out = io.StringIO()
        code = dashboard_server.serve(self.tmp, port=0, ready=ready, out=out)
        self.assertEqual(code, 0)
        info = json.loads(out.getvalue())
        self.assertEqual(info["url"], f"http://127.0.0.1:{seen['port']}/")
        self.assertEqual(seen["status"], 200)
        self.assertEqual(info["root"], os.path.abspath(self.tmp))

    def test_serve_reports_port_in_use(self):
        import dashboard_server
        import socket
        blocker = socket.socket()
        self.addCleanup(blocker.close)
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        err = io.StringIO()
        with mock.patch("sys.stderr", err):
            code = dashboard_server.serve(self.tmp, port=blocker.getsockname()[1], out=io.StringIO())
        self.assertEqual(code, 1)
        self.assertIn("cannot bind", err.getvalue())


if __name__ == "__main__":
    unittest.main()
