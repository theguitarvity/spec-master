import unittest

import _pathfix  # noqa: F401
import constitution_diff


class ConstitutionDiffTests(unittest.TestCase):
    def test_new_heading_is_addition(self):
        existing = "# Constitution\n\n## Principle A\nDo X.\n"
        proposed = "# Constitution\n\n## Principle A\nDo X.\n\n## Principle B\nDo Y.\n"
        results = {r["heading"]: r["classification"] for r in constitution_diff.diff(existing, proposed)}
        self.assertEqual(results["Principle B"], "ADDITION")
        self.assertEqual(results["Principle A"], "UNCHANGED")

    def test_removed_heading_is_removal_candidate(self):
        existing = "# Constitution\n\n## Principle A\nDo X.\n\n## Principle B\nDo Y.\n"
        proposed = "# Constitution\n\n## Principle A\nDo X.\n"
        results = {r["heading"]: r["classification"] for r in constitution_diff.diff(existing, proposed)}
        self.assertEqual(results["Principle B"], "REMOVAL_CANDIDATE")

    def test_non_normative_change_is_modification(self):
        existing = "## Style\nPrefer tabs.\n"
        proposed = "## Style\nPrefer spaces.\n"
        results = {r["heading"]: r["classification"] for r in constitution_diff.diff(existing, proposed)}
        self.assertEqual(results["Style"], "MODIFICATION")

    def test_normative_change_is_conflict(self):
        existing = "## Security\nThe system MUST encrypt data at rest.\n"
        proposed = "## Security\nThe system SHOULD encrypt data at rest.\n"
        results = {r["heading"]: r["classification"] for r in constitution_diff.diff(existing, proposed)}
        self.assertEqual(results["Security"], "CONFLICT")

    def test_missing_existing_file_treats_all_as_additions(self):
        results = constitution_diff.diff("", "## New\nSomething.\n")
        self.assertEqual(results[0]["classification"], "ADDITION")


if __name__ == "__main__":
    unittest.main()
