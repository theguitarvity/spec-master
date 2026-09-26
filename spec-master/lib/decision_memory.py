"""Decision memory for Spec Master (roadmap item 9).

Every resolved escalation becomes a `Decision` node in the project knowledge
graph (`.spec-master/knowledge/graph/decision/...`), linked to:

- `agent.<role>` via DECIDED_BY (the role that decided, per the escalation
  route from team_model.escalation_route);
- the feature it influences via INFLUENCES, when that feature is in the graph.

When an ADR trigger applies (new external provider, core data model,
security/privacy change, boundary or infra change, rejected alternatives, or
a route the playbooks mark as ADR-worthy) an `ADR` node and an ADR Markdown
file are written as well — into the project's existing ADR directory when one
exists, otherwise `.spec-master/adr/`.

Roles read past decisions back with `decisions_for_role()` /
`decisions_for_feature()`, so a later intake starts from what was already
decided instead of re-litigating it. Deterministic, stdlib only; node ids are
content hashes, so recording the same decision twice updates one node.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import os
import re

import team_model
from graph.model import GraphEdge, GraphNode
from graph.store import FileGraphStore
from knowledge import profiles

GRAPH_RELDIR = os.path.join(".spec-master", "knowledge", "graph")
FALLBACK_ADR_RELDIR = os.path.join(".spec-master", "adr")
ADR_DIR_CANDIDATES = ("docs/adr", "docs/adrs", "docs/decisions", "doc/adr", "adr", "adrs")

ADR_TRIGGERS = {
    "new_external_provider": "Introduces a new external provider or third-party dependency",
    "new_core_data_model": "Introduces or reshapes a core data model",
    "security_privacy_change": "Changes the security or privacy posture",
    "boundary_change": "Moves a service, module, or trust boundary",
    "infra_change": "Changes infrastructure or deployment topology",
    "rejected_alternatives": "Meaningful alternatives were considered and rejected",
}

_REVERSE_ROLE_ALIASES = {knowledge: team for team, knowledge in profiles.TEAM_ROLE_ALIASES.items()}


def canonical_role(role: str) -> str:
    """Knowledge-base role ids (product-owner, infrastructure, ux) -> team_model ids."""
    return _REVERSE_ROLE_ALIASES.get(role, role)


def _slug(text: str, limit: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:limit].rstrip("-") or "decision"


def _one_line(text: str) -> str:
    # Frontmatter-safe: no newlines, no ": " (YAML mapping), no " #" (YAML
    # comment), no leading YAML indicator characters.
    text = re.sub(r"\s+", " ", str(text)).replace(": ", " - ").replace(" #", " ")
    return text.strip().lstrip("-?:,[]{}#&*!|>'\"%@` ").rstrip(":")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _graph_exists(root: str) -> bool:
    return os.path.isdir(os.path.join(os.path.abspath(root), GRAPH_RELDIR))


def adr_directory(root: str) -> str:
    root = os.path.abspath(root)
    for candidate in ADR_DIR_CANDIDATES:
        if os.path.isdir(os.path.join(root, candidate)):
            return candidate
    return FALLBACK_ADR_RELDIR


def _next_adr_number(directory: str) -> int:
    numbers = [0]
    if os.path.isdir(directory):
        for name in os.listdir(directory):
            match = re.match(r"^(\d{3,5})[-_]", name)
            if match:
                numbers.append(int(match.group(1)))
    return max(numbers) + 1


def _feature_node_id(graph, feature: str | None) -> str | None:
    if not feature:
        return None
    for candidate in (feature, f"feature.{feature}"):
        if graph.get_node(candidate) is not None:
            return candidate
    return None


def _decision_body(record: dict) -> str:
    lines = ["## Decision", "", record["decision"], "", "## Context", "",
             f"- Kind: `{record['kind']}`",
             f"- Raised by: `{record['raised_by']}`",
             f"- Decided by: `{record['decided_by']}`"]
    if record.get("feature"):
        lines.append(f"- Feature: `{record['feature']}`")
    if record.get("chain"):
        lines.append(f"- Escalation chain: {' → '.join(record['chain'])}")
    lines.append(f"- Recorded at: {record['recorded_at']}")
    if record.get("rationale"):
        lines += ["", "## Rationale", "", record["rationale"]]
    if record.get("alternatives"):
        lines += ["", "## Alternatives considered", ""] + [f"- {alt}" for alt in record["alternatives"]]
    if record.get("adr_triggers"):
        lines += ["", "## ADR triggers", ""] + [f"- {t}: {ADR_TRIGGERS.get(t, t)}" for t in record["adr_triggers"]]
    return "\n".join(lines)


def _adr_markdown(number: int, record: dict) -> str:
    lines = [f"# ADR {number:04d}: {record['title']}", "",
             f"- Status: Accepted",
             f"- Date: {record['recorded_at'][:10]}",
             f"- Deciders: {record['decided_by']} (raised by {record['raised_by']})",
             f"- Decision node: `{record['id']}`"]
    if record.get("feature"):
        lines.append(f"- Feature: `{record['feature']}`")
    lines += ["", "## Context", "",
              f"Escalation `{record['kind']}` routed through {' → '.join(record.get('chain') or [record['decided_by']])}.",
              "Triggers: " + ", ".join(ADR_TRIGGERS.get(t, t) for t in record["adr_triggers"]) + ".",
              "", "## Decision", "", record["decision"]]
    if record.get("rationale"):
        lines += ["", "## Rationale", "", record["rationale"]]
    if record.get("alternatives"):
        lines += ["", "## Alternatives considered", ""] + [f"- {alt}" for alt in record["alternatives"]]
    lines += ["", "## Consequences", "",
              "Revisit when the triggering context changes; supersede with a new ADR rather than editing this one.", ""]
    return "\n".join(lines)


def record_decision(root: str, *, kind: str, raised_by: str, decision: str, decided_by: str | None = None,
                    rationale: str = "", feature: str | None = None, alternatives: list[str] | None = None,
                    adr_triggers: list[str] | None = None, title: str | None = None) -> dict:
    if not decision or not str(decision).strip():
        raise ValueError("decision text is required")
    raised_by = canonical_role(raised_by)
    route = None
    if kind in team_model.ESCALATION_ROUTES:
        route = team_model.escalation_route(kind, raised_by)
    elif not decided_by:
        raise ValueError(f"unknown escalation kind `{kind}` needs an explicit decided_by")
    decided_by = canonical_role(decided_by or route["decided_by"])
    if decided_by not in team_model._ROLE_IDS:
        raise ValueError(f"unknown role: {decided_by}")
    triggers = list(dict.fromkeys(adr_triggers or []))
    unknown = [t for t in triggers if t not in ADR_TRIGGERS]
    if unknown:
        raise ValueError(f"unknown ADR trigger(s): {', '.join(unknown)} (known: {', '.join(ADR_TRIGGERS)})")
    if route and route["adr_candidate"] and "route_adr_candidate" not in triggers:
        triggers.append("route_adr_candidate")

    decision = str(decision).strip()
    title = _one_line(title or decision)[:100]
    digest = hashlib.sha256("|".join([kind, raised_by, decided_by, decision, feature or ""]).encode()).hexdigest()[:8]
    node_id = f"decision.{_slug(kind + '-' + title)}-{digest}"
    chain = route["chain"] if route else [decided_by]
    involved = list(dict.fromkeys([decided_by, raised_by] + chain))
    record = {
        "id": node_id, "kind": kind, "title": title, "decision": decision, "rationale": rationale or "",
        "raised_by": raised_by, "decided_by": decided_by, "chain": chain, "feature": feature,
        "alternatives": list(alternatives or []), "adr_triggers": triggers, "recorded_at": _now(),
    }

    store = FileGraphStore(root)
    graph = store.load()
    tags = ["decision", f"kind:{kind}", f"decided-by:{decided_by}", f"raised-by:{raised_by}"]
    tags += [f"involves:{role}" for role in involved]
    if feature:
        tags.append(f"feature:{feature}")
    existing = graph.get_node(node_id)
    node = GraphNode(
        id=node_id, type="Decision", name=title, source="EXPLICIT", confidence=1.0, tags=tags,
        first_seen=(existing.first_seen if existing else {"phase": "escalation", "at": record["recorded_at"]}),
        last_verified={"at": record["recorded_at"]},
        content=_decision_body(record),
    )
    store.save_node(node)

    agent_id = f"agent.{decided_by}"
    if graph.get_node(agent_id) is None:
        store.save_node(GraphNode(id=agent_id, type="Agent", name=f"{decided_by} agent", source="EXPLICIT",
                                  tags=["agent", f"role:{decided_by}"]))
    edges = [(node_id, "DECIDED_BY", agent_id)]
    feature_node = _feature_node_id(graph, feature)
    if feature_node:
        edges.append((node_id, "INFLUENCES", feature_node))

    adr = None
    if triggers:
        adr_id = f"adr.{node_id.split('.', 1)[1]}"
        rel_dir = adr_directory(root)
        abs_dir = os.path.join(os.path.abspath(root), rel_dir)
        prior = graph.get_node(adr_id)
        prior_path = next((t.split(":", 1)[1] for t in (prior.tags if prior else []) if t.startswith("path:")), None)
        if prior_path and os.path.isfile(os.path.join(os.path.abspath(root), prior_path)):
            rel_path = prior_path
            number = int(re.match(r"^(\d+)", os.path.basename(prior_path)).group(1))
        else:
            number = _next_adr_number(abs_dir)
            rel_path = os.path.join(rel_dir, f"{number:04d}-{_slug(title)}.md")
        os.makedirs(abs_dir, exist_ok=True)
        with open(os.path.join(os.path.abspath(root), rel_path), "w", encoding="utf-8") as fh:
            fh.write(_adr_markdown(number, record))
        store.save_node(GraphNode(id=adr_id, type="ADR", name=f"ADR {number:04d} - {title}", source="EXPLICIT",
                                  tags=["adr", f"path:{rel_path}"] + [f"trigger:{t}" for t in triggers],
                                  content=f"ADR file: `{rel_path}`\n\nDerived from decision `{node_id}`."))
        edges.append((adr_id, "DERIVED_FROM", node_id))
        adr = {"id": adr_id, "path": rel_path, "number": number}

    current = {(e.source, e.relation, e.target) for e in store.all_edges()}
    for source, relation, target in edges:
        if (source, relation, target) not in current:
            store.save_edge(GraphEdge(source=source, relation=relation, target=target, provenance="EXPLICIT",
                                      evidence={"description": f"escalation {kind} resolved"},
                                      first_seen={"at": record["recorded_at"]}))
    return {"decision": record, "node": node_id, "adr": adr,
            "edges": [{"source": s, "relation": r, "target": t} for s, r, t in edges]}


def record_from_event(root: str, payload: dict) -> dict:
    """Hook entry point for `escalation.resolved` events."""
    fields = ("kind", "raised_by", "decision", "decided_by", "rationale", "feature",
              "alternatives", "adr_triggers", "title")
    return record_decision(root, **{k: payload[k] for k in fields if payload.get(k) is not None})


# --------------------------------------------------------------------------- read side

def _tag_value(tags: list[str], prefix: str) -> str | None:
    for tag in tags:
        if tag.startswith(prefix + ":"):
            return tag.split(":", 1)[1]
    return None


def _summarize(node, adr_by_decision: dict) -> dict:
    body = node.content or ""
    decision_text = body.split("## Decision", 1)[-1].split("##", 1)[0].strip() if "## Decision" in body else ""
    return {
        "id": node.id,
        "title": node.name,
        "kind": _tag_value(node.tags, "kind"),
        "decided_by": _tag_value(node.tags, "decided-by"),
        "raised_by": _tag_value(node.tags, "raised-by"),
        "feature": _tag_value(node.tags, "feature"),
        "involves": [t.split(":", 1)[1] for t in node.tags if t.startswith("involves:")],
        "decision": decision_text,
        "recorded_at": (node.first_seen or {}).get("at"),
        "adr": adr_by_decision.get(node.id),
    }


def all_decisions(root: str) -> list[dict]:
    """Every Decision node, newest first. Read-only: no graph dir is created."""
    if not _graph_exists(root):
        return []
    store = FileGraphStore(root)
    nodes = store.all_nodes()
    adr_by_decision = {}
    by_id = {n.id: n for n in nodes}
    for edge in store.all_edges():
        if edge.relation == "DERIVED_FROM" and edge.source.startswith("adr.") and edge.source in by_id:
            adr_by_decision[edge.target] = _tag_value(by_id[edge.source].tags, "path")
    decisions = [_summarize(n, adr_by_decision) for n in nodes if n.type == "Decision"]
    return sorted(decisions, key=lambda d: d.get("recorded_at") or "", reverse=True)


def decisions_for_role(root: str, role: str, limit: int | None = None) -> list[dict]:
    role = canonical_role(role)
    selected = [d for d in all_decisions(root) if role in d["involves"] or role == "spec-master"]
    return selected[:limit] if limit else selected


def decisions_for_feature(root: str, feature: str, limit: int | None = None) -> list[dict]:
    selected = [d for d in all_decisions(root) if d.get("feature") in (feature, f"feature.{feature}")]
    return selected[:limit] if limit else selected
