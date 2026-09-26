import json
import os
import re
import shutil
import tempfile
import time
import unittest
from unittest import mock

import _pathfix  # noqa: F401
import dashboard
import decision_memory
import hooks
import state as state_mod
from graph.model import GraphNode
from graph.store import FileGraphStore

ALL_PASSED = {phase: "PASSED" for phase in state_mod.FEATURE_PHASES}


def _tree(root):
    """Every path under root, relative, so tests can assert nothing else was created."""
    found = set()
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            found.add(os.path.relpath(os.path.join(dirpath, name), root))
    return found


class DashboardTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmp, ".spec-master", "state.json")
        state_mod.init(self.state_path, context="ctx.md")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _features(self, *features, **top_level):
        s = state_mod.load(self.state_path)
        for feature in features:
            state_mod.upsert_feature(s, dict(feature))
        s.update(top_level)
        state_mod.save(self.state_path, s)

    def _age(self, seconds=3600):
        """Push state.json and the firings log into the past so the page is not `settling`."""
        past = time.time() - seconds
        for rel in (dashboard.STATE_RELPATH, dashboard.FIRINGS_RELPATH):
            path = os.path.join(self.tmp, rel)
            if os.path.exists(path):
                os.utime(path, (past, past))

    def _lock(self, phase="specify", age_seconds=0):
        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - age_seconds))
        with open(os.path.join(self.tmp, dashboard.LOCK_RELPATH), "w", encoding="utf-8") as fh:
            json.dump({"phase": phase, "pid": 4242, "started_at": started}, fh)

    def _html(self, **kwargs):
        with open(dashboard.write(self.tmp, **kwargs), encoding="utf-8") as fh:
            return fh.read()


class CompletenessTests(DashboardTestBase):
    def test_feature_percent_counts_skipped_as_done(self):
        self._features({"id": "f1", "name": "F1",
                        "phases": {"specify": "PASSED", "clarify": "SKIPPED", "plan": "PASSED"}})
        feature = dashboard.build_model(self.tmp)["features"][0]
        self.assertEqual((feature["done"], feature["total"]), (3, 7))
        self.assertEqual(feature["percent"], 42.9)
        self.assertEqual(feature["current_phase"], "tasks")
        self.assertEqual([p["phase"] for p in feature["phases"]], state_mod.FEATURE_PHASES)

    def test_global_percent_is_phase_weighted(self):
        self._features({"id": "f1", "name": "F1", "phases": {**ALL_PASSED, "clarify": "SKIPPED"}},
                       {"id": "f2", "name": "F2"})
        model = dashboard.build_model(self.tmp)
        self.assertEqual(model["completeness"], {"done": 7, "total": 14, "percent": 50.0,
                                                 "features": 2, "features_done": 1})
        self.assertEqual(model["phase_totals"], {"PASSED": 6, "SKIPPED": 1, "PENDING": 7})
        self.assertEqual([f["percent"] for f in model["features"]], [100.0, 0.0])

    def test_no_features_is_zero_percent(self):
        completeness = dashboard.build_model(self.tmp)["completeness"]
        self.assertEqual((completeness["percent"], completeness["total"], completeness["features"]), (0.0, 0, 0))

    def test_failed_and_blocked_are_not_done(self):
        self._features({"id": "f1", "name": "F1", "phases": {"specify": "PASSED", "clarify": "FAILED",
                                                             "plan": "BLOCKED"}})
        self.assertEqual(dashboard.build_model(self.tmp)["features"][0]["done"], 1)


