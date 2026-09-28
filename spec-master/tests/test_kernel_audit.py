import datetime as dt
import json
import os
import shutil
import tempfile
import unittest

import _pathfix  # noqa: F401
from kernel import audit

NOW = dt.datetime(2026, 10, 12, 12, 0, tzinfo=dt.timezone.utc)


def entry(session, decision="allow", at="2026-09-28T10:00:00Z", tool="Bash", target="git status",
          reason="ok", event="pre-tool-use", ms=40.0):
    return {"at": at, "session": session, "event": event, "tool": tool, "target": target, "decision": decision,
            "reason": reason, "mode": "audit", "enforced": False, "elapsed_ms": ms}


class RedactionTests(unittest.TestCase):
    def test_credentials_never_reach_the_summary(self):
        cases = {
            "git push https://user:s3cr3t@github.com/o/r.git": "git push https://***@github.com/o/r.git",
            "git clone https://ghp_abcdefghijklmnopqrstuvwxyz0123@github.com/o/r":
                "git clone https://***@github.com/o/r",
            'curl -H "Authorization: Bearer abc.def" https://x': 'curl -H "Authorization: ***" https://x',
            "twine upload --password hunter2 dist/*": "twine upload --password *** dist/*",
            "npm publish --access-key=zzz": "npm publish --access-key=***",
            "GITHUB_TOKEN=abc123 gh pr create": "GITHUB_TOKEN=*** gh pr create",
            "echo sk-abcdefghijklmnopqrstuvwxyz": "echo ***",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(audit.redact(raw), expected)

    def test_long_targets_are_cut(self):
        self.assertEqual(len(audit.redact("x" * 500)), audit.TARGET_CHARS)


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, ".spec-master", "hooks"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def log(self, *entries, garbage=False):
        with open(os.path.join(self.root, audit.DECISIONS_RELPATH), "a", encoding="utf-8") as fh:
            for item in entries:
                fh.write(json.dumps(item) + "\n")
            if garbage:
                fh.write('{"torn": \n')

    def policy(self, **values):
        with open(os.path.join(self.root, audit.POLICY_RELPATH), "w", encoding="utf-8") as fh:
            json.dump(values, fh)

    def saved(self):
        with open(os.path.join(self.root, audit.SUMMARY_RELPATH), encoding="utf-8") as fh:
            return [json.loads(line) for line in fh]

    def test_report_counts_sessions_and_ignores_manual_runs(self):
        self.log(entry("s1"), entry("s1", "deny", target="git push -f origin main", reason="force push"),
                 entry("s2", ms=90.0), entry(None, "deny"), garbage=True)
        report = audit.report(self.root, now=NOW)
        self.assertEqual((report["sessions"], report["total"], report["would_block"]), (2, 3, 1))
        self.assertEqual(report["would_block_rate"], 0.3333)
        self.assertEqual(report["ignored_without_session"], 1)
        self.assertEqual(report["flagged_kinds"], {"deny Bash": 1})
        self.assertEqual(report["flagged"][0]["target"], "git push -f origin main")
        self.assertEqual(report["hook_p95_ms_worst_session"], 90.0)
        self.assertIsNone(report["saved"])

    def test_save_is_idempotent_and_adds_up_across_machines(self):
        self.log(entry("s1"), entry("s1", "ask", target="git push origin main"), entry(None))
        audit.report(self.root, save_summary=True, now=NOW)
        audit.report(self.root, save_summary=True, now=NOW)
        self.assertEqual([s["session"] for s in self.saved()], ["s1"])  # no manual runs, no duplicates
        # another container: its own local log, the committed summary from the first one
        os.unlink(os.path.join(self.root, audit.DECISIONS_RELPATH))
        self.log(entry("s2", at="2026-09-29T09:00:00Z"))
        report = audit.report(self.root, save_summary=True, now=NOW)
        self.assertEqual((report["sessions"], report["total"], report["would_block"], report["would_ask"]),
                         (2, 3, 0, 1))  # an ask prompts, it does not block
        self.assertIn("ask(s) would prompt the user", report["next"])
        self.assertEqual([s["session"] for s in self.saved()], ["s1", "s2"])

    def test_period_and_advice(self):
        self.policy(hooks_mode="audit", audit_started_at="2026-10-02")
        self.log(entry("s1"))
        early = audit.report(self.root, now=NOW)
        self.assertEqual((early["days"], early["period_complete"]), (10, False))
        self.assertIn("keep auditing", early["next"])
        done = audit.report(self.root, now=NOW + dt.timedelta(days=5))
        self.assertTrue(done["period_complete"] and done["criterion_met_without_review"])
        self.assertIn("harness mode --mode block", done["next"])
        self.log(*[entry("s1", "deny") for _ in range(3)])
        review = audit.report(self.root, now=NOW + dt.timedelta(days=5))
        self.assertFalse(review["criterion_met_without_review"])
        self.assertIn("review the denials in `flagged`", review["next"])
        self.policy(hooks_mode="block", audit_started_at="2026-10-02")
        self.assertIn("already block", audit.report(self.root, now=NOW)["next"])

    def test_without_a_start_date_the_first_decision_opens_the_period(self):
        self.log(entry("s1", at="2026-10-01T08:00:00Z"))
        self.assertEqual(audit.report(self.root, now=NOW)["started"], "2026-10-01")
        empty = tempfile.mkdtemp()
        try:
            report = audit.report(empty, now=NOW)
            self.assertEqual((report["total"], report["started"]), (0, None))
            self.assertIn("no decisions recorded yet", report["next"])
        finally:
            shutil.rmtree(empty)


if __name__ == "__main__":
    unittest.main()
