"""Spec Master harness kernel (lane flow, opt-in).

The model does the semantic work; the kernel decides the next step, what is
allowed, which context to load, when a change is done and how to measure it;
the host enforces those decisions through its hooks. Stdlib only.
"""
