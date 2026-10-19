import json
import os
import shutil
import tempfile
import unittest

import _pathfix  # noqa: F401
import discovery

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
CORE_PHASES = {"constitution", "specify", "clarify", "plan", "tasks", "analyze", "implement"}


def _write(root, rel, text=""):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _write_json(root, rel, data):
    _write(root, rel, json.dumps(data))


def _skill(root, skills_dir, name):
    rel = f"{skills_dir}/speckit-{name}/SKILL.md"
    _write(root, rel, f"---\nname: speckit-{name}\ndescription: {name} phase\n---\n")
    return rel


def _integration_json(root, integration, installed=None, separator=None, version="0.16.4", **extra):
    installed = installed or [integration]
    settings = {key: {"script": "sh"} for key in installed}
    if separator is not None:
        settings[integration]["invoke_separator"] = separator
    _write_json(root, ".specify/integration.json", {
        "version": version, "integration_state_schema": 1,
        "installed_integrations": installed, "integration_settings": settings,
        "integration": integration, "default_integration": integration, **extra,
    })


def _manifest(root, integration, files):
    _write_json(root, f".specify/integrations/{integration}.manifest.json", {
        "integration": integration, "version": "0.16.4",
        "files": {path: "0" * 64 for path in files},
    })


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_repo_reports_no_stacks_and_no_invented_commands(self):
        result = discovery.scan(self.tmp)
        self.assertEqual(result["stacks"], [])
        self.assertFalse(result["spec_kit_present"])
        self.assertFalse(result["ci_present"])

    def test_node_repo_detects_scripts(self):
        pkg = {
            "name": "demo",
            "scripts": {"test": "jest", "lint": "eslint .", "build": "vite build"},
        }
        with open(os.path.join(self.tmp, "package.json"), "w", encoding="utf-8") as fh:
            json.dump(pkg, fh)
        result = discovery.scan(self.tmp)
        node_stack = next(s for s in result["stacks"] if s["language"] == "node")
        self.assertEqual(node_stack["commands"]["test"], "npm run test")
        self.assertEqual(node_stack["commands"]["lint"], "npm run lint")
        self.assertEqual(node_stack["commands"]["build"], "npm run build")

    def test_node_repo_prefers_pnpm_when_lockfile_present(self):
        pkg = {"scripts": {"test": "jest"}}
        with open(os.path.join(self.tmp, "package.json"), "w", encoding="utf-8") as fh:
            json.dump(pkg, fh)
        with open(os.path.join(self.tmp, "pnpm-lock.yaml"), "w", encoding="utf-8") as fh:
            fh.write("")
        result = discovery.scan(self.tmp)
        node_stack = next(s for s in result["stacks"] if s["language"] == "node")
        self.assertEqual(node_stack["commands"]["test"], "pnpm run test")

    def test_python_repo_detects_pytest_via_tests_dir(self):
        os.makedirs(os.path.join(self.tmp, "tests"))
        with open(os.path.join(self.tmp, "pyproject.toml"), "w", encoding="utf-8") as fh:
            fh.write("[project]\nname='demo'\n")
        result = discovery.scan(self.tmp)
        py_stack = next(s for s in result["stacks"] if s["language"] == "python")
        self.assertEqual(py_stack["commands"]["test"], "pytest")

    def test_go_repo_detected(self):
        with open(os.path.join(self.tmp, "go.mod"), "w", encoding="utf-8") as fh:
            fh.write("module demo\n")
        result = discovery.scan(self.tmp)
        go_stack = next(s for s in result["stacks"] if s["language"] == "go")
        self.assertEqual(go_stack["commands"]["test"], "go test ./...")

    def test_spec_kit_and_constitution_detection(self):
        os.makedirs(os.path.join(self.tmp, ".specify", "memory"))
        with open(
            os.path.join(self.tmp, ".specify", "memory", "constitution.md"), "w", encoding="utf-8"
        ) as fh:
            fh.write("# Constitution\n")
        result = discovery.scan(self.tmp)
        self.assertTrue(result["spec_kit_present"])
        self.assertTrue(result["constitution_present"])

    def test_speckit_commands_listed(self):
        cmd_dir = os.path.join(self.tmp, ".claude", "commands")
        os.makedirs(cmd_dir)
        for name in ("speckit.specify.md", "speckit.plan.md", "other.md"):
            with open(os.path.join(cmd_dir, name), "w", encoding="utf-8") as fh:
                fh.write("")
        result = discovery.scan(self.tmp)
        self.assertEqual(result["speckit_commands"], ["speckit.plan.md", "speckit.specify.md"])
        self.assertEqual(
            result["speckit_command_paths"]["claude"],
            [".claude/commands/speckit.plan.md", ".claude/commands/speckit.specify.md"],
        )

    def test_opencode_speckit_commands_listed(self):
        cmd_dir = os.path.join(self.tmp, ".opencode", "commands")
        os.makedirs(cmd_dir)
        for name in ("speckit.specify.md", "speckit.plan.md", "other.md"):
            with open(os.path.join(cmd_dir, name), "w", encoding="utf-8") as fh:
                fh.write("")
        result = discovery.scan(self.tmp)
        self.assertEqual(result["speckit_commands"], ["speckit.plan.md", "speckit.specify.md"])
        self.assertEqual(
            result["speckit_command_paths"]["opencode"],
            [".opencode/commands/speckit.plan.md", ".opencode/commands/speckit.specify.md"],
        )

    def test_git_worktree_checkout_is_a_git_repo(self):
        self.assertFalse(discovery.scan(self.tmp)["is_git_repo"])
        _write(self.tmp, ".git", "gitdir: /src/repo/.git/worktrees/feature-a\n")
        self.assertTrue(discovery.scan(self.tmp)["is_git_repo"])
        _write(self.tmp, ".git", "not a gitdir pointer\n")
        self.assertFalse(discovery.scan(self.tmp)["is_git_repo"])


