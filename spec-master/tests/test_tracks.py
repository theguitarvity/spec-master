import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

import _pathfix  # noqa: F401
import cli
import tracks


def _write(root, rel, text=""):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _evidence_paths(items):
    return [e.split(":")[0] for item in items for e in item["evidence"]]


class _TmpCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _legacy(self):
        _write(self.tmp, "package.json", json.dumps({"scripts": {"test": "jest", "lint": "eslint ."}}))
        _write(self.tmp, "package-lock.json", "{}")
        _write(self.tmp, ".github/workflows/ci.yml", "name: ci\n")
        _write(self.tmp, ".editorconfig", "root = true\n")
        _write(self.tmp, "src/app.js", "// TODO fix\nmodule.exports = 1;\n")
        _write(self.tmp, "src/util.js", "x\ny\nz\n")
        _write(self.tmp, "src/util.test.js", "test\n")
        _write(self.tmp, "node_modules/dep/index.js", "// TODO ignored\n")


class MapCodebaseTests(_TmpCase):
    def test_map_has_all_sections_and_evidence_on_every_finding(self):
        self._legacy()
        result = tracks.map_codebase(self.tmp)
        for key in ("stack", "packages", "architecture", "conventions", "risks"):
            self.assertIn(key, result)
        self.assertEqual(result["stack"][0]["language"], "node")
        for section in ("architecture", "conventions", "risks"):
            for item in result[section]:
                self.assertTrue(item["evidence"], (section, item))

    def test_pruned_directories_do_not_leak_into_findings(self):
        self._legacy()
        result = tracks.map_codebase(self.tmp)
        self.assertFalse([p for p in _evidence_paths(result["risks"]) if "node_modules" in p])
        todo = [r for r in result["risks"] if r["kind"] == "todo-markers"][0]
        self.assertEqual(todo["evidence"][0], "src/app.js:1")

    def test_conventions_are_detected_from_files_present(self):
        self._legacy()
        kinds = {c["kind"] for c in tracks.map_codebase(self.tmp)["conventions"]}
        self.assertIn("editorconfig", kinds)
        self.assertIn("ci", kinds)

    def test_missing_ci_and_lockfile_are_risks_with_checked_path_as_evidence(self):
        _write(self.tmp, "package.json", "{}")
        _write(self.tmp, "src/a.js", "x\n")
        kinds = {r["kind"]: r for r in tracks.map_codebase(self.tmp)["risks"]}
        self.assertIn("no-ci", kinds)
        self.assertIn("no-lockfile", kinds)
        self.assertIn("no-tests", kinds)

    def test_empty_repo_invents_nothing(self):
        result = tracks.map_codebase(self.tmp)
        self.assertEqual(result["stack"], [])
        self.assertEqual(result["architecture"], [])
        self.assertEqual(result["conventions"], [])

    def test_scope_limits_the_map(self):
        _write(self.tmp, "services/b/go.mod", "module b\n")
        _write(self.tmp, "services/b/main.go", "package main\n")
        _write(self.tmp, "other/package.json", "{}")
        _write(self.tmp, "other/x.js", "// FIXME\n")
        result = tracks.map_codebase(self.tmp, scope="services/b")
        self.assertEqual(result["scope"], "services/b")
        self.assertEqual([s["language"] for s in result["stack"]], ["go"])
        self.assertFalse([p for p in _evidence_paths(result["risks"]) if p.startswith("other")])
        with self.assertRaises(ValueError):
            tracks.map_codebase(self.tmp, scope="../x")

    def test_monorepo_packages_are_reported(self):
        _write(self.tmp, "packages/a/package.json", "{}")
        _write(self.tmp, "services/b/go.mod", "module b\n")
        paths = [p["path"] for p in tracks.map_codebase(self.tmp)["packages"]]
        self.assertEqual(paths, ["packages/a", "services/b"])


class ConstitutionProposalTests(_TmpCase):
    def test_every_principle_cites_evidence_that_exists(self):
        _write(self.tmp, "package.json", json.dumps({"scripts": {"test": "jest"}}))
        _write(self.tmp, ".github/workflows/ci.yml", "name: ci\n")
        _write(self.tmp, "src/a.test.js", "t\n")
        proposal = tracks.propose_constitution(tracks.map_codebase(self.tmp))
        self.assertFalse(proposal["applied"])
        self.assertTrue(proposal["principles"])
        for principle in proposal["principles"]:
            self.assertTrue(principle["evidence"])
            for ref in principle["evidence"]:
                self.assertTrue(os.path.exists(os.path.join(self.tmp, ref.split(":")[0])), ref)
        self.assertIn("PROPOSAL", proposal["markdown"])

    def test_empty_repo_yields_no_principles_and_unresolved_note(self):
        proposal = tracks.propose_constitution(tracks.map_codebase(self.tmp))
        self.assertEqual(proposal["principles"], [])
        self.assertIn("[UNRESOLVED]", proposal["markdown"])

    def test_proposal_never_writes_the_real_constitution(self):
        _write(self.tmp, "package.json", "{}")
        tracks.propose_constitution(tracks.map_codebase(self.tmp))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".specify", "memory", "constitution.md")))


