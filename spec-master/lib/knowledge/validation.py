"""Validation for knowledge modules (concept knowledge base)."""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from .manifest import KnowledgeManifest
from .model import DEPTH_LEVELS, AGENT_ROLES
from graph.ontology import validate_entity_type


def validate_manifest(manifest: KnowledgeManifest) -> dict:
    """Validate all modules in a knowledge manifest."""
    modules = manifest.all_modules()
    issues = []

    for m in modules:
        # Check type is valid ontology entity type
        if not validate_entity_type(m.type):
            issues.append({"module": m.id, "issue": f"unknown type: {m.type}"})

        # Check depth levels are valid
        for role, depth in m.depth.items():
            if depth not in DEPTH_LEVELS:
                issues.append({"module": m.id,
                                "issue": f"invalid depth {depth!r} for role {role!r}"})
            if role not in AGENT_ROLES:
                issues.append({"module": m.id,
                                "issue": f"unknown role {role!r} in depth map"})

        # Check applicable_roles are known
        for role in m.applicable_roles:
            if role not in AGENT_ROLES:
                issues.append({"module": m.id,
                                "issue": f"unknown applicable_role: {role!r}"})

    return {
        "total_modules": len(modules),
        "issues": issues,
        "valid": len(issues) == 0,
    }
