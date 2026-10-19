import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import _pathfix  # noqa: F401
import cli
import decision_memory
from graph.enrichment import enrich_from_discovery
from graph.events import read_events
from graph.model import GraphNode
from graph.store import FileGraphStore


def _run_cli(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(list(argv))
    return code, buf.getvalue()


class EnrichFromDiscoveryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp_path = Path(tmp.name)

    def test_enrich_from_discovery_empty(self):
        nodes, edges = enrich_from_discovery({}, project_root=str(self.tmp_path))
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].type, "Project")
        self.assertEqual(len(edges), 0)

    def test_enrich_from_discovery_full(self):
        discovery_res = {
            "ci_present": True,
            "readme_present": True,
            "docs_present": True,
            "stacks": [
                {"language": "Python", "manifest": "requirements.txt", "commands": {"test": "pytest"}}
            ]
        }

        (self.tmp_path / "adr").mkdir()
        (self.tmp_path / "spec-master").mkdir()
        (self.tmp_path / "openapi.yaml").write_text("")

        nodes, edges = enrich_from_discovery(discovery_res, project_root=str(self.tmp_path))

        types = {n.type for n in nodes}
        self.assertIn("Project", types)
        self.assertIn("Technology", types)
        self.assertIn("Deployment", types)
        self.assertIn("Test", types)
        self.assertIn("ADR", types)
        self.assertIn("API", types)
        self.assertIn("Artifact", types)
        self.assertIn("Package", types)

        self.assertEqual(len(edges), 8)
        relations = {e.relation for e in edges}
        self.assertIn("USES", relations)
        self.assertIn("TESTED_BY", relations)
        self.assertIn("CONTAINS", relations)
        self.assertIn("EXPOSES", relations)


class EnrichDiscoveryIntoExistingGraphTests(unittest.TestCase):
    """`graph enrich-discovery` run against a project whose graph already has content."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp_path = Path(tmp.name)

    def _project(self, name):
        root = self.tmp_path / name
        root.mkdir()
        (root / "README.md").write_text("# Demo\n", encoding="utf-8")
        return root

    def _graph_cli(self, action, root):
        code, out = _run_cli("graph", action, "--path", str(root))
        self.assertEqual(code, 0, out)
        return json.loads(out)

    def test_enrichment_keeps_decision_edges_and_the_graph_stays_valid(self):
        root = self._project("demo")
        # What `team resolve` leaves in the graph: a Decision linked to the
        # deciding agent (DECIDED_BY) and to the feature it influences (INFLUENCES).
        FileGraphStore(str(root)).save_node(GraphNode(id="feature.billing", type="Feature", name="Billing"))
        decision = decision_memory.record_decision(
            str(root), kind="architecture_inconsistency", raised_by="backend-dev",
            decision="Keep repositories behind the domain port", feature="billing")["node"]
        report = self._graph_cli("validate", root)
        self.assertIs(report["valid"], True, report)

        self._graph_cli("enrich-discovery", root)

        report = self._graph_cli("validate", root)
        self.assertIs(report["valid"], True, report)
        edges = {(e.source, e.relation, e.target) for e in FileGraphStore(str(root)).load().edges}
        self.assertIn((decision, "DECIDED_BY", "agent.architect"), edges)
        self.assertIn((decision, "INFLUENCES", "feature.billing"), edges)
        self.assertIn(("project.demo", "CONTAINS", "artifact.readme"), edges)

    def test_enriching_a_clone_reuses_the_existing_project_node(self):
        original = self._project("original-checkout")
        self._graph_cli("enrich-discovery", original)
        clone = self.tmp_path / "clone-elsewhere"
        shutil.copytree(original, clone)

        nodes, edges = enrich_from_discovery({"readme_present": True}, project_root=str(clone))
        self.assertEqual((nodes[0].id, nodes[0].name), ("project.original-checkout", "original-checkout"))
        self.assertEqual({e.source for e in edges}, {"project.original-checkout"})

        self._graph_cli("enrich-discovery", clone)
        graph = FileGraphStore(str(clone)).load()
        self.assertEqual([nid for nid in graph.nodes if nid.startswith("project.")],
                         ["project.original-checkout"])
        report = self._graph_cli("validate", clone)
        self.assertIs(report["valid"], True, report)

    def test_project_id_comes_from_the_directory_without_a_single_project_node(self):
        fresh = self._project("fresh-project")
        nodes, _ = enrich_from_discovery({}, project_root=str(fresh))
        self.assertEqual(nodes[0].id, "project.fresh-project")
        self.assertFalse((fresh / ".spec-master").exists())  # looking for one wrote nothing

        ambiguous = self._project("third-name")
        store = FileGraphStore(str(ambiguous))
        store.save_node(GraphNode(id="project.first", type="Project", name="first"))
        store.save_node(GraphNode(id="project.second", type="Project", name="second"))
        nodes, _ = enrich_from_discovery({}, project_root=str(ambiguous))
        self.assertEqual(nodes[0].id, "project.third-name")

    def test_enrichment_logs_events_only_for_what_changed(self):
        root = self._project("demo")
        events_path = root / ".spec-master" / "knowledge" / "graph-events.jsonl"
        manifest_path = root / ".spec-master" / "knowledge" / "graph-manifest.json"
        self._graph_cli("enrich-discovery", root)
        events = read_events(events_path)
        manifest = manifest_path.read_text(encoding="utf-8")
        self.assertNotEqual(events, [])

        self._graph_cli("enrich-discovery", root)  # nothing changed
        self.assertEqual(read_events(events_path), events)
        self.assertEqual(manifest_path.read_text(encoding="utf-8"), manifest)

        (root / "docs").mkdir()
        self._graph_cli("enrich-discovery", root)  # one new artifact and its edge
        new = [(e["event"], e.get("node_id") or e["target"]) for e in read_events(events_path)[len(events):]]
        self.assertEqual(new, [("NODE_CREATED", "artifact.docs"), ("EDGE_CREATED", "artifact.docs")])


if __name__ == "__main__":
    unittest.main()
