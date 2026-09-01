"""Graph enrichment from repository discovery.

Converts discovery.scan() output into GraphNode + GraphEdge objects
for the Project Knowledge Graph. All extracted entities carry provenance
and evidence pointing to the source manifest file.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .store import GraphStore

from .model import GraphNode, GraphEdge
from .provenance import DISCOVERED_FROM_CONFIG, DISCOVERED_FROM_CODEBASE


def _slug(name: str) -> str:
    """Convert a name to a stable lowercase slug."""
    import re
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-")


def enrich_from_discovery(discovery_result: dict,
                           project_root: str = ".") -> tuple[list[GraphNode], list[GraphEdge]]:
    """Convert a discovery.scan() result into graph nodes and edges.

    Returns (nodes, edges) — caller is responsible for persisting them.
    """
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    root = Path(project_root).resolve()

    # --- Project node ---
    project_name = root.name
    project_id = f"project.{_slug(project_name)}"
    nodes.append(GraphNode(
        id=project_id,
        type="Project",
        name=project_name,
        source=DISCOVERED_FROM_CONFIG,
        confidence=1.0,
        tags=["project"],
        content=f"# {project_name}\n\nDiscovered project root.",
    ))

    # --- Repository artifacts that matter even for manifest-light skill repos ---
    if discovery_result.get("readme_present"):
        readme_id = "artifact.readme"
        nodes.append(GraphNode(
            id=readme_id,
            type="Artifact",
            name="README",
            source=DISCOVERED_FROM_CONFIG,
            confidence=1.0,
            tags=["documentation"],
            raw_frontmatter={"evidence": {"file": "README.md"}},
            content="# README\n\nRepository README discovered at project root.",
        ))
        edges.append(GraphEdge(
            source=project_id,
            relation="CONTAINS",
            target=readme_id,
            provenance=DISCOVERED_FROM_CONFIG,
            confidence=1.0,
            evidence={"file": "README.md"},
        ))

    if discovery_result.get("docs_present"):
        docs_id = "artifact.docs"
        nodes.append(GraphNode(
            id=docs_id,
            type="Artifact",
            name="Documentation",
            source=DISCOVERED_FROM_CONFIG,
            confidence=0.95,
            tags=["documentation"],
            raw_frontmatter={"evidence": {"file": "docs/"}},
            content="# Documentation\n\nDocumentation directory discovered.",
        ))
        edges.append(GraphEdge(
            source=project_id,
            relation="CONTAINS",
            target=docs_id,
            provenance=DISCOVERED_FROM_CONFIG,
            confidence=0.95,
            evidence={"file": "docs/"},
        ))

    if (root / "spec-master").is_dir():
        package_id = "package.spec-master"
        nodes.append(GraphNode(
            id=package_id,
            type="Package",
            name="Spec Master Engine Package",
            source=DISCOVERED_FROM_CODEBASE,
            confidence=1.0,
            tags=["harness", "engine"],
            raw_frontmatter={"evidence": {"file": "spec-master/"}},
            content="# spec-master\n\nCore Spec Master package discovered.",
        ))
        edges.append(GraphEdge(
            source=project_id,
            relation="CONTAINS",
            target=package_id,
            provenance=DISCOVERED_FROM_CODEBASE,
            confidence=1.0,
            evidence={"file": "spec-master/"},
        ))

    # --- Technology nodes from stacks ---
    for stack in discovery_result.get("stacks", []):
        lang = stack.get("language", "unknown")
        lang_id = f"technology.{_slug(lang)}"
        manifest = stack.get("manifest", "")
        tech_node = GraphNode(
            id=lang_id,
            type="Technology",
            name=lang,
            source=DISCOVERED_FROM_CONFIG,
            confidence=1.0,
            tags=["technology", "stack", lang],
            raw_frontmatter={"evidence": {"file": manifest}},
            content=f"# {lang}\n\nDetected via `{manifest}`.",
        )
        nodes.append(tech_node)
        edges.append(GraphEdge(
            source=project_id,
            relation="USES",
            target=lang_id,
            provenance=DISCOVERED_FROM_CONFIG,
            confidence=1.0,
            evidence={"file": manifest},
        ))

    # --- CI/CD node ---
    if discovery_result.get("ci_present"):
        ci_id = "deployment.ci-cd"
        nodes.append(GraphNode(
            id=ci_id,
            type="Deployment",
            name="CI/CD Pipeline",
            source=DISCOVERED_FROM_CONFIG,
            confidence=0.9,
            tags=["ci-cd", "deployment"],
            content="# CI/CD Pipeline\n\nDetected CI configuration.",
        ))
        edges.append(GraphEdge(
            source=project_id,
            relation="USES",
            target=ci_id,
            provenance=DISCOVERED_FROM_CONFIG,
            confidence=0.9,
        ))

    # --- Test suite node ---
    for stack in discovery_result.get("stacks", []):
        if stack.get("commands", {}).get("test"):
            test_id = f"test.{_slug(stack.get('language', 'unknown'))}-suite"
            nodes.append(GraphNode(
                id=test_id,
                type="Test",
                name=f"{stack['language']} Test Suite",
                source=DISCOVERED_FROM_CONFIG,
                confidence=0.9,
                tags=["test", stack.get("language", "")],
                content=f"# Test Suite\n\nCommand: `{stack['commands']['test']}`",
            ))
            edges.append(GraphEdge(
                source=project_id,
                relation="TESTED_BY",
                target=test_id,
                provenance=DISCOVERED_FROM_CONFIG,
                confidence=0.9,
                evidence={"file": stack.get("manifest", "")},
            ))

    # --- ADR node (if docs/decisions or adr/ present) ---
    for adr_dir in ("docs/decisions", "adr", "docs/adr", "ADR"):
        adr_path = root / adr_dir
        if adr_path.is_dir():
            adr_id = "adr.collection"
            nodes.append(GraphNode(
                id=adr_id,
                type="ADR",
                name="Architecture Decision Records",
                source=DISCOVERED_FROM_CONFIG,
                confidence=0.95,
                tags=["adr", "architecture"],
                content=f"# ADRs\n\nFound in `{adr_dir}/`.",
            ))
            edges.append(GraphEdge(
                source=project_id,
                relation="CONTAINS",
                target=adr_id,
                provenance=DISCOVERED_FROM_CONFIG,
                confidence=0.95,
                evidence={"file": adr_dir},
            ))
            break

    # --- OpenAPI node ---
    for api_file in ("openapi.yaml", "openapi.json", "swagger.yaml",
                      "swagger.json", "api/openapi.yaml"):
        if (root / api_file).exists():
            api_id = "api.openapi-spec"
            nodes.append(GraphNode(
                id=api_id,
                type="API",
                name="OpenAPI Specification",
                source=DISCOVERED_FROM_CODEBASE,
                confidence=1.0,
                tags=["api", "openapi"],
                content=f"# OpenAPI Spec\n\nFound at `{api_file}`.",
            ))
            edges.append(GraphEdge(
                source=project_id,
                relation="EXPOSES",
                target=api_id,
                provenance=DISCOVERED_FROM_CODEBASE,
                confidence=1.0,
                evidence={"file": api_file},
            ))
            break

    # Deduplicate nodes by id
    seen_ids: set[str] = set()
    unique_nodes = []
    for n in nodes:
        if n.id not in seen_ids:
            seen_ids.add(n.id)
            unique_nodes.append(n)

    return unique_nodes, edges
