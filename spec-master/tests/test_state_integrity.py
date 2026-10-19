import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

import _pathfix  # noqa: F401
import state as state_mod

LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "lib")


class AtomicSaveAndLockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, ".spec-master", "state.json")
        state_mod.init(self.path, context="ctx.md")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_leaves_no_temp_files(self):
        state_mod.save(self.path, state_mod.load(self.path))
        leftovers = [name for name in os.listdir(os.path.dirname(self.path)) if name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_transaction_saves_only_on_success(self):
        with state_mod.transaction(self.path) as s:
            s["status"] = "DISCOVERING"
        self.assertEqual(state_mod.load(self.path)["status"], "DISCOVERING")
        with self.assertRaises(RuntimeError):
            with state_mod.transaction(self.path) as s:
                s["status"] = "PLANNING"
                raise RuntimeError("boom")
        self.assertEqual(state_mod.load(self.path)["status"], "DISCOVERING")

    def test_lock_times_out_while_held(self):
        with state_mod.locked(self.path):
            with self.assertRaises(state_mod.StateError):
                with state_mod.locked(self.path, timeout=0.1):
                    pass

    def test_concurrent_threads_do_not_lose_updates(self):
        def add(index):
            with state_mod.transaction(self.path) as s:
                state_mod.upsert_feature(s, {"id": f"f{index}"})

        threads = [threading.Thread(target=add, args=(i,)) for i in range(16)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        ids = {f["id"] for f in state_mod.load(self.path)["features"]}
        self.assertEqual(ids, {f"f{i}" for i in range(16)})

    def test_concurrent_cli_processes_do_not_lose_updates(self):
        # The audit reproduced 6-50% lost updates with 16 concurrent upserts.
        cli = os.path.join(LIB_DIR, "cli.py")
        procs = [
            subprocess.Popen(
                [sys.executable, cli, "state", "upsert-feature", "--path", self.path,
                 "--feature-json", json.dumps({"id": f"p{i}", "name": f"P{i}"})],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            for i in range(16)
        ]
        codes = [proc.wait(timeout=60) for proc in procs]
        for proc in procs:
            proc.stdout.close()
            proc.stderr.close()
        self.assertEqual(codes, [0] * 16)
        ids = {f["id"] for f in state_mod.load(self.path)["features"]}
        self.assertEqual(ids, {f"p{i}" for i in range(16)})


class UpsertMetadataTests(unittest.TestCase):
    def setUp(self):
        self.state = state_mod.default_state("ctx.md")

    def upsert(self, feature, **kwargs):
        return state_mod.upsert_feature_metadata(self.state, feature, **kwargs)

    def test_new_feature_starts_pending_and_metadata_merges(self):
        feature, info = self.upsert({"id": "f1", "name": "One", "spec_directory": "specs/001-f1"})
        self.assertEqual(feature["status"], "PENDING")
        self.assertEqual(set(feature["phases"].values()), {"PENDING"})
        self.assertEqual(info, {"imported_phases": [], "rejected": []})
        feature, _ = self.upsert({"id": "f1", "description": "More detail"})
        self.assertEqual(feature["name"], "One")  # merged, not replaced
        self.assertEqual(feature["description"], "More detail")

    def test_phase_promotion_through_upsert_is_refused(self):
        self.upsert({"id": "f1"})
        with self.assertRaises(state_mod.InvalidTransitionError) as ctx:
            self.upsert({"id": "f1", "phases": {"specify": "PASSED"}})
        self.assertIn("phases", str(ctx.exception))
        self.assertEqual(state_mod.find_feature(self.state, "f1")["phases"]["specify"], "PENDING")

    def test_completed_status_needs_every_phase_done(self):
        self.upsert({"id": "f1"})
        with self.assertRaises(state_mod.InvalidTransitionError):
            self.upsert({"id": "f1", "status": "COMPLETED"})
        feature, _ = self.upsert({"id": "f1", "status": "BLOCKED"})  # non-promoting statuses are metadata
        self.assertEqual(feature["status"], "BLOCKED")

    def test_ghost_feature_is_refused(self):
        # The audit's reproduction: COMPLETED + all phases PASSED for a directory that does not exist.
        ghost = {"id": "ghost", "status": "COMPLETED", "spec_directory": "specs/999-ghost",
                 "phases": {phase: "PASSED" for phase in state_mod.FEATURE_PHASES}}
        with self.assertRaises(state_mod.InvalidTransitionError):
            self.upsert(ghost)
        self.assertEqual(self.state["features"], [])

    def test_import_unverified_reports_promoted_phases(self):
        history = {"id": "old", "status": "COMPLETED",
                   "phases": {phase: "PASSED" for phase in state_mod.FEATURE_PHASES}}
        feature, info = self.upsert(history, allow_unverified=True)
        self.assertEqual(feature["status"], "COMPLETED")
        self.assertEqual(info["imported_phases"], list(state_mod.FEATURE_PHASES))
        self.assertEqual(info["rejected"], ["phases"])

    def test_core_owned_fields_are_never_accepted(self):
        for field, value in (("evidence", {"plan": {"verified": True}}), ("attempts", {"plan": []}),
                             ("risk", {"tier": "XS"})):
            with self.subTest(field=field):
                with self.assertRaises(state_mod.InvalidTransitionError):
                    self.upsert({"id": "f1", field: value}, allow_unverified=True)

    def test_unknown_phase_or_status_is_an_error(self):
        with self.assertRaises(state_mod.InvalidTransitionError):
            self.upsert({"id": "f1", "phases": {"deploy": "PASSED"}}, allow_unverified=True)
        with self.assertRaises(state_mod.InvalidTransitionError):
            self.upsert({"id": "f1", "phases": {"plan": "DONE"}}, allow_unverified=True)
        with self.assertRaises(state_mod.StateError):
            self.upsert({"name": "no id"})


class GitignoreTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_locks_under_spec_master_are_ignored_once(self):
        target = os.path.join(self.root, ".spec-master", "metrics", "rounds.json")
        with state_mod.locked(target):
            pass
        gitignore = os.path.join(self.root, ".spec-master", ".gitignore")
        with open(gitignore, encoding="utf-8") as fh:
            self.assertIn("*.lock", fh.read().splitlines())
        with open(gitignore, "w", encoding="utf-8") as fh:
            fh.write("custom\n")
        with state_mod.locked(os.path.join(self.root, ".spec-master", "state.json")):
            pass
        with open(gitignore, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "custom\n")  # never rewritten

    def test_locks_elsewhere_write_nothing_else(self):
        target = os.path.join(self.root, "data", "file.json")
        with state_mod.locked(target):
            pass
        self.assertEqual(sorted(os.listdir(os.path.join(self.root, "data"))), ["file.json.lock"])
        self.assertIsNone(state_mod.spec_master_dir(target))


if __name__ == "__main__":
    unittest.main()
