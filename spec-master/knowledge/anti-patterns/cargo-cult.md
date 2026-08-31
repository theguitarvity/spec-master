---
id: antipattern.cargo-cult
type: AntiPattern
name: Cargo Cult Programming
category: anti-patterns
applicable_roles:
  - architect
  - tech-lead
tags:
  - anti-pattern
  - practices
depth:
  architect: L3
---

# Cargo Cult Programming

## Definition
Copying practices without understanding their purpose. CQRS everywhere, microservices for a todo app.

## Problem it addresses
A pattern or practice that solved a real problem for one team, in one context, gets copied by another team facing a completely different problem — because it looked sophisticated, was in a popular blog post, or 'that's what good engineers do' — without anyone checking whether the original problem actually applies here.

## Core principles
- Named after cargo cults that built replica airstrips hoping the (previously coincidental) cargo planes would return — copying the visible form of a practice without understanding the causal mechanism that made it useful.
- The tell is a practice adopted with no traceable problem it's solving in the current context — 'we should use CQRS' with no stated read/write model mismatch, 'we need microservices' with no stated need for independent deployability.
- The fix is always the same: ask what specific problem this pattern solves, and verify that problem actually exists here, before adopting it.

## Appropriate use
Not applicable as a technique — the relevant action is recognizing when a proposed pattern is being adopted for its reputation rather than a stated, verified problem, and asking for that problem before proceeding.

## Inappropriate use
Not applicable — there's no context where copying a practice without understanding why it worked elsewhere is the right call; always trace back to the specific problem before adopting an unfamiliar pattern.

## Trade-offs
Adopting a pattern without the problem it solves pays its full complexity cost (more moving parts, more to learn, more to maintain) with none of its benefit, since that benefit was tied to a problem that isn't actually present.

## Typical violations
Introducing [[architecture.microservices]] for a small internal tool with one team and no independent-scaling requirement, purely because 'that's how modern systems are built'.

## Anti-patterns
This entry is itself the anti-pattern; see [[principle.yagni]] and [[agile.chestertons-fence]] for the corresponding discipline (verify the reason before adopting, or before removing) that prevents it.

## Related concepts
- [[principle.yagni]]
- [[agile.chestertons-fence]]
