"""Fake `opencode run` stand-in for tests.

No real OpenCode install, Ollama, or network access is ever needed: tests
patch `subprocess.run` with the callable returned by `fake_subprocess_run`,
which plays back a scripted sequence of `FakeAgentStep`s instead of
actually spawning a subprocess.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


class FakeAgentStep:
    """One scripted `opencode run` invocation's effect."""

    def __init__(self, *, writes=None, stdout="", returncode=0):
        self.writes = writes or {}  # {project-relative path: file content}
        self.stdout = stdout
        self.returncode = returncode

    def apply(self, project: Path) -> subprocess.CompletedProcess:
        for relative_path, content in self.writes.items():
            target = project / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return subprocess.CompletedProcess(
            args=["opencode", "run"],
            returncode=self.returncode,
            stdout=self.stdout,
            stderr="",
        )


def fake_subprocess_run(steps: list[FakeAgentStep], project: Path):
    """Build a `subprocess.run`-compatible callable that plays back `steps`.

    Each call applies the next step in order; once `steps` is exhausted, the
    last step keeps repeating (so a test with a single scripted step can
    still run any number of attempts).
    """
    state = {"count": 0}

    def _run(*args, **kwargs):
        index = min(state["count"], len(steps) - 1)
        state["count"] += 1
        return steps[index].apply(project)

    return _run
