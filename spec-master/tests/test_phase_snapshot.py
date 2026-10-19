"""P4: pruned walk and mtime/size hash cache for phase_contracts.snapshot."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

import _pathfix  # noqa: F401
import phase_contracts as pc


def _write(root, relative, data=b"x"):
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


class WalkTests(unittest.TestCase):
    def test_pruned_directories_are_never_entered(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "src/a.py")
            for name in (".git", "node_modules", "dist", "build", "target", ".venv", "vendor", "vendored",
                         "__pycache__", ".mypy_cache"):
                _write(tmp, f"{name}/deep/f.txt")
                _write(tmp, f"src/{name}/g.txt")
            files = sorted(pc.walk_project(Path(tmp)))
            self.assertEqual(files, ["src/a.py"])

    def test_walk_does_not_descend_into_pruned_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "node_modules/x/y.js")
            seen = []
            real = os.walk

            def spy(*a, **k):
                for top, dirs, files in real(*a, **k):
                    seen.append(top)
                    yield top, dirs, files

            pc.os.walk = spy
            try:
                list(pc.walk_project(Path(tmp)))
            finally:
                pc.os.walk = real
            self.assertFalse(any("node_modules" in s for s in seen))

    def test_spec_master_ignored_prefixes_still_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, ".spec-master/state.json")
            _write(tmp, ".spec-master/logs/a.log")
            _write(tmp, ".spec-master/failed-attempts/a.json")
            _write(tmp, ".spec-master/cache/snapshot.json")
            _write(tmp, ".spec-master/keep.txt")
            self.assertEqual(sorted(pc.walk_project(Path(tmp))), [".spec-master/keep.txt"])


class SnapshotTests(unittest.TestCase):
    def test_hashes_match_sha256(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "a.txt", b"hello")
            self.assertEqual(pc.snapshot(Path(tmp)), {"a.txt": hashlib.sha256(b"hello").hexdigest()})

    def test_detects_modify_add_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "a.txt", b"one")
            _write(tmp, "b.txt", b"two")
            before = pc.snapshot(Path(tmp))
            _write(tmp, "a.txt", b"changed!")
            _write(tmp, "c.txt", b"new")
            os.remove(Path(tmp) / "b.txt")
            after = pc.snapshot(Path(tmp))
            self.assertEqual(pc.changed_paths(before, after), ["a.txt", "b.txt", "c.txt"])

    def test_same_size_rewrite_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "a.txt", b"aaaa")
            before = pc.snapshot(Path(tmp))
            _write(tmp, "a.txt", b"bbbb")
            self.assertEqual(pc.changed_paths(before, pc.snapshot(Path(tmp))), ["a.txt"])

    def test_cache_written_and_reused_without_rehashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, ".spec-master/keep.txt", b"k")
            _write(tmp, "a.txt", b"hello")
            pc.snapshot(Path(tmp))
            cache = Path(tmp) / ".spec-master" / "cache" / "snapshot.json"
            self.assertTrue(cache.is_file())
            calls = []
            real = pc._sha256_file
            pc._sha256_file = lambda p: calls.append(p) or real(p)
            try:
                pc.snapshot(Path(tmp))
            finally:
                pc._sha256_file = real
            self.assertEqual(calls, [])

    def test_cache_file_is_not_part_of_the_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "a.txt")
            first = pc.snapshot(Path(tmp))
            second = pc.snapshot(Path(tmp))
            self.assertEqual(first, second)
            self.assertFalse(any(k.startswith(".spec-master/cache") for k in second))

    def test_corrupt_cache_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "a.txt", b"hello")
            _write(tmp, ".spec-master/cache/snapshot.json", b"{not json")
            self.assertEqual(pc.snapshot(Path(tmp)), {"a.txt": hashlib.sha256(b"hello").hexdigest()})

    def test_stale_cache_entry_with_wrong_shape_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "a.txt", b"hello")
            _write(tmp, ".spec-master/cache/snapshot.json", json.dumps({"files": {"a.txt": "bogus"}}).encode())
            self.assertEqual(pc.snapshot(Path(tmp)), {"a.txt": hashlib.sha256(b"hello").hexdigest()})

    def test_unwritable_cache_dir_does_not_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "a.txt", b"hello")
            _write(tmp, ".spec-master", b"i am a file, not a dir")
            self.assertIn("a.txt", pc.snapshot(Path(tmp)))


if __name__ == "__main__":
    unittest.main()
