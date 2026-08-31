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


if __name__ == "__main__":
    unittest.main()
