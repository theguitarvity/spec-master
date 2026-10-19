import unittest
import _pathfix
from graph import ontology


class GraphOntologyTests(unittest.TestCase):

    def test_entity_types(self):
        types = ontology.entity_types()
        assert "Project" in types
        assert "Component" in types

    def test_relation_types(self):
        types = ontology.relation_types()
        assert "UNRESOLVED_RELATION" in types
        assert "DEPENDS_ON" in types

    def test_validate_entity_type(self):
        assert ontology.validate_entity_type("Project") is True
        assert ontology.validate_entity_type("InvalidType") is False

    def test_validate_relation_type(self):
        assert ontology.validate_relation_type("DEPENDS_ON") is True
        assert ontology.validate_relation_type("INVALID_REL") is False

    def test_coerce_relation_type(self):
        assert ontology.coerce_relation_type("DEPENDS_ON") == "DEPENDS_ON"
        assert ontology.coerce_relation_type("INVALID_REL") == "UNRESOLVED_RELATION"

    def test_validate_provenance(self):
        assert ontology.validate_provenance("EXPLICIT") is True
        assert ontology.validate_provenance("INFERRED") is True
        assert ontology.validate_provenance("INVALID") is False


if __name__ == "__main__":
    unittest.main()
