"""Provenance classification for the Spec Master Knowledge Graph.

Every piece of knowledge must carry provenance. Inferences never
automatically acquire factual status.
"""
from __future__ import annotations

# Canonical provenance types (mirrored from ontology.yaml)
EXPLICIT = "EXPLICIT"
DISCOVERED_FROM_CODEBASE = "DISCOVERED_FROM_CODEBASE"
DISCOVERED_FROM_CONFIG = "DISCOVERED_FROM_CONFIG"
DISCOVERED_FROM_SPEC = "DISCOVERED_FROM_SPEC"
DISCOVERED_FROM_ADR = "DISCOVERED_FROM_ADR"
DISCOVERED_FROM_TEST = "DISCOVERED_FROM_TEST"
INFERRED = "INFERRED"
GENERATED = "GENERATED"
USER_CONFIRMED = "USER_CONFIRMED"
UNRESOLVED = "UNRESOLVED"

ALL_TYPES = {
    EXPLICIT, DISCOVERED_FROM_CODEBASE, DISCOVERED_FROM_CONFIG,
    DISCOVERED_FROM_SPEC, DISCOVERED_FROM_ADR, DISCOVERED_FROM_TEST,
    INFERRED, GENERATED, USER_CONFIRMED, UNRESOLVED,
}

# Confidence thresholds
CONFIDENCE_DETERMINISTIC = 1.00
CONFIDENCE_PROJECT_EVIDENCE = 0.90
CONFIDENCE_STRONG_INFERENCE_MIN = 0.70
CONFIDENCE_HYPOTHESIS_MIN = 0.50
CONFIDENCE_UNRESOLVED_MAX = 0.49


def is_valid(provenance: str) -> bool:
    return provenance in ALL_TYPES


def is_factual(provenance: str, confidence: float) -> bool:
    """Return True only if this knowledge can be treated as a confirmed fact."""
    if provenance in (EXPLICIT, USER_CONFIRMED, DISCOVERED_FROM_CODEBASE,
                      DISCOVERED_FROM_CONFIG, DISCOVERED_FROM_ADR):
        return confidence >= CONFIDENCE_PROJECT_EVIDENCE
    return False


def is_inference(provenance: str) -> bool:
    return provenance in (INFERRED, GENERATED)


def confidence_label(confidence: float) -> str:
    if confidence >= CONFIDENCE_DETERMINISTIC:
        return "deterministic"
    if confidence >= CONFIDENCE_PROJECT_EVIDENCE:
        return "project_evidence"
    if confidence >= CONFIDENCE_STRONG_INFERENCE_MIN:
        return "strong_inference"
    if confidence >= CONFIDENCE_HYPOTHESIS_MIN:
        return "hypothesis"
    return "unresolved"
