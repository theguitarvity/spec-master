import _pathfix  # noqa: F401

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pr_step
import traceability

PHASES_DONE = {p: "PASSED" for p in ["specify", "clarify", "plan", "tasks", "analyze", "implement", "validate"]}


def _write(root, rel, text):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _feature(**overrides):
    feature = {
        "id": "login-flow",
        "name": "Login flow",
        "description": "Users can sign in with email and password.",
        "source_requirements": ["docs/context.md#login"],
        "acceptance_criteria": [
            "When the user submits valid credentials, the system shall open the dashboard",
            "Invalid credentials show an error",
        ],
        "branch": "feature/login-flow",
        "spec_directory": "specs/001-login-flow",
        "phases": dict(PHASES_DONE),
    }
    feature.update(overrides)
    return feature


def _state(workflow="git-flow", **feature_overrides):
    return {
        "version": 1,
        "context": "ctx.md",
        "workflow": workflow,
        "status": "VALIDATING",
        "features": [_feature(**feature_overrides)],
        "quality_gates": [
            {"name": "tests", "command": "pytest -q", "result": "PASSED", "exit_code": 0, "blocking": True},
        ],
        "traceability": [
            {"requirement": "FR-001: sign in", "source": "ctx.md", "feature": "login-flow",
             "spec": "specs/001-login-flow/spec.md", "plan": "plan.md", "task": "T001",
             "test": "test_login.py", "status": "VALIDATED"},
            {"requirement": "FR-900: other", "source": "ctx.md", "feature": "other-feature",
             "spec": "", "plan": "", "task": "", "test": "", "status": "PLANNED"},
        ],
    }


def _git_config(url, extra=""):
    return (
        "[core]\n\trepositoryformatversion = 0\n\tbare = false  ; comment\n"
        f'[remote "origin"]\n\turl = {url}\n\tfetch = +refs/heads/*:refs/remotes/origin/*\n'
        f'[branch "main"]\n\tremote = origin\n\tmerge = refs/heads/main\n{extra}'
    )


class _Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.state_path = os.path.join(self.root, ".spec-master", "state.json")
        _write(self.root, "specs/001-login-flow/spec.md", "# Spec\n")
        _write(self.root, "specs/001-login-flow/plan.md", "# Plan\n")
        _write(self.root, "specs/001-login-flow/contracts/api.md", "# API\n")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def make_git(self, url="git@github.com:acme/app.git", heads=("develop",), packed=(), remotes=(),
                 extra_config=""):
        _write(self.root, ".git/config", _git_config(url, extra_config))
        _write(self.root, ".git/HEAD", "ref: refs/heads/feature/login-flow\n")
        for head in heads:
            _write(self.root, f".git/refs/heads/{head}", "0" * 40 + "\n")
        for ref in remotes:
            _write(self.root, f".git/refs/remotes/{ref}", "0" * 40 + "\n")
        if packed:
            lines = ["# pack-refs with: peeled fully-peeled sorted"]
            lines += [f"{'1' * 40} {ref}" for ref in packed]
            _write(self.root, ".git/packed-refs", "\n".join(lines) + "\n")

    def plan(self, state, **kwargs):
        return pr_step.plan_pr(self.root, state, self.state_path, "login-flow", **kwargs)


class GatingTests(_Base):
    def test_trunk_is_noop(self):
        result = self.plan(_state(workflow="trunk"))
        self.assertEqual(result["action"], "noop")
        self.assertIn("Trunk", result["reason"])
        self.assertFalse((Path(self.root) / ".spec-master" / "reports").exists())

    def test_missing_workflow_is_noop(self):
        self.assertEqual(self.plan(_state(workflow=None))["action"], "noop")

    def test_git_flow_without_branch_is_blocked(self):
        result = self.plan(_state(branch=None))
        self.assertEqual(result["action"], "blocked")
        self.assertIn("branch", result["reason"])

    def test_validate_not_passed_is_blocked(self):
        phases = dict(PHASES_DONE, validate="RUNNING")
        result = self.plan(_state(phases=phases))
        self.assertEqual(result["action"], "blocked")
        self.assertIn("RUNNING", result["reason"])
        self.assertFalse(pr_step.body_path_for(self.root, "login-flow").exists())

    def test_head_equal_to_base_is_blocked(self):
        result = self.plan(_state(branch="develop"), base="develop")
        self.assertEqual(result["action"], "blocked")

    def test_unknown_feature_raises(self):
        with self.assertRaises(ValueError):
            pr_step.plan_pr(self.root, _state(), self.state_path, "nope")


