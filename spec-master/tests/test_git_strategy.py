import unittest

import _pathfix  # noqa: F401
import git_strategy


class GitStrategyTests(unittest.TestCase):
    def test_trunk_never_creates_branch(self):
        result = git_strategy.plan("trunk", feature_name="Session renewal bypass")
        self.assertFalse(result["create_branch"])
        self.assertIsNone(result["branch"])
        self.assertFalse(result["install_git_extension"])

    def test_git_flow_slugifies_feature_name(self):
        result = git_strategy.plan("git-flow", feature_name="Session Renewal Bypass")
        self.assertEqual(result["branch"], "feature/session-renewal-bypass")

    def test_git_flow_preserves_explicit_identifier_in_name(self):
        result = git_strategy.plan("git-flow", feature_name="APP-1234 Session renewal")
        self.assertEqual(result["branch"], "APP-1234")

    def test_git_flow_preserves_explicit_issue_id_argument(self):
        result = git_strategy.plan(
            "git-flow", feature_name="Session renewal", issue_id="PROJ-847"
        )
        self.assertEqual(result["branch"], "PROJ-847")

    def test_extension_not_reinstalled_when_already_present(self):
        result = git_strategy.plan(
            "git-flow",
            feature_name="Session renewal",
            git_extension_installed=True,
            spec_kit_present=True,
        )
        self.assertFalse(result["install_git_extension"])

    def test_extension_install_suggested_only_when_spec_kit_present(self):
        result = git_strategy.plan(
            "git-flow",
            feature_name="Session renewal",
            git_extension_installed=False,
            spec_kit_present=True,
        )
        self.assertTrue(result["install_git_extension"])

        result_no_speckit = git_strategy.plan(
            "git-flow",
            feature_name="Session renewal",
            git_extension_installed=False,
            spec_kit_present=False,
        )
        self.assertFalse(result_no_speckit["install_git_extension"])


if __name__ == "__main__":
    unittest.main()
