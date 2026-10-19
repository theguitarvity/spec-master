"""P6b: cli.py imports its engine modules lazily (first attribute access)."""
import _pathfix  # noqa: F401

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import cli

LIB = Path(__file__).resolve().parent.parent / "lib"

HEAVY = ("dashboard", "tracker_orchestration", "worktree", "pr_step", "evals", "telemetry",
         "team_workstreams", "discovery", "ears")


def _probe(code):
    proc = subprocess.run([sys.executable, "-c", code], cwd=str(LIB), capture_output=True, text=True, timeout=60)
    return proc


class LazyImportTests(unittest.TestCase):
    def test_a_simple_command_does_not_load_the_heavy_modules(self):
        code = (
            "import sys, io, json\n"
            "import cli\n"
            "cli.main(['policy', 'preflight', 'ls'])\n"
            f"print(json.dumps([m for m in {list(HEAVY)!r} if m in sys.modules]))\n"
        )
        proc = _probe(code)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout.strip().splitlines()[-1]), [])

    def test_help_still_lists_every_group(self):
        proc = subprocess.run([sys.executable, str(LIB / "cli.py"), "--help"], capture_output=True, text=True,
                              timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for group in ("state", "protocol", "dashboard", "traceability", "metrics"):
            self.assertIn(group, proc.stdout)

    def test_proxy_imports_on_first_attribute_and_forwards_set_and_delete(self):
        proxy = cli._lazy("json")
        self.assertEqual(proxy.dumps({"a": 1}), '{"a": 1}')
        with mock.patch.object(proxy, "dumps", lambda *_a, **_k: "patched"):
            self.assertEqual(json.dumps({}), "patched")
        self.assertEqual(json.dumps({}), "{}")

    def test_every_lazy_name_resolves_to_a_module(self):
        names = [n for n, v in vars(cli).items() if isinstance(v, cli._LazyModule)]
        self.assertGreater(len(names), 15)
        for name in names:
            self.assertTrue(hasattr(getattr(cli, name), "__name__"), name)


if __name__ == "__main__":
    unittest.main()
