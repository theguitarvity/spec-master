import json
import unittest

import _pathfix  # noqa: F401
from kernel import hosts

PATCH = """*** Begin Patch
*** Update File: src/calc.py
@@
-    return a + b
+    return int(a) + int(b)
*** Add File: tests/test_new.py
+import unittest
*** Delete File: old.py
*** End Patch
"""


class NormalizeTests(unittest.TestCase):
    def test_shell_and_write_tools_become_canonical(self):
        shell = hosts.normalize({"tool_name": "run_shell_command", "tool_input": {"command": "ls"}})
        self.assertEqual((shell["tool_name"], shell["host_tool_name"]), ("Bash", "run_shell_command"))
        write = hosts.normalize({"tool_name": "write_file", "tool_input": {"absolute_path": "/p/a.py"}})
        self.assertEqual((write["tool_name"], write["tool_input"]["file_path"]), ("Write", "/p/a.py"))
        edit = hosts.normalize({"tool_name": "Edit", "tool_input": {"file_path": "a.py"}})
        self.assertEqual(edit["tool_name"], "Edit")  # Claude's own names are kept
        cursor_write = hosts.normalize({"tool_name": "Delete", "tool_input": {"target_file": "x.py"}})
        self.assertEqual((cursor_write["tool_name"], cursor_write["tool_input"]["file_path"]), ("Write", "x.py"))

    def test_codex_patches_list_every_file(self):
        patch = hosts.normalize({"tool_name": "apply_patch", "tool_input": {"command": PATCH}})
        self.assertEqual(patch["tool_input"]["file_paths"], ["src/calc.py", "tests/test_new.py", "old.py"])
        self.assertEqual(hosts.patch_paths("*** Update File: a.py\n*** Move to: b.py\n"), ["a.py", "b.py"])

    def test_copilot_camel_case_payloads(self):
        edit = hosts.normalize({"sessionId": "s1", "toolName": "edit",
                                "toolArgs": json.dumps({"path": "src/a.py", "old_str": "a", "new_str": "b"})})
        self.assertEqual((edit["tool_name"], edit["tool_input"]["file_path"], edit["session_id"]),
                         ("Write", "src/a.py", "s1"))
        shell = hosts.normalize({"toolName": "bash", "toolArgs": {"command": "git push -f"}})
        self.assertEqual((shell["tool_name"], shell["tool_input"]["command"]), ("Bash", "git push -f"))
        raw = hosts.normalize({"toolName": "bash", "toolArgs": "ls -la"})
        self.assertEqual(raw["tool_input"], {"command": "ls -la"})

    def test_cursor_shell_events_carry_no_tool_name(self):
        shell = hosts.normalize({"hook_event_name": "beforeShellExecution", "command": "git push -f", "cwd": "/p"})
        self.assertEqual((shell["tool_name"], shell["tool_input"]["command"]), ("Bash", "git push -f"))

    def test_antigravity_tool_calls(self):
        shell = hosts.normalize({"conversationId": "a1", "workspacePaths": ["/p"], "toolCall": {
            "name": "run_command", "args": {"CommandLine": "git push -f", "Cwd": "/p"}}})
        self.assertEqual((shell["tool_name"], shell["tool_input"]["command"], shell["session_id"],
                          shell["workspace_roots"]), ("Bash", "git push -f", "a1", ["/p"]))
        edit = hosts.normalize({"toolCall": {"name": "multi_replace_file_content", "args": {"TargetFile": "/p/a.py"}}})
        self.assertEqual((edit["tool_name"], edit["tool_input"]["file_path"]), ("Write", "/p/a.py"))
        stop = hosts.normalize({"conversationId": "a1", "workspacePaths": ["/p"], "fullyIdle": True})
        self.assertEqual((stop["session_id"], stop["workspace_roots"]), ("a1", ["/p"]))

    def test_other_tools_and_bad_input_pass_through(self):
        payload = {"tool_name": "read_file", "tool_input": {"path": "a.py"}}
        self.assertIs(hosts.normalize(payload), payload)
        self.assertEqual(hosts.normalize({"tool_name": "write_file", "tool_input": None})["tool_input"], {})

    def test_detect(self):
        self.assertEqual(hosts.detect({"hook_event_name": "BeforeTool"}), "gemini")
        self.assertEqual(hosts.detect({"hook_event_name": "beforeShellExecution"}), "cursor")
        self.assertEqual(hosts.detect({"hook_event_name": "preToolUse", "cursor_version": "3.9"}), "cursor")
        self.assertEqual(hosts.detect({"hook_event_name": "PreToolUse"}), "claude")
        self.assertEqual(hosts.detect({"conversationId": "a1", "toolCall": {}}), "antigravity")
        self.assertEqual(hosts.detect({}, "kiro"), "kiro")
        self.assertEqual(hosts.detect({}, "unknown-host"), "claude")