class SpecKitEntrypointTests(unittest.TestCase):
    """Spec Kit >= 0.4.5 skills layout, legacy commands layout, integration state."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_skills_layout_detected_without_integration_json(self):
        plan = _skill(self.tmp, ".claude/skills", "plan")
        specify = _skill(self.tmp, ".claude/skills", "specify")
        _write(self.tmp, ".claude/skills/spec-master/SKILL.md", "---\nname: spec-master\n---\n")
        os.makedirs(os.path.join(self.tmp, ".claude", "skills", "speckit-empty"))  # no SKILL.md
        result = discovery.scan(self.tmp)
        self.assertEqual(result["speckit_commands"], ["speckit-plan", "speckit-specify"])
        self.assertEqual(result["speckit_command_paths"], {"claude": [plan, specify]})
        self.assertEqual(result["speckit_integration"], "claude")
        self.assertEqual(result["speckit_invoke_separator"], "-")
        self.assertEqual(result["speckit_phase_entrypoints"], {"plan": plan, "specify": specify})
        self.assertIsNone(result["speckit_version"])

    def test_commands_layout_implies_dot_separator(self):
        _write(self.tmp, ".claude/commands/speckit.plan.md")
        _write(self.tmp, ".claude/commands/other.md")
        result = discovery.scan(self.tmp)
        self.assertEqual(result["speckit_invoke_separator"], ".")
        self.assertEqual(result["speckit_phase_entrypoints"], {"plan": ".claude/commands/speckit.plan.md"})

    def test_skill_preferred_over_legacy_command_for_the_same_phase(self):
        _write(self.tmp, ".claude/commands/speckit.plan.md")
        skill = _skill(self.tmp, ".claude/skills", "plan")
        result = discovery.scan(self.tmp)
        self.assertEqual(result["speckit_commands"], ["speckit-plan", "speckit.plan.md"])
        self.assertEqual(result["speckit_phase_entrypoints"], {"plan": skill})
        self.assertEqual(result["speckit_invoke_separator"], "-")

    def test_both_layouts_detected_in_every_agent_dir(self):
        for agent_dir in (".claude", ".github", ".agents", ".opencode", ".qwen", ".codex"):
            for rel in (f"{agent_dir}/commands/speckit.plan.md", f"{agent_dir}/skills/speckit-plan/SKILL.md"):
                with self.subTest(path=rel):
                    root = tempfile.mkdtemp()
                    self.addCleanup(shutil.rmtree, root, ignore_errors=True)
                    _write(root, rel)
                    result = discovery.scan(root)
                    paths = [p for group in result["speckit_command_paths"].values() for p in group]
                    self.assertEqual(paths, [rel])
                    self.assertEqual(result["speckit_phase_entrypoints"], {"plan": rel})

    def test_integration_state_and_manifest_are_authoritative(self):
        _integration_json(self.tmp, "claude", separator="-", version="0.16.4")
        plan = _skill(self.tmp, ".claude/skills", "plan")
        specify = _skill(self.tmp, ".claude/skills", "specify")
        _manifest(self.tmp, "claude", [plan, specify, ".claude/skills/speckit-tasks/SKILL.md"])  # tasks deleted
        extension = _skill(self.tmp, ".claude/skills", "git-feature")  # extension: not in the manifest
        _write(self.tmp, ".claude/commands/speckit.implement.md")  # stale legacy command
        result = discovery.scan(self.tmp)
        self.assertEqual(result["speckit_version"], "0.16.4")
        self.assertEqual(result["speckit_integration"], "claude")
        self.assertEqual(result["speckit_invoke_separator"], "-")
        self.assertEqual(result["speckit_phase_entrypoints"], {"plan": plan, "specify": specify})
        # The inventory still shows everything on disk (e.g. a git extension).
        self.assertEqual(result["speckit_commands"],
                         ["speckit-git-feature", "speckit-plan", "speckit-specify", "speckit.implement.md"])
        self.assertEqual(result["speckit_command_paths"]["claude"],
                         [".claude/commands/speckit.implement.md", extension, plan, specify])

    def test_directory_scan_is_the_fallback_without_a_usable_manifest(self):
        cases = {
            "no manifest": None,
            "invalid manifest JSON": "{not json",
            "manifest lists nothing on disk": json.dumps(
                {"files": {".github/skills/speckit-tasks/SKILL.md": "0"}}),
        }
        for label, manifest_text in cases.items():
            with self.subTest(label):
                root = tempfile.mkdtemp()
                self.addCleanup(shutil.rmtree, root, ignore_errors=True)
                _integration_json(root, "copilot", separator="-")
                if manifest_text is not None:
                    _write(root, ".specify/integrations/copilot.manifest.json", manifest_text)
                plan = _skill(root, ".github/skills", "plan")
                _write(root, ".github/skills/spec-master/SKILL.md")
                result = discovery.scan(root)
                self.assertEqual(result["speckit_integration"], "copilot")
                self.assertEqual(result["speckit_command_paths"], {"copilot": [plan]})
                self.assertEqual(result["speckit_phase_entrypoints"], {"plan": plan})

    def test_manifest_paths_outside_the_repository_are_ignored(self):
        root = os.path.join(self.tmp, "repo")
        _write(self.tmp, "outside/speckit-plan/SKILL.md")
        _integration_json(root, "claude", separator="-")
        _manifest(root, "claude", ["../outside/speckit-plan/SKILL.md",
                                   os.path.join(self.tmp, "outside", "speckit-plan", "SKILL.md")])
        result = discovery.scan(root)
        self.assertEqual(result["speckit_commands"], [])
        self.assertEqual(result["speckit_phase_entrypoints"], {})

    def test_shared_agents_dir_belongs_to_the_installed_integration(self):
        plan = _skill(self.tmp, ".agents/skills", "plan")
        self.assertEqual(discovery.scan(self.tmp)["speckit_command_paths"], {"codex": [plan]})
        _integration_json(self.tmp, "zed", separator="-")
        result = discovery.scan(self.tmp)
        self.assertEqual(result["speckit_command_paths"], {"zed": [plan]})
        self.assertEqual(result["speckit_phase_entrypoints"], {"plan": plan})

    def test_multi_install_phase_map_follows_the_default_integration(self):
        _integration_json(self.tmp, "copilot", installed=["claude", "copilot"], separator=".")
        claude_plan = _skill(self.tmp, ".claude/skills", "plan")
        agent = ".github/agents/speckit.plan.agent.md"
        prompt = ".github/prompts/speckit.plan.prompt.md"
        _write(self.tmp, agent)
        _write(self.tmp, prompt)
        _manifest(self.tmp, "claude", [claude_plan])
        _manifest(self.tmp, "copilot", [prompt, agent, ".vscode/settings.json"])
        result = discovery.scan(self.tmp)
        self.assertEqual(result["speckit_integration"], "copilot")
        self.assertEqual(result["speckit_invoke_separator"], ".")
        self.assertEqual(result["speckit_phase_entrypoints"], {"plan": agent})
        self.assertEqual(result["speckit_command_paths"],
                         {"claude": [claude_plan], "copilot": [agent, prompt]})

    def test_unsupported_separator_setting_falls_back_to_the_layout(self):
        _integration_json(self.tmp, "claude", separator="/")
        _skill(self.tmp, ".claude/skills", "plan")
        self.assertEqual(discovery.scan(self.tmp)["speckit_invoke_separator"], "-")

    def test_version_and_integration_from_init_options_on_older_installs(self):
        _write_json(self.tmp, ".specify/init-options.json", {"ai": "claude", "speckit_version": "0.3.2"})
        _write(self.tmp, ".claude/commands/speckit.plan.md")
        result = discovery.scan(self.tmp)
        self.assertEqual(result["speckit_version"], "0.3.2")
        self.assertEqual(result["speckit_integration"], "claude")
        self.assertEqual(result["speckit_invoke_separator"], ".")

    def test_ambiguous_install_without_state_has_no_phase_map(self):
        _skill(self.tmp, ".claude/skills", "plan")
        _write(self.tmp, ".opencode/commands/speckit.plan.md")
        result = discovery.scan(self.tmp)
        self.assertEqual(sorted(result["speckit_command_paths"]), ["claude", "opencode"])
        self.assertIsNone(result["speckit_integration"])
        self.assertIsNone(result["speckit_invoke_separator"])
        self.assertEqual(result["speckit_phase_entrypoints"], {})

    def test_this_repository_reports_its_installed_skills(self):
        state_path = os.path.join(REPO_ROOT, ".specify", "integration.json")
        if not os.path.isfile(state_path):
            self.skipTest("not running inside the spec-master repository")
        with open(state_path, encoding="utf-8") as fh:
            state = json.load(fh)
        result = discovery.scan(REPO_ROOT)
        self.assertEqual(result["speckit_integration"], state["integration"])
        self.assertEqual(result["speckit_version"], state["version"])
        self.assertLessEqual(CORE_PHASES, set(result["speckit_phase_entrypoints"]))
        for path in result["speckit_phase_entrypoints"].values():
            self.assertTrue(os.path.isfile(os.path.join(REPO_ROOT, path)), path)


if __name__ == "__main__":
    unittest.main()
