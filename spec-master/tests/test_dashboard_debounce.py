"""P5: debounced dashboard re-render from hooks and a cached graph section."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import _pathfix  # noqa: F401
import dashboard
import hooks


class DebounceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.addCleanup(self.tmp.cleanup)
        self.calls = []
        self.patch = mock.patch.object(dashboard, "write", side_effect=lambda r: self.calls.append(r) or "out.html")
        self.patch.start()
        self.addCleanup(self.patch.stop)
        env = {k: v for k, v in os.environ.items() if k != "SPEC_MASTER_DASHBOARD_DEBOUNCE"}
        self.env = mock.patch.dict(os.environ, env, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def _fire(self):
        return hooks._run_internal(self.root, {"type": "render_dashboard"}, {})

    def test_burst_renders_once(self):
        first = self._fire()
        second = self._fire()
        third = self._fire()
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(first["executed"])
        self.assertNotIn("debounced", first)
        self.assertTrue(second["executed"] and second["debounced"])
        self.assertTrue(third["debounced"])

    def test_renders_again_after_the_window(self):
        with mock.patch.dict(os.environ, {"SPEC_MASTER_DASHBOARD_DEBOUNCE": "0.05"}):
            self._fire()
            time.sleep(0.08)
            self._fire()
        self.assertEqual(len(self.calls), 2)

    def test_zero_disables_the_debounce(self):
        with mock.patch.dict(os.environ, {"SPEC_MASTER_DASHBOARD_DEBOUNCE": "0"}):
            self._fire()
            self._fire()
        self.assertEqual(len(self.calls), 2)

    def test_bad_value_falls_back_to_default(self):
        with mock.patch.dict(os.environ, {"SPEC_MASTER_DASHBOARD_DEBOUNCE": "soon"}):
            self.assertEqual(hooks.dashboard_debounce_seconds(), hooks.DASHBOARD_DEBOUNCE_DEFAULT)
        self.assertEqual(hooks.DASHBOARD_DEBOUNCE_DEFAULT, 2.0)

    def test_stamp_lives_under_cache_and_corrupt_stamp_renders(self):
        self._fire()
        stamp = Path(self.root) / ".spec-master" / "cache" / "dashboard-render.json"
        self.assertTrue(stamp.is_file())
        stamp.write_text("{garbage", encoding="utf-8")
        self._fire()
        self.assertEqual(len(self.calls), 2)

    def test_failed_render_does_not_stamp(self):
        self.patch.stop()
        with mock.patch.object(dashboard, "write", side_effect=RuntimeError("boom")):
            result = self._fire()
        self.patch.start()
        self.assertFalse(result["executed"])
        self.assertFalse((Path(self.root) / ".spec-master" / "cache" / "dashboard-render.json").exists())


class GraphCacheTests(unittest.TestCase):
    def setUp(self):
        dashboard._GRAPH_CACHE.clear()

    def _graph_dir(self, root):
        path = Path(root) / dashboard.GRAPH_RELPATH
        path.mkdir(parents=True)
        return path

    def test_absent_graph_is_not_cached_or_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = dashboard._graph(tmp, [])
            self.assertFalse(out["present"])
            self.assertFalse((Path(tmp) / dashboard.GRAPH_RELPATH).exists())

    def test_second_call_reuses_the_loaded_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._graph_dir(tmp)
            loads = []
            import graph.store as store
            real = store.FileGraphStore.load

            def counting(self_):
                loads.append(1)
                return real(self_)

            with mock.patch.object(store.FileGraphStore, "load", counting):
                first = dashboard._graph(tmp, [])
                second = dashboard._graph(tmp, [])
            self.assertEqual(len(loads), 1)
            self.assertEqual(first, second)

    def test_a_changed_file_invalidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            gdir = self._graph_dir(tmp)
            loads = []
            import graph.store as store
            real = store.FileGraphStore.load

            def counting(self_):
                loads.append(1)
                return real(self_)

            with mock.patch.object(store.FileGraphStore, "load", counting):
                dashboard._graph(tmp, [])
                (gdir / "n.md").write_text("changed", encoding="utf-8")
                dashboard._graph(tmp, [])
            self.assertEqual(len(loads), 2)

    def test_cached_result_is_a_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._graph_dir(tmp)
            first = dashboard._graph(tmp, [])
            first["nodes"] = 999
            self.assertNotEqual(dashboard._graph(tmp, [])["nodes"], 999)


if __name__ == "__main__":
    unittest.main()
