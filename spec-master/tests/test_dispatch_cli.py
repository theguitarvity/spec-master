import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import _pathfix  # noqa: F401
import cli

LIB = Path(cli.__file__).resolve().parent
FEATURE = "feat"


def _run(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(list(argv))
    text = buf.getvalue()
    return code, (json.loads(text) if text.strip() else None)


def _project():
    tmp = tempfile.TemporaryDirectory()
    root = os.path.realpath(tmp.name)
    os.makedirs(os.path.join(root, ".spec-master"))
    os.makedirs(os.path.join(root, ".git"))
    packages = [{"id": "A", "feature_id": FEATURE, "title": "a", "owner_agent": "backend-dev",
                 "depends_on": [], "owned_paths": ["src/a/*"]},
                {"id": "B", "feature_id": FEATURE, "title": "b", "owner_agent": "frontend-dev",
                 "depends_on": [], "owned_paths": ["src/b/*"]}]
    with open(os.path.join(root, ".spec-master", "workstreams.json"), "w", encoding="utf-8") as fh:
        json.dump({"packages": packages}, fh)
    return tmp, root


class DispatchCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp, self.root = _project()
        self.addCleanup(self.tmp.cleanup)

    def test_manifest_command_prints_the_manifest(self):
        code, out = _run("dispatch", "manifest", "--feature", FEATURE, "--wave", "0", "--path", self.root)
        self.assertEqual(code, 0)
        self.assertEqual(out["schema"], "spec-master.dispatch/v1")
        self.assertEqual(len(out["entries"]), 4)

    def test_max_agents_is_applied_and_validated(self):
        _, out = _run("dispatch", "manifest", "--feature", FEATURE, "--wave", "0", "--max-agents", "1",
                      "--path", self.root)
        self.assertEqual([len(b) for b in out["batches"]], [1, 1])
        code, out = _run("dispatch", "manifest", "--feature", FEATURE, "--wave", "0", "--max-agents", "9",
                         "--path", self.root)
        self.assertEqual(code, 1)
        self.assertIn("error", out)

    def test_patch_lane_is_refused_unless_forced_with_a_reason(self):
        code, out = _run("dispatch", "manifest", "--feature", FEATURE, "--wave", "0", "--lane", "patch",
                         "--path", self.root)
        self.assertEqual(code, 1)
        code, out = _run("dispatch", "manifest", "--feature", FEATURE, "--wave", "0", "--lane", "patch",
                         "--force-lane", "benchmark", "--path", self.root)
        self.assertEqual(code, 0)
        self.assertEqual(out["forced_lane_reason"], "benchmark")

    def test_result_status_and_aggregate_commands(self):
        text_file = os.path.join(self.root, "out.txt")
        with open(text_file, "w", encoding="utf-8") as fh:
            fh.write('done\n```json\n{"phase_result": "artifact_updated", "summary": "ok"}\n```\n')
        code, out = _run("dispatch", "result", "--feature", FEATURE, "--wave", "0", "--package", "A",
                         "--agent-id", "ag1", "--text-file", text_file, "--path", self.root)
        self.assertEqual(code, 0)
        self.assertEqual(out["phase_result"], "artifact_updated")
        code, out = _run("dispatch", "status", "--feature", FEATURE, "--wave", "0", "--path", self.root)
        self.assertEqual(code, 0)
        self.assertTrue(any(e["result_recorded"] for e in out["entries"]))

    def test_dispatch_does_not_load_heavy_modules_at_parser_build(self):
        code = ("import sys, cli\ncli.build_parser()\n"
                "print('dispatch' in sys.modules, 'worktree' in sys.modules)")
        proc = subprocess.run([sys.executable, "-c", code], cwd=str(LIB), capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.stdout.strip().splitlines()[-1], "False False", proc.stderr)


if __name__ == "__main__":
    unittest.main()