class CharacterizationTests(_TmpCase):
    def test_untested_sources_are_ranked_by_size(self):
        _write(self.tmp, "src/big.py", "x = 1\n" * 50)
        _write(self.tmp, "src/small.py", "x = 1\n" * 5)
        _write(self.tmp, "src/covered.py", "x = 1\n" * 99)
        _write(self.tmp, "tests/test_covered.py", "pass\n")
        _write(self.tmp, "src/__init__.py", "")
        targets = tracks.characterization_targets(self.tmp)
        self.assertEqual([t["path"] for t in targets], ["src/big.py", "src/small.py"])
        self.assertEqual(targets[0]["lines"], 50)

    def test_tests_outside_the_scope_still_count_as_coverage(self):
        _write(self.tmp, "src/core.py", "x\n")
        _write(self.tmp, "tests/test_core.py", "pass\n")
        self.assertEqual(tracks.characterization_targets(self.tmp, scope="src"), [])

    def test_scope_and_limit(self):
        _write(self.tmp, "a/one.py", "x\n")
        _write(self.tmp, "b/two.py", "x\n")
        self.assertEqual([t["path"] for t in tracks.characterization_targets(self.tmp, scope="a")], ["a/one.py"])
        _write(self.tmp, "a/three.py", "x\n")
        self.assertEqual(len(tracks.characterization_targets(self.tmp, limit=1)), 1)


class GreenfieldTests(_TmpCase):
    def test_intake_asks_for_the_stack(self):
        intake = tracks.greenfield_intake()
        stack = [q for q in intake["questions"] if q["id"] == "stack"][0]
        self.assertEqual(set(stack["options"]), {"python", "node", "go", "rust"})
        self.assertTrue(intake["proposes_only"])

    def test_propose_writes_nothing(self):
        for stack in ("python", "node", "go", "rust"):
            proposal = tracks.greenfield_propose(self.tmp, stack, "demo-app")
            self.assertFalse(proposal["applied"])
            self.assertTrue(proposal["requires_confirmation"])
            paths = [f["path"] for f in proposal["files"]]
            self.assertTrue(any(p.startswith(".github/workflows/") for p in paths), stack)
            self.assertTrue(proposal["gates"]["test"], stack)
        self.assertEqual(os.listdir(self.tmp), [])

    def test_unknown_stack_and_bad_name_are_rejected(self):
        with self.assertRaises(ValueError):
            tracks.greenfield_propose(self.tmp, "cobol", "x")
        with self.assertRaises(ValueError):
            tracks.greenfield_propose(self.tmp, "python", "../evil")

    def test_apply_requires_confirmation(self):
        with self.assertRaises(tracks.ConfirmationRequired):
            tracks.greenfield_apply(self.tmp, "python", "demo", confirmed=False)
        self.assertEqual(os.listdir(self.tmp), [])

    def test_apply_writes_new_files_and_never_overwrites(self):
        _write(self.tmp, "README.md", "mine\n")
        result = tracks.greenfield_apply(self.tmp, "python", "demo", confirmed=True)
        self.assertTrue(result["applied"])
        self.assertIn("README.md", result["skipped"])
        with open(os.path.join(self.tmp, "README.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "mine\n")
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, ".github", "workflows", "ci.yml")))
        self.assertFalse([n for _, _, fs in os.walk(self.tmp) for n in fs if n.endswith(".tmp")])

    def test_generated_python_skeleton_passes_its_own_gate(self):
        import subprocess
        import sys
        tracks.greenfield_apply(self.tmp, "python", "demo", confirmed=True)
        done = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                              cwd=self.tmp, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)


class WriteDocsTests(_TmpCase):
    def test_write_new_file_never_overwrites(self):
        self.assertTrue(tracks.write_new_file(self.tmp, ".spec-master/context/x.md", "a"))
        self.assertFalse(tracks.write_new_file(self.tmp, ".spec-master/context/x.md", "b"))
        with open(os.path.join(self.tmp, ".spec-master", "context", "x.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "a")


class TracksCliTests(_TmpCase):
    def _run(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(list(argv))
        return code, buf.getvalue()

    def test_brownfield_map_and_write(self):
        _write(self.tmp, "package.json", "{}")
        code, out = self._run("tracks", "brownfield-map", "--path", self.tmp, "--write")
        self.assertEqual(code, 0)
        self.assertIn("stack", json.loads(out))
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, ".spec-master", "context", "codebase-map.md")))

    def test_brownfield_constitution_writes_only_a_proposal(self):
        _write(self.tmp, "package.json", "{}")
        _write(self.tmp, ".github/workflows/ci.yml", "x\n")
        code, _ = self._run("tracks", "brownfield-constitution", "--path", self.tmp, "--write")
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, ".spec-master", "context", "constitution-proposal.md")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".specify")))

    def test_bad_scope_exits_nonzero(self):
        code, out = self._run("tracks", "brownfield-map", "--path", self.tmp, "--scope", "../x")
        self.assertEqual(code, 1)
        self.assertIn("error", json.loads(out))

    def test_greenfield_apply_without_confirm_exits_nonzero_and_writes_nothing(self):
        code, out = self._run("tracks", "greenfield-apply", "--path", self.tmp, "--stack", "python", "--name", "d")
        self.assertEqual(code, 2)
        self.assertIn("confirm", json.loads(out)["error"])
        self.assertEqual(os.listdir(self.tmp), [])

    def test_greenfield_propose_then_apply_with_confirm(self):
        code, out = self._run("tracks", "greenfield-propose", "--path", self.tmp, "--stack", "go", "--name", "d")
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(out)["applied"])
        self.assertEqual(os.listdir(self.tmp), [])
        code, out = self._run("tracks", "greenfield-apply", "--path", self.tmp, "--stack", "go",
                              "--name", "d", "--confirm")
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "go.mod")))

    def test_discovery_scan_accepts_scope(self):
        _write(self.tmp, "svc/go.mod", "module a\n")
        code, out = self._run("discovery", "scan", "--path", self.tmp, "--scope", "svc")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["scope"], "svc")


if __name__ == "__main__":
    unittest.main()
