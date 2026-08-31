# Stack-Specific Knowledge Modules (stub)

The categories under `knowledge/` (`foundations/`, `architecture/`, `distributed-systems/`,
`design/`, `security/`, `agile/`, `anti-patterns/`) hold stack-agnostic concept knowledge —
principles, patterns, and laws that apply regardless of language or framework.

`stacks/` is reserved for the next layer: stack-specific idiom and pitfall modules that
extend a stack-agnostic concept for a particular language, framework, or runtime — e.g.
how [[principle.dependency-inversion]] is idiomatically applied in Go (no classes, so it's
interfaces + constructor injection) versus in Python (duck typing often skips the interface
declaration entirely) versus in Java (explicit interfaces, DI containers).

## Intended structure

```
stacks/
  node/       # Node.js / TypeScript idioms, common pitfalls, ecosystem conventions
  python/     # Python idioms, common pitfalls, ecosystem conventions
  java/       # Java / JVM idioms, common pitfalls, ecosystem conventions
  go/         # Go idioms, common pitfalls, ecosystem conventions
```

Each stack module follows the same frontmatter schema as any other knowledge module
(see `spec-master/lib/knowledge/model.py`), with `category: stacks` and a `related`
wikilink back to the stack-agnostic concept it specializes — e.g. a
`stacks/go/dependency-inversion-in-go.md` module would link back to
[[principle.dependency-inversion]] rather than duplicating its definition.

## Status

Directory scaffold only. No stack-specific modules are populated yet — this is left for
a follow-up pass once the routing/loading layer (Phase D) is in place and can validate
which stack modules actually get selected for a given project's detected tech stack
(`discovery.py` already detects Node/Python/Go/Rust/Java manifests; `stacks/` is the
knowledge side of that same detection).
