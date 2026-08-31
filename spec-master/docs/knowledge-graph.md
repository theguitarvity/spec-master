# Knowledge Graph & Concept Knowledge Base

Spec Master carries two complementary, file-based knowledge systems, both
implemented as deterministic Python under `spec-master/lib/` — no database,
no LLM calls, no external services. Git is the source of truth for both.

1. **Project Knowledge Graph** (`spec-master/lib/graph/`) — a per-project,
   typed graph of what actually exists in *this* codebase: components,
   services, requirements, tests, ADRs, and the relationships between them.
   Built by discovery/enrichment, validated, and queryable.
2. **Concept Knowledge Base** (`spec-master/lib/knowledge/`) — a
   stack-agnostic library of ~75 software engineering concepts (principles,
   patterns, anti-patterns, laws) that ships *with* Spec Master itself,
   independent of any one project. Routed to agents by role and task.

They meet at `spec-master/lib/graph/context.py`, which combines both into a
single budgeted bundle for an agent working a specific task as a specific
Team Mode role.

## Project Knowledge Graph

### Data model (`graph/model.py`)

- `GraphNode` — `id` (namespaced, e.g. `service.payments-api`), ontology
  `type`, `status` (`active` / `deprecated` / `stale`), `source`
  (provenance), `confidence` (0.0–1.0), tags, aliases, and Markdown `content`.
- `GraphEdge` — typed `source → relation → target`, with its own provenance,
  confidence, evidence pointer, and an active/removed/superseded `status`.
- `Graph` — in-memory container: `add_node`/`add_edge`, `get_node`,
  `neighbors(node_id, relations=None, direction="out"|"in"|"both")`, `stats()`.

Entity types, relation types, and provenance types are all closed sets
defined in `spec-master/knowledge/ontology.yaml` (loaded by `graph/ontology.py`,
with an embedded fallback if PyYAML isn't installed) — agents may not invent
new types; anything unrecognized is coerced to `UNRESOLVED_RELATION`.

### Storage (`graph/store.py`)

`FileGraphStore` persists each node as a Markdown file with YAML frontmatter
under `<project>/.spec-master/knowledge/graph/<category>/<id>.md`, maintains
a `graph-manifest.json` index for fast loading, and appends every mutation
to `graph-events.jsonl` (an audit log — see `graph/events.py`). Wikilinks
(`[[other.id]]`) in a node's Markdown body become `RELATED_TO` edges
automatically (`graph/parser.py`); explicit typed edges live in the manifest.
`EntityResolver` (`graph/resolver.py`) prevents duplicate nodes by matching
names/aliases against existing canonical ids before a new one is created.

### Populating the graph (`graph/enrichment.py`)

`enrich_from_discovery()` converts `discovery.scan()`'s output (detected
languages, manifests, CI, existing specs) into `GraphNode`/`GraphEdge`
objects with `DISCOVERED_FROM_CODEBASE` / `DISCOVERED_FROM_CONFIG`
provenance and an evidence pointer back to the source file — nothing is
invented; everything traces back to something the scanner actually found.

### Querying (`graph/query.py`, `graph/traversal.py`)

- `query.py` — filters and search: `find_by_type`, `find_by_tag`,
  `find_by_status`, `find_by_relation`, `find_matching(predicate)`,
  `search(text)`, `edges_between`, `nodes_by_confidence`.
- `traversal.py` — bounded BFS: `bfs(graph, start_id, max_depth, direction)`,
  `descendants`/`ancestors`, `shortest_path`, and `blast_radius(graph,
  node_id, max_depth)` — "what's affected if this node changes", computed as
  the transitive closure of everything that (directly or indirectly)
  depends on it. All traversals are depth-bounded and cycle-safe.

### Maps (`graph/maps.py`)

Pure Markdown renderers for human/agent skimming: `render_system_map`
(all nodes grouped by type, with outgoing edges), `render_node_map`
(one node's neighborhood within N hops, grouped by distance), and
`render_dependency_map` (adjacency list for one relation type).

### Validation, drift, and health

- `graph/validation.py` — `validate_graph()` runs nine deterministic checks
  (orphan nodes, stale nodes, broken wikilinks, duplicate aliases, unknown
  entity/relation types, invalid provenance, low-confidence edges, nodes
  without evidence) and returns a structured, all-issues report.
- `graph/drift.py` — **structural drift**: `diff_graphs(old, new)` and
  `detect_structural_drift()` compare two graph snapshots and flag when a
  previously EXPLICIT/DISCOVERED (i.e. trustworthy) node or edge has
  disappeared — the signal that a spec has drifted from what the codebase
  now actually does. **Temporal drift**: `detect_temporal_drift()` flags
  nodes/edges not re-verified within `max_age_days`, via `graph/temporal.py`.
- `graph/health.py` — `compute_health()` combines both into a single 0–100
  score and letter grade (deductions weighted so broken links/unknown types
  cost more than an old timestamp), with `render_health_report()` for a
  human-readable Markdown summary.

### Traceability integration (additive)

`traceability.py`'s original API (`add_row`/`render`, backed by
`state["traceability"]`) is unchanged. Three additive functions derive rows
directly from the graph instead: `row_from_requirement_node()` walks a
`Requirement` node's `SATISFIES`/`BELONGS_TO` (→ Feature), `IMPLEMENTS`
(← Task), and `TESTED_BY` (→ Test) edges into one row; `rows_from_graph()`
does this for every Requirement node; `sync_from_graph(state, graph)` merges
those rows into `state["traceability"]`, idempotently, without touching or
duplicating manually-added rows.