class RenderTests(unittest.TestCase):
    def reply(self, host, event, decision, enforce=True, **extra):
        code, out, err = hosts.render(host, event, {"decision": decision, "reason": "why", **extra}, enforce)
        return code, (json.loads(out) if out.startswith("{") else out), err

    def body(self, *args, **kwargs):
        return self.reply(*args, **kwargs)[1]

    def test_audit_mode_never_interferes(self):
        for host in hosts.HOSTS:
            with self.subTest(host=host):
                code, out, err = self.reply(host, "pre-tool-use", "deny", enforce=False)
                self.assertEqual((code, err), (0, ""))
                self.assertIn(out, ("", {}, {"permission": "allow"}))

    def test_claude_and_qwen(self):
        for host in ("claude", "qwen"):
            self.assertEqual(self.body(host, "pre-tool-use", "ask")["hookSpecificOutput"]["permissionDecision"], "ask")
            self.assertEqual(self.body(host, "stop", "block")["decision"], "block")

    def test_codex(self):
        self.assertEqual(self.body("codex", "pre-tool-use", "deny")["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(self.reply("codex", "pre-tool-use", "ask"), (0, "", ""))  # left to Codex's approvals
        self.assertEqual(self.body("codex", "stop", "allow"), {})  # a Stop hook always prints JSON
        self.assertEqual(self.body("codex", "stop", "block")["decision"], "block")

    def test_gemini(self):
        self.assertEqual(self.body("gemini", "pre-tool-use", "deny"), {"decision": "deny", "reason": "[Spec Master] why"})
        self.assertEqual(self.body("gemini", "stop", "block")["decision"], "deny")
        post = self.body("gemini", "post-tool-use", "escalate")
        self.assertEqual(post["hookSpecificOutput"]["additionalContext"], "[Spec Master] why")
        start = self.body("gemini", "session-start", "allow", enforce=False, context="card")
        self.assertEqual(start["hookSpecificOutput"]["additionalContext"], "card")

    def test_copilot_always_answers_one_object(self):
        self.assertEqual(self.body("copilot", "pre-tool-use", "allow"), {})
        self.assertEqual(self.body("copilot", "pre-tool-use", "deny"),
                         {"permissionDecision": "deny", "permissionDecisionReason": "[Spec Master] why"})
        self.assertEqual(self.body("copilot", "stop", "block")["decision"], "block")
        self.assertEqual(self.body("copilot", "post-tool-use", "escalate"), {"additionalContext": "[Spec Master] why"})
        self.assertEqual(self.body("copilot", "session-start", "allow", context="card"), {"additionalContext": "card"})

    def test_cursor_always_answers_json(self):
        self.assertEqual(self.body("cursor", "pre-tool-use", "allow"), {"permission": "allow"})
        denied = self.body("cursor", "pre-tool-use", "deny")
        self.assertEqual((denied["permission"], denied["agent_message"]), ("deny", "[Spec Master] why"))
        self.assertEqual(self.body("cursor", "pre-tool-use", "ask")["permission"], "ask")
        self.assertEqual(self.body("cursor", "stop", "block"), {"followup_message": "[Spec Master] why"})
        self.assertEqual(self.body("cursor", "post-tool-use", "escalate"), {"additional_context": "[Spec Master] why"})
        self.assertEqual(self.body("cursor", "session-start", "allow", context="card"), {"additional_context": "card"})
        self.assertEqual(self.body("cursor", "stop", "allow"), {})

    def test_antigravity_never_answers_allow(self):
        self.assertEqual(self.body("antigravity", "pre-tool-use", "allow"), {})
        self.assertEqual(self.body("antigravity", "pre-tool-use", "ask"), {"decision": "ask", "reason": "[Spec Master] why"})
        self.assertEqual(self.body("antigravity", "stop", "block"), {"decision": "continue", "reason": "[Spec Master] why"})
        self.assertEqual(self.body("antigravity", "stop", "allow"), {})
        self.assertEqual(self.body("antigravity", "post-tool-use", "escalate"), {})

    def test_kiro_blocks_with_exit_code_two(self):
        self.assertEqual(self.reply("kiro", "pre-tool-use", "deny"), (2, "", "[Spec Master] why"))
        self.assertEqual(self.reply("kiro", "pre-tool-use", "ask"), (0, "", ""))
        self.assertEqual(self.body("kiro", "stop", "block"), {"decision": "block", "reason": "[Spec Master] why"})
        self.assertEqual(self.reply("kiro", "session-start", "allow", context="card"), (0, "card", ""))


if __name__ == "__main__":
    unittest.main()