class ConfirmRequiredTests(_Base):
    def test_confirm_required_writes_body_with_matrix_and_criteria(self):
        self.make_git()
        _write(self.root, ".spec-master/reports/final-report.md", "# Spec Master Execution Report\nSUCCESS\n")
        result = self.plan(_state())
        self.assertEqual(result["action"], "confirm_required")
        self.assertIn("Ask the user explicitly", result["message"])
        self.assertNotIn("directive", result)
        self.assertEqual(result["head"], "feature/login-flow")
        self.assertEqual(result["base"], "develop")
        self.assertEqual(result["provider"], "github")
        self.assertEqual(result["tool"], "gh")
        self.assertIsInstance(result["tool_available"], bool)

        body_path = Path(result["body_path"])
        self.assertEqual(body_path, Path(self.root) / ".spec-master" / "reports" / "pr-login-flow.md")
        body = body_path.read_text(encoding="utf-8")
        self.assertIn("# Login flow", body)
        self.assertIn("Users can sign in with email and password.", body)
        self.assertIn("- [x] When the user submits valid credentials, the system shall open the dashboard", body)
        self.assertIn("- [x] Invalid credentials show an error", body)
        self.assertIn("| validate | PASSED |", body)
        self.assertIn("## Traceability Matrix — login-flow", body)
        self.assertIn("| FR-001: sign in |", body)
        self.assertNotIn("FR-900", body)  # other feature's rows excluded
        self.assertIn("| tests | PASSED | 0 | yes | pytest -q |", body)
        self.assertIn("`specs/001-login-flow/spec.md`", body)
        self.assertIn("`specs/001-login-flow/contracts/`", body)
        self.assertIn("<summary>Spec Master final report</summary>", body)
        self.assertIn("Generated by Spec Master", body)
        self.assertFalse(list(body_path.parent.glob("*.tmp")))

    def test_body_includes_per_feature_store_rows_and_validate_attempts(self):
        state = _state()
        state["traceability"] = []
        state["traceability_store"] = {"version": 1, "path": "traceability/features"}
        state["quality_gates"] = []
        state["attempts"] = {"validate": [
            {"number": 1, "status": "FAILED", "reason": "tests_failed", "finished_at": "2026-01-01T00:00:00Z",
             "quality_gates": [{"name": "lint", "result": "PASSED", "exit_code": 0, "blocking": False,
                                "command": "ruff check"}]},
            {"number": 2, "status": "PASSED", "reason": "", "finished_at": "2026-01-01T01:00:00Z",
             "quality_gates": [{"name": "tests", "result": "PASSED", "exit_code": 0, "blocking": True,
                                "command": "pytest"}]},
        ]}
        traceability.add_feature_row(self.state_path, {"requirement": "FR-002: store row", "feature": "login-flow",
                                                       "status": "VALIDATED"})
        body = Path(self.plan(state)["body_path"]).read_text(encoding="utf-8")
        self.assertIn("FR-002: store row", body)
        self.assertIn("### Validate Attempts", body)
        self.assertIn("| 1 | FAILED | tests_failed |", body)
        self.assertIn("| tests | PASSED | 0 | yes | pytest |", body)  # gates of the last attempt

    def test_title_carries_issue_id_from_branch(self):
        result = self.plan(_state(branch="PROJ-42"))
        self.assertEqual(result["title"], "Login flow (PROJ-42)")
        self.assertEqual(result["head"], "PROJ-42")

    def test_no_git_repo_means_unknown_provider_and_no_base(self):
        result = self.plan(_state())
        self.assertEqual(result["provider"], "unknown")
        self.assertIsNone(result["base"])
        self.assertIsNone(result["tool"])
        self.assertFalse(result["tool_available"])
        self.assertIn("no git repository", result["base_evidence"])

    def test_rerun_is_idempotent(self):
        first = Path(self.plan(_state())["body_path"]).read_text(encoding="utf-8")
        second = Path(self.plan(_state())["body_path"]).read_text(encoding="utf-8")
        self.assertEqual(first, second)


