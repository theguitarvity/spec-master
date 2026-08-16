# Qwen-compatible adapter

This adapter documents how Spec Master runs in Qwen-based environments that
expose the same two primitives the other adapters rely on: file-system
access and the ability to execute commands or shell scripts.

Like the Claude Code, Copilot, and Codex adapters, this file stays thin on
purpose:

- It points back at [`../PROTOCOL.md`](../PROTOCOL.md), the canonical
  model-agnostic protocol shared by every adapter.
- It reuses the same `python3 spec-master/lib/cli.py ...` core for every
  structural decision.
- It assumes the host environment already defines how a Qwen session receives
  an invocation argument and how it asks the user for clarification.

Because Qwen deployments can vary widely, this adapter does not invent a
global install path or a particular skill-directory convention. When the
host platform offers a per-project pointer, point it at the same engine
files under `spec-master/` and follow the protocol exactly as the other
adapters do.

## Resuming

Re-invoking Spec Master with the same context file follows the same Step 0
behavior described in `../PROTOCOL.md`: compare the stored fingerprint,
resume when identical, and ask whether to resume or restart when the input
changed.
