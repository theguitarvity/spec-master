"""Agent context builder: combines the project graph and the concept
knowledge base into one budgeted bundle for a specific agent role and task.

This is the actual integration point the rest of Phase D exists to support —
an agent asks "what do I need to know to work on X as role Y" and gets back
a capped, ranked bundle instead of everything the graph and knowledge base
could theoretically offer.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from .traversal import bfs
from .query import search as graph_search

DEFAULT_NODE_DEPTH = 2
DEFAULT_NODE_BUDGET = 12


def _node_summary(node) -> dict:
    return {
        "id": node.id,
        "type": node.type,
        "name": node.name,
        "status": node.status,
        "confidence": node.confidence,
        "tags": node.tags,
    }


def _module_summary(module) -> dict:
    return {
        "id": module.id,
        "type": module.type,
        "name": module.name,
        "category": module.category,
    }


def build_agent_context(role: str, graph, knowledge_manifest=None,
                         focus_node_id: "str | None" = None,
                         keywords: "list[str] | None" = None,
                         tech_stacks: "list[str] | None" = None,
                         node_depth: int = DEFAULT_NODE_DEPTH,
                         node_budget: int = DEFAULT_NODE_BUDGET,
                         module_budget: "int | None" = None) -> dict:
    """Build a budgeted context bundle for `role` working on a task.

    - graph_nodes: nodes near focus_node_id (within node_depth hops), or
      keyword-matched nodes if no focus node is given, capped at node_budget.
    - knowledge_modules: relevant concept knowledge for `role`, via the
      Knowledge Router, capped at its own budget.

    Both halves are optional in practice — a graph with no nodes, or no
    knowledge manifest, still returns a valid (partially empty) bundle.
    """
    from knowledge.router import KnowledgeRouter
    from knowledge import profiles

    keywords = keywords or []
    graph_nodes: list = []

    if focus_node_id and focus_node_id in graph.nodes:
        graph_nodes.append(graph.get_node(focus_node_id))
        reached = bfs(graph, focus_node_id, max_depth=node_depth, direction="both")
        ordered_ids = sorted(reached, key=lambda nid: (reached[nid], nid))
        for nid in ordered_ids:
            node = graph.get_node(nid)
            if node:
                graph_nodes.append(node)
    elif keywords:
        seen_ids = set()
        for kw in keywords:
            for node in graph_search(graph, kw):
                if node.id not in seen_ids:
                    seen_ids.add(node.id)
                    graph_nodes.append(node)

    graph_nodes = graph_nodes[:node_budget]

    router = KnowledgeRouter(knowledge_manifest)
    budget = module_budget if module_budget is not None else profiles.DEFAULT_MODULE_BUDGET
    modules = router.for_context(role, keywords=keywords, tech_stacks=tech_stacks,
                                  limit=budget)

    return {
        "role": role,
        "focus_node_id": focus_node_id,
        "graph_nodes": [_node_summary(n) for n in graph_nodes],
        "knowledge_modules": [_module_summary(m) for m in modules],
        "budget": {
            "node_count": len(graph_nodes),
            "node_budget": node_budget,
            "module_count": len(modules),
            "module_budget": budget,
        },
    }