class DirectiveTests(_Base):
    def test_github_from_remote_url_argument(self):
        self.make_git(url="https://gitlab.com/acme/app.git")  # argument wins over .git/config
        result = self.plan(_state(), confirm=True, remote_url="https://github.com/acme/app.git", draft=True)
        self.assertEqual(result["action"], "open_pr")
        self.assertEqual(result["provider"], "github")
        self.assertEqual(result["remote_evidence"], "argument")
        self.assertEqual(result["directive"]["requires"], ["user_confirmed"])
        self.assertEqual(result["directive"]["argv"], [
            "gh", "pr", "create", "--base", "develop", "--head", "feature/login-flow",
            "--title", "Login flow", "--body-file", result["body_path"], "--draft",
        ])
        self.assertTrue(Path(result["body_path"]).is_file())

    def test_github_from_git_config_scp_url(self):
        self.make_git(url="git@github.com:acme/app.git")
        result = self.plan(_state(), confirm=True)
        self.assertEqual(result["provider"], "github")
        self.assertEqual(result["remote_url"], "git@github.com:acme/app.git")
        self.assertEqual(result["directive"]["argv"][:3], ["gh", "pr", "create"])
        self.assertNotIn("--draft", result["directive"]["argv"])

    def test_gitlab_passes_body_text(self):
        result = self.plan(_state(), confirm=True, remote_url="git@gitlab.example.com:group/app.git", base="main")
        argv = result["directive"]["argv"]
        self.assertEqual(result["provider"], "gitlab")
        self.assertEqual(argv[:3], ["glab", "mr", "create"])
        self.assertEqual(argv[argv.index("--target-branch") + 1], "main")
        self.assertEqual(argv[argv.index("--source-branch") + 1], "feature/login-flow")
        body = Path(result["body_path"]).read_text(encoding="utf-8")
        self.assertEqual(argv[argv.index("--description") + 1], body)
        self.assertIn("--yes", argv)

    def test_azure_from_git_config(self):
        self.make_git(url="https://acme:s3cret@dev.azure.com/acme/proj/_git/app", heads=("main",))
        result = self.plan(_state(), confirm=True, draft=True)
        argv = result["directive"]["argv"]
        self.assertEqual(result["provider"], "azure")
        self.assertEqual(result["remote_url"], "https://***@dev.azure.com/acme/proj/_git/app")
        self.assertNotIn("s3cret", json.dumps(result))
        self.assertEqual(argv[:4], ["az", "repos", "pr", "create"])
        self.assertEqual(argv[argv.index("--source-branch") + 1], "feature/login-flow")
        self.assertEqual(argv[argv.index("--target-branch") + 1], "main")
        self.assertEqual(argv[argv.index("--title") + 1], "Login flow")
        self.assertIn("Traceability Matrix", argv[argv.index("--description") + 1])
        self.assertEqual(argv[-2:], ["--draft", "true"])

    def test_azure_long_description_is_truncated_with_pointer(self):
        long_criteria = [f"Criterion number {i} " + "x" * 200 for i in range(40)]
        result = self.plan(_state(acceptance_criteria=long_criteria), confirm=True,
                           remote_url="git@ssh.dev.azure.com:v3/acme/proj/app", base="main")
        description = result["directive"]["argv"][result["directive"]["argv"].index("--description") + 1]
        self.assertLessEqual(len(description), pr_step.AZURE_DESCRIPTION_LIMIT)
        self.assertIn(".spec-master/reports/pr-login-flow.md", description)
        self.assertTrue(any("4000" in note for note in result["notes"]))

    def test_visualstudio_host_is_azure(self):
        self.assertEqual(pr_step.detect_provider("https://acme.visualstudio.com/proj/_git/app"), "azure")

    def test_unknown_provider_gives_manual_instruction(self):
        result = self.plan(_state(), confirm=True, remote_url="https://git.internal.example/app.git", base="main")
        self.assertEqual(result["provider"], "unknown")
        self.assertIsNone(result["directive"]["argv"])
        self.assertIn(".spec-master/reports/pr-login-flow.md", result["directive"]["manual"])
        self.assertEqual(result["directive"]["requires"], ["user_confirmed"])
        self.assertEqual(result["pre_directives"], [])

    def test_missing_base_omits_flag_and_notes_it(self):
        self.make_git(heads=())
        result = self.plan(_state(), confirm=True)
        self.assertIsNone(result["base"])
        self.assertNotIn("--base", result["directive"]["argv"])
        self.assertTrue(any("default branch" in n for n in result["notes"]))

    def test_push_pre_directive_only_when_branch_not_on_remote(self):
        self.make_git()
        result = self.plan(_state(), confirm=True)
        self.assertFalse(result["head_on_remote"])
        self.assertEqual(result["pre_directives"][0]["argv"],
                         ["git", "push", "-u", "origin", "feature/login-flow"])
        self.assertEqual(result["pre_directives"][0]["requires"], ["user_confirmed"])

        self.make_git(remotes=("origin/feature/login-flow",))
        result = self.plan(_state(), confirm=True)
        self.assertTrue(result["head_on_remote"])
        self.assertEqual(result["pre_directives"], [])

    def test_tool_missing_from_path_is_informational(self):
        with mock.patch.object(pr_step.shutil, "which", return_value=None):
            result = self.plan(_state(), confirm=True, remote_url="https://github.com/a/b", base="main")
        self.assertFalse(result["tool_available"])
        self.assertEqual(result["action"], "open_pr")
        self.assertTrue(any("not on PATH" in n for n in result["notes"]))

    def test_never_executes_anything(self):
        self.make_git()
        with mock.patch.object(subprocess, "run") as run, mock.patch.object(subprocess, "Popen") as popen, \
                mock.patch.object(subprocess, "call") as call, mock.patch.object(os, "system") as system:
            self.plan(_state())
            self.plan(_state(), confirm=True)
            self.plan(_state(), confirm=True, remote_url="https://gitlab.com/a/b")
            self.plan(_state(), confirm=True, remote_url="https://dev.azure.com/a/b/_git/c")
        run.assert_not_called()
        popen.assert_not_called()
        call.assert_not_called()
        system.assert_not_called()


