import json
import os
import shutil
import subprocess
import tempfile
import unittest

import _pathfix  # noqa: F401
from kernel import install


class InstallHooksTests(unittest.TestCase):
    def setUp(self):
        self.project = tempfile.mkdtemp()
        self.settings = os.path.join(self.project, ".claude", "settings.json")

    def tearDown(self):
        shutil.rmtree(self.project, ignore_errors=True)

    def read(self, path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_merges_without_touching_other_settings_or_hooks(self):
        os.makedirs(os.path.dirname(self.settings))
        existing = {"permissions": {"allow": ["Bash(npm test)"]},
                    "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "lint.sh"}]}]}}
        with open(self.settings, "w") as fh:
            json.dump(existing, fh)
        result = install.install_hooks(self.project)
        merged = self.read(self.settings)
        self.assertEqual(merged["permissions"], existing["permissions"])
        pre = merged["hooks"]["PreToolUse"]
        self.assertEqual(pre[0]["hooks"][0]["command"], "lint.sh")
        self.assertIn("kernel/hookd.py", pre[1]["hooks"][0]["command"])
        self.assertEqual(sorted(merged["hooks"]), sorted(install.EVENTS))
        self.assertEqual(result["events"], sorted(install.EVENTS))

    def test_is_idempotent(self):
        install.install_hooks(self.project)
        install.install_hooks(self.project)
        merged = self.read(self.settings)
        for event, entries in merged["hooks"].items():
            with self.subTest(event=event):
                self.assertEqual(len(entries), 1)

    def test_mode_is_written_to_the_policy_and_dry_run_writes_nothing(self):
        install.install_hooks(self.project, dry_run=True, mode="block")
        self.assertFalse(os.path.exists(self.settings))
        install.install_hooks(self.project, mode="block")
        self.assertEqual(self.read(os.path.join(self.project, ".spec-master", "policy.json")), {"hooks_mode": "block"})

    def test_set_mode_keeps_the_policy_and_leaves_settings_alone(self):
        policy_path = os.path.join(self.project, ".spec-master", "policy.json")
        os.makedirs(os.path.dirname(policy_path))
        with open(policy_path, "w") as fh:
            json.dump({"min_lane": "standard"}, fh)
        install.set_mode(self.project, "block")
        self.assertEqual(self.read(policy_path), {"min_lane": "standard", "hooks_mode": "block"})
        self.assertFalse(os.path.exists(self.settings))
        with self.assertRaises(ValueError):
            install.set_mode(self.project, "loud")

    def test_audit_mode_records_when_the_audit_started(self):
        install.set_mode(self.project, "audit")
        policy_path = os.path.join(self.project, ".spec-master", "policy.json")
        started = self.read(policy_path)["audit_started_at"]
        self.assertRegex(started, r"^\d{4}-\d{2}-\d{2}$")
        with open(policy_path, "w") as fh:
            json.dump({"hooks_mode": "audit", "audit_started_at": "2026-01-02"}, fh)
        install.set_mode(self.project, "audit")
        install.set_mode(self.project, "block")
        self.assertEqual(self.read(policy_path), {"hooks_mode": "block", "audit_started_at": "2026-01-02"})
        with open(os.path.join(self.project, ".spec-master", ".gitignore")) as fh:
            self.assertIn("hooks/decisions.jsonl", fh.read())

    def test_hook_commands_point_at_a_real_engine(self):
        with self.assertRaises(ValueError):
            install.install_hooks(self.project, engine=self.project)
        for entry in install.hooks_block(str(install.ENGINE))["PreToolUse"]:
            script = entry["hooks"][0]["command"].split()[1].strip("'")
            self.assertTrue(os.path.isfile(script))

    def test_an_engine_inside_the_project_is_portable_and_fails_open(self):
        os.symlink(str(install.ENGINE), os.path.join(self.project, "spec-master"))
        install.install_hooks(self.project, engine=os.path.join(self.project, "spec-master"), mode="block")
        command = self.read(self.settings)["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        self.assertEqual(command, 'python3 "$CLAUDE_PROJECT_DIR"/spec-master/lib/kernel/hookd.py pre-tool-use || true')
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push --force"}})

        def run(project_dir):
            return subprocess.run(["sh", "-c", command], input=payload, capture_output=True, text=True, timeout=30,
                                  env={**os.environ, "CLAUDE_PROJECT_DIR": project_dir})
        enforced = run(self.project)
        self.assertEqual(enforced.returncode, 0, enforced.stderr)
        self.assertEqual(json.loads(enforced.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")
        missing = run(os.path.join(self.project, "nowhere"))  # engine gone: never a blocking error
        self.assertEqual((missing.returncode, missing.stdout), (0, ""))

    def test_qwen_gets_the_same_hooks_in_its_settings(self):
        os.symlink(str(install.ENGINE), os.path.join(self.project, "spec-master"))
        result = install.install_hooks(self.project, engine=os.path.join(self.project, "spec-master"), host="qwen")
        path = os.path.join(self.project, ".qwen", "settings.json")
        self.assertEqual((result["host"], result["settings"]), ("qwen", path))
        hooks = self.read(path)["hooks"]
        self.assertEqual(sorted(hooks), sorted(install.EVENTS))
        self.assertEqual(hooks["PreToolUse"][0]["hooks"][0]["command"],
                         'python3 "$QWEN_PROJECT_DIR"/spec-master/lib/kernel/hookd.py pre-tool-use --host qwen || true')
        self.assertFalse(os.path.exists(self.settings))

    def test_kiro_gets_its_own_hooks_file(self):
        os.symlink(str(install.ENGINE), os.path.join(self.project, "spec-master"))
        engine = os.path.join(self.project, "spec-master")
        result = install.install_hooks(self.project, engine=engine, mode="block", host="kiro")
        path = os.path.join(self.project, ".kiro", "hooks", "spec-master.json")
        self.assertEqual((result["host"], result["settings"]), ("kiro", path))
        first = self.read(path)
        install.install_hooks(self.project, engine=engine, host="kiro")  # rewritten, never duplicated
        hooks = self.read(path)
        self.assertEqual(hooks, first)
        self.assertEqual(hooks["version"], "v1")
        self.assertEqual([h["trigger"] for h in hooks["hooks"]], list(install.KIRO_EVENTS))
        self.assertFalse(os.path.exists(self.settings))
        pre = hooks["hooks"][0]
        self.assertEqual(pre["action"]["command"], "test -f spec-master/lib/kernel/hookd.py && "
                                                   "python3 spec-master/lib/kernel/hookd.py pre-tool-use --host kiro")
        with self.assertRaises(ValueError):
            install.install_hooks(self.project, host="vim")

    def test_kiro_blocks_through_exit_code_two_and_fails_open(self):
        os.symlink(str(install.ENGINE), os.path.join(self.project, "spec-master"))
        install.install_hooks(self.project, engine=os.path.join(self.project, "spec-master"), mode="block", host="kiro")
        command = self.read(os.path.join(self.project, ".kiro", "hooks", "spec-master.json"))["hooks"][0]["action"]["command"]

        def run(cwd, tool, tool_input):  # Kiro runs command hooks from the project root
            payload = {"hook_event_name": "preToolUse", "cwd": cwd, "tool_name": tool, "tool_input": tool_input}
            return subprocess.run(["sh", "-c", command], input=json.dumps(payload), capture_output=True, text=True,
                                  timeout=30, cwd=cwd)
        denied = run(self.project, "execute_bash", {"command": "git push --force origin main"})
        self.assertEqual(denied.returncode, 2, denied.stdout)
        self.assertIn("[Spec Master]", denied.stderr)
        state = os.path.join(self.project, ".spec-master", "state.json")
        self.assertEqual(run(self.project, "fs_write", {"command": "create", "path": state}).returncode, 2)
        self.assertEqual(run(self.project, "execute_bash", {"command": "ls"}).returncode, 0)
        os.unlink(os.path.join(self.project, "spec-master"))
        gone = run(self.project, "execute_bash", {"command": "git push --force"})
        self.assertNotEqual(gone.returncode, 2)  # a missing engine only warns

    def test_plugin_hooks_json_declares_the_same_events(self):
        path = os.path.join(str(install.ENGINE), "hooks", "hooks.json")
        declared = self.read(path)["hooks"]
        self.assertEqual(sorted(declared), sorted(install.EVENTS))
        for event, (matcher, name, _timeout) in install.EVENTS.items():
            with self.subTest(event=event):
                entry = declared[event][0]
                self.assertEqual(entry.get("matcher"), matcher)
                self.assertTrue(entry["hooks"][0]["command"].endswith(f'hookd.py" {name}'))


if __name__ == "__main__":
    unittest.main()
