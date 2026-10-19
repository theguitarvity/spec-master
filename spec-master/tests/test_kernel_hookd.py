"""Deterministic replay evals for the hook daemon.

Each case feeds hookd the JSON a host sends on a lifecycle event and checks
the answer, in audit mode (decide + log, never interfere) and in block mode
(enforce). These are the adversarial cases of the proposal's wave 1: the
agent implementing before analyze, editing core-owned state, running a
destructive command, stopping without verification, resuming after a
compaction.
"""
import io
import json
import os
import subprocess
import sys
import unittest

import _pathfix  # noqa: F401
import kernel_fixtures as fx
from kernel import changes, hookd, step

HOOKD = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "lib", "kernel", "hookd.py")


class HookdReplayTests(unittest.TestCase):
    def setUp(self):
        self.root = fx.make_repo()
        self.env_backup = {name: os.environ.pop(name, None) for name in ("CLAUDE_PROJECT_DIR", "GEMINI_PROJECT_DIR")}

    def tearDown(self):
        for name, value in self.env_backup.items():
            if value is not None:
                os.environ[name] = value
        fx.remove(self.root)

    def block_mode(self):
        fx.write(self.root, ".spec-master/policy.json", json.dumps({"hooks_mode": "block"}))

    def hook(self, event, payload, *flags):
        payload = {"cwd": self.root, **payload}
        out = io.StringIO()
        stdout = sys.stdout
        sys.stdout = out
        try:
            code = hookd.main([event, *flags], stdin=io.StringIO(json.dumps(payload)))
        finally:
            sys.stdout = stdout
        text = out.getvalue().strip()
        return code, (json.loads(text) if text else None)

    def decisions(self):
        path = os.path.join(self.root, hookd.DECISIONS_RELPATH)
        with open(path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh]

    def pre_bash(self, command):
        return self.hook("pre-tool-use", {"tool_name": "Bash", "tool_input": {"command": command}})

    def pre_write(self, path):
        return self.hook("pre-tool-use", {"tool_name": "Write", "tool_input": {"file_path": path, "content": "x"}})

    # --- destructive commands -------------------------------------------------

    def test_audit_mode_logs_but_never_interferes(self):
        code, out = self.pre_bash("git push -f origin main")
        self.assertEqual((code, out), (0, None))
        last = self.decisions()[-1]
        self.assertEqual((last["decision"], last["mode"], last["enforced"]), ("deny", "audit", False))
        self.assertLess(last["elapsed_ms"], 500)

    def test_block_mode_denies_destructive_and_asks_for_publishing(self):
        self.block_mode()
        _, out = self.pre_bash("git reset --hard HEAD~1")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("Principle V", out["hookSpecificOutput"]["permissionDecisionReason"])
        _, out = self.pre_bash("git push origin main")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")
        self.assertEqual(self.pre_bash("python3 -m unittest"), (0, None))

    # --- core-owned files -----------------------------------------------------

    def test_editing_state_json_is_denied(self):
        self.block_mode()
        _, out = self.pre_write(os.path.join(self.root, ".spec-master", "state.json"))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        _, out = self.hook("pre-tool-use", {"tool_name": "Edit", "tool_input": {
            "file_path": ".spec-master/metrics/rounds.json", "old_string": "0", "new_string": "9"}})
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    # --- "implement now" in the legacy flow ----------------------------------

    def test_implementing_while_specify_runs_is_denied(self):
        self.block_mode()
        state = {"version": 1, "context": "ctx.md", "status": "SPECIFYING", "features": [
            {"id": "f1", "spec_directory": "specs/001-f1",
             "phases": {"specify": "RUNNING", "clarify": "PENDING", "plan": "PENDING", "tasks": "PENDING",
                        "analyze": "PENDING", "implement": "PENDING", "validate": "PENDING"}}]}
        fx.write(self.root, ".spec-master/state.json", json.dumps(state))
        _, out = self.pre_write("src/calc.py")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("analyze PASSED", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertEqual(self.pre_write("specs/001-f1/spec.md"), (0, None))
        state["features"][0]["phases"].update({phase: "PASSED" for phase in
                                               ("specify", "clarify", "plan", "tasks", "analyze")})
        state["features"][0]["phases"]["implement"] = "RUNNING"
        fx.write(self.root, ".spec-master/state.json", json.dumps(state))
        self.assertEqual(self.pre_write("src/calc.py"), (0, None))

    # --- a running patch change -----------------------------------------------

    def start_change(self):
        return step.begin(self.root, intent="add() accepts strings", paths=["src/calc.py", "tests/test_calc.py"])

    def test_writes_outside_the_change_envelope_are_denied_tests_allowed(self):
        self.block_mode()
        started = self.start_change()
        self.assertEqual(self.pre_write("src/calc.py"), (0, None))
        self.assertEqual(self.pre_write("tests/test_other.py"), (0, None))
        self.assertEqual(self.pre_write(changes.note_relpath(started["change"])), (0, None))
        _, out = self.pre_write("src/other.py")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        _, out = self.pre_write(".spec-master/changes/%s.json" % started["change"])
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_post_tool_use_flags_a_change_that_outgrew_the_patch_lane(self):
        self.block_mode()
        self.start_change()
        fx.write(self.root, "src/calc.py", fx.CALC + "".join(f"\ndef f{i}():\n    return {i}\n" for i in range(30)))
        _, out = self.hook("post-tool-use", {"tool_name": "Write", "tool_input": {"file_path": "src/calc.py"}})
        self.assertEqual(out["decision"], "block")
        self.assertIn("no longer fits the patch lane", out["reason"])

    def test_stop_without_verification_is_blocked_then_paused(self):
        self.block_mode()
        started = self.start_change()
        for _ in range(hookd.MAX_STOP_REENTRIES):
            _, out = self.hook("stop", {"stop_hook_active": False})
            self.assertEqual(out["decision"], "block")
            self.assertIn("step end", out["reason"])
        self.assertEqual(self.hook("stop", {"stop_hook_active": False}), (0, None))
        self.assertEqual(changes.load(self.root, started["change"])["status"], "PAUSED")

    def test_stop_hook_active_never_loops(self):
        self.block_mode()
        self.start_change()
        self.assertEqual(self.hook("stop", {"stop_hook_active": True}), (0, None))

    def test_audit_mode_stop_does_not_touch_the_record(self):
        started = self.start_change()
        self.assertEqual(self.hook("stop", {"stop_hook_active": False}), (0, None))
        record = changes.load(self.root, started["change"])
        self.assertEqual((record["status"], record["stop_reentries"]), ("RUNNING", 0))

    # --- resume after a compaction -------------------------------------------

    def test_session_start_reinjects_the_current_card(self):
        started = self.start_change()
        _, out = self.hook("session-start", {"source": "compact"})
        context = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn(started["change"], context)
        self.assertIn("Declared files: src/calc.py", context)

    # --- the hooks audit ------------------------------------------------------

    def test_decisions_carry_the_host_session(self):
        self.hook("pre-tool-use", {"session_id": "sess-1", "tool_name": "Bash", "tool_input": {"command": "ls"}})
        self.assertEqual(self.decisions()[-1]["session"], "sess-1")

    def test_session_start_asks_for_the_audit_summary_only_during_an_audit(self):
        self.assertEqual(self.hook("session-start", {"source": "startup"}), (0, None))  # no audit started
        fx.write(self.root, ".spec-master/policy.json",
                 json.dumps({"hooks_mode": "audit", "audit_started_at": "2026-09-28"}))
        _, out = self.hook("session-start", {"source": "startup"})
        context = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("since 2026-09-28", context)
        self.assertIn("harness audit --path . --save", context)
        started = self.start_change()
        _, out = self.hook("session-start", {"source": "compact"})
        both = out["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(both.index(started["change"]) < both.index("harness audit"))
        fx.write(self.root, ".spec-master/policy.json",
                 json.dumps({"hooks_mode": "block", "audit_started_at": "2026-09-28"}))
        _, out = self.hook("session-start", {"source": "startup"})
        self.assertNotIn("harness audit", out["hookSpecificOutput"]["additionalContext"])

    # --- other hosts -------------------------------------------------------------

    def gemini(self, event, hook_event, payload):
        return self.hook(event, {"hook_event_name": hook_event, "session_id": "g1", **payload}, "--host", "gemini")

    def test_gemini_tools_and_replies(self):
        self.block_mode()
        _, out = self.gemini("pre-tool-use", "BeforeTool",
                             {"tool_name": "run_shell_command", "tool_input": {"command": "git push -f origin main"}})
        self.assertEqual(out["decision"], "deny")
        self.assertIn("[Spec Master]", out["reason"])
        _, out = self.gemini("pre-tool-use", "BeforeTool",
                             {"tool_name": "run_shell_command", "tool_input": {"command": "git push origin main"}})
        self.assertEqual(out["decision"], "ask")
        _, out = self.gemini("pre-tool-use", "BeforeTool", {"tool_name": "write_file", "tool_input": {
            "file_path": os.path.join(self.root, ".spec-master", "state.json"), "content": "{}"}})
        self.assertEqual(out["decision"], "deny")
        self.assertEqual(self.gemini("pre-tool-use", "BeforeTool", {"tool_name": "replace", "tool_input": {
            "file_path": "src/calc.py", "old_string": "a", "new_string": "b"}}), (0, None))
        last = self.decisions()[-1]
        self.assertEqual((last["host"], last["tool"], last["session"]), ("gemini", "replace", "g1"))

    def test_gemini_is_detected_without_the_flag(self):
        self.block_mode()
        _, out = self.hook("pre-tool-use", {"hook_event_name": "BeforeTool", "tool_name": "run_shell_command",
                                            "tool_input": {"command": "git reset --hard"}})
        self.assertEqual(out, {"decision": "deny", "reason": out["reason"]})

    def test_gemini_stop_retries_and_post_tool_use_informs(self):
        self.block_mode()
        self.start_change()
        _, out = self.gemini("stop", "AfterAgent", {"stop_hook_active": False})
        self.assertEqual(out["decision"], "deny")
        self.assertIn("step end", out["reason"])
        fx.write(self.root, "src/calc.py", fx.CALC + "".join(f"\ndef f{i}():\n    return {i}\n" for i in range(30)))
        _, out = self.gemini("post-tool-use", "AfterTool", {"tool_name": "write_file",
                                                          "tool_input": {"file_path": "src/calc.py"}})
        self.assertIn("no longer fits the patch lane", out["hookSpecificOutput"]["additionalContext"])

    def test_gemini_audit_mode_and_session_start(self):
        _, out = self.gemini("pre-tool-use", "BeforeTool",
                             {"tool_name": "run_shell_command", "tool_input": {"command": "git push -f"}})
        self.assertIsNone(out)
        self.assertEqual(self.decisions()[-1]["decision"], "deny")
        started = self.start_change()
        _, out = self.gemini("session-start", "SessionStart", {"source": "startup"})
        self.assertIn(started["change"], out["hookSpecificOutput"]["additionalContext"])

    def antigravity(self, event, payload):
        # Antigravity runs hooks from the plugin's directory: only `workspacePaths` names the project.
        payload = {"conversationId": "a1", "workspacePaths": [self.root], "cwd": os.path.dirname(HOOKD), **payload}
        return self.hook(event, payload, "--host", "antigravity")

    def test_antigravity_gates_tools_in_its_workspace(self):
        self.block_mode()

        def run(command):
            return self.antigravity("pre-tool-use", {"toolCall": {"name": "run_command", "args": {
                "CommandLine": command, "Cwd": self.root, "WaitMsBeforeAsync": 5000}}, "stepIdx": 1})[1]
        self.assertEqual(run("git push --force origin main")["decision"], "deny")
        self.assertEqual(run("git push origin main")["decision"], "ask")
        self.assertEqual(run("ls"), {})  # no opinion: never "allow", which would skip the user's approval
        _, out = self.antigravity("pre-tool-use", {"toolCall": {"name": "write_to_file", "args": {
            "TargetFile": os.path.join(self.root, ".spec-master", "state.json"), "CodeContent": "{}"}}})
        self.assertEqual(set(out), {"decision", "reason"})  # protojson: known fields only
        last = self.decisions()[-1]
        self.assertEqual((last["host"], last["tool"], last["session"]), ("antigravity", "write_to_file", "a1"))

    def test_antigravity_stop_continues_the_loop(self):
        self.start_change()
        self.assertEqual(self.antigravity("stop", {"executionNum": 1, "terminationReason": "model_stop",
                                                   "fullyIdle": True})[1], {})  # audit mode
        self.block_mode()
        _, out = self.antigravity("stop", {"executionNum": 2, "terminationReason": "model_stop", "fullyIdle": True})
        self.assertEqual(out["decision"], "continue")
        self.assertIn("step end", out["reason"])

    def test_enforced_means_the_host_got_another_answer(self):
        self.block_mode()
        self.hook("pre-tool-use", {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}},
                  "--host", "codex")  # an "ask" Codex cannot show: its own approvals decide
        self.pre_bash("git push origin main")
        codex, claude = self.decisions()[-2:]
        self.assertEqual((codex["decision"], codex["enforced"]), ("ask", False))
        self.assertEqual((claude["decision"], claude["enforced"]), ("ask", True))

    def test_qwen_speaks_claude(self):
        self.block_mode()
        _, out = self.hook("pre-tool-use", {"tool_name": "Bash", "tool_input": {"command": "git clean -fdx"}},
                           "--host", "qwen")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    # --- robustness -------------------------------------------------------------

    def test_unknown_event_and_garbage_input(self):
        stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            self.assertEqual(hookd.main(["nope"], stdin=io.StringIO("{}")), 1)
        finally:
            sys.stderr = stderr
        cwd = os.getcwd()
        os.chdir(self.root)  # garbage carries no cwd: hookd falls back to the process's
        try:
            code = hookd.main(["pre-tool-use"], stdin=io.StringIO("not json"))
        finally:
            os.chdir(cwd)
        self.assertEqual(code, 0)

    def test_projects_without_spec_master_are_never_written_to(self):
        bare = fx.make_repo(with_tests=False)  # no .spec-master/ at all
        try:
            payload = {"cwd": bare, "tool_name": "Bash", "tool_input": {"command": "git push -f"}}
            out = io.StringIO()
            stdout, sys.stdout = sys.stdout, out
            try:
                self.assertEqual(hookd.main(["pre-tool-use"], stdin=io.StringIO(json.dumps(payload))), 0)
            finally:
                sys.stdout = stdout
            self.assertEqual(out.getvalue(), "")  # audit mode by default
            self.assertFalse(os.path.exists(os.path.join(bare, ".spec-master")))
        finally:
            fx.remove(bare)

    def test_runs_as_a_script_with_the_project_dir_from_the_environment(self):
        self.block_mode()
        proc = subprocess.run(
            [sys.executable, HOOKD, "pre-tool-use"],
            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "git clean -fdx"}}),
            capture_output=True, text=True, env={**os.environ, "CLAUDE_PROJECT_DIR": self.root}, timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")


if __name__ == "__main__":
    unittest.main()
