import _pathfix  # noqa: F401

import copy
import json
import os
import shutil
import tempfile
import unittest

import metrics
import metrics_export


def _row(round_id="r1-plan", started="2026-09-26T10:00:00Z", ended="2026-09-26T10:30:00Z", **kw):
    return metrics.record_round(
        round_id=round_id, phase=kw.pop("phase", "plan"), started_at=started, ended_at=ended,
        input_tokens=kw.pop("input_tokens", 1200), output_tokens=kw.pop("output_tokens", 300),
        work_packages_completed=kw.pop("work_packages_completed", 2),
        features_completed=kw.pop("features_completed", 1), **kw,
    )


class SchemaFileTests(unittest.TestCase):
    def test_schema_is_draft_2020_12_and_closed(self):
        schema = metrics_export.load_schema()
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(schema["$defs"]["rounds"]["type"], "array")
        for key in ("notes", "feature_id", "tier"):
            self.assertIn(key, schema["properties"])
            self.assertNotIn(key, schema["required"])

    def test_every_record_round_key_is_described(self):
        schema = metrics_export.load_schema()
        row = _row(notes="n", feature_id="f", tier="M")
        self.assertEqual(set(row) - set(schema["properties"]), set())
        self.assertEqual(set(schema["required"]) - set(row), set())

    def test_unsupported_keyword_raises_instead_of_passing(self):
        with self.assertRaises(metrics_export.SchemaError):
            metrics_export.validate(5, {"type": "integer", "multipleOf": 2})
        with self.assertRaises(metrics_export.SchemaError):
            metrics_export.validate({}, {"$ref": "https://example.com/remote.json"})


class ValidateRoundsTests(unittest.TestCase):
    def test_real_shaped_rows_validate(self):
        rounds = [
            _row(),
            _row("r2-tasks", "2026-09-26T11:00:00.123456+00:00", "2026-09-26T11:05:00+00:00", phase="tasks",
                 notes="parallel"),
            _row("r3-zero", "2026-09-26T12:00:00", "2026-09-26T12:00:00", input_tokens=0, output_tokens=0,
                 work_packages_completed=0, features_completed=0),
        ]
        report = metrics_export.validate_rounds(rounds)
        self.assertEqual(report, {"valid": True, "errors": [], "warnings": []})

    def test_repo_rounds_file_validates_when_present(self):
        path = metrics_export.default_rounds_path(os.path.join(os.path.dirname(__file__), "..", ".."))
        if not os.path.exists(path):
            self.skipTest("no rounds.json in this checkout")
        report = metrics_export.validate_rounds(metrics_export.load_rounds(path))
        self.assertTrue(report["valid"], report["errors"])

    def test_optional_feature_id_and_tier_accepted(self):
        row = _row(feature_id="context-delta-reporting", tier="M")
        self.assertEqual((row["feature_id"], row["tier"]), ("context-delta-reporting", "M"))
        self.assertTrue(metrics_export.validate_rounds([row])["valid"])
        bad = dict(row, feature_id="", tier=3)
        errors = metrics_export.validate_rounds([bad])["errors"]
        self.assertEqual(sorted(e["path"] for e in errors), ["/feature_id", "/tier"])

    def _errors(self, row):
        report = metrics_export.validate_rounds([_row(), row])
        self.assertFalse(report["valid"])
        self.assertTrue(all(e["index"] == 1 for e in report["errors"]))
        return {e["path"]: e["message"] for e in report["errors"]}

    def test_negative_count(self):
        errors = self._errors(dict(_row(), input_tokens=-1))
        self.assertIn("/input_tokens", errors)
        self.assertIn("minimum", errors["/input_tokens"])

    def test_missing_required(self):
        row = _row()
        del row["phase"]
        errors = self._errors(row)
        self.assertIn("/phase", errors)
        self.assertIn("missing", errors["/phase"])

    def test_wrong_type(self):
        errors = self._errors(dict(_row(), duration_seconds="1800", round_id=7))
        self.assertIn("expected number", errors["/duration_seconds"])
        self.assertIn("expected string", errors["/round_id"])

    def test_bool_is_not_an_integer(self):
        errors = self._errors(dict(_row(), features_completed=True))
        self.assertIn("/features_completed", errors)
        self.assertIn("boolean", errors["/features_completed"])

    def test_float_with_fraction_is_not_an_integer_but_whole_float_is(self):
        self.assertIn("/output_tokens", self._errors(dict(_row(), output_tokens=1.5)))
        self.assertTrue(metrics_export.validate_rounds([dict(_row(), output_tokens=300.0)])["valid"])

    def test_bad_timestamps(self):
        errors = self._errors(dict(_row(), started_at="yesterday", ended_at="2026-02-30T10:00:00Z"))
        self.assertIn("/started_at", errors)
        self.assertIn("/ended_at", errors)
        self.assertIn("date-time", errors["/ended_at"])

    def test_unknown_key_rejected(self):
        errors = self._errors(dict(_row(), cost_usd=1.2))
        self.assertIn("/cost_usd", errors)

    def test_non_array_and_non_object_rows(self):
        report = metrics_export.validate_rounds({"round_id": "x"})
        self.assertEqual(report["errors"][0]["index"], None)
        self.assertEqual(report["errors"][0]["path"], "")
        report = metrics_export.validate_rounds(["nope"])
        self.assertEqual(report["errors"], [{"index": 0, "path": "", "message": "expected object, got string"}])

    def test_consistency_warnings_do_not_invalidate(self):
        rows = [dict(_row(), total_tokens=1), _row(), _row("r9", "2026-09-26T10:00:00Z", "2026-09-26T09:00:00Z")]
        report = metrics_export.validate_rounds(rows)
        self.assertTrue(report["valid"])
        messages = [(w["index"], w["path"]) for w in report["warnings"]]
        self.assertIn((0, "/total_tokens"), messages)
        self.assertIn((1, "/round_id"), messages)
        self.assertIn((2, "/ended_at"), messages)


