import unittest
from unittest.mock import patch

import _pathfix  # noqa: F401
import team_workstreams
import worktree


def _package(package_id: str, feature_id: str = "feat-1", reviewer_agent: str = "fullstack-dev"):
    return {
        "id": package_id,
        "feature_id": feature_id,
        "owner_agent": "backend-dev",
        "reviewer_agent": reviewer_agent,
        "depends_on": [],
    }


class WaveGroupingReuseTests(unittest.TestCase):
    """US1: package-shaped input flows through worktree.compute_waves unchanged."""

    def test_worktree_compute_waves_accepts_package_shaped_input(self):
        packages = [_package("pkg-a", "feat-1"), _package("pkg-b", "feat-1")]
        mapped = [{"id": p["id"], "dependencies": p["depends_on"]} for p in packages]
        waves = worktree.compute_waves(mapped)
        self.assertEqual(len(waves), 1)
        self.assertEqual(set(waves[0]["feature_ids"]), {"pkg-a", "pkg-b"})


class RecordReviewVerdictTests(unittest.TestCase):
    def test_record_review_verdict_rejects_non_assigned_reviewer(self):
        packages = [_package("pkg-a", reviewer_agent="fullstack-dev")]
        with self.assertRaises(ValueError):
            team_workstreams.record_review_verdict(
                packages, "pkg-a", reviewer_agent="backend-dev", status="APPROVED"
            )

    def test_record_review_verdict_accepts_assigned_reviewer(self):
        packages = [_package("pkg-a", reviewer_agent="fullstack-dev")]
        result = team_workstreams.record_review_verdict(
            packages, "pkg-a", reviewer_agent="fullstack-dev", status="APPROVED"
        )
        package = result[0]
        self.assertEqual(package["review_verdict"]["status"], "APPROVED")
        self.assertEqual(package["review_verdict"]["reviewer_agent"], "fullstack-dev")

    def test_record_review_verdict_requires_reason_when_rejected(self):
        packages = [_package("pkg-a", reviewer_agent="fullstack-dev")]
        with self.assertRaises(ValueError):
            team_workstreams.record_review_verdict(
                packages, "pkg-a", reviewer_agent="fullstack-dev", status="REJECTED"
            )


class RecordIntegrationVerdictTests(unittest.TestCase):
    def test_record_integration_verdict_approved(self):
        packages = [_package("pkg-a")]
        result = team_workstreams.record_integration_verdict(packages, "pkg-a", status="APPROVED")
        self.assertEqual(result[0]["integration_verdict"], {"status": "APPROVED", "reason": None})

    def test_record_integration_verdict_requires_reason_when_rejected(self):
        packages = [_package("pkg-a")]
        with self.assertRaises(ValueError):
            team_workstreams.record_integration_verdict(packages, "pkg-a", status="REJECTED")


class IntegrationStateTests(unittest.TestCase):
    def test_integration_state_transitions(self):
        cases = [
            ({}, "review_pending"),
            ({"review_verdict": {"status": "APPROVED"}}, "integration_pending"),
            (
                {
                    "review_verdict": {"status": "APPROVED"},
                    "integration_verdict": {"status": "APPROVED"},
                },
                "integration_ready",
            ),
            ({"review_verdict": {"status": "REJECTED"}}, "rejected"),
            (
                {
                    "review_verdict": {"status": "APPROVED"},
                    "integration_verdict": {"status": "REJECTED"},
                },
                "rejected",
            ),
        ]
        for package, expected in cases:
            with self.subTest(package=package):
                self.assertEqual(team_workstreams.integration_state(package), expected)


class AggregateWithVerdictsTests(unittest.TestCase):
    def test_aggregate_with_verdicts_annotates_integration_state(self):
        handles = [{"feature_id": "pkg-a", "final_status": "PASSED", "changed_files": ["a.py"]}]
        packages = [
            {
                **_package("pkg-a"),
                "review_verdict": {"status": "APPROVED"},
                "integration_verdict": {"status": "APPROVED"},
            }
        ]
        result = team_workstreams.aggregate_with_verdicts(0, handles, packages)
        self.assertEqual(result["wave_index"], 0)
        self.assertEqual(result["features"][0]["changed_files"], ["a.py"])
        self.assertEqual(result["features"][0]["integration_state"], "integration_ready")

    def test_aggregate_with_verdicts_calls_worktree_aggregate(self):
        handles = [{"feature_id": "pkg-a", "final_status": "PASSED", "changed_files": []}]
        packages = [_package("pkg-a")]
        with patch.object(worktree, "aggregate", wraps=worktree.aggregate) as mock_aggregate:
            team_workstreams.aggregate_with_verdicts(0, handles, packages)
        mock_aggregate.assert_called_once_with(0, handles)


class ReuseNotDuplicateTests(unittest.TestCase):
    """US3: team_workstreams.py must not reimplement wave/worktree/conflict logic."""

    def test_team_workstreams_defines_no_duplicate_wave_or_worktree_logic(self):
        duplicated = {"compute_waves", "plan_worktree", "conflicts"}
        self.assertTrue(duplicated.isdisjoint(dir(team_workstreams)))


if __name__ == "__main__":
    unittest.main()
