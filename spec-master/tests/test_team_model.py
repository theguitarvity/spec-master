from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import _pathfix  # noqa: F401
import team_model  # noqa: E402


ENGINE_ROOT = Path(__file__).resolve().parent.parent
CLI = ENGINE_ROOT / "lib" / "cli.py"


class TeamModelTests(unittest.TestCase):
    def test_roles_include_tech_lead_ui_ux_and_specialized_devs(self):
        role_ids = {role["id"] for role in team_model.roles()}

        self.assertIn("tech-lead", role_ids)
        self.assertIn("ui-ux-brand", role_ids)
        self.assertIn("backend-dev", role_ids)
        self.assertIn("frontend-dev", role_ids)
        self.assertIn("fullstack-dev", role_ids)

    def test_guided_intake_supports_new_project_without_context_file(self):
        intake = team_model.guided_intake()

        self.assertEqual(intake["mode"], "guided-intake")
        self.assertEqual(intake["output_context"], ".spec-master/context.generated.md")
        self.assertGreaterEqual(len(intake["questions"]), 5)
        self.assertEqual(intake["questions"][0]["id"], "project_type")
        self.assertTrue(intake["questions"][0]["required"])

    def test_adoption_plan_is_additive_and_state_preserving(self):
        plan = team_model.adoption_plan()

        self.assertEqual(plan["mode"], "team-adoption")
        self.assertIn(".spec-master/state.json", plan["inputs"])
        self.assertIn(".spec-master/workstreams.json", plan["outputs"])
        self.assertIn("adoption is additive and state-preserving by default", plan["rules"])

    def test_workstreams_assign_specialized_dev_owners_and_peer_reviewers(self):
        plan = team_model.build_workstreams(
            [
                {
                    "id": "checkout",
                    "tasks": [
                        "Create API endpoint for checkout",
                        "Build frontend form for payment",
                        "Connect UI screen to backend API",
                    ],
                }
            ]
        )

        packages = plan["packages"]
        self.assertEqual(packages[0]["owner_agent"], "backend-dev")
        self.assertEqual(packages[1]["owner_agent"], "frontend-dev")
        self.assertEqual(packages[2]["owner_agent"], "fullstack-dev")
        for package in packages:
            self.assertNotEqual(package["owner_agent"], package["reviewer_agent"])

    def test_workstreams_keep_tech_lead_as_conflict_owner(self):
        plan = team_model.build_workstreams([{"id": "settings", "tasks": ["Build settings page"]}])

        self.assertEqual(plan["technical_owner"], "tech-lead")
        self.assertEqual(plan["conflict_policy"]["owner"], "tech-lead")
        self.assertIn("frontend-dev", plan["lanes"])

    def test_cli_exposes_team_intake_and_workstreams(self):
        intake = subprocess.check_output(
            [sys.executable, str(CLI), "team", "intake"],
            text=True,
        )
        self.assertEqual(json.loads(intake)["mode"], "guided-intake")

        adoption = subprocess.check_output(
            [sys.executable, str(CLI), "team", "adopt"],
            text=True,
        )
        self.assertEqual(json.loads(adoption)["mode"], "team-adoption")

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json") as fh:
            json.dump([{"id": "auth", "tasks": ["Add auth API", "Create login screen"]}], fh)
            fh.flush()
            output = subprocess.check_output(
                [sys.executable, str(CLI), "team", "workstreams", "--file", fh.name],
                text=True,
            )

        packages = json.loads(output)["packages"]
        self.assertEqual(packages[0]["reviewer_agent"], "fullstack-dev")
        self.assertEqual(packages[1]["owner_agent"], "frontend-dev")


if __name__ == "__main__":
    unittest.main()