class TimestampTests(unittest.TestCase):
    def test_exact_nanoseconds(self):
        self.assertEqual(metrics_export.timestamp_unix_nano("1970-01-01T00:00:01.123456789Z"), 1123456789)
        self.assertEqual(metrics_export.timestamp_unix_nano("2026-09-26T12:25:51.489017+00:00"),
                         1790425551489017000)
        self.assertEqual(metrics_export.timestamp_unix_nano("1970-01-01T01:00:00+01:00"), 0)
        self.assertEqual(metrics_export.timestamp_unix_nano("1970-01-01T00:00:00"), 0)  # naive = UTC

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            metrics_export.timestamp_unix_nano("2026-13-01T00:00:00Z")


class OtlpTests(unittest.TestCase):
    def setUp(self):
        self.rounds = [
            _row("r2-tasks", "2026-09-26T11:00:00Z", "2026-09-26T11:10:00Z", phase="tasks", notes="secret",
                 feature_id="feat-a", tier="S"),
            _row("r1-plan", "2026-09-26T10:00:00Z", "2026-09-26T10:30:00Z"),
        ]

    def test_structure(self):
        payload = metrics_export.to_otlp(self.rounds)
        rm = payload["resourceMetrics"]
        self.assertEqual(len(rm), 1)
        self.assertEqual(rm[0]["resource"]["attributes"],
                         [{"key": "service.name", "value": {"stringValue": "spec-master"}}])
        scope = rm[0]["scopeMetrics"][0]
        self.assertEqual(scope["scope"], {"name": "spec-master.metrics", "version": metrics_export.SCHEMA_VERSION})
        by_name = {m["name"]: m for m in scope["metrics"]}
        self.assertEqual(list(by_name), [m[0] for m in metrics_export.OTLP_METRICS])

        duration = by_name["spec_master.round.duration"]
        self.assertEqual(duration["unit"], "s")
        self.assertNotIn("sum", duration)
        self.assertEqual([p["asDouble"] for p in duration["gauge"]["dataPoints"]], [1800.0, 600.0])

        for name, field in (("spec_master.tokens.input", "input_tokens"),
                            ("spec_master.tokens.output", "output_tokens"),
                            ("spec_master.work_packages.completed", "work_packages_completed"),
                            ("spec_master.features.completed", "features_completed")):
            metric = by_name[name]
            self.assertEqual(metric["sum"]["aggregationTemporality"], 1)
            self.assertIs(metric["sum"]["isMonotonic"], True)
            values = [p["asInt"] for p in metric["sum"]["dataPoints"]]
            self.assertTrue(all(isinstance(v, str) for v in values))
            self.assertEqual(values, [str(self.rounds[1][field]), str(self.rounds[0][field])])
        self.assertEqual(by_name["spec_master.tokens.input"]["unit"], "{token}")

    def test_timestamps_are_nanosecond_strings(self):
        point = metrics_export.to_otlp(self.rounds)["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][1]["sum"][
            "dataPoints"][0]
        self.assertEqual(point["startTimeUnixNano"], str(metrics_export.timestamp_unix_nano("2026-09-26T10:00:00Z")))
        self.assertEqual(point["timeUnixNano"], str(metrics_export.timestamp_unix_nano("2026-09-26T10:30:00Z")))
        self.assertTrue(point["timeUnixNano"].isdigit())
        self.assertEqual(len(point["timeUnixNano"]), 19)

    def test_attributes(self):
        points = metrics_export.to_otlp(self.rounds)["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0][
            "gauge"]["dataPoints"]
        first = {a["key"]: a["value"]["stringValue"] for a in points[0]["attributes"]}
        second = {a["key"]: a["value"]["stringValue"] for a in points[1]["attributes"]}
        self.assertEqual(first, {"spec_master.round_id": "r1-plan", "spec_master.phase": "plan"})
        self.assertEqual(second, {"spec_master.round_id": "r2-tasks", "spec_master.phase": "tasks",
                                  "spec_master.feature_id": "feat-a", "spec_master.tier": "S"})
        self.assertNotIn("secret", json.dumps(points))

    def test_deterministic_regardless_of_input_order(self):
        a = metrics_export.export(self.rounds)
        b = metrics_export.export(list(reversed(copy.deepcopy(self.rounds))))
        self.assertEqual(a, b)
        self.assertTrue(a.endswith("\n"))
        self.assertEqual(json.loads(a), metrics_export.to_otlp(self.rounds))

    def test_empty_rounds(self):
        payload = json.loads(metrics_export.export([]))
        self.assertEqual(payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"], [])
        self.assertEqual(metrics_export.export([], fmt="jsonl"), "")

    def test_service_name_and_scope_version(self):
        payload = metrics_export.to_otlp(self.rounds, service_name="acme", scope_version="9.9")
        rm = payload["resourceMetrics"][0]
        self.assertEqual(rm["resource"]["attributes"][0]["value"]["stringValue"], "acme")
        self.assertEqual(rm["scopeMetrics"][0]["scope"]["version"], "9.9")


class ExportTests(unittest.TestCase):
    def test_jsonl(self):
        rounds = [_row("b"), _row("a", feature_id="f", tier="XL")]
        text = metrics_export.export(rounds, fmt="jsonl")
        lines = text.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual([json.loads(line) for line in lines], rounds)  # input order kept
        self.assertTrue(text.endswith("\n"))
        self.assertNotIn(", ", text)  # compact separators
        self.assertNotIn('": ', text)
        self.assertEqual(list(json.loads(lines[1])), sorted(rounds[1]))  # sorted keys

    def test_invalid_rounds_raise_with_report(self):
        with self.assertRaises(metrics_export.InvalidRoundsError) as ctx:
            metrics_export.export([dict(_row(), input_tokens=-5)])
        self.assertIsInstance(ctx.exception, ValueError)
        self.assertEqual(ctx.exception.report["errors"][0]["path"], "/input_tokens")

    def test_unknown_format(self):
        with self.assertRaises(ValueError):
            metrics_export.export([_row()], fmt="csv")

    def test_load_and_write(self):
        tmp = tempfile.mkdtemp()
        try:
            path = metrics_export.default_rounds_path(tmp)
            self.assertTrue(path.endswith(os.path.join(".spec-master", "metrics", "rounds.json")))
            with self.assertRaises(ValueError):
                metrics_export.load_rounds(path)
            os.makedirs(os.path.dirname(path))
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("{not json")
            with self.assertRaises(ValueError):
                metrics_export.load_rounds(path)
            out = metrics_export.write_text_atomic(os.path.join(tmp, "out", "m.json"), "x\n")
            with open(out, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "x\n")
            self.assertEqual(os.listdir(os.path.dirname(out)), ["m.json"])
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
