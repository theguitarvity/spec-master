"""Policy-enforced command governance for the Spec Master harness.

Spec Master cannot sandbox the operating system when running inside a hosted
agent, but it can provide a deterministic command broker: adapters should
preflight shell commands here and only execute commands classified as allowed.
"""
from __future__ import annotations

import shlex

DEFAULT_ALLOWED_EXECUTABLES = {
    "python", "python3", "pytest", "uv", "uvx",
    "npm", "pnpm", "yarn", "node",
    "git", "go", "cargo", "mvn", "gradle",
}

BLOCKED_TOKENS = {
    "rm", "sudo", "chmod", "chown", "mkfs", "dd", "killall",
}

BLOCKED_SEQUENCES = {
    "rm -rf", "git reset --hard", "git clean -fd", "git checkout --",
    "> /dev/", "curl | sh", "wget | sh",
}


def classify_command(command: str,
                     allowed_executables: set[str] | None = None) -> dict:
    allowed = allowed_executables or DEFAULT_ALLOWED_EXECUTABLES
    stripped = command.strip()
    if not stripped:
        return {"allowed": False, "risk": "blocked", "reason": "empty command"}

    lowered = " ".join(stripped.lower().split())
    for sequence in BLOCKED_SEQUENCES:
        if sequence in lowered:
            return {"allowed": False, "risk": "blocked", "reason": f"blocked sequence: {sequence}"}

    try:
        parts = shlex.split(stripped)
    except ValueError as exc:
        return {"allowed": False, "risk": "blocked", "reason": f"parse error: {exc}"}

    if not parts:
        return {"allowed": False, "risk": "blocked", "reason": "empty command"}

    executable = parts[0].split("/")[-1]
    if executable in BLOCKED_TOKENS:
        return {"allowed": False, "risk": "blocked", "reason": f"blocked executable: {executable}"}
    if executable not in allowed:
        return {"allowed": False, "risk": "requires_approval", "reason": f"unknown executable: {executable}"}

    if executable == "git" and len(parts) >= 3 and parts[1:3] == ["push", "--force"]:
        return {"allowed": False, "risk": "requires_approval", "reason": "force push requires approval"}

    return {"allowed": True, "risk": "low", "reason": "allowed by default policy"}


def preflight(commands: list[str]) -> dict:
    decisions = [{"command": command, **classify_command(command)} for command in commands]
    return {
        "allowed": all(d["allowed"] for d in decisions),
        "commands": decisions,
        "blocked": [d for d in decisions if not d["allowed"]],
    }
