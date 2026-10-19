import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import _pathfix  # noqa: F401
import cli
from kernel import doctor


class DoctorTests(unittest.TestCase):
    def test_this_repository_passes_its_own_doctor(self):
        report = doctor.run(str(doctor.ENGINE.parent), cli.build_parser())
        by_name = {c["name"]: c for c in report["checks"]}
        self.assertEqual(report["errors"], [], json.dumps([c for c in report["checks"] if not c["ok"]], indent=1))
        for name in ("protocol_conformance", "kernel_budget", "hook_path_budget", "step_path_budget", "cards",
                     "speckit_version", "evidence", "metrics", "policy", "gates", "hooks"):
            self.assertIn(name, by_name)
        self.assertIn("kernel/hookd.py", by_name["hook_path_budget"]["modules"])
        self.assertNotIn("risk_profile.py", by_name["hook_path_budget"]["modules"])  # hooks stay import-light

    def test_loc_ignores_docstrings_comments_and_blank_lines(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            source = tmp / "m.py"
            source.write_text('"""Doc\n\nmore doc\n"""\n# comment\n\nx = 1\n\ndef f():\n    """One line."""\n    return x\n')
            self.assertEqual(doctor.loc(source), 3)
        finally:
            shutil.rmtree(tmp)

    def test_speckit_version_range(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / ".specify").mkdir()
            for version, ok in (("0.16.4", True), ("1.0.12", True), ("1.1.0", False), ("0.15.9", False)):
                (tmp / ".specify" / "integration.json").write_text(json.dumps({"version": version}))
                with self.subTest(version=version):
                    self.assertEqual(doctor.speckit_version(tmp)["ok"], ok)
        finally:
            shutil.rmtree(tmp)

    def test_conformance_catches_a_drifted_doc(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "spec-master").mkdir()
            (tmp / "spec-master" / "PROTOCOL.md").write_text(
                "Run `python3 spec-master/lib/cli.py state show --summary` and "
                "`python3 spec-master/lib/cli.py knowledge for-context --role x`.\n")
            checked, problems = doctor.conformance(tmp, cli.build_parser())
            self.assertEqual(checked, 2)
            self.assertEqual(len(problems), 1)
            self.assertIn("knowledge for-context", problems[0])
        finally:
            shutil.rmtree(tmp)

    def test_cli_exit_code_follows_errors(self):
        code, out = _run("doctor", "run", "--path", str(doctor.ENGINE.parent), "--errors-only")
        self.assertEqual(code, 0, out)
        self.assertTrue(json.loads(out)["ok"])


def _run(*argv):
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(list(argv))
    return code, buf.getvalue()


if __name__ == "__main__":
    unittest.main()
