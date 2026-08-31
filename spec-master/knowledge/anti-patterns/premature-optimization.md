---
id: antipattern.premature-optimization
type: AntiPattern
name: Premature Optimization
category: anti-patterns
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
tags:
  - anti-pattern
  - performance
depth:
  tech-lead: L3
---

# Premature Optimization

## Definition
"Premature optimization is the root of all evil" (Knuth). Measure first, optimize second.

## Problem it addresses
Engineers often optimize code paths based on a guess about where performance matters, before measuring — spending real effort and adding real complexity to make something faster that was never actually a bottleneck, while the real bottleneck goes unaddressed.

## Core principles
- 'Premature optimization is the root of all evil' (Donald Knuth) — the full quote clarifies this refers to optimizing the ~97% of code that isn't performance-critical, not an argument against ever optimizing.
- Measure first: profile to find the actual bottleneck before spending effort optimizing anything, since intuition about where time is spent is frequently wrong.
- Optimization usually trades code clarity for speed — that trade is only worth making where a measurement shows it's needed; everywhere else, it's a pure cost with no corresponding benefit.

## Appropriate use
Optimize once profiling data identifies a real, measured bottleneck that matters for a stated performance requirement — and optimize that specific hot path, not the whole codebase preemptively.

## Inappropriate use
Don't hand-optimize a rarely-called function's algorithmic complexity, or avoid a clear, simple abstraction, out of a general feeling that 'this might be slow' with no measurement backing it up.

## Trade-offs
Optimized code is often less clear and more complex than the straightforward version, which is only worth paying for where a measured bottleneck justifies it — applied without measurement, it's pure complexity cost with no guaranteed benefit, since the guessed bottleneck may not even be the real one.

## Typical violations
Micro-optimizing a loop that runs once at startup while an unindexed database query that runs on every request — the actual bottleneck — goes unnoticed and unmeasured.

## Anti-patterns
Optimizing without profiling is itself the anti-pattern; it often travels together with over-engineering more generally, since both stem from designing for a guessed future need instead of a measured, present one — see [[principle.yagni]].

## Related concepts
- [[principle.yagni]]
- [[principle.kiss]]
