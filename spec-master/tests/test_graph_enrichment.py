import pytest
import _pathfix
from graph.enrichment import enrich_from_discovery

def test_enrich_from_discovery_empty(tmp_path):
    nodes, edges = enrich_from_discovery({}, project_root=str(tmp_path))
    assert len(nodes) == 1
    assert nodes[0].type == "Project"
    assert len(edges) == 0

def test_enrich_from_discovery_full(tmp_path):
    discovery_res = {
        "ci_present": True,
        "stacks": [
            {"language": "Python", "manifest": "requirements.txt", "commands": {"test": "pytest"}}
        ]
    }
    
    (tmp_path / "adr").mkdir()
    (tmp_path / "openapi.yaml").write_text("")

    nodes, edges = enrich_from_discovery(discovery_res, project_root=str(tmp_path))
    
    types = {n.type for n in nodes}
    assert "Project" in types
    assert "Technology" in types
    assert "Deployment" in types
    assert "Test" in types
    assert "ADR" in types
    assert "API" in types
    
    assert len(edges) == 5
    relations = {e.relation for e in edges}
    assert "USES" in relations
    assert "TESTED_BY" in relations
    assert "CONTAINS" in relations
    assert "EXPOSES" in relations
