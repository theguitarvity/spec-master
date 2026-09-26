import os
import shutil
import tempfile
import unittest

import _pathfix  # noqa: F401
import tracker_orchestration
import traceability

_GITHUB_ISSUES_FRONTMATTER = """---
name: "speckit-taskstoissues"
description: "Convert existing tasks into actionable, dependency-ordered GitHub issues for the feature based on available design artifacts."
argument-hint: "Optional filter or label for GitHub issues"
compatibility: "Requires spec-kit project structure with .specify/ directory"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/taskstoissues.md"
user-invocable: true
disable-model-invocation: false
---

body
"""


def _write_skill(base: str, integration_dir: str, skill_name: str, content: str) -> None:
    skill_dir = os.path.join(base, integration_dir, skill_name)
    os.makedirs(skill_dir, exist_ok=True)
    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write(content)


class DetectTrackerExtensionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_detect_tracker_extensions_finds_github_issues_skill(self):
        _write_skill(
            self.tmp, os.path.join(".claude", "skills"), "speckit-taskstoissues",
            _GITHUB_ISSUES_FRONTMATTER,
        )
        result = tracker_orchestration.detect_tracker_extensions(self.tmp)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["skill"], "speckit-taskstoissues")
        self.assertEqual(result[0]["integration"], "claude")
        self.assertEqual(result[0]["tracker_type"], "github_issues")
        self.assertEqual(
            result[0]["path"], os.path.join(".claude", "skills", "speckit-taskstoissues", "SKILL.md")
        )

    def test_detect_tracker_extensions_empty_when_no_skills_dir(self):
        result = tracker_orchestration.detect_tracker_extensions(self.tmp)
        self.assertEqual(result, [])

    def test_detect_tracker_extensions_skips_non_tracker_skill(self):
        _write_skill(
            self.tmp, os.path.join(".claude", "skills"), "speckit-lint",
            '---\nname: "speckit-lint"\ndescription: "Run project linters."\n---\n',
        )
        result = tracker_orchestration.detect_tracker_extensions(self.tmp)
        self.assertEqual(result, [])

    def test_detect_tracker_extensions_skips_malformed_frontmatter(self):
        _write_skill(
            self.tmp, os.path.join(".claude", "skills"), "speckit-broken",
            "---\nname: broken\ndescription: missing closing fence, mentions jira\n",
        )
        result = tracker_orchestration.detect_tracker_extensions(self.tmp)
        self.assertEqual(result, [])


class OrchestrateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_orchestrate_returns_invocation_for_detected_extension(self):
        _write_skill(
            self.tmp, os.path.join(".claude", "skills"), "speckit-taskstoissues",
            _GITHUB_ISSUES_FRONTMATTER,
        )
        result = tracker_orchestration.orchestrate(self.tmp)
        self.assertTrue(result["orchestrated"])
        self.assertEqual(
            result["invocations"],
            [{"skill": "speckit-taskstoissues", "tracker_type": "github_issues", "command": "/speckit-taskstoissues"}],
        )
        self.assertIsNone(result["reason"])

    def test_orchestrate_lists_all_when_multiple_detected(self):
        _write_skill(
            self.tmp, os.path.join(".claude", "skills"), "speckit-taskstoissues",
            _GITHUB_ISSUES_FRONTMATTER,
        )
        _write_skill(
            self.tmp, os.path.join(".opencode", "skill"), "speckit-jira-sync",
            '---\nname: "speckit-jira-sync"\ndescription: "Sync tasks with Jira issues."\n---\n',
        )
        result = tracker_orchestration.orchestrate(self.tmp)
        self.assertEqual(len(result["invocations"]), 2)
        tracker_types = {inv["tracker_type"] for inv in result["invocations"]}
        self.assertEqual(tracker_types, {"github_issues", "jira"})

    def test_orchestrate_returns_false_when_nothing_detected(self):
        result = tracker_orchestration.orchestrate(self.tmp)
        self.assertEqual(
            result,
            {"orchestrated": False, "extensions": [], "invocations": [], "reason": result["reason"]},
        )
        self.assertTrue(result["reason"])

    def test_tracker_orchestration_module_has_no_network_imports(self):
        module_path = os.path.join(os.path.dirname(tracker_orchestration.__file__), "tracker_orchestration.py")
        with open(module_path, "r", encoding="utf-8") as fh:
            source = fh.read()
        for forbidden in ("import requests", "import urllib", "import http.client", "import socket"):
            self.assertNotIn(forbidden, source)


class TraceabilityIssueColumnTests(unittest.TestCase):
    def test_traceability_add_row_issue_defaults_empty(self):
        state = {}
        traceability.add_row(state, {"requirement": "R001", "source": "app-features.md"})
        row = state["traceability"][0]
        self.assertEqual(row["issue"], "")

    def test_traceability_add_row_with_issue_renders_in_matrix(self):
        state = {"traceability": []}
        traceability.add_row(state, {
            "requirement": "FR-004", "source": "spec.md", "issue": "https://github.com/x/y/issues/1",
        })
        rendered = traceability.render(state)
        self.assertIn("https://github.com/x/y/issues/1", rendered)


if __name__ == "__main__":
    unittest.main()
