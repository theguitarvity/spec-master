import importlib.util
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import _pathfix  # noqa: F401
import packaging
from kernel import hookd, hosts

ENGINE = Path(packaging.__file__).resolve().parent.parent
ROOT = ENGINE.parent
FILES = packaging.render()
# The closed key sets of the Agent Plugins 1.0.0 schemas (plugin.schema.json, mcp.schema.json).
AGENT_PLUGIN_KEYS = {"$schema", "name", "version", "description", "author", "homepage", "repository", "license",
                     "keywords", "extensions"}
AGENT_PLUGIN_NAME = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
STDIO_SERVER_KEYS = {"type", "command", "args", "env", "cwd"}
# Where each host's hook command expects the engine: plugin-root variable -> directory. A
# relative path is resolved from the repository root (Antigravity runs hooks from there).
ROOT_VARIABLES = {"${CLAUDE_PLUGIN_ROOT}": ENGINE, "${PLUGIN_ROOT}": ENGINE, "$PLUGIN_ROOT": ENGINE,
                  "${CURSOR_PLUGIN_ROOT}": ENGINE, "${extensionPath}": ROOT}
ALL_EVENTS = set(packaging.EVENTS)
HOOK_FILES = {  # generated hooks file -> (host whose dialect its commands ask for, events it wires)
    "spec-master/hooks/hooks.json": ("claude", ALL_EVENTS),
    "spec-master/hooks/codex-hooks.json": ("codex", ALL_EVENTS),
    "spec-master/hooks/copilot-hooks.json": ("copilot", ALL_EVENTS),
    "spec-master/hooks/cursor-hooks.json": ("cursor", ALL_EVENTS),
    "hooks/hooks.json": ("gemini", ALL_EVENTS),
    "hooks.json": ("antigravity", {"pre-tool-use", "stop"}),  # no session start; PostToolUse replies nothing
}


def parsed(relative):
    return json.loads(FILES[relative])