class RenderTests(DashboardTestBase):
    def test_dynamic_text_is_escaped(self):
        self._features({"id": "f1", "name": "<script>alert(1)</script>", "risk": {"tier": "<b>XL</b>"},
                        "dependencies": ['"><img src=x onerror=alert(2)>']})
        page = self._html()
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertNotIn("<img src=x", page)
        self.assertNotIn("<b>XL</b>", page)

    def test_tier_badge_only_when_risk_is_set(self):
        self._features({"id": "f1", "name": "F1", "risk": {"tier": "l"}}, {"id": "f2", "name": "F2"})
        model = dashboard.build_model(self.tmp)
        self.assertEqual([f["risk_tier"] for f in model["features"]], ["L", None])
        page = dashboard.render_html(model)
        self.assertEqual(page.count('class="tier"'), 1)
        self.assertIn('<span class="tier" title="Risk tier">L</span>', page)

    def test_phase_pills_carry_status_class_glyph_and_label(self):
        self._features({"id": "f1", "name": "F1", "phases": {"specify": "PASSED", "clarify": "SKIPPED",
                                                             "plan": "FAILED", "tasks": "BLOCKED"}})
        page = self._html()
        for css, phase, status in (("good", "specify", "PASSED"), ("skip", "clarify", "SKIPPED"),
                                   ("crit", "plan", "FAILED"), ("serious", "tasks", "BLOCKED"),
                                   ("neutral", "analyze", "PENDING")):
            self.assertIn(f'<li class="pill t-{css}" title="{phase}: {status}">', page)
            self.assertIn(f'<span class="sr">: {status}</span>', page)
        self.assertIn('aria-label="Phase status legend"', page)

    def test_page_is_self_contained_with_dark_mode_and_timestamp(self):
        self._features({"id": "f1", "name": "F1"})
        page = self._html()
        self.assertNotRegex(page, r"https?://")
        self.assertNotIn("<link", page)
        self.assertNotIn(" src=", page)
        self.assertIn("@media (prefers-color-scheme:dark)", page)
        self.assertIn('name="viewport"', page)
        self.assertRegex(page, r'<time datetime="\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ">')
        self.assertIn("UTC", page)
        self.assertRegex(dashboard.build_model(self.tmp)["generated_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_negative_refresh_is_rejected(self):
        with self.assertRaises(ValueError):
            dashboard.render_html(dashboard.build_model(self.tmp), refresh=-1)


class RunStateTests(DashboardTestBase):
    def test_meta_refresh_present_iff_active(self):
        self._features({"id": "f1", "name": "F1"})
        self._age()
        model = dashboard.build_model(self.tmp)
        self.assertEqual((model["run"]["state"], model["run"]["active"]), ("idle", False))
        idle_page = self._html()
        self.assertNotIn('http-equiv="refresh"', idle_page)
        self.assertNotIn('class="spin"', idle_page)
        self.assertNotIn("<script", idle_page)

        self._lock("specify")
        model = dashboard.build_model(self.tmp)
        self.assertTrue(model["run"]["active"])
        self.assertEqual(model["run"]["lock"]["phase"], "specify")
        page = self._html()
        self.assertIn('<meta http-equiv="refresh" content="5">', page)
        self.assertIn('class="spin"', page)
        self.assertIn('<meta http-equiv="refresh" content="12">', self._html(refresh=12))

    def test_refresh_zero_disables_meta_refresh(self):
        self._lock("plan")
        page = self._html(refresh=0)
        self.assertNotIn('http-equiv="refresh"', page)
        self.assertIn('class="spin"', page)  # still shown as running, just not auto-reloading

    def test_stale_lock_is_not_active(self):
        self._lock("implement", age_seconds=2 * dashboard.DEFAULT_PHASE_TIMEOUT)
        self._age()
        run = dashboard.build_model(self.tmp)["run"]
        self.assertFalse(run["active"])
        self.assertTrue(run["lock"]["stale"])
        self.assertNotIn('http-equiv="refresh"', self._html())

    def test_lock_staleness_follows_configured_phase_timeout(self):
        self._features(execution={"phase_timeout_seconds": 3600})
        self._lock("implement", age_seconds=1200)
        self.assertTrue(dashboard.build_model(self.tmp)["run"]["active"])

    def test_running_phase_is_active_without_lock(self):
        self._features({"id": "f1", "name": "F1", "phases": {"specify": "PASSED", "clarify": "RUNNING"}})
        self._age()
        run = dashboard.build_model(self.tmp)["run"]
        self.assertTrue(run["active"])
        self.assertEqual(run["running_phases"], ["f1:clarify"])
        self.assertIn('http-equiv="refresh"', self._html())

    def test_recent_change_between_phases_settles_without_meta_refresh(self):
        self._features({"id": "f1", "name": "F1", "phases": {"specify": "PASSED"}})
        run = dashboard.build_model(self.tmp)["run"]
        self.assertEqual((run["state"], run["active"]), ("settling", False))
        page = self._html()
        self.assertNotIn('http-equiv="refresh"', page)
        self.assertIn("location.reload()", page)
        self.assertNotIn("location.reload()", self._html(refresh=0))

    def test_terminal_status_is_idle_even_when_recent(self):
        self._features({"id": "f1", "name": "F1", "phases": ALL_PASSED}, status="COMPLETED")
        self.assertEqual(dashboard.build_model(self.tmp)["run"]["state"], "idle")
        self.assertNotIn("<script", self._html())

    def test_resumed_run_with_terminal_status_settles_after_phase_started(self):
        self._features({"id": "f1", "name": "F1"}, status="BLOCKED")
        hooks.emit(self.tmp, "phase.started", {"feature": "f1", "phase": "specify"})
        run = dashboard.build_model(self.tmp)["run"]
        self.assertEqual((run["state"], run["last_lifecycle_event"]), ("settling", "phase.started"))


class SafetyTests(DashboardTestBase):
    def test_missing_state_still_writes_a_page(self):
        empty = tempfile.mkdtemp()
        try:
            path = dashboard.write(empty)
            self.assertEqual(path, os.path.join(os.path.abspath(empty), ".spec-master", "reports", "dashboard.html"))
            with open(path, encoding="utf-8") as fh:
                page = fh.read()
            self.assertIn("Not initialized", page)
            self.assertEqual(_tree(empty), {".spec-master", os.path.join(".spec-master", "reports"),
                                            os.path.join(".spec-master", "reports", "dashboard.html")})
            model = dashboard.build_model(empty)
            self.assertFalse(model["initialized"])
            self.assertEqual(model["errors"], [])
        finally:
            shutil.rmtree(empty, ignore_errors=True)

    def test_corrupt_state_degrades_and_is_left_untouched(self):
        with open(self.state_path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        page = self._html()
        self.assertIn("could not be read", page)
        model = dashboard.build_model(self.tmp)
        self.assertFalse(model["initialized"])
        self.assertEqual([e["source"] for e in model["errors"]], ["state"])
        with open(self.state_path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "{not json")

    def test_write_creates_only_the_report_and_never_the_graph_dir(self):
        self._features({"id": "f1", "name": "F1"})
        with open(self.state_path, "rb") as fh:
            before_bytes = fh.read()
        before_mtime = os.path.getmtime(self.state_path)
        before_tree = _tree(self.tmp)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, dashboard.GRAPH_RELPATH)))

        dashboard.write(self.tmp)
        dashboard.build_model(self.tmp)

        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".spec-master", "knowledge")))
        self.assertEqual(_tree(self.tmp) - before_tree,
                         {os.path.join(".spec-master", "reports"),
                          os.path.join(".spec-master", "reports", "dashboard.html")})
        with open(self.state_path, "rb") as fh:
            self.assertEqual(fh.read(), before_bytes)
        self.assertEqual(os.path.getmtime(self.state_path), before_mtime)

    def test_default_output_is_written_atomically(self):
        expected = os.path.join(os.path.abspath(self.tmp), ".spec-master", "reports", "dashboard.html")
        with mock.patch("dashboard.os.replace", wraps=os.replace) as replace:
            path = dashboard.write(self.tmp)
        self.assertEqual(path, expected)
        replace.assert_called_once()
        src, dst = replace.call_args.args
        self.assertEqual(dst, expected)
        self.assertEqual(os.path.dirname(src), os.path.dirname(expected))
        self.assertTrue(os.path.basename(src).startswith(".dashboard."))
        self.assertEqual(os.listdir(os.path.dirname(expected)), ["dashboard.html"])

    def test_failed_write_leaves_no_temp_file(self):
        with mock.patch("dashboard.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                dashboard.write(self.tmp)
        self.assertEqual(os.listdir(os.path.join(self.tmp, ".spec-master", "reports")), [])

    def test_relative_and_absolute_output(self):
        rel = dashboard.write(self.tmp, output=os.path.join("out", "dash.html"))
        self.assertEqual(rel, os.path.join(os.path.abspath(self.tmp), "out", "dash.html"))
        self.assertTrue(os.path.isfile(rel))
        other = tempfile.mkdtemp()
        try:
            target = os.path.join(other, "d.html")
            self.assertEqual(dashboard.write(self.tmp, output=target), os.path.abspath(target))
            self.assertTrue(os.path.isfile(target))
        finally:
            shutil.rmtree(other, ignore_errors=True)

    def test_model_is_json_serializable(self):
        self._features({"id": "f1", "name": "F1", "risk": {"tier": "M"}})
        self._lock()
        json.dumps(dashboard.build_model(self.tmp))


class SourceTests(DashboardTestBase):
    def _write_json(self, rel, payload):
        path = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            if isinstance(payload, str):
                fh.write(payload)
            else:
                json.dump(payload, fh)

    def test_workstreams_grouped_by_status_and_owner(self):
        approved = {"status": "APPROVED"}
        self._write_json(dashboard.WORKSTREAMS_RELPATH, {
            "mode": "team", "technical_owner": "tech-lead",
            "packages": [
                {"id": "wp1", "feature_id": "f1", "title": "API", "owner_agent": "backend-dev",
                 "review_verdict": approved, "integration_verdict": approved},
                {"id": "wp2", "feature_id": "f1", "title": "DB", "owner_agent": "backend-dev", "depends_on": ["wp1"]},
                {"id": "wp3", "feature_id": "f1", "title": "UI", "owner_agent": "frontend-dev", "status": "done"},
                "not-a-package",
            ]})
        ws = dashboard.build_model(self.tmp)["workstreams"]
        self.assertEqual(ws["by_status"], {"integration_ready": 1, "review_pending": 1, "done": 1})
        self.assertEqual(ws["by_owner"]["backend-dev"]["by_status"], {"integration_ready": 1, "review_pending": 1})
        self.assertEqual(ws["by_owner"]["frontend-dev"]["packages"], ["wp3"])
        self.assertEqual(ws["technical_owner"], "tech-lead")
        self.assertIn("frontend-dev", self._html())

    def test_workstreams_tolerate_lists_unknown_shapes_and_corruption(self):
        self._write_json(dashboard.WORKSTREAMS_RELPATH, [{"id": "wp1", "owner": "qa", "status": "RUNNING"}])
        self.assertEqual(dashboard.build_model(self.tmp)["workstreams"]["by_owner"]["qa"]["total"], 1)
        self._write_json(dashboard.WORKSTREAMS_RELPATH, {"lanes": 3})
        ws = dashboard.build_model(self.tmp)["workstreams"]
        self.assertEqual((ws["present"], ws["packages"]), (True, []))
        self._write_json(dashboard.WORKSTREAMS_RELPATH, "[oops")
        model = dashboard.build_model(self.tmp)
        self.assertEqual([e["source"] for e in model["errors"]], ["workstreams"])
        self.assertIn("Some sources could not be read", dashboard.render_html(model))

    def test_traceability_counts_by_status_and_feature(self):
        self._features({"id": "f1", "name": "F1"}, traceability=[
            {"requirement": "R1", "feature": "f1", "status": "traced"},
            {"requirement": "R2", "feature": "f1", "status": "untraced"},
            {"requirement": "R3", "feature": "f2", "status": "traced"},
        ])
        tr = dashboard.build_model(self.tmp)["traceability"]
        self.assertEqual(tr["rows"], 3)
        self.assertEqual(tr["by_status"], {"traced": 2, "untraced": 1})
        self.assertEqual(tr["by_feature"]["f1"], {"total": 2, "by_status": {"traced": 1, "untraced": 1}})

    def test_latest_ten_decisions(self):
        FileGraphStore(self.tmp).save_node(GraphNode(id="feature.checkout", type="Feature", name="Checkout"))
        for i in range(12):
            decision_memory.record_decision(self.tmp, kind="architecture_inconsistency", raised_by="backend-dev",
                                            decision=f"Decision number {i}", feature="checkout")
        model = dashboard.build_model(self.tmp)
        self.assertEqual((len(model["decisions"]), model["decisions_total"]), (10, 12))
        self.assertTrue(all(d["decided_by"] for d in model["decisions"]))
        self.assertIn("latest 10 of 12", dashboard.render_html(model))

    def test_hook_firings_newest_first(self):
        hooks.emit(self.tmp, "phase.started", {"feature": "f1", "phase": "specify"})
        hooks.emit(self.tmp, "phase.transition", {"feature": "f1", "phase": "specify", "status": "PASSED"})
        firings = dashboard.build_model(self.tmp)["hooks"]
        self.assertEqual([f["type"] for f in firings], ["phase.transition", "phase.started"])
        self.assertEqual(firings[0]["details"]["status"], "PASSED")
        self.assertIn("dashboard-refresh", [x["hook"] for x in firings[0]["fired"]])

    def test_metrics_summary_and_corrupt_rounds(self):
        self._write_json(dashboard.ROUNDS_RELPATH, [{"duration_seconds": 3600, "total_tokens": 1000,
                                                    "work_packages_completed": 4, "features_completed": 1}])
        metrics = dashboard.build_model(self.tmp)["metrics"]
        self.assertEqual((metrics["rounds"], metrics["packages_per_hour"]), (1, 4.0))
        self._write_json(dashboard.ROUNDS_RELPATH, "{broken")
        model = dashboard.build_model(self.tmp)
        self.assertIsNone(model["metrics"])
        self.assertEqual([e["source"] for e in model["errors"]], ["metrics"])

    def test_graph_map_is_escaped_inside_details(self):
        FileGraphStore(self.tmp).save_node(GraphNode(id="feature.checkout", type="Feature", name="Checkout <v2>"))
        model = dashboard.build_model(self.tmp)
        self.assertEqual(model["graph"]["nodes"], 1)
        page = dashboard.render_html(model)
        section = page[page.index('id="graph"'):]
        self.assertIn("<details>", section)
        self.assertIn("<pre>", section)
        self.assertIn("Checkout &lt;v2&gt;", section)
        self.assertNotIn("Checkout <v2>", page)


class HookIntegrationTests(DashboardTestBase):
    def test_phase_transition_event_renders_the_dashboard(self):
        self._features({"id": "f1", "name": "F1", "phases": {"specify": "PASSED"}})
        result = hooks.emit(self.tmp, "phase.transition", {"feature": "f1", "phase": "specify", "status": "PASSED"})
        path = os.path.join(self.tmp, ".spec-master", "reports", "dashboard.html")
        self.assertTrue(os.path.isfile(path))
        fired = {entry["hook"]: entry for entry in result["fired"]}
        self.assertEqual(fired["dashboard-refresh"]["result"], {"executed": True, "output": os.path.abspath(path)})
        with open(path, encoding="utf-8") as fh:
            self.assertRegex(fh.read(), re.escape("1/7 phases"))


if __name__ == "__main__":
    unittest.main()
