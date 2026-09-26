import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

import _pathfix  # noqa: F401
import cli
import context_delta

SPEC_V1 = "# Feature\n\n## User Stories\nAs a user...\n\n## Requirements\nFR-001 must work\n"
SPEC_V2 = "# Feature\n\n## User Stories\nAs a user, I want more...\n\n## Edge Cases\nEmpty input\n"
TASKS_V1 = "# Tasks\n\n- [ ] T001 Create model in src/a.py\n- [ ] T002 Write tests\n- [ ] T003 Docs\n"
TASKS_V2 = "# Tasks\n\n- [x] T001 Create model in src/a.py\n- [ ] T002 Write integration tests\n- [ ] T004 New\n"


def _write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class ContextDeltaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state = {
            "context": "ctx.md",
            "features": [{"id": "feat-a", "spec_directory": "specs/001-feat-a"}],
        }
        _write(self.tmp, "ctx.md", "# Context\n")
        _write(self.tmp, ".spec-master/context/tech-stack.md", "# Stack\n## Lang\nPython\n")
        _write(self.tmp, "specs/001-feat-a/spec.md", SPEC_V1)
        _write(self.tmp, "specs/001-feat-a/tasks.md", TASKS_V1)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_first_run_has_no_baseline(self):
        result = context_delta.report(self.tmp, self.state)
        self.assertFalse(result["baseline"])
        self.assertIn("baseline", context_delta.render(result))

    def test_unchanged_tree_reports_nothing(self):
        context_delta.save_snapshot(self.tmp, context_delta.snapshot(self.tmp, self.state))
        result = context_delta.report(self.tmp, self.state)
        self.assertTrue(result["baseline"])
        self.assertEqual(result["artifacts"], [])

    def test_sections_tasks_and_stale_phases(self):
        context_delta.save_snapshot(self.tmp, context_delta.snapshot(self.tmp, self.state))
        _write(self.tmp, "specs/001-feat-a/spec.md", SPEC_V2)
        _write(self.tmp, "specs/001-feat-a/tasks.md", TASKS_V2)
        _write(self.tmp, "specs/001-feat-a/plan.md", "# Plan\n")
        _write(self.tmp, ".spec-master/context/tech-stack.md", "# Stack\n## Lang\nGo\n")
        result = context_delta.report(self.tmp, self.state)
        by_artifact = {e["artifact"]: e for e in result["artifacts"]}

        spec = by_artifact[os.path.join("specs", "001-feat-a", "spec.md")]
        self.assertEqual(spec["change"], "MODIFIED")
        sections = {s["name"]: s["change"] for s in spec["sections"]}
        self.assertEqual(sections, {"User Stories": "MODIFIED", "Edge Cases": "ADDED", "Requirements": "REMOVED"})

        tasks = {t["id"]: t for t in by_artifact[os.path.join("specs", "001-feat-a", "tasks.md")]["tasks"]}
        self.assertEqual(tasks["T001"]["detail"], ["checked"])
        self.assertEqual(tasks["T002"]["detail"], ["text"])
        self.assertEqual(tasks["T003"]["change"], "REMOVED")
        self.assertEqual(tasks["T004"]["change"], "ADDED")

        self.assertEqual(by_artifact[os.path.join("specs", "001-feat-a", "plan.md")]["change"], "ADDED")
        self.assertEqual(result["stale_phases"]["feat-a"], ["clarify", "plan", "tasks", "analyze"])
        self.assertEqual(result["stale_phases"]["*"], ["plan", "tasks", "analyze"])
        self.assertEqual(result["summary"], {"ADDED": 1, "MODIFIED": 3, "REMOVED": 0})

        markdown = context_delta.render(result)
        self.assertIn("## MODIFIED `specs/001-feat-a/spec.md` — feature `feat-a`", markdown)
        self.assertIn("MODIFIED task T001 (checked)", markdown)
        self.assertNotIn("implement,", markdown)

    def test_removed_artifact(self):
        context_delta.save_snapshot(self.tmp, context_delta.snapshot(self.tmp, self.state))
        os.remove(os.path.join(self.tmp, "specs", "001-feat-a", "tasks.md"))
        result = context_delta.report(self.tmp, self.state)
        self.assertEqual(result["artifacts"][0]["change"], "REMOVED")

    def test_cli_snapshot_then_report(self):
        state_path = os.path.join(self.tmp, ".spec-master", "state.json")
        _write(self.tmp, ".spec-master/state.json", json.dumps(self.state))
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(cli.main(["delta", "snapshot", "--path", self.tmp, "--state", state_path]), 0)
        self.assertGreaterEqual(json.loads(buf.getvalue())["artifacts"], 3)
        _write(self.tmp, "specs/001-feat-a/tasks.md", TASKS_V2)
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["delta", "report", "--path", self.tmp, "--state", state_path, "--format", "markdown"])
        self.assertIn("# Context Delta", buf.getvalue())
        self.assertIn("ADDED task T004", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
