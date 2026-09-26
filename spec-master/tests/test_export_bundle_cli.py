import _pathfix  # noqa: F401

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

import cli
import metrics


def _run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(argv)
    return code, buf.getvalue()


def _run_json(argv):
    code, out = _run(argv)
    return code, json.loads(out)


def _write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


class MetricsExportCliTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.rounds = [
            metrics.record_round(round_id="r1", phase="plan", started_at="2026-09-26T10:00:00Z",
                                 ended_at="2026-09-26T10:30:00Z", input_tokens=100, output_tokens=50,
                                 work_packages_completed=1, features_completed=0),
            metrics.record_round(round_id="r2", phase="implement", started_at="2026-09-26T11:00:00Z",
                                 ended_at="2026-09-26T12:00:00Z", input_tokens=900, output_tokens=400,
                                 work_packages_completed=3, features_completed=1, feature_id="feat-a",
                                 tier="M"),
        ]
        self.rounds_path = _write(self.root, ".spec-master/metrics/rounds.json", json.dumps(self.rounds))

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_validate_default_path(self):
        code, payload = _run_json(["metrics", "validate", "--path", self.root])
        self.assertEqual(code, 0)
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["rounds"], 2)
        self.assertEqual(payload["rounds_file"], self.rounds_path)

    def test_validate_reports_errors_and_exits_1(self):
        bad = _write(self.root, "bad.json", json.dumps([dict(self.rounds[0], input_tokens=-1, extra=1)]))
        code, payload = _run_json(["metrics", "validate", "--rounds", bad])
        self.assertEqual(code, 1)
        self.assertFalse(payload["valid"])
        self.assertEqual(sorted(e["path"] for e in payload["errors"]), ["/extra", "/input_tokens"])
        self.assertEqual({e["index"] for e in payload["errors"]}, {0})

    def test_export_otlp_to_stdout(self):
        code, payload = _run_json(["metrics", "export", "--path", self.root])
        self.assertEqual(code, 0)
        metrics_list = payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]
        self.assertEqual(metrics_list[0]["name"], "spec_master.round.duration")
        sums = [m for m in metrics_list if "sum" in m]
        self.assertTrue(all(m["sum"]["aggregationTemporality"] == 1 for m in sums))
        self.assertEqual(sums[0]["sum"]["dataPoints"][1]["asInt"], "900")

    def test_export_jsonl_to_file(self):
        out = os.path.join(self.root, "export", "rounds.jsonl")
        code, payload = _run_json(["metrics", "export", "--path", self.root, "--format", "jsonl", "--output", out])
        self.assertEqual(code, 0)
        self.assertEqual(payload, {"output": out, "format": "jsonl", "rounds": 2})
        with open(out, encoding="utf-8") as fh:
            self.assertEqual([json.loads(line) for line in fh.read().splitlines()], self.rounds)

    def test_export_refuses_invalid_rounds(self):
        bad = _write(self.root, "bad.json", json.dumps([dict(self.rounds[0], started_at="soon")]))
        out = os.path.join(self.root, "never.json")
        code, payload = _run_json(["metrics", "export", "--rounds", bad, "--output", out])
        self.assertEqual(code, 1)
        self.assertIn("error", payload)
        self.assertEqual(payload["errors"][0]["path"], "/started_at")
        self.assertFalse(os.path.exists(out))

    def test_missing_rounds_file_is_an_error(self):
        code, payload = _run_json(["metrics", "validate", "--rounds", os.path.join(self.root, "nope.json")])
        self.assertEqual(code, 1)
        self.assertIn("error", payload)


class BundleCliTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.state_path = os.path.join(self.root, ".spec-master", "state.json")
        os.makedirs(os.path.dirname(self.state_path))
        code, _ = _run(["state", "init", "--path", self.state_path, "--context", "docs/ctx.md"])
        self.assertEqual(code, 0)
        feature = {
            "id": "feat-a", "name": "Feature A", "description": "Export data.",
            "source_requirements": ["app-features.md#export"], "acceptance_criteria": ["CSV export"],
            "dependencies": [], "spec_directory": "specs/001-feat-a",
        }
        code, _ = _run(["state", "upsert-feature", "--path", self.state_path, "--feature-json", json.dumps(feature)])
        self.assertEqual(code, 0)
        _write(self.root, ".spec-master/context/app-features.md", "# App Features\n\nCTX-DOC\n")
        _write(self.root, "specs/001-feat-a/spec.md", "# Spec\n\nSPEC-BODY\n")

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_build_writes_default_path(self):
        code, payload = _run_json(["bundle", "build", "--path", self.root, "--feature", "feat-a"])
        self.assertEqual(code, 0)
        self.assertEqual(payload["phase"], "specify")
        self.assertEqual(payload["output"], os.path.join(self.root, ".spec-master", "bundles", "feat-a-specify.md"))
        self.assertGreater(payload["tokens"], 0)
        self.assertIn(".spec-master/context/app-features.md", [i["id"] for i in payload["included"]])
        self.assertEqual(payload["omitted"], [])
        with open(payload["output"], encoding="utf-8") as fh:
            md = fh.read()
        self.assertIn("## Phase prompt: specify", md)
        self.assertIn("- **Generated at:** ", md)

    def test_build_stdout_explicit_phase_and_budget(self):
        code, md = _run(["bundle", "build", "--path", self.root, "--feature", "feat-a", "--phase", "clarify",
                         "--budget", "50", "--stdout", "--no-timestamp"])
        self.assertEqual(code, 0)
        self.assertTrue(md.startswith("# Spec Master web bundle: Feature A / clarify"))
        self.assertNotIn("Generated at", md)
        tail = md[md.index("## Not included"):]
        self.assertIn("- `specs/001-feat-a/spec.md`", tail)
        self.assertFalse(os.path.exists(os.path.join(self.root, ".spec-master", "bundles")))

    def test_build_custom_output_and_state(self):
        out = os.path.join(self.root, "out", "b.md")
        code, payload = _run_json(["bundle", "build", "--path", self.root, "--state", self.state_path,
                                   "--feature", "feat-a", "--phase", "plan", "--output", out])
        self.assertEqual(code, 0)
        self.assertEqual(payload["output"], out)
        self.assertTrue(os.path.isfile(out))
        self.assertIn("specs/001-feat-a/spec.md", [i["id"] for i in payload["included"]])

    def test_build_errors(self):
        code, payload = _run_json(["bundle", "build", "--path", self.root, "--feature", "nope"])
        self.assertEqual(code, 1)
        self.assertIn("unknown feature", payload["error"])
        code, payload = _run_json(["bundle", "build", "--path", self.root, "--phase", "plan"])
        self.assertEqual(code, 1)
        self.assertIn("error", payload)
        empty = tempfile.mkdtemp()
        try:
            code, payload = _run_json(["bundle", "build", "--path", empty, "--feature", "feat-a"])
            self.assertEqual(code, 1)
            self.assertIn("cannot load state", payload["error"])
        finally:
            shutil.rmtree(empty)


if __name__ == "__main__":
    unittest.main()