## Concept Knowledge Base

Lives at `spec-master/knowledge/`, one Markdown file per concept, each with
YAML frontmatter (`id`, `type`, `name`, `category`, `applicable_roles`,
`tags`, `depth` — an `L0`–`L4` proficiency expectation per role) and a
consistent body: Definition, Problem it addresses, Core principles,
Appropriate/Inappropriate use, Trade-offs, Typical violations, Anti-patterns,
Related concepts (as `[[wikilinks]]` to other module ids).

```text
knowledge/
  foundations/        14 modules  — SOLID, DRY, YAGNI, coupling/cohesion, ...
  architecture/        21 modules  — hexagonal, CQRS, sagas, circuit breaker, ...
  distributed-systems/ 12 modules  — CAP/PACELC, consensus, replication, ...
  design/               8 modules  — DDD tactical patterns (aggregate, VO, ...)
  security/             8 modules  — OWASP Top 10 & API Top 10, auth, RBAC, ...
  agile/                8 modules  — Conway's/Brooks's/Little's Law, Kanban, ...
  anti-patterns/        5 modules  — distributed monolith, god object, ...
  stacks/               scaffold only — reserved for language/framework-
                         specific idiom modules (see stacks/README.md)
```

The core design rule (`knowledge/model.py`'s docstring): **more knowledge
must not mean more prompt.** Nothing loads the whole knowledge base into an
agent's context — every access path is selective.

### Loading and routing

- `knowledge/manifest.py` — `KnowledgeManifest` scans the tree once,
  indexes by id/role/category/tag, and auto-discovers the knowledge root by
  walking up from its own location (deliberately excluding its own
  containing directory — `lib/knowledge/` — from matching, since it shares
  its name with the real content root and would otherwise shadow it).
- `knowledge/profiles.py` — reconciles the two role vocabularies in this
  codebase: Team Mode (`team_model.py`) uses `po`/`infra`/`ui-ux-brand`;
  the knowledge base uses `product-owner`/`infrastructure`/`ux`.
  `resolve_knowledge_role()` is the one place that translates between them.
  Also defines per-role category priority (`CATEGORY_WEIGHTS_BY_ROLE`) and
  the default module budget (`DEFAULT_MODULE_BUDGET = 8`).
- `knowledge/router.py` — `KnowledgeRouter` is the actual selection engine:
  `for_role()` (applicable + ranked by depth/category), `for_query()`
  (role-filtered text search), `for_context()` (the primary entrypoint —
  role + keywords + detected tech stack, ranked and capped). Every method
  returns a bounded, ranked list, never "everything that matches."
- `knowledge/validation.py` — `validate_manifest()` checks every module's
  `type` against the ontology, and every role/depth entry against the known
  role vocabulary.

## Putting it together: `graph/context.py`

`build_agent_context(role, graph, knowledge_manifest, focus_node_id=None,
keywords=None, tech_stacks=None, node_depth=2, node_budget=12,
module_budget=8)` is the integration point: graph nodes near a focus node
(or keyword-matched, if no focus node), plus role-relevant knowledge
modules, both explicitly budgeted, returned as one JSON-serializable bundle
with a `budget` section reporting exactly what was included and why.

## CLI reference

All commands are JSON on stdout (Markdown for `graph maps` and file writes
for `graph health`), via `python3 spec-master/lib/cli.py <command> ...`.

```text
graph validate --path .                                   # validate_graph() report
graph stats --path .                                      # Graph.stats()
graph neighbors <node_id> [--relations R1,R2] --path .     # direct edges
graph stale --path .                                       # status=="stale" nodes
graph rebuild --path .                                     # rebuild graph-manifest.json
graph health --path .                                       # score + grade, writes graph-health.md
graph maps --path . --map-type system|node|dependencies
    [--node-id ID] [--depth N] [--relation REL]            # Markdown maps

knowledge list [--role R] [--category C] [--tag T]
knowledge get <id>
knowledge search <query>
knowledge for-role --role R [--limit N]
knowledge route --role R [--keywords k1,k2] [--tech-stacks node,python] [--limit N]
knowledge stats
knowledge validate
```

`graph/drift.py`'s snapshot-diffing functions (`diff_graphs`,
`detect_structural_drift`, `detect_temporal_drift`) are library-level and
used programmatically (e.g. by a future CI step that snapshots the graph
before/after a discovery re-scan) — they aren't wired to a CLI action yet,
since that needs a place to persist the "old" snapshot that the current
single-snapshot `FileGraphStore` CLI model doesn't provide.
