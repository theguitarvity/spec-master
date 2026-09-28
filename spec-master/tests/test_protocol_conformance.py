"""Every CLI invocation the agent-facing docs tell an agent to run must exist.

The protocol drifted from the parser before (`knowledge get --id`,
`knowledge for-context`), which costs a failed turn every time an agent
follows the instructions literally. The extractor lives in kernel/doctor.py,
so `doctor run` (CI) and this test apply the same rule.
"""
import re
import unittest
from pathlib import Path

import _pathfix  # noqa: F401
import cli
from kernel import doctor

REPO = Path(__file__).resolve().parents[2]


class ProtocolConformanceTests(unittest.TestCase):
    def test_documented_invocations_exist_in_the_parser(self):
        checked, problems = doctor.conformance(REPO, cli.build_parser())
        self.assertGreater(checked, 50, "the extractor found suspiciously few invocations")
        self.assertEqual(problems, [], "\n" + "\n".join(problems))

    def test_extractor_reports_unknown_groups_actions_and_flags(self):
        catalog = {"state": {"show": {"--path", "--summary"}}}
        found = list(doctor.invocations("python3 spec-master/lib/cli.py state show --path . --nope", catalog))
        self.assertEqual(found, [("state", "show", ["--path", "--nope"])])
        found = list(doctor.invocations("python3 spec-master/lib/cli.py telemetry ingest --latest", catalog))
        self.assertEqual(found, [("telemetry", None, [])])
        self.assertEqual(list(doctor.invocations("├── cli.py todos os grupos", catalog)), [])
        self.assertEqual(list(doctor.code_fragments("run `state show\n  --summary` now")), ["state show --summary"])

    def test_protocol_does_not_cite_an_unversioned_claude_md(self):
        text = (REPO / "spec-master" / "PROTOCOL.md").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"CLAUDE\.md\s*§|§\d+ of CLAUDE\.md", text))


if __name__ == "__main__":
    unittest.main()
