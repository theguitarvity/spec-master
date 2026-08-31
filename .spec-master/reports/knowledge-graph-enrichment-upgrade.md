# Knowledge Graph & Concept Knowledge Base — Upgrade Report

**Scope:** Phases C (Concept Knowledge), D (Agent Integration), E (Intelligence
Layer), plus validation and documentation, of the Spec Master
Graph-Augmented Knowledge Upgrade. Phases A (Graph Foundation) and B
(Discovery Graph) were already complete on entry (94 tests passing).

## Starting state: a structural mess, found before any new code was written

The previous work session had produced real content, but written to the
wrong location: a duplicate `knowledge/`, `lib/graph/` (empty), `lib/knowledge/`,
`scripts/generate_md.py`, and `run_tests.py` at the **repository root**,
instead of under `spec-master/`. The checklist's own paths
(`spec-master/knowledge/...`, `spec-master/lib/knowledge/...`) and the
manifest's auto-discovery logic both expect the content under `spec-master/`.
Three misplaced `test_knowledge_*.py` files were also found directly under a
root-level `tests/` directory. All of this was consolidated into
`spec-master/knowledge/`, `spec-master/lib/knowledge/`, and
`spec-master/tests/` before any new work began; the stray root-level
directories were removed.

## Two real bugs found and fixed

1. **All 68 pre-existing knowledge nodes had generic, non-specific body
   content.** Every section past "Definition" (Problem it addresses, Core
   principles, Appropriate/Inappropriate use, Trade-offs, Typical
   violations, Anti-patterns) was the exact same boilerplate paragraph
   copy-pasted across every single file, regardless of topic — e.g. CAP
   Theorem and OAuth2 shared the identical "Problem it addresses" text. This
   defeats the entire purpose of a concept knowledge base. All 68 nodes were
   rewritten with real, concept-specific content before any other Phase C
   work proceeded.
2. **`knowledge/manifest.py`'s `_find_knowledge_root()` matched the wrong
   directory.** Its own containing directory (`spec-master/lib/knowledge/`,
   the Python package) happens to share the name "knowledge" with the real
   content root (`spec-master/knowledge/`), and the ancestor-walk matched
   itself before ever reaching the real one. With no `knowledge_root`
   passed explicitly, `KnowledgeManifest()` silently loaded **zero**
   modules — undetected because every existing test passed an explicit
   `knowledge_root=tmp_path`, so the auto-discovery path had no coverage.
   Fixed by excluding the module's own directory from the match; a new test
   (`test_router_default_manifest_uses_real_knowledge_base`) now exercises
   the real auto-discovery path end to end.

## Phase C — Concept Knowledge

- Rewrote all 68 existing nodes with real, per-concept content (not
  generic filler), preserving their existing frontmatter and Related
  concepts.
- Validation surfaced 10 dangling wikilinks — concepts referenced by
  existing nodes' `related` lists that were never actually created (e.g.
  `pattern.bulkhead`, `architecture.onion`, `distributed.2pc`,
  `distributed.split-brain`, `principle.defensive-programming`,
  `security.rbac`, `security.owasp-api`, `architecture.evolutionary`).
  Added all 8 as real nodes rather than leaving the links broken — this
  was a correctness fix, not padding.
- **Final count: 76 real modules** (foundations 14, architecture 21,
  distributed-systems 12, design 8, security 8, agile 8, anti-patterns 5),
  **0 broken wikilinks**, `knowledge validate` clean.
  This is short of the original per-category estimates in the task
  checklist (~155 total across categories). That was a deliberate choice:
  the checklist's node counts were explicitly marked "~N" (estimates), and
  the priority was fixing the systemic quality bug above and closing every
  broken reference it and the original set left behind, over inflating the
  count with additional filler nodes. Every node that exists has real,
  differentiated content.
- `stacks/` was added as a directory scaffold (`node/`, `python/`, `java/`,
  `go/`, plus a `README.md` explaining the intended stack-specific-module
  pattern) per the checklist's "(stub structure)" annotation — intentionally
  not populated with content this pass.
- `spec-master/lib/knowledge/validation.py` (present but not yet wired) and
  `test_knowledge_validation.py` were recovered from the misplaced root
  files and moved into place alongside `test_knowledge_model.py` /
  `test_knowledge_manifest.py`.