class GitEvidenceTests(_Base):
    def test_base_prefers_develop_then_main_then_master(self):
        self.make_git(heads=("develop", "main"))
        self.assertEqual(pr_step.detect_base(self.root)[0], "develop")
        shutil.rmtree(os.path.join(self.root, ".git"))
        self.make_git(heads=(), packed=("refs/heads/main", "refs/remotes/origin/main"))
        base, evidence = pr_step.detect_base(self.root)
        self.assertEqual(base, "main")
        self.assertIn("refs/heads/main", evidence)
        shutil.rmtree(os.path.join(self.root, ".git"))
        self.make_git(heads=("master",))
        self.assertEqual(pr_step.detect_base(self.root)[0], "master")

    def test_explicit_base_wins(self):
        self.make_git(heads=("develop",))
        self.assertEqual(pr_step.detect_base(self.root, "release/1.0"), ("release/1.0", "argument"))

    def test_git_flow_config_names_develop_branch(self):
        self.make_git(heads=("dev", "main"), extra_config='[gitflow "branch"]\n\tdevelop = dev\n\tmaster = main\n')
        self.assertEqual(pr_step.detect_base(self.root)[0], "dev")

    def test_only_remote_refs_do_not_count_as_local_branch(self):
        self.make_git(heads=(), packed=("refs/remotes/origin/develop",))
        self.assertIsNone(pr_step.detect_base(self.root)[0])

    def test_worktree_git_file_resolves_common_dir(self):
        main = Path(self.root) / "main-repo"
        wt = Path(self.root) / "wt"
        _write(main, ".git/config", _git_config("https://gitlab.com/acme/app.git"))
        _write(main, ".git/refs/heads/develop", "0" * 40)
        _write(main, ".git/worktrees/wt/HEAD", "ref: refs/heads/feature/x\n")
        _write(main, ".git/worktrees/wt/commondir", "../..\n")
        _write(wt, ".git", "gitdir: ../main-repo/.git/worktrees/wt\n")
        self.assertEqual(pr_step.origin_url(wt), ("https://gitlab.com/acme/app.git", "origin"))
        self.assertEqual(pr_step.detect_base(wt)[0], "develop")

    def test_single_non_origin_remote_is_used(self):
        _write(self.root, ".git/config", '[remote "upstream"]\n\turl = https://github.com/acme/app\n')
        self.assertEqual(pr_step.origin_url(self.root), ("https://github.com/acme/app", "upstream"))

    def test_parse_git_config(self):
        parsed = pr_step.parse_git_config(
            "# comment\n[core]\n\tbare = false ; trailing\n\tfilemode\n"
            '[remote "origin"]\n\turl = "git@github.com:a/b.git"\n\tfetch = one\n\tfetch = two\n'
            "[Section.Sub]\nKey = v # c\n"
        )
        self.assertEqual(parsed["core"], {"bare": "false", "filemode": "true"})
        self.assertEqual(parsed["remote origin"]["url"], "git@github.com:a/b.git")
        self.assertEqual(parsed["remote origin"]["fetch"], "two")
        self.assertEqual(parsed["section.sub"]["key"], "v")

    def test_remote_host_and_provider(self):
        cases = {
            "https://github.com/a/b.git": ("github.com", "github"),
            "git@github.com:a/b.git": ("github.com", "github"),
            "ssh://git@gitlab.acme.io:2222/a/b.git": ("gitlab.acme.io", "gitlab"),
            "https://user:tok@dev.azure.com/o/p/_git/r": ("dev.azure.com", "azure"),
            "git@ssh.dev.azure.com:v3/o/p/r": ("ssh.dev.azure.com", "azure"),
            "https://bitbucket.org/a/b.git": ("bitbucket.org", "unknown"),
            "": ("", "unknown"),
        }
        for url, (host, provider) in cases.items():
            with self.subTest(url=url):
                self.assertEqual(pr_step.remote_host(url), host)
                self.assertEqual(pr_step.detect_provider(url), provider)


if __name__ == "__main__":
    unittest.main()
