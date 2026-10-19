"""P6a: the MCP server dispatches CLI calls in-process instead of one subprocess each."""
import _pathfix  # noqa: F401

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MCP_DIR = Path(__file__).resolve().parent.parent / "mcp"
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

import spec_master_mcp as mcp  # noqa: E402

PREFLIGHT = ["policy", "preflight", "ls -la"]
STATE_SHOW = ["state", "show", "--path", ".spec-master/state.json"]


class InProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = str(Path(self.tmp.name).resolve())

    def server(self, inprocess):
        return mcp.Server(project_root=self.root, timeout=60, inprocess=inprocess)

    def test_default_is_in_process_and_env_can_disable_it(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SPEC_MASTER_MCP_INPROCESS", None)
            os.environ.pop("SPEC_MASTER_MCP_TIMEOUT", None)
            self.assertTrue(mcp.Server(project_root=self.root).inprocess)
        with mock.patch.dict(os.environ, {"SPEC_MASTER_MCP_INPROCESS": "0"}):
            self.assertFalse(mcp.Server(project_root=self.root).inprocess)

    def test_an_explicit_timeout_keeps_the_enforceable_subprocess_path(self):
        os.environ.pop("SPEC_MASTER_MCP_INPROCESS", None)
        self.assertFalse(mcp.Server(project_root=self.root, timeout=5).inprocess)
        with mock.patch.dict(os.environ, {"SPEC_MASTER_MCP_TIMEOUT": "9"}):
            self.assertFalse(mcp.Server(project_root=self.root).inprocess)

    def test_no_subprocess_is_started_for_a_normal_call(self):
        server = self.server(True)
        with mock.patch.object(subprocess, "run", side_effect=AssertionError("subprocess used")):
            result = server.run_cli(PREFLIGHT)
        self.assertFalse(result["isError"])

    def test_success_result_matches_the_subprocess_result(self):
        inproc = self.server(True).run_cli(PREFLIGHT)
        sub = self.server(False).run_cli(PREFLIGHT)
        self.assertEqual(inproc, sub)
        self.assertIn("structuredContent", inproc)

    def test_handled_error_matches_the_subprocess_result(self):
        inproc = self.server(True).run_cli(STATE_SHOW)
        sub = self.server(False).run_cli(STATE_SHOW)
        self.assertEqual(inproc["isError"], sub["isError"])
        self.assertEqual(inproc["content"][0], sub["content"][0])

    def test_argparse_exit_is_an_error_result_not_a_crash(self):
        result = self.server(True).run_cli(["state", "no-such-action"])
        self.assertTrue(result["isError"])
        self.assertIn("exit code 2", result["content"][-1]["text"])

    def test_unexpected_exception_is_an_error_result(self):
        import cli
        with mock.patch.object(cli, "main", side_effect=RuntimeError("boom")):
            result = self.server(True).run_cli(PREFLIGHT)
        self.assertTrue(result["isError"])
        self.assertIn("boom", result["content"][-1]["text"])

    def test_cwd_and_streams_are_restored(self):
        before_cwd, before_out, before_err = os.getcwd(), sys.stdout, sys.stderr
        self.server(True).run_cli(PREFLIGHT)
        self.assertEqual(os.getcwd(), before_cwd)
        self.assertIs(sys.stdout, before_out)
        self.assertIs(sys.stderr, before_err)

    def test_relative_paths_resolve_against_the_project_root(self):
        server = self.server(True)
        seen = []
        import cli

        def fake_main(argv):
            seen.append(os.getcwd())
            return 0

        with mock.patch.object(cli, "main", fake_main):
            server.run_cli(PREFLIGHT)
        self.assertEqual(seen, [self.root])

    def test_long_or_hostile_groups_still_use_a_subprocess(self):
        server = self.server(True)
        sentinel = {"content": [{"type": "text", "text": "sub"}], "isError": False}
        with mock.patch.object(server, "_run_cli_subprocess", return_value=sentinel) as sub:
            for group in ("controller", "gates", "evals", "doctor", "dashboard"):
                self.assertIs(server.run_cli([group, "x"]), sentinel)
            self.assertEqual(sub.call_count, 5)

    def test_in_process_failure_to_import_falls_back_to_subprocess(self):
        server = self.server(True)
        sentinel = {"content": [{"type": "text", "text": "sub"}], "isError": False}
        with mock.patch.object(server, "_run_cli_inprocess", side_effect=ImportError("nope")), \
                mock.patch.object(server, "_run_cli_subprocess", return_value=sentinel):
            self.assertIs(server.run_cli(PREFLIGHT), sentinel)

    def test_stray_fd1_writes_do_not_reach_the_protocol_channel(self):
        server = self.server(True)
        import cli
        read_fd, write_fd = os.pipe()
        saved = os.dup(1)
        os.dup2(write_fd, 1)

        def noisy(argv):
            os.write(1, b"STRAY")
            return 0

        try:
            with mock.patch.object(cli, "main", noisy):
                server.run_cli(PREFLIGHT)
        finally:
            os.dup2(saved, 1)
            os.close(saved)
            os.close(write_fd)
        os.set_blocking(read_fd, False)
        try:
            leaked = os.read(read_fd, 100)
        except BlockingIOError:
            leaked = b""
        os.close(read_fd)
        self.assertEqual(leaked, b"")


if __name__ == "__main__":
    unittest.main()
