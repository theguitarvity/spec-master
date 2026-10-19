import unittest

import _pathfix  # noqa: F401
from graph import ontology


class OntologyTests(unittest.TestCase):
    def test_entity_types(self):
        types = ontology.entity_types()
        self.assertIn("Project", types)
        self.assertIn("Component", types)

    def test_relation_types(self):
        types = ontology.relation_types()
        self.assertIn("UNRESOLVED_RELATION", types)
        self.assertIn("DEPENDS_ON", types)

    def test_validate_entity_type(self):
        self.assertIs(ontology.validate_entity_type("Project"), True)
        self.assertIs(ontology.validate_entity_type("InvalidType"), False)

    def test_validate_relation_type(self):
        self.assertIs(ontology.validate_relation_type("DEPENDS_ON"), True)
        self.assertIs(ontology.validate_relation_type("INVALID_REL"), False)

    def test_coerce_relation_type(self):
        self.assertEqual(ontology.coerce_relation_type("DEPENDS_ON"), "DEPENDS_ON")
        self.assertEqual(ontology.coerce_relation_type("INVALID_REL"), "UNRESOLVED_RELATION")

    def test_validate_provenance(self):
        self.assertIs(ontology.validate_provenance("EXPLICIT"), True)
        self.assertIs(ontology.validate_provenance("INFERRED"), True)
        self.assertIs(ontology.validate_provenance("INVALID"), False)


if __name__ == "__main__":
    unittest.main()
