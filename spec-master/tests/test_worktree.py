import subprocess
import unittest
from unittest.mock import patch

import _pathfix  # noqa: F401
import worktree


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["git"], returncode=returncode, stdout=stdout)


class ComputeWavesTests(unittest.TestCase):
    def test_compute_waves_independent_features_same_wave(self):
        features = [
            {"id": "a", "dependencies": []},
            {"id": "b", "dependencies": []},
        ]
        waves = worktree.compute_waves(features)
        self.assertEqual(len(waves), 1)
        self.assertEqual(set(waves[0]["feature_ids"]), {"a", "b"})

    def test_compute_waves_dependency_strictly_later_wave(self):
        features = [
            {"id": "a", "dependencies": []},
            {"id": "b", "dependencies": ["a"]},
        ]
        waves = worktree.compute_waves(features)
        self.assertEqual(waves[0]["feature_ids"], ["a"])
        self.assertEqual(waves[1]["feature_ids"], ["b"])


class PlanWorktreeTests(unittest.TestCase):
    def test_plan_worktree_creates_handle_per_feature_in_multi_feature_wave(self):
        with patch.object(worktree, "run_git", return_value=_completed()) as mock_run_git, \
             patch("worktree.os.path.isdir", return_value=False):
            handle = worktree.plan_worktree("feat-a", "/repo", "trunk", wave_size=2)

        mock_run_git.assert_called_once()
        args, kwargs = mock_run_git.call_args
        self.assertIn("worktree", args[0])
        self.assertIn("add", args[0])
        self.assertEqual(handle["path"], "/repo/.spec-master/worktrees/feat-a")
        self.assertEqual(handle["feature_id"], "feat-a")
        self.assertEqual(handle["state"], "created")

    def test_plan_worktree_reuses_existing_path_without_recreating(self):
        with patch.object(worktree, "run_git") as mock_run_git, \
             patch("worktree.os.path.isdir", return_value=True):
            handle = worktree.plan_worktree("feat-a", "/repo", "trunk", wave_size=2)

        mock_run_git.assert_not_called()
        self.assertEqual(handle["path"], "/repo/.spec-master/worktrees/feat-a")
        self.assertEqual(handle["state"], "created")

    def test_single_feature_wave_skips_worktree_creation(self):
        with patch.object(worktree, "run_git") as mock_run_git:
            handle = worktree.plan_worktree("feat-a", "/repo", "trunk", wave_size=1)

        mock_run_git.assert_not_called()
        self.assertEqual(handle["path"], "/repo")
        self.assertEqual(handle["state"], "skipped")

    def test_non_git_repo_falls_back_to_sequential(self):
        with patch.object(worktree, "run_git") as mock_run_git:
            handle = worktree.plan_worktree("feat-a", "/repo", "trunk", wave_size=2, is_git_repo=False)

        mock_run_git.assert_not_called()
        self.assertEqual(handle["path"], "/repo")
        self.assertEqual(handle["state"], "skipped")


class ResolveProjectRootTests(unittest.TestCase):
    def test_resolve_project_root_returns_worktree_path(self):
        with patch.object(worktree, "run_git", return_value=_completed()), \
             patch("worktree.os.path.isdir", return_value=False):
            handle = worktree.plan_worktree("feat-a", "/repo", "trunk", wave_size=2)

        self.assertEqual(worktree.resolve_project_root(handle), handle["path"])
        self.assertEqual(worktree.resolve_project_root(handle), "/repo/.spec-master/worktrees/feat-a")


class ConflictsTests(unittest.TestCase):
    def test_conflicts_detects_overlapping_files(self):
        responses = [
            _completed("head-a\n"),   # rev-parse HEAD in path_a
            _completed("head-b\n"),   # rev-parse HEAD in path_b
            _completed("base\n"),     # merge-base
            _completed("shared.py\nonly_a.py\n"),  # diff base..head_a
            _completed("shared.py\nonly_b.py\n"),  # diff base..head_b
        ]
        with patch.object(worktree, "run_git", side_effect=responses):
            result = worktree.conflicts("/repo/wt-a", "/repo/wt-b")

        self.assertEqual(result["files"], ["shared.py"])

    def test_conflicts_empty_when_no_overlap(self):
        responses = [
            _completed("head-a\n"),
            _completed("head-b\n"),
            _completed("base\n"),
            _completed("only_a.py\n"),
            _completed("only_b.py\n"),
        ]
        with patch.object(worktree, "run_git", side_effect=responses):
            result = worktree.conflicts("/repo/wt-a", "/repo/wt-b")

        self.assertEqual(result["files"], [])


class AggregateTests(unittest.TestCase):
    def test_aggregate_records_status_and_changed_files(self):
        handles = [
            {"feature_id": "a", "final_status": "PASSED", "changed_files": ["a.py"]},
            {"feature_id": "b", "final_status": "PASSED", "changed_files": ["b.py"]},
        ]
        result = worktree.aggregate(0, handles)
        self.assertEqual(result["wave_index"], 0)
        self.assertEqual(len(result["features"]), 2)
        self.assertEqual(result["features"][0]["feature_id"], "a")
        self.assertEqual(result["features"][0]["changed_files"], ["a.py"])
        self.assertEqual(result["conflicts"], [])

    def test_aggregate_preserves_blocked_worktree_directory(self):
        handles = [{"feature_id": "a", "state": "conflict_pending", "path": "/repo/.spec-master/worktrees/a"}]
        with patch.object(worktree, "run_git") as mock_run_git:
            result = worktree.aggregate(0, handles)

        mock_run_git.assert_not_called()
        self.assertEqual(result["features"][0]["final_status"], "conflict_pending")


if __name__ == "__main__":
    unittest.main()
