import unittest
import _pathfix
from graph.temporal import make_first_seen, make_last_verified, is_stale, now_iso
from datetime import datetime, timezone, timedelta


class GraphTemporalTests(unittest.TestCase):

    def test_make_first_seen(self):
        d = make_first_seen(commit="abc", phase="design")
        assert "timestamp" in d
        assert d["commit"] == "abc"
        assert d["phase"] == "design"

    def test_make_last_verified(self):
        d = make_last_verified(commit="def")
        assert "timestamp" in d
        assert d["commit"] == "def"

    def test_is_stale_recent(self):
        now = datetime.now(timezone.utc).isoformat()
        assert is_stale({"timestamp": now}, max_age_days=30) is False

    def test_is_stale_old(self):
        old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        assert is_stale({"timestamp": old}, max_age_days=30) is True

    def test_is_stale_missing(self):
        assert is_stale({}, max_age_days=30) is True


if __name__ == "__main__":
    unittest.main()
