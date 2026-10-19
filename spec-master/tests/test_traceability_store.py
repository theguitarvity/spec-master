import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import _pathfix  # noqa: F401
import cli
import state as state_mod
import traceability


def _row(req, feature, status="VALIDATED"):
    return {"requirement": req, "source": "ctx.md", "feature": feature, "status": status}


def _run_cli(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(list(argv))
    return code, buf.getvalue()


class TraceabilityStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_path = str(Path(self.tmp, ".spec-master", "state.json"))
        state_mod.init(self.state_path, context="ctx.md")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_add_feature_row_writes_one_file_per_feature_and_dedupes(self):
        traceability.add_feature_row(self.state_path, _row("FR-001", "feat-a"))
        traceability.add_feature_row(self.state_path, _row("FR-001", "feat-a"))
        traceability.add_feature_row(self.state_path, _row("FR-002", "feat-b"))
        path = traceability.feature_file(self.state_path, "feat-a")
        payload = json.loads(path.read_text())
        self.assertEqual(payload["feature"], "feat-a")
        self.assertEqual(len(payload["rows"]), 1)
        self.assertEqual(len(traceability.load_store_rows(self.state_path)), 2)

    def test_unsafe_feature_ids_are_sanitized_and_empty_is_unassigned(self):
        self.assertEqual(traceability.feature_file(self.state_path, "../x y").name, "x-y.json")
        self.assertEqual(traceability.feature_file(self.state_path, "").name, "_unassigned.json")

    def test_load_rows_merges_inline_and_store_without_duplicates(self):
        state = state_mod.load(self.state_path)
        traceability.add_row(state, _row("FR-001", "feat-a"))
        traceability.add_feature_row(self.state_path, _row("FR-001", "feat-a"))
        traceability.add_feature_row(self.state_path, _row("FR-009", "feat-z"))
        rows = traceability.load_rows(state, self.state_path)
        self.assertEqual([r["requirement"] for r in rows], ["FR-001", "FR-009"])
        only_z = traceability.load_rows(state, self.state_path, feature="feat-z")
        self.assertEqual([r["requirement"] for r in only_z], ["FR-009"])

    def test_migrate_moves_inline_rows_and_is_idempotent(self):
        state = state_mod.load(self.state_path)
        for req, feat in (("FR-001", "a"), ("FR-002", "a"), ("FR-001", "b")):
            traceability.add_row(state, _row(req, feat))
        summary = traceability.migrate_from_state(state, self.state_path)
        self.assertEqual(summary["migrated_rows"], 3)
        self.assertEqual(summary["features"], {"a": 2, "b": 1})
        self.assertEqual(state["traceability"], [])
        self.assertTrue(traceability.uses_store(state))
        again = traceability.migrate_from_state(state, self.state_path)
        self.assertEqual(again["migrated_rows"], 0)
        self.assertEqual(len(traceability.load_rows(state, self.state_path)), 3)

    def test_render_rows_matches_legacy_render(self):
        state = {"traceability": [_row("FR-001", "a")]}
        self.assertEqual(traceability.render(state), traceability.render_rows(state["traceability"]))

    def test_cli_add_goes_to_store_after_migrate(self):
        code, _ = _run_cli("traceability", "add", "--path", self.state_path,
                           "--row-json", json.dumps(_row("FR-001", "a")))
        self.assertEqual(code, 0)
        self.assertEqual(len(state_mod.load(self.state_path)["traceability"]), 1)

        code, out = _run_cli("traceability", "migrate", "--path", self.state_path)
        self.assertEqual(json.loads(out)["migrated_rows"], 1)

        _run_cli("traceability", "add", "--path", self.state_path,
                 "--row-json", json.dumps(_row("FR-002", "a")))
        self.assertEqual(state_mod.load(self.state_path)["traceability"], [])
        self.assertEqual(len(traceability.load_store_rows(self.state_path, "a")), 2)

        report = str(Path(self.tmp, ".spec-master", "reports", "traceability.md"))
        code, out = _run_cli("traceability", "render", "--path", self.state_path, "--output", report)
        self.assertEqual(json.loads(out)["rows"], 2)
        self.assertIn("FR-002", Path(report).read_text())

    def test_cli_state_init_starts_with_the_store(self):
        fresh = str(Path(self.tmp, "fresh", ".spec-master", "state.json"))
        code, out = _run_cli("state", "init", "--path", fresh, "--context", "ctx.md")
        self.assertEqual(code, 0)
        self.assertTrue(traceability.uses_store(json.loads(out)))
        _run_cli("traceability", "add", "--path", fresh, "--row-json", json.dumps(_row("FR-001", "a")))
        self.assertEqual(state_mod.load(fresh)["traceability"], [])
        self.assertEqual(len(traceability.load_store_rows(fresh, "a")), 1)

        code, out = _run_cli("traceability", "render", "--path", self.state_path, "--feature", "a")
        self.assertIn("Requirement Traceability — a", out)


if __name__ == "__main__":
    unittest.main()


class TraceabilityRestatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_path = str(Path(self.tmp, ".spec-master", "state.json"))
        state_mod.init(self.state_path, context="ctx.md")
        traceability.add_feature_row(self.state_path, _row("FR-001 a", "feat-a", "PASSED"))
        traceability.add_feature_row(self.state_path, _row("FR-002 b", "feat-a", "PASSED"))
        traceability.add_feature_row(self.state_path, _row("Old plan row", "feat-a", "PLANNED"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def statuses(self):
        return {r["requirement"]: (r["status"], r.get("issue", ""))
                for r in traceability.load_store_rows(self.state_path, "feat-a")}

    def test_cli_restatus_rewrites_only_matching_rows(self):
        code, out = _run_cli("traceability", "restatus", "--path", self.state_path, "--feature", "feat-a",
                             "--from", "PASSED", "--to", "COVERED")
        self.assertEqual((code, json.loads(out)["changed"]), (0, 2))
        self.assertEqual(self.statuses()["FR-001 a"][0], "COVERED")
        self.assertEqual(self.statuses()["Old plan row"][0], "PLANNED")

    def test_requirement_filter_and_note(self):
        state = state_mod.load(self.state_path)
        result = traceability.restatus(state, self.state_path, "feat-a", "PLANNED", "SUPERSEDED",
                                       requirement="Old", note="replaced by FR rows")
        self.assertEqual(result["rows"], ["Old plan row"])
        self.assertEqual(self.statuses()["Old plan row"], ("SUPERSEDED", "replaced by FR rows"))

    def test_same_status_is_refused(self):
        with self.assertRaises(ValueError):
            traceability.restatus({}, self.state_path, "feat-a", "PASSED", "PASSED")
