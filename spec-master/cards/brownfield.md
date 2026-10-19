# Brownfield track (existing code)

Use when the repository already has code and the user wants Spec Master on it,
whole or for one directory (`--scope path/`). Read-only until the user agrees.

1. **Map** — `python3 spec-master/lib/cli.py tracks brownfield-map --path . [--scope dir/] --write`.
   Four readers, one pass: stack, architecture, conventions, risks. A host may
   run them as parallel subagents. Every finding cites `file:line`; the walk
   skips `.git node_modules dist build target .venv vendor __pycache__`.
   `--write` saves `.spec-master/context/codebase-map.md` and never overwrites.
2. **Constitution by evidence** — `tracks brownfield-constitution --path . --write`
   saves `.spec-master/context/constitution-proposal.md`. It lists only
   principles backed by evidence and marks the rest `[UNRESOLVED]`. It is a
   proposal: the user approves it, then run `speckit-constitution`. Never write
   `.specify/memory/constitution.md` from this output directly.
3. **First feature, bounded** — name the compatibility boundary (public API,
   data, CLI flags) in the spec; tag claims `[DISCOVERED_FROM_CODEBASE]`.
4. **Characterization tests (optional phase, before implement)** —
   `tracks brownfield-characterize --path . [--scope dir/]` ranks untested
   source files. For each file the change touches, write tests that pin the
   *current* behaviour (including odd outputs), run them green on untouched
   code, commit them separately, then implement. Skip when the touched code is
   already tested or the change is XS/S.
5. **Converge** — finish with `speckit-converge` to append unbuilt work.

Partial adoption: pass the same `--scope` everywhere; `discovery scan --scope dir/`
limits stacks and packages to that directory. Native mode is untouched.
