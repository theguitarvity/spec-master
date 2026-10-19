from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import _pathfix  # noqa: F401
import metrics  # noqa: E402


ENGINE_ROOT = Path(__file__).resolve().parent.parent
CLI = ENGINE_ROOT / "lib" / "cli.py"


class MetricsTests(unittest.TestCase):
    def test_record_round_calculates_token_and_delivery_speed(self):
        row = metrics.record_round(
            round_id="round-001",
            phase="implement",
            started_at="2026-08-31T10:00:00Z",
            ended_at="2026-08-31T10:30:00Z",
            input_tokens=1200,
            output_tokens=800,
            work_packages_completed=2,
            features_completed=1,
        )

        self.assertEqual(row["total_tokens"], 2000)
        self.assertEqual(row["duration_seconds"], 1800.0)
        self.assertEqual(row["tokens_per_minute"], 66.667)
        self.assertEqual(row["packages_per_hour"], 4.0)
        self.assertEqual(row["features_per_hour"], 2.0)

    def test_summarize_accumulates_rounds(self):
        rows = [
            metrics.record_round(
                round_id="round-001",
                phase="tasks",
                started_at="2026-08-31T10:00:00Z",
                ended_at="2026-08-31T10:15:00Z",
                input_tokens=500,
                output_tokens=500,
                work_packages_completed=1,
            ),
            metrics.record_round(
                round_id="round-002",
                phase="implement",
                started_at="2026-08-31T10:15:00Z",
                ended_at="2026-08-31T10:45:00Z",
                input_tokens=1000,
                output_tokens=2000,
                work_packages_completed=3,
                features_completed=1,
            ),
        ]

        summary = metrics.summarize(rows)

        self.assertEqual(summary["rounds"], 2)
        self.assertEqual(summary["total_tokens"], 4000)
        self.assertEqual(summary["work_packages_completed"], 4)
        self.assertEqual(summary["features_completed"], 1)

    def test_cli_records_and_summarizes_metrics(self):
        output = subprocess.check_output(
            [
                sys.executable,
                str(CLI),
                "metrics",
                "record-round",
                "--round-id",
                "round-001",
                "--phase",
                "validate",
                "--started-at",
                "2026-08-31T12:00:00Z",
                "--ended-at",
                "2026-08-31T12:10:00Z",
                "--input-tokens",
                "100",
                "--output-tokens",
                "200",
                "--work-packages-completed",
                "1",
            ],
            text=True,
        )
        row = json.loads(output)
        self.assertEqual(row["total_tokens"], 300)

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json") as fh:
            json.dump([row], fh)
            fh.flush()
            summary_output = subprocess.check_output(
                [sys.executable, str(CLI), "metrics", "summarize", "--file", fh.name],
                text=True,
            )

        self.assertEqual(json.loads(summary_output)["rounds"], 1)


class RecordRoundSourceTests(unittest.TestCase):
    ARGS = dict(round_id="r1", phase="plan", started_at="2026-08-31T10:00:00Z", ended_at="2026-08-31T10:10:00Z")

    def test_without_source_the_row_is_the_v1_row(self):
        row = metrics.record_round(**self.ARGS, input_tokens=5)
        self.assertNotIn("source", row)
        self.assertEqual(list(row)[-1], "features_per_hour")

    def test_manual_with_tokens_stays_manual(self):
        row = metrics.record_round(**self.ARGS, input_tokens=5, source="manual", tier="s")
        self.assertEqual(row["source"], "manual")
        self.assertEqual(list(row)[-2:], ["tier", "source"])

    def test_manual_without_tokens_is_stored_as_unverified(self):
        self.assertEqual(metrics.record_round(**self.ARGS, source="manual")["source"], "manual-unverified")
        self.assertEqual(metrics.record_round(**self.ARGS, source=" manual-unverified ")["source"],
                         "manual-unverified")

    def test_host_sources_require_measured_tokens(self):
        for source in metrics.HOST_SOURCES:
            with self.assertRaises(ValueError):
                metrics.record_round(**self.ARGS, source=source)
            self.assertEqual(metrics.record_round(**self.ARGS, output_tokens=1, source=source)["source"], source)

    def test_unknown_source_is_rejected(self):
        with self.assertRaises(ValueError):
            metrics.record_round(**self.ARGS, input_tokens=1, source="vibes")


if __name__ == "__main__":
    unittest.main()
