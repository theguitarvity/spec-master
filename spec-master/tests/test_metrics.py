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

    # --- H8: atomic append (feature harness-hygiene) ---
    def _row(self, round_id):
        return metrics.record_round(
            round_id=round_id, phase="implement",
            started_at="2026-10-19T10:00:00Z", ended_at="2026-10-19T10:10:00Z",
        )

    def _tmpdir(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def test_append_round_creates_missing_file_and_parent_dir(self):
        path = self._tmpdir() / "metrics" / "rounds.json"
        rows = metrics.append_round(path, self._row("r1"))
        self.assertEqual([r["round_id"] for r in rows], ["r1"])
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))[0]["round_id"], "r1")

    def test_append_round_keeps_existing_rows_in_order(self):
        path = self._tmpdir() / "rounds.json"
        metrics.append_round(path, self._row("r1"))
        metrics.append_round(path, self._row("r2"))
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual([r["round_id"] for r in data], ["r1", "r2"])

    def test_append_round_refuses_corrupt_or_non_list_file_untouched(self):
        root = self._tmpdir()
        for content in ("{not json", '{"round_id": "x"}'):
            path = root / "rounds.json"
            path.write_text(content, encoding="utf-8")
            with self.assertRaises(ValueError):
                metrics.append_round(path, self._row("r1"))
            self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_append_round_leaves_no_temp_files(self):
        root = self._tmpdir()
        path = root / "rounds.json"
        metrics.append_round(path, self._row("r1"))
        metrics.append_round(path, self._row("r2"))
        leftovers = sorted(p.name for p in root.iterdir() if p.name != "rounds.json")
        self.assertEqual(leftovers, [])

    def _cli_record(self, round_id, *extra):
        return subprocess.run(
            [sys.executable, str(CLI), "metrics", "record-round", "--round-id", round_id,
             "--phase", "plan", "--started-at", "2026-10-19T10:00:00Z",
             "--ended-at", "2026-10-19T10:05:00Z", *extra],
            capture_output=True, text=True,
        )

    def test_cli_record_round_append_twice_yields_two_rows(self):
        path = self._tmpdir() / "rounds.json"
        for rid in ("r1", "r2"):
            result = self._cli_record(rid, "--append", str(path))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["round_id"], rid)
        self.assertEqual([r["round_id"] for r in json.loads(path.read_text(encoding="utf-8"))], ["r1", "r2"])

    def test_cli_record_round_without_append_writes_nothing(self):
        root = self._tmpdir()
        result = subprocess.run(
            [sys.executable, str(CLI), "metrics", "record-round", "--round-id", "r1",
             "--phase", "plan", "--started-at", "2026-10-19T10:00:00Z",
             "--ended-at", "2026-10-19T10:05:00Z"],
            capture_output=True, text=True, cwd=root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(root.iterdir()), [])

    def test_cli_record_round_append_to_corrupt_file_exits_1(self):
        path = self._tmpdir() / "rounds.json"
        path.write_text("{oops", encoding="utf-8")
        result = self._cli_record("r1", "--append", str(path))
        self.assertEqual(result.returncode, 1)
        self.assertIn("rounds.json", result.stderr)
        self.assertEqual(path.read_text(encoding="utf-8"), "{oops")

    def test_cli_record_round_append_failure_prints_no_row(self):
        path = self._tmpdir() / "rounds.json"
        path.write_text("[1", encoding="utf-8")
        result = self._cli_record("r1", "--append", str(path))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")

    def test_append_round_preserves_file_mode(self):
        import os, stat
        path = self._tmpdir() / "rounds.json"
        path.write_text("[]", encoding="utf-8")
        os.chmod(path, 0o644)
        metrics.append_round(path, self._row("r1"))
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o644)

    def test_append_round_writes_through_symlink(self):
        import os
        root = self._tmpdir()
        real = root / "real.json"
        real.write_text("[]", encoding="utf-8")
        link = root / "rounds.json"
        os.symlink(real, link)
        metrics.append_round(link, self._row("r1"))
        self.assertTrue(link.is_symlink())
        self.assertEqual(len(json.loads(real.read_text(encoding="utf-8"))), 1)

    def test_concurrent_cli_appends_keep_every_row(self):
        path = self._tmpdir() / "rounds.json"
        procs = [subprocess.Popen(
            [sys.executable, str(CLI), "metrics", "record-round", "--round-id", f"r{i}",
             "--phase", "plan", "--started-at", "2026-10-19T10:00:00Z",
             "--ended-at", "2026-10-19T10:05:00Z", "--append", str(path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for i in range(8)]
        self.assertEqual([p.wait() for p in procs], [0] * 8)
        ids = sorted(r["round_id"] for r in json.loads(path.read_text(encoding="utf-8")))
        self.assertEqual(ids, sorted(f"r{i}" for i in range(8)))


if __name__ == "__main__":
    unittest.main()
