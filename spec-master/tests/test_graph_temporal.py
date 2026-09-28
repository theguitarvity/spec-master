import unittest
from datetime import datetime, timezone, timedelta

import _pathfix  # noqa: F401
from graph.temporal import make_first_seen, make_last_verified, is_stale, now_iso


class GraphTemporalTests(unittest.TestCase):
    def test_make_first_seen(self):
        d = make_first_seen(commit="abc", phase="design")
        self.assertIn("timestamp", d)
        self.assertEqual(d["commit"], "abc")
        self.assertEqual(d["phase"], "design")

    def test_make_last_verified(self):
        d = make_last_verified(commit="def")
        self.assertIn("timestamp", d)
        self.assertEqual(d["commit"], "def")

    def test_is_stale_recent(self):
        now = datetime.now(timezone.utc).isoformat()
        self.assertIs(is_stale({"timestamp": now}, max_age_days=30), False)

    def test_is_stale_old(self):
        old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        self.assertIs(is_stale({"timestamp": old}, max_age_days=30), True)

    def test_is_stale_missing(self):
        self.assertIs(is_stale({}, max_age_days=30), True)


if __name__ == "__main__":
    unittest.main()
