import _pathfix  # noqa: F401

import contextlib
import io
import json
import os
import tempfile
import unittest

import cli
import ledger
from test_telemetry import _main_session_lines, _write_jsonl


class TokensCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "proj")
        os.makedirs(os.path.join(self.root, ".spec-master"))
        self.transcript = _write_jsonl(os.path.join(self.tmp, "t.jsonl"), _main_session_lines())

    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(list(argv))
        return code, json.loads(out.getvalue())

    def test_ingest_then_summary(self):
        code, result = self.run_cli("tokens", "ingest", "--path", self.root, "--transcript", self.transcript)
        self.assertEqual(code, 0)
        self.assertGreater(result["appended"], 0)
        self.assertEqual(len(ledger.read(self.root)), result["appended"])
        code, summary = self.run_cli("tokens", "summary", "--path", self.root)
        self.assertEqual(code, 0)
        self.assertEqual(summary["schema"], ledger.SUMMARY_SCHEMA)
        self.assertGreater(summary["totals"]["total_tokens"], 0)

    def test_ingest_twice_appends_nothing_new(self):
        self.run_cli("tokens", "ingest", "--path", self.root, "--transcript", self.transcript)
        _, again = self.run_cli("tokens", "ingest", "--path", self.root, "--transcript", self.transcript)
        self.assertEqual(again["appended"], 0)

    def test_summary_since_in_the_future_is_empty(self):
        self.run_cli("tokens", "ingest", "--path", self.root, "--transcript", self.transcript)
        _, summary = self.run_cli("tokens", "summary", "--path", self.root, "--since", "2999-01-01T00:00:00Z")
        self.assertEqual(summary["totals"]["total_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
