import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import _pathfix  # noqa: F401
import dispatch
import worktree

FEATURE = "feat"


def _package(pid, owner="backend-dev", depends=(), owns=None, kind=None):
    package = {"id": pid, "feature_id": FEATURE, "title": f"title {pid}", "owner_agent": owner,
               "depends_on": list(depends), "owned_paths": owns if owns is not None else [f"src/{pid}/*"]}
    if kind:
        package["kind"] = kind
    return package


def _write(root, relative, text):
    path = os.path.join(root, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def _project(packages, policy=None, git=True):
    tmp = tempfile.TemporaryDirectory()
    root = os.path.realpath(tmp.name)
    _write(root, ".spec-master/workstreams.json", json.dumps({"packages": packages}))
    if policy is not None:
        _write(root, ".spec-master/policy.json", json.dumps(policy))
    if git:
        os.makedirs(os.path.join(root, ".git"))
    return tmp, root


class ResolveCapTests(unittest.TestCase):
    def test_argument_beats_policy_beats_default(self):
        tmp, root = _project([], policy={"dispatch": {"max_agents": 6}})
        self.addCleanup(tmp.cleanup)
        self.assertEqual(dispatch.resolve_cap(root, 2), 2)
        self.assertEqual(dispatch.resolve_cap(root, None), 6)
        tmp2, root2 = _project([])
        self.addCleanup(tmp2.cleanup)
        self.assertEqual(dispatch.resolve_cap(root2, None), 4)

    def test_zero_and_nine_are_rejected(self):
        tmp, root = _project([])
        self.addCleanup(tmp.cleanup)
        for bad in (0, 9, -1):
            with self.assertRaises(ValueError):
                dispatch.resolve_cap(root, bad)

    def test_invalid_policy_value_is_rejected(self):
        tmp, root = _project([], policy={"dispatch": {"max_agents": 99}})
        self.addCleanup(tmp.cleanup)
        with self.assertRaises(ValueError):
            dispatch.resolve_cap(root, None)


class BuildPackagesTests(unittest.TestCase):
    def test_packages_come_from_tasks_md_with_owner_and_depends_on(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = tmp.name
        _write(root, ".spec-master/state.json",
               json.dumps({"features": [{"id": FEATURE, "spec_directory": "specs/001-feat"}]}))
        _write(root, "specs/001-feat/tasks.md",
               "- [ ] T001 [US1] build the api endpoint | depends_on: [] | owns: src/api/*\n"
               "- [ ] T002 [P] build the ui form | depends_on: [T001] | owns: src/ui/*, tests/ui/*\n"
               "- [x] T003 done already | depends_on: [] | owns: x\n")
        packages = dispatch.build_packages(root, FEATURE)
        self.assertEqual([p["id"] for p in packages], ["T001", "T002"])
        self.assertEqual(packages[1]["depends_on"], ["T001"])
        self.assertEqual(packages[1]["owned_paths"], ["src/ui/*", "tests/ui/*"])
        self.assertNotEqual(packages[0]["reviewer_agent"], packages[0]["owner_agent"])

    def test_workstreams_json_wins_and_is_filtered_by_feature(self):
        other = dict(_package("X"), feature_id="other")
        tmp, root = _project([_package("A"), other])
        self.addCleanup(tmp.cleanup)
        self.assertEqual([p["id"] for p in dispatch.build_packages(root, FEATURE)], ["A"])


class BuildManifestTests(unittest.TestCase):
    def test_entry_fields_and_reviewer_differs_from_owner(self):
        tmp, root = _project([_package("A"), _package("B", owner="frontend-dev")])
        self.addCleanup(tmp.cleanup)
        manifest = dispatch.build_manifest(root, FEATURE, 0)
        self.assertEqual(manifest["schema"], "spec-master.dispatch/v1")
        keys = {"agent_key", "package_id", "feature_id", "role", "card", "playbook", "model", "effort", "worktree",
                "branch", "owner", "reviewer", "owned_paths", "depends_on", "result_path"}
        for entry in manifest["entries"]:
            self.assertTrue(keys <= set(entry), keys - set(entry))
            self.assertNotEqual(entry["reviewer"], entry["owner"])
        roles = sorted(e["role"] for e in manifest["entries"])
        self.assertEqual(roles, ["sm-implement", "sm-implement", "sm-review", "sm-review"])
        self.assertFalse(manifest["integration"]["auto_merge"])
        self.assertTrue(manifest["fallback_instructions"])

    def test_seven_independent_packages_cap_four_make_batches_4_3(self):
        tmp, root = _project([_package(f"P{i}") for i in range(7)])
        self.addCleanup(tmp.cleanup)
        manifest = dispatch.build_manifest(root, FEATURE, 0, max_agents=4)
        self.assertEqual([len(b) for b in manifest["batches"]], [4, 3])
        flat = [k for batch in manifest["batches"] for k in batch]
        self.assertEqual(len(set(flat)), 7)
        self.assertEqual(manifest["max_agents"], 4)

    def test_review_entry_carries_after_and_sits_in_review_batches(self):
        tmp, root = _project([_package("A"), _package("B")])
        self.addCleanup(tmp.cleanup)
        manifest = dispatch.build_manifest(root, FEATURE, 0)
        by_key = {e["agent_key"]: e for e in manifest["entries"]}
        reviews = [e for e in manifest["entries"] if e["role"] == "sm-review"]
        self.assertEqual(len(reviews), 2)
        for review in reviews:
            self.assertEqual(review["after"], [f"{FEATURE}:{review['package_id']}:sm-implement"])
            self.assertIn(review["after"][0], by_key)
            self.assertTrue(review["read_only"])
        self.assertEqual(sum(len(b) for b in manifest["review_batches"]), 2)

    def test_dependent_package_lands_in_a_later_wave(self):
        tmp, root = _project([_package("A"), _package("B", depends=["A"])])
        self.addCleanup(tmp.cleanup)
        wave0 = dispatch.build_manifest(root, FEATURE, 0)
        wave1 = dispatch.build_manifest(root, FEATURE, 1)
        self.assertEqual({e["package_id"] for e in wave0["entries"]}, {"A"})
        self.assertEqual({e["package_id"] for e in wave1["entries"]}, {"B"})
        with self.assertRaises(ValueError):
            dispatch.build_manifest(root, FEATURE, 2)

    def test_single_package_wave_and_non_git_repo_have_no_worktree(self):
        tmp, root = _project([_package("A")])
        self.addCleanup(tmp.cleanup)
        self.assertTrue(all(e["worktree"] is None for e in dispatch.build_manifest(root, FEATURE, 0)["entries"]))
        tmp2, root2 = _project([_package("A"), _package("B")], git=False)
        self.addCleanup(tmp2.cleanup)
        self.assertTrue(all(e["worktree"] is None for e in dispatch.build_manifest(root2, FEATURE, 0)["entries"]))

    def test_multi_package_git_wave_plans_worktree_paths_for_owner_and_reviewer(self):
        tmp, root = _project([_package("A"), _package("B")])
        self.addCleanup(tmp.cleanup)
        manifest = dispatch.build_manifest(root, FEATURE, 0)
        for entry in manifest["entries"]:
            self.assertEqual(entry["worktree"], os.path.join(root, ".spec-master", "worktrees", entry["package_id"]))

    def test_patch_lane_is_refused_and_force_needs_a_reason(self):
        tmp, root = _project([_package("A")])
        self.addCleanup(tmp.cleanup)
        with self.assertRaises(ValueError):
            dispatch.build_manifest(root, FEATURE, 0, lane="patch")
        with self.assertRaises(ValueError):
            dispatch.build_manifest(root, FEATURE, 0, lane="patch", force_lane=True)
        manifest = dispatch.build_manifest(root, FEATURE, 0, lane="patch", force_lane="measuring")
        self.assertEqual(manifest["forced_lane_reason"], "measuring")

    def test_sm_spec_only_for_spec_kind_packages(self):
        tmp, root = _project([_package("S", kind="spec"), _package("A")])
        self.addCleanup(tmp.cleanup)
        manifest = dispatch.build_manifest(root, FEATURE, 0)
        roles = {e["package_id"]: e["role"] for e in manifest["entries"] if e["role"] != "sm-review"}
        self.assertEqual(roles, {"S": "sm-spec", "A": "sm-implement"})

    def test_deterministic_and_within_the_token_budget(self):
        tmp, root = _project([_package(f"P{i}") for i in range(4)])
        self.addCleanup(tmp.cleanup)
        first = dispatch.build_manifest(root, FEATURE, 0)
        second = dispatch.build_manifest(root, FEATURE, 0)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertLessEqual(first["estimated_tokens"], 2000)
        body = {k: v for k, v in first.items() if k != "estimated_tokens"}
        self.assertLessEqual(len(json.dumps(body, separators=(",", ":"))) // 4, 2000)

    def test_unknown_feature_raises(self):
        tmp, root = _project([_package("A")])
        self.addCleanup(tmp.cleanup)
        with self.assertRaises(ValueError):
            dispatch.build_manifest(root, "nope", 0)


def _git(root, *args):
    return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=root, check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


class PrepareTests(unittest.TestCase):
    def _repo(self):
        tmp, root = _project([_package("A"), _package("B")], git=False)
        self.addCleanup(tmp.cleanup)
        _git(root, "init", "-q")
        _write(root, "README.md", "x")
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "init")
        return root

    def test_prepare_delegates_to_plan_worktree_and_writes_scope_and_marker(self):
        root = self._repo()
        with patch.object(worktree, "plan_worktree", wraps=worktree.plan_worktree) as plan:
            result = dispatch.prepare(root, FEATURE, 0)
        self.assertEqual(plan.call_count, 2)
        for entry in result["prepared"]:
            self.assertTrue(os.path.isdir(entry["worktree"]))
            with open(os.path.join(entry["worktree"], ".spec-master", "worktree.json"), encoding="utf-8") as fh:
                marker = json.load(fh)
            self.assertEqual(marker["agent_key"], entry["agent_key"])
            self.assertEqual(marker["main_root"], root)
            self.assertFalse(marker["read_only"])
            self.assertTrue(os.path.isfile(dispatch.scope_path(root, entry["agent_key"])))

    def test_prepare_is_idempotent(self):
        root = self._repo()
        first = dispatch.prepare(root, FEATURE, 0)
        second = dispatch.prepare(root, FEATURE, 0)
        self.assertEqual(first["prepared"], second["prepared"])

    def test_review_phase_writes_read_only_markers(self):
        root = self._repo()
        dispatch.prepare(root, FEATURE, 0)
        result = dispatch.prepare(root, FEATURE, 0, phase="review")
        for entry in result["prepared"]:
            with open(os.path.join(entry["worktree"], ".spec-master", "worktree.json"), encoding="utf-8") as fh:
                marker = json.load(fh)
            self.assertEqual(marker["role"], "sm-review")
            self.assertTrue(marker["read_only"])

    def test_in_place_packages_get_scope_but_no_marker(self):
        tmp, root = _project([_package("A")])
        self.addCleanup(tmp.cleanup)
        result = dispatch.prepare(root, FEATURE, 0)
        self.assertFalse(os.path.exists(os.path.join(root, ".spec-master", "worktree.json")))
        self.assertTrue(os.path.isfile(dispatch.scope_path(root, result["prepared"][0]["agent_key"])))


class AggregateTests(unittest.TestCase):
    def test_aggregate_reports_and_never_mutates(self):
        tmp, root = _project([_package("A"), _package("B")])
        self.addCleanup(tmp.cleanup)
        calls = []

        def fake(args, cwd):
            calls.append(args)
            out = ""
            if args[:1] == ["status"]:
                out = " M src/a.py\n"
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=out)

        with patch.object(worktree, "run_git", side_effect=fake):
            result = dispatch.aggregate(root, FEATURE, 0)
        self.assertEqual({f["feature_id"] for f in result["features"]}, {"A", "B"})
        for feature in result["features"]:
            self.assertEqual(feature["integration_state"], "review_pending")
            self.assertIn("src/a.py", feature["changed_files"])
        self.assertIn("conflicts", result)
        forbidden = {"merge", "rebase", "push", "reset", "checkout"}
        for args in calls:
            self.assertNotIn(args[0], forbidden)
            self.assertFalse(args[:2] == ["worktree", "remove"])


class RecordResultTests(unittest.TestCase):
    def setUp(self):
        self.tmp, self.root = _project([_package("A"), _package("B")])
        self.addCleanup(self.tmp.cleanup)

    def _record(self, text, **kw):
        return dispatch.record_result(self.root, FEATURE, 0, "A", text, **kw)

    def test_parses_last_phase_result_and_allow_lists_fields(self):
        text = ('noise {"phase_result":"failed"} more\n'
                '{"phase_result":"artifact_updated","summary":"done","files":["a.py"],"questions":[],'
                '"evidence":"ok","secret":"leak"}')
        record = self._record(text)
        self.assertEqual(record["phase_result"], "artifact_updated")
        self.assertNotIn("secret", record)
        self.assertEqual(record["files"], ["a.py"])
        self.assertFalse(record["truncated"])
        with open(os.path.join(self.root, record["path"]), encoding="utf-8") as fh:
            stored = json.load(fh)
        self.assertEqual(stored["schema"], "spec-master.dispatch-result/v1")

    def test_large_result_is_truncated_to_8000_chars(self):
        big = json.dumps({"phase_result": "artifact_updated", "summary": "s" * 20000,
                          "files": [f"f{i}.py" * 20 for i in range(500)], "evidence": "e" * 20000})
        record = self._record(big)
        self.assertTrue(record["truncated"])
        self.assertLessEqual(len(json.dumps(record, ensure_ascii=False)), dispatch.RESULT_MAX_CHARS)
        with open(os.path.join(self.root, record["path"]), encoding="utf-8") as fh:
            self.assertLessEqual(len(fh.read().strip()), dispatch.RESULT_MAX_CHARS)

    def test_invalid_block_is_recorded_as_failed_with_reason(self):
        record = self._record("no json here {not json}")
        self.assertEqual(record["phase_result"], "failed")
        self.assertIn("no valid phase_result", record["summary"])

    def test_owner_cannot_review_own_package(self):
        self._record('{"phase_result":"artifact_updated"}', agent_key=f"{FEATURE}:A:sm-implement", agent_id="ag1")
        with self.assertRaises(ValueError):
            dispatch.record_result(self.root, FEATURE, 0, "A", '{"phase_result":"artifact_updated"}',
                                   role="sm-review", agent_key=f"{FEATURE}:A:sm-implement")
        with self.assertRaises(ValueError):
            dispatch.record_result(self.root, FEATURE, 0, "A", '{"phase_result":"artifact_updated"}',
                                   role="sm-review", agent_id="ag1")

    def test_review_requires_the_owner_result_first(self):
        with self.assertRaises(ValueError):
            dispatch.record_result(self.root, FEATURE, 0, "A", '{"phase_result":"artifact_updated"}',
                                   role="sm-review")
        self._record('{"phase_result":"artifact_updated"}')
        record = dispatch.record_result(self.root, FEATURE, 0, "A", '{"phase_result":"artifact_updated"}',
                                        role="sm-review", agent_id="ag2")
        self.assertTrue(record["path"].endswith("A.review.json"))

    def test_unknown_package_and_role_raise(self):
        with self.assertRaises(ValueError):
            dispatch.record_result(self.root, FEATURE, 0, "ZZ", "{}")
        with self.assertRaises(ValueError):
            self._record("{}", role="sm-bogus")

    def test_write_is_atomic_no_temp_files_left(self):
        record = self._record('{"phase_result":"artifact_updated"}')
        directory = os.path.dirname(os.path.join(self.root, record["path"]))
        self.assertEqual([n for n in os.listdir(directory) if n.endswith(".tmp")], [])


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp, self.root = _project([_package("A"), _package("B")])
        self.addCleanup(self.tmp.cleanup)

    def _entry(self, status, package, role):
        return next(e for e in status["entries"] if e["role"] == role and e["package_id"] == package)

    def test_missing_producers_give_nulls_and_a_note(self):
        status = dispatch.status(self.root, FEATURE, 0)
        entry = self._entry(status, "A", "sm-implement")
        self.assertIsNone(entry["started_at"])
        self.assertIsNone(entry["tokens"])
        self.assertFalse(entry["result_recorded"])
        self.assertTrue(status["notes"])

    def test_joins_events_and_ledger_by_agent_id_and_skips_corrupt_lines(self):
        dispatch.record_result(self.root, FEATURE, 0, "A", '{"phase_result":"artifact_updated"}', agent_id="ag1")
        _write(self.root, ".spec-master/events.jsonl",
               json.dumps({"type": "agent.started", "ts": "2026-01-01T00:00:00Z", "agent_id": "ag1"}) + "\n"
               "{corrupt\n" +
               json.dumps({"type": "agent.finished", "ts": "2026-01-01T00:05:00Z", "agent_id": "ag1"}) + "\n")

        def provider(root):
            return {"by_agent": {"ag1": {"agent_type": "sm-implement", "total_tokens": 42}}}

        status = dispatch.status(self.root, FEATURE, 0, ledger_summary=provider)
        entry = self._entry(status, "A", "sm-implement")
        self.assertEqual(entry["started_at"], "2026-01-01T00:00:00Z")
        self.assertEqual(entry["finished_at"], "2026-01-01T00:05:00Z")
        self.assertEqual(entry["tokens"]["total_tokens"], 42)
        self.assertTrue(entry["result_recorded"])

    def test_review_eligible_only_after_owner_result(self):
        before = dispatch.status(self.root, FEATURE, 0)
        self.assertFalse(self._entry(before, "A", "sm-review")["eligible"])
        dispatch.record_result(self.root, FEATURE, 0, "A", '{"phase_result":"artifact_updated"}')
        after = dispatch.status(self.root, FEATURE, 0)
        self.assertTrue(self._entry(after, "A", "sm-review")["eligible"])
        self.assertFalse(self._entry(after, "B", "sm-review")["eligible"])

    def test_status_is_read_only(self):
        dispatch.status(self.root, FEATURE, 0)
        self.assertFalse(os.path.exists(os.path.join(self.root, ".spec-master", "dispatch")))


if __name__ == "__main__":
    unittest.main()
