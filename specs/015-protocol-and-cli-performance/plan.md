# Implementation Plan: Protocol and CLI Performance (P1-P6)

**Spec**: `specs/015-protocol-and-cli-performance/spec.md`

## Technical context

Python 3.10+, stdlib only, `unittest`. New code lives in `spec-master/lib/` OUTSIDE `kernel/` (budget: kernel <= 2,500 LOC, about 56 left). `cli.py` changes are small additive blocks, except the lazy-import change, done last as one isolated edit.

## Constitution check

I stdlib core: pass. III tests first, mirrored `test_<module>.py`: pass. IV evidence: `state advance` reuses the evidence check, no bypass. VI native behaviour unchanged: existing commands keep their output; `state transition` is refactored into a shared helper with identical output. VII hooks/doctor budgets: new code outside kernel, hook path untouched except the debounce in `hooks.py` (not the hookd path). Pass.

## Design

| Item | Module | Design |
|---|---|---|
| P1 | `lib/advance.py` (new), `state.py` (+`next_phase`), `cli.py` (+`state advance`, helper extracted from `state transition`) | `advance.next_block(feature, profile)` builds `{phase, status, hint}`; `state.next_phase(feature)` is the shared "first phase not PASSED/SKIPPED" function, also used by `controller` status. cli composes: validate JSON, one state transaction (transition + evidence + traceability rows), then round append, then hooks. |
| P2 | `lib/protocol_sections.py` (new), `cards/full-cycle.md` (new), `templates/entrypoints/full-cycle.md`, `cli.py` (+`protocol sections|show`) | Section index by markdown headings (outside code fences). Router lists steps with the exact `protocol show --section` call. |
| P3 | `risk_profile.py` | `PHASE_HINTS` table by tier and phase; `hints` key in every profile; `controller._render_prompt` appends one hint line. |
| P4 | `phase_contracts.py`, `discovery.py` | `walk_project` uses `os.walk` with in-place dir pruning; `snapshot` uses it plus a `{path: [size, mtime_ns, sha]}` cache file `.spec-master/cache/snapshot.json` (ignored by the snapshot itself). |
| P5 | `hooks.py`, `dashboard.py` | `.spec-master/cache/dashboard-render.json` timestamp debounce (default 2 s, `SPEC_MASTER_DASHBOARD_DEBOUNCE`); graph cache keyed by (path, size, mtime_ns) in process and on disk-free. |
| P6 | `mcp/spec_master_mcp.py`, `cli.py` | `run_cli` calls `cli.main(argv)` in process under a lock, with `redirect_stdout/stderr`, cwd/env restore, `SystemExit` handling; subprocess fallback. `cli.py` replaces eager imports by a lazy `_LazyModule` proxy for modules not used while building the parser. |

## Project structure (changed or new)

```
spec-master/lib/advance.py            new
spec-master/lib/protocol_sections.py  new
spec-master/cards/full-cycle.md       new
spec-master/lib/{state,risk_profile,phase_contracts,discovery,hooks,dashboard,controller,cli}.py   additive
spec-master/mcp/spec_master_mcp.py    in-process dispatch
spec-master/templates/entrypoints/full-cycle.md
spec-master/PROTOCOL.md               documents advance, protocol show, hints
spec-master/tests/test_{advance,protocol_sections,risk_hints,phase_snapshot,dashboard_debounce,mcp_inprocess,cli_lazy}.py
```

## Risks
- `test_protocol_conformance` parses documented CLI invocations: every new command is added to the parser in the same step it is documented.
- Lazy imports conflict with other features adding imports to `cli.py`: done last, mechanical, listed in the report.
- In-process MCP must not leak global state (`PRETTY`, cwd): saved and restored under a lock.
