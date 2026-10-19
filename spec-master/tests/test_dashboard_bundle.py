"""The committed React bundle: integrity, relative assets, and isolation from the Python core.

Offline and Node-free: only hashes and reads files.
"""
import json
import os
import re
import tempfile
import shutil
import unittest
from pathlib import Path

import _pathfix  # noqa: F401
import dashboard_server
import packaging

ROOT = Path(dashboard_server.DEFAULT_DIST).resolve().parents[2]
WEB = ROOT / "dashboard" / "web"
DIST = WEB / "dist"


class BundleIntegrityTests(unittest.TestCase):
    def test_default_dist_is_the_committed_bundle(self):
        self.assertEqual(Path(dashboard_server.DEFAULT_DIST).resolve(), DIST.resolve())
        self.assertTrue((DIST / "index.html").is_file())

    def test_manifest_matches_every_file(self):
        self.assertEqual(dashboard_server.verify_manifest(str(DIST)), [])

    def test_manifest_lists_the_entry_and_assets(self):
        files = json.loads((DIST / "MANIFEST.json").read_text(encoding="utf-8"))["files"]
        self.assertIn("index.html", files)
        self.assertTrue(any(name.endswith(".js") for name in files))

    def test_a_tampered_asset_is_detected(self):
        copy = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, copy, True)
        target = os.path.join(copy, "dist")
        shutil.copytree(DIST, target)
        js = next(p for p in Path(target, "assets").iterdir() if p.suffix == ".js")
        js.write_text(js.read_text(encoding="utf-8") + "\n//x", encoding="utf-8")
        self.assertTrue(dashboard_server.verify_manifest(target))

    def test_index_references_only_relative_assets(self):
        html = (DIST / "index.html").read_text(encoding="utf-8")
        refs = re.findall(r'(?:src|href)="([^"]+)"', html)
        self.assertTrue(refs)
        for ref in refs:
            self.assertTrue(ref.startswith("./"), f"asset must be relative: {ref}")
            self.assertTrue((DIST / ref[2:]).is_file(), f"missing asset: {ref}")
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)

    def test_no_sourcemaps_or_node_modules_are_committed(self):
        self.assertEqual(list(DIST.rglob("*.map")), [])
        tracked = [p for p in DIST.rglob("*") if "node_modules" in p.parts]
        self.assertEqual(tracked, [])


class CoreIsolationTests(unittest.TestCase):
    def test_python_core_never_imports_node_tooling(self):
        for name in ("dashboard_server.py", "dashboard.py"):
            text = (Path(dashboard_server.__file__).parent / name).read_text(encoding="utf-8")
            self.assertNotRegex(text, r"subprocess[^\n]*\b(npm|node|npx)\b")

    @unittest.skipUnless((ROOT / ".git").exists(), "not inside the Spec Master repository")
    def test_packaging_has_no_drift(self):
        self.assertEqual(packaging.check(ROOT), [])

    def test_generated_plugin_files_do_not_reference_the_web_source(self):
        for rel, content in packaging.render().items():
            text = content if isinstance(content, str) else json.dumps(content)
            self.assertNotIn("dashboard/web", text, rel)


if __name__ == "__main__":
    unittest.main()
