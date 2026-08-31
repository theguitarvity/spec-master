"""Ontology loader and validator for the Spec Master Knowledge Graph.

Reads ontology.yaml (relative to the spec-master/ package root) and exposes
the canonical sets of entity types, relation types, provenance types, and
confidence levels. Agents may NOT invent new types — unknown types are
classified as UNRESOLVED_RELATION.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

try:
    import yaml  # PyYAML, optional but recommended
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

# Fallback: minimal embedded ontology so the module works without PyYAML
_EMBEDDED_ENTITY_TYPES = {
    "Project", "Domain", "Subdomain", "BoundedContext", "Feature",
    "Requirement", "Component", "Service", "Module", "Package",
    "Class", "Interface", "API", "Endpoint", "Event", "Topic",
    "Queue", "Database", "Table", "Collection", "Cache",
    "ExternalSystem", "Dependency", "Deployment", "Container",
    "KubernetesResource", "Test", "ADR", "Risk", "Vulnerability",
    "Pattern", "AntiPattern", "Principle", "Technology", "Framework",
    "Library", "Agent", "Task", "Artifact", "QualityAttribute", "Policy",
}

_EMBEDDED_RELATION_TYPES = {
    "CONTAINS", "BELONGS_TO", "DEPENDS_ON", "CALLS", "READS_FROM",
    "WRITES_TO", "PUBLISHES", "CONSUMES", "IMPLEMENTS", "SATISFIES",
    "TESTED_BY", "DEPLOYED_ON", "USES", "GOVERNED_BY", "DECIDED_BY",
    "VIOLATES", "MITIGATES", "EXPOSES", "AUTHENTICATES_WITH",
    "AUTHORIZES_WITH", "OWNED_BY", "RELATED_TO", "REQUIRES", "PROVIDES",
    "CONFLICTS_WITH", "SUPERSEDES", "INFLUENCES", "DERIVED_FROM",
    "UNRESOLVED_RELATION",
}

_EMBEDDED_PROVENANCE_TYPES = {
    "EXPLICIT", "DISCOVERED_FROM_CODEBASE", "DISCOVERED_FROM_CONFIG",
    "DISCOVERED_FROM_SPEC", "DISCOVERED_FROM_ADR", "DISCOVERED_FROM_TEST",
    "INFERRED", "GENERATED", "USER_CONFIRMED", "UNRESOLVED",
}


def _find_ontology_path() -> Path | None:
    # Search upward from this file to find spec-master/knowledge/ontology.yaml
    here = Path(__file__).resolve().parent
    for ancestor in [here, here.parent, here.parent.parent, here.parent.parent.parent]:
        candidate = ancestor / "knowledge" / "ontology.yaml"
        if candidate.exists():
            return candidate
    return None


@lru_cache(maxsize=1)
def load_ontology(ontology_path: str | None = None) -> dict:
    """Load and return the ontology dict. Cached after first load."""
    if ontology_path is None:
        found = _find_ontology_path()
        path = found
    else:
        path = Path(ontology_path)

    if path and path.exists() and _HAS_YAML:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data

    # Fallback to embedded
    return {
        "schema_version": "1.0",
        "entity_types": sorted(_EMBEDDED_ENTITY_TYPES),
        "relation_types": sorted(_EMBEDDED_RELATION_TYPES),
        "provenance_types": sorted(_EMBEDDED_PROVENANCE_TYPES),
        "confidence_levels": {
            "deterministic": 1.00,
            "project_evidence": 0.90,
            "strong_inference_min": 0.70,
            "hypothesis_min": 0.50,
            "unresolved_max": 0.49,
        },
    }


def entity_types(ontology_path: str | None = None) -> set[str]:
    data = load_ontology(ontology_path)
    return set(data.get("entity_types", _EMBEDDED_ENTITY_TYPES))


def relation_types(ontology_path: str | None = None) -> set[str]:
    data = load_ontology(ontology_path)
    return set(data.get("relation_types", _EMBEDDED_RELATION_TYPES))


def provenance_types(ontology_path: str | None = None) -> set[str]:
    data = load_ontology(ontology_path)
    return set(data.get("provenance_types", _EMBEDDED_PROVENANCE_TYPES))


def validate_entity_type(type_str: str, ontology_path: str | None = None) -> bool:
    return type_str in entity_types(ontology_path)


def validate_relation_type(type_str: str, ontology_path: str | None = None) -> bool:
    return type_str in relation_types(ontology_path)


def validate_provenance(prov: str, ontology_path: str | None = None) -> bool:
    return prov in provenance_types(ontology_path)


def coerce_relation_type(type_str: str, ontology_path: str | None = None) -> str:
    """Return the type if valid, else UNRESOLVED_RELATION."""
    if validate_relation_type(type_str, ontology_path):
        return type_str
    return "UNRESOLVED_RELATION"
