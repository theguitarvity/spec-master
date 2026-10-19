"""Host subagent definitions (`sm-spec`, `sm-implement`, `sm-review`) rendered per host.

`packaging.render()` merges `render_agents()`. Bodies point to `cards/dispatch.md`
instead of embedding the protocol. Formats and the hosts that fall back to
`FALLBACK_INSTRUCTIONS` are recorded in specs/018-multi-agent-dispatch/contracts/host-agents.md.
"""
from __future__ import annotations

CARD = "cards/dispatch.md"
FALLBACK_INSTRUCTIONS = (
    "No subagent support: run the entries of each batch one after another in this session. For every "
    "entry: cd to its worktree (or stay in place when null), read cards/dispatch.md, execute the task "
    "test-first inside owned_paths, run `dispatch result` with the final PhaseResult, then run its sm-review "
    "entry from a fresh context. Never merge; hand over with `dispatch aggregate`.")

_SCOPE = ("Read your entry in the dispatch manifest (`dispatch manifest --feature F --wave N`), work only in "
          "its worktree and owned_paths, and finish with ONE PhaseResult block (artifact_updated | "
          "no_changes_required | user_decision_required | failed) under 2000 tokens. Never merge, rebase "
          "or push.")

ROLES = {
    "sm-spec": {
        "description": "Spec Master subagent: writes the spec artifact of one work package from the dispatch manifest.",
        "writes": True,
        "body": f"Follow `{CARD}`. Produce only the spec artifacts of your package; ask via "
                f"user_decision_required instead of guessing. {_SCOPE}",
    },
    "sm-implement": {
        "description": "Spec Master subagent: implements one work package test-first inside its worktree.",
        "writes": True,
        "body": f"Follow `{CARD}`. Write the failing test first, then the code, inside owned_paths only. {_SCOPE}",
    },
    "sm-review": {
        "description": "Spec Master subagent: read-only peer review of one finished work package (reviewer is not the owner).",
        "writes": False,
        "body": f"Follow `{CARD}`. You are read-only: inspect the diff and tests of the package and report "
                f"findings; never edit files. {_SCOPE}",
    },
}

# host -> (output directory relative to the repo root, tool names for read-only / writing roles)
HOSTS = {
    "claude": ("spec-master/agents", ("Read, Grep, Glob, Bash", "Read, Grep, Glob, Bash, Write, Edit")),
    "gemini": ("agents", ("read_file, grep_search, glob, run_shell_command",
                          "read_file, grep_search, glob, run_shell_command, write_file, replace")),
}


def _markdown(name: str, role: dict, tools: str) -> str:
    return ("---\n"
            f"name: {name}\n"
            f"description: {role['description']}\n"
            f"tools: {tools}\n"
            "---\n"
            f"{role['body']}\n")


def render_agents() -> dict[str, str]:
    """Repository-relative path -> exact file content for every host with plugin-shipped agents."""
    files = {}
    for directory, (read_only, writing) in HOSTS.values():
        for name, role in ROLES.items():
            files[f"{directory}/{name}.md"] = _markdown(name, role, writing if role["writes"] else read_only)
    return files