## Phase D — Agent Integration

New modules, all with test coverage:

- `knowledge/profiles.py` — reconciles Team Mode's role ids (`po`, `infra`,
  `ui-ux-brand`) against the knowledge base's role vocabulary
  (`product-owner`, `infrastructure`, `ux`) — a real mismatch between two
  parts of the existing codebase that would otherwise have silently broken
  role-based routing for those three roles. Also holds per-role category
  priority and the default module budget.
- `knowledge/router.py` — `KnowledgeRouter`: `for_role`, `for_query`,
  `for_context` (role + keywords + tech stack, ranked, capped), plus
  `budget_summary` for visibility into what was actually selected.
- `graph/query.py` — filter/search helpers over `Graph` (by type, tag,
  status, relation, predicate, text search, confidence range).
- `graph/traversal.py` — bounded, cycle-safe BFS: `descendants`,
  `ancestors`, `shortest_path`, `blast_radius`.
- `graph/context.py` — `build_agent_context()`, the integration point
  combining graph neighborhood + routed knowledge modules into one budgeted
  bundle.
- `graph/maps.py` — Markdown renderers: system map, node-focused map,
  dependency adjacency map.
- `cli.py` — the previously stubbed `knowledge` subcommand (`{"status":
  "stub"}`) is now fully wired (`list`, `get`, `search`, `for-role`,
  `route`, `stats`, `validate`); `graph maps` added as a new `graph` action.

## Phase E — Intelligence Layer

- `graph/drift.py` — `diff_graphs()` / `detect_structural_drift()` (flags a
  previously EXPLICIT/DISCOVERED node or edge that has disappeared between
  two graph snapshots — the concrete signal for spec drift) and
  `detect_temporal_drift()` (nodes/edges not re-verified within a max age).
- `graph/health.py` — `compute_health()`: a single 0–100 score / letter
  grade combining structural validation and temporal staleness, with
  `render_health_report()` for Markdown output. `cli.py`'s `graph health`
  action was upgraded to use this (previously an inline stub that only
  echoed `valid`/`total_issues`).
- `traceability.py` — additive graph integration
  (`row_from_requirement_node`, `rows_from_graph`, `sync_from_graph`),
  walking `SATISFIES`/`BELONGS_TO`/`IMPLEMENTS`/`TESTED_BY` edges from
  `Requirement` nodes. The original `add_row`/`render` API and its existing
  test coverage are untouched — this only adds a second, graph-derived way
  to populate the same table.

`drift.py`'s diff functions are library-level, not CLI-wired: they need a
persisted "old" snapshot to diff against, which the current CLI's
single-snapshot `FileGraphStore` model doesn't provide. Documented as a
known boundary in `docs/knowledge-graph.md` rather than papered over with an
incomplete CLI action.

## Validation

```text
python3 spec-master/lib/cli.py graph validate   # 0 issues on a seeded graph
python3 spec-master/lib/cli.py graph stats      # correct node/edge counts
python3 spec-master/lib/cli.py graph health      # score 100, grade A on a seeded graph
python3 spec-master/lib/cli.py knowledge stats   # 76 modules, correct per-category counts
python3 spec-master/lib/cli.py knowledge validate  # 0 issues
```

All 5 platform adapters (`claude-code.md`, `copilot.md`, `codex.md`,
`qwen.md`, `generic.md`) and their project entrypoints are untouched by this
work and still point at `spec-master/lib/cli.py`, which remains
backward-compatible (only new subcommands/actions were added; no existing
command signature changed).

**Full regression:** `python3 -m pytest spec-master/tests/ -v` (run from
`spec-master/tests/`, per the existing `_pathfix.py` convention) —
**195 passed, 0 failed** (94 from Phases A+B, 101 new across Phases C–E).

## Known gaps / left for a follow-up pass

- `stacks/` has no populated modules yet (scaffold only, by design this pass).
- Node counts per category (76 total) are below the checklist's original
  "~155" estimate — every existing node has real content and zero broken
  links, but the breadth hasn't been pushed to that estimate.
- `graph/drift.py` has no CLI surface yet (see above).