def commands(value):
    """Every hook command string in a hooks file, whatever its shape."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("command", "bash") and isinstance(item, str):
                yield item
            else:
                yield from commands(item)
    elif isinstance(value, list):
        for item in value:
            yield from commands(item)


class GeneratedFilesTests(unittest.TestCase):
    @unittest.skipUnless((ROOT / ".git").exists(), "the engine is not inside the Spec Master repository")
    def test_committed_files_match_the_generator(self):
        self.assertEqual(packaging.check(ROOT), [],
                         "run `python3 spec-master/lib/packaging.py generate` and commit the result")

    def test_generate_then_check_round_trips(self):
        target = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, target, True)
        self.assertEqual(sorted(packaging.generate(target)), sorted(FILES))
        self.assertEqual(packaging.check(target), [])
        self.assertEqual(packaging.generate(target), [])  # nothing left to write
        Path(target, "plugin.json").write_text("{}\n", encoding="utf-8")
        self.assertEqual(packaging.check(target), ["plugin.json"])

    def test_every_json_file_parses(self):
        for relative, content in FILES.items():
            if relative.endswith(".json"):
                with self.subTest(file=relative):
                    self.assertIsInstance(json.loads(content), dict)

    def test_one_version_everywhere(self):
        manifests = ["plugin.json", "gemini-extension.json", "spec-master/.claude-plugin/plugin.json",
                     "spec-master/.codex-plugin/plugin.json", "spec-master/.github/plugin/plugin.json",
                     "spec-master/.cursor-plugin/plugin.json"]
        for relative in manifests:
            with self.subTest(file=relative):
                self.assertEqual(parsed(relative)["version"], packaging.VERSION)
                self.assertEqual(parsed(relative)["name"], packaging.NAME)
        self.assertEqual(parsed(".claude-plugin/marketplace.json")["plugins"][0]["version"], packaging.VERSION)
        server = (ENGINE / packaging.MCP_SERVER).read_text(encoding="utf-8")
        self.assertIn(f'SERVER_VERSION = "{packaging.VERSION}"', server)


class AgentPluginsTests(unittest.TestCase):
    def test_manifest_follows_the_closed_1_0_0_schema(self):
        manifest = parsed("plugin.json")
        self.assertEqual(manifest["$schema"], "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json")
        self.assertLessEqual(set(manifest), AGENT_PLUGIN_KEYS)
        self.assertRegex(manifest["name"], AGENT_PLUGIN_NAME)
        self.assertLessEqual(set(manifest["author"]), {"name", "email", "url"})

    def test_mcp_servers_follow_the_1_0_0_schema(self):
        mcp = parsed("mcp.json")
        self.assertEqual(mcp["$schema"], "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json")
        self.assertEqual(set(mcp), {"$schema", "mcpServers"})
        for name, server in mcp["mcpServers"].items():
            with self.subTest(server=name):
                self.assertEqual(server["type"], "stdio")
                self.assertLessEqual(set(server), STDIO_SERVER_KEYS)
                script = server["args"][0].replace("${PLUGIN_ROOT}", str(ROOT))
                self.assertTrue(Path(script).is_file(), script)


def hookd_call(command):
    """(hookd path on disk, event, --host value) of one hook command."""
    tokens = shlex.split(command.split("||")[0])
    index = next(i for i, token in enumerate(tokens) if token.endswith("hookd.py"))
    script = tokens[index]
    for variable, directory in ROOT_VARIABLES.items():
        if script.startswith(variable + "/"):
            script = str(directory) + script[len(variable):]
            break
    host = tokens[tokens.index("--host") + 1] if "--host" in tokens else None
    return ROOT / script, tokens[index + 1], host


class HookFilesTests(unittest.TestCase):
    def test_every_command_runs_hookd_in_its_hosts_dialect(self):
        for relative, (host, _events) in HOOK_FILES.items():
            found = list(commands(parsed(relative)))
            self.assertTrue(found, relative)
            for command in found:
                with self.subTest(file=relative, command=command):
                    script, event, requested = hookd_call(command)
                    self.assertTrue(script.is_file(), script)
                    self.assertIn(event, hookd.HANDLERS)
                    # Claude's payload is read as Claude's without a flag; every other host names itself.
                    self.assertEqual(requested, None if host == "claude" else host)
                    self.assertIn(host, hosts.HOSTS)

    def test_every_hook_file_wires_its_events(self):
        for relative, (_host, events) in HOOK_FILES.items():
            with self.subTest(file=relative):
                self.assertEqual({hookd_call(c)[1] for c in commands(parsed(relative))}, events)

    def test_copilot_never_fails_closed_on_a_missing_engine(self):
        for command in commands(parsed("spec-master/hooks/copilot-hooks.json")):
            self.assertTrue(command.endswith("|| echo '{}'"), command)

    def test_gemini_timeouts_are_milliseconds(self):
        for entries in parsed("hooks/hooks.json")["hooks"].values():
            for hook in entries[0]["hooks"]:
                self.assertGreaterEqual(hook["timeout"], 1000)

    def test_every_plugin_starts_the_mcp_server_with_the_entrypoint_only(self):
        declarations = {"spec-master/.mcp.json": "mcpServers", "spec-master/.codex-mcp.json": "mcpServers",
                        "mcp.json": "mcpServers", "gemini-extension.json": "mcpServers",
                        "mcp_config.json": "mcpServers"}
        for relative, key in declarations.items():
            with self.subTest(file=relative):
                args = parsed(relative)[key][packaging.NAME]["args"]
                self.assertEqual(args[1:], ["--tools", "entrypoint"])

    def test_antigravity_runs_everything_from_the_plugin_directory(self):
        server = parsed("mcp_config.json")["mcpServers"][packaging.NAME]
        self.assertNotIn("cwd", server)
        self.assertTrue((ROOT / server["args"][0]).is_file())
        for command in commands(parsed("hooks.json")):
            self.assertNotIn("$", command)  # nothing for Antigravity to expand


class SkillTests(unittest.TestCase):
    def test_skills_are_path_free_and_identical_in_both_roots(self):
        import cli
        for name, spec in packaging.SKILLS.items():
            with self.subTest(skill=name):
                text = FILES[f"skills/{name}/SKILL.md"]
                self.assertEqual(text, FILES[f"spec-master/skills/{name}/SKILL.md"])
                self.assertTrue(text.startswith(f"---\nname: {name}\ndescription: "))
                frontmatter = dict(line.split(": ", 1) for line in text.split("---\n")[1].splitlines())
                self.assertEqual(json.loads(frontmatter["description"]), spec["description"])  # quoted scalar
                self.assertIn("harness_entrypoint", text)
                self.assertIn(spec["flow"], cli.ENTRYPOINT_TEMPLATES)
                self.assertNotIn("CLAUDE_PLUGIN_ROOT", text)

    @unittest.skipUnless(importlib.util.find_spec("yaml"), "PyYAML is optional")
    def test_frontmatter_is_strict_yaml(self):
        import yaml
        for name, spec in packaging.SKILLS.items():
            with self.subTest(skill=name):
                data = yaml.safe_load(FILES[f"skills/{name}/SKILL.md"].split("---\n")[1])
                self.assertEqual(data, {"name": name, "description": spec["description"]})

    def test_the_fallback_command_renders_the_instructions(self):
        result = subprocess.run([sys.executable, str(ENGINE / "lib" / "cli.py"), "harness", "entrypoint",
                                 "--flow", "lane", "--argument", "patch fix the typo"],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        reply = json.loads(result.stdout)
        self.assertEqual(reply["engine"], ENGINE.as_posix())
        self.assertIn(f"{ENGINE.as_posix()}/cards/router.md", reply["instructions"])
        self.assertIn("patch fix the typo", reply["instructions"])


if __name__ == "__main__":
    unittest.main()
