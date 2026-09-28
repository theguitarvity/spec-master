import unittest

import _pathfix  # noqa: F401
from knowledge import profiles


class KnowledgeProfilesTests(unittest.TestCase):
    def test_resolve_knowledge_role_aliases(self):
        self.assertEqual(profiles.resolve_knowledge_role("po"), "product-owner")
        self.assertEqual(profiles.resolve_knowledge_role("infra"), "infrastructure")
        self.assertEqual(profiles.resolve_knowledge_role("ui-ux-brand"), "ux")

    def test_resolve_knowledge_role_passthrough_for_matching_ids(self):
        for role in ("architect", "tech-lead", "backend-dev", "frontend-dev",
                     "fullstack-dev", "qa", "devops", "security", "scrum-master"):
            self.assertEqual(profiles.resolve_knowledge_role(role), role)

    def test_resolve_knowledge_role_unknown_passthrough(self):
        self.assertEqual(profiles.resolve_knowledge_role("totally-unknown"), "totally-unknown")

    def test_is_known_knowledge_role(self):
        self.assertTrue(profiles.is_known_knowledge_role("architect"))
        self.assertTrue(profiles.is_known_knowledge_role("product-owner"))
        self.assertFalse(profiles.is_known_knowledge_role("po"))  # team_model id, not knowledge id

    def test_team_model_roles_all_resolve_to_known_knowledge_roles(self):
        from team_model import AGENT_ROLES

        for role in AGENT_ROLES:
            resolved = profiles.resolve_knowledge_role(role["id"])
            self.assertTrue(profiles.is_known_knowledge_role(resolved), (
                f"team_model role {role['id']!r} resolves to {resolved!r}, "
                f"which is not a known knowledge-base role"
            ))

    def test_category_weight_orders_preferred_categories_first(self):
        w_arch = profiles.category_weight("architect", "architecture")
        w_agile = profiles.category_weight("architect", "agile")
        self.assertLess(w_arch, w_agile)

    def test_category_weight_unknown_role_defaults_to_zero(self):
        self.assertEqual(profiles.category_weight("nonexistent-role", "architecture"), 0)

    def test_stack_languages_to_categories(self):
        result = profiles.stack_languages_to_categories(["node", "python", "ruby"])
        self.assertEqual(result, ["node", "python"])

    def test_stack_languages_to_categories_dedupes_and_preserves_order(self):
        result = profiles.stack_languages_to_categories(["python", "node", "python"])
        self.assertEqual(result, ["python", "node"])


if __name__ == "__main__":
    unittest.main()
