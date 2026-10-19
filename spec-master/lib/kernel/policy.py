"""Command and write policy enforced at the host boundary.

`decide_command` classifies a shell command line as allow / ask / deny from
its argv (every segment of a compound command, redirections included);
`decide_write` does the same for a file the agent is about to write. The
hook daemon (hookd.py) turns these decisions into the host's PreToolUse
answer; `policy preflight` keeps its historical output shape on top of them.

Deny is reserved for what the constitution forbids or what cannot be undone
locally (Principle V: never `git reset --hard`, never delete work it did not
create); actions that publish outside the repository are `ask` (Principle X:
they need the user's explicit confirmation).
"""
from __future__ import annotations

import fnmatch
import os
import re
import shlex

ALLOW, ASK, DENY = "allow", "ask", "deny"
_RANK = {ALLOW: 0, ASK: 1, DENY: 2}

# Files only the core writes (state, change records, telemetry, policy/gates
# declarations). Globs are relative to the project root.
PROTECTED_WRITES = (
    ".spec-master/state.json",
    ".spec-master/changes/*.json",
    ".spec-master/metrics/rounds.json",
    ".spec-master/policy.json",
    ".spec-master/gates.json",
    ".git/*",
)

_SEPARATORS = {"&&", "||", ";", "|", "&", "(", ")", ";;", "|&"}
_REDIRECT_RE = re.compile(r"&?>>?\|?&?|<")
_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_SHELLS = {"sh", "bash", "zsh", "dash", "fish"}
_DOWNLOADERS = {"curl", "wget"}
_ALWAYS_DENY = {"sudo", "doas", "su", "mkfs", "dd", "shutdown", "reboot", "halt", "poweroff", "killall"}
_PUBLISH = {
    ("npm", "publish"), ("pnpm", "publish"), ("yarn", "publish"), ("cargo", "publish"),
    ("gem", "push"), ("poetry", "publish"), ("twine", "upload"), ("docker", "push"),
}


def _decision(decision: str, reason: str) -> dict:
    return {"decision": decision, "reason": reason}


def _worst(decisions: list[dict]) -> dict:
    return max(decisions, key=lambda d: _RANK[d["decision"]]) if decisions else _decision(ALLOW, "empty")


def _is_protected(path: str, root: str | None) -> bool:
    relative = path
    if root and os.path.isabs(path):
        try:
            relative = os.path.relpath(os.path.realpath(path), os.path.realpath(root))
        except ValueError:
            return False
    relative = relative.replace(os.sep, "/")
    while relative.startswith("./"):
        relative = relative[2:]
    return any(fnmatch.fnmatch(relative, pattern) for pattern in PROTECTED_WRITES)


def _split(command: str) -> tuple[list[list[str]], list[str]] | None:
    """(segments, redirection targets) or None when the line cannot be parsed."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return None
    segments: list[list[str]] = [[]]
    targets: list[str] = []
    pending = None  # "file" after a redirection, "fd" after a descriptor dup (2>&1)
    for token in tokens:
        if pending:
            if pending == "file":
                targets.append(token)
            pending = None
            continue
        if _REDIRECT_RE.fullmatch(token):
            pending = "fd" if token.endswith("&") else "file"
            if segments[-1] and segments[-1][-1].isdigit():
                segments[-1].pop()  # the "2" of "2>" is a descriptor, not an argument
            continue
        if token in _SEPARATORS or set(token) <= set("&|;()"):
            segments.append([token])  # keep the separator as a marker
            segments.append([])
            continue
        segments[-1].append(token)
    return [s for s in segments if s], targets


def _rm(argv: list[str], root: str | None) -> dict:
    flags = "".join(a.lstrip("-") for a in argv[1:] if a.startswith("-") and not a.startswith("--"))
    long_flags = {a for a in argv[1:] if a.startswith("--")}
    recursive = "r" in flags.lower() or "--recursive" in long_flags
    targets = [a for a in argv[1:] if not a.startswith("-")]
    dangerous = {"/", "~", ".", "..", "*", "./", "./*", "$HOME", "~/"}
    for target in targets:
        expanded = os.path.expanduser(target)
        if target in dangerous or target.startswith("/*"):
            return _decision(DENY, f"rm of {target!r} would delete the project or the system")
        if root and os.path.isabs(expanded):
            inside = os.path.realpath(expanded).startswith(os.path.realpath(root) + os.sep)
            if not inside:
                return _decision(DENY, f"rm outside the project: {target}")
    if recursive:
        return _decision(ASK, "recursive delete inside the project")
    return _decision(ALLOW, "delete of specific files")


def _git(argv: list[str]) -> dict:
    args = [a for a in argv[1:] if a not in ("-C",)]
    sub = next((a for a in args if not a.startswith("-")), "")
    rest = args[args.index(sub) + 1:] if sub in args else []
    if sub == "reset" and "--hard" in rest:
        return _decision(DENY, "git reset --hard discards work (constitution Principle V)")
    if sub == "clean" and any(a.startswith("-") and "f" in a.lstrip("-") or a == "--force" for a in rest):
        return _decision(DENY, "git clean -f deletes untracked work (constitution Principle V)")
    if sub in ("filter-branch", "filter-repo") or (sub == "update-ref" and "-d" in rest):
        return _decision(DENY, f"git {sub} rewrites or deletes history")
    if sub == "push":
        forced = any(a in ("-f", "--force", "--force-with-lease", "--mirror", "--delete", "-d")
                     or a.startswith("--force") for a in rest)
        refspec_force = any(a.startswith("+") or (a.startswith(":") and len(a) > 1) for a in rest)
        if forced or refspec_force:
            return _decision(DENY, "force/delete push rewrites a shared branch")
        return _decision(ASK, "git push publishes outside the repository (Principle X)")
    if sub == "checkout" and ("--" in rest or "." in rest):
        return _decision(ASK, "git checkout -- discards local changes")
    if sub == "restore" or (sub == "branch" and "-D" in rest) or (sub == "stash" and rest[:1] in (["drop"], ["clear"])):
        return _decision(ASK, f"git {sub} can discard work")
    if sub == "rebase":
        return _decision(ASK, "git rebase rewrites history")
    return _decision(ALLOW, f"git {sub or '(no subcommand)'}")


def _segment(argv: list[str], root: str | None) -> dict:
    while argv and _ENV_ASSIGN.match(argv[0]):
        argv = argv[1:]
    if not argv:
        return _decision(ALLOW, "environment assignment")
    executable = os.path.basename(argv[0])
    second = argv[1] if len(argv) > 1 else ""
    if executable in _ALWAYS_DENY or executable.startswith("mkfs"):
        return _decision(DENY, f"{executable} is never run by an agent")
    if executable == "rm":
        return _rm(argv, root)
    if executable == "git":
        return _git(argv)
    if (executable, second) in _PUBLISH:
        return _decision(ASK, f"{executable} {second} publishes outside the repository (Principle X)")
    if executable == "gh":
        if second == "repo" and "delete" in argv:
            return _decision(DENY, "gh repo delete")
        if second in ("pr", "release") and any(a in ("create", "merge", "edit", "delete") for a in argv[2:]):
            return _decision(ASK, f"gh {second} changes a shared resource (Principle X)")
    if executable == "glab" and second == "mr" or executable == "az" and "pr" in argv:
        return _decision(ASK, "opening a merge/pull request needs the user's confirmation (Principle X)")
    if executable in ("kubectl", "helm", "terraform", "pulumi"):
        if any(a in ("destroy", "delete", "uninstall") for a in argv[1:]):
            return _decision(DENY, f"{executable} destroys shared infrastructure")
        if any(a in ("apply", "install", "upgrade", "up", "rollout") for a in argv[1:]):
            return _decision(ASK, f"{executable} changes shared infrastructure (Principle X)")
    if executable in ("chmod", "chown") and any(a in ("-R", "--recursive") for a in argv[1:]):
        return _decision(ASK, f"recursive {executable}")
    if executable == "find" and ("-delete" in argv or ("-exec" in argv and "rm" in argv)):
        return _decision(ASK, "find that deletes files")
    if executable in ("python", "python3", "node") and any(
            re.search(r"rmtree|unlink|rmdir|remove\(|rmSync|rm\(", a) for a in argv[1:]):
        return _decision(ASK, "inline script that deletes files")
    return _decision(ALLOW, f"{executable}")


def decide_command(command: str, *, root: str | None = None) -> dict:
    """allow / ask / deny for a shell command line, worst segment wins."""
    if not (command or "").strip():
        return _decision(DENY, "empty command")
    parsed = _split(command)
    if parsed is None:
        return _decision(ASK, "the command could not be parsed")
    segments, targets = parsed
    decisions = []
    for target in targets:
        if _is_protected(target, root):
            decisions.append(_decision(DENY, f"redirection into a core-owned file: {target}"))
    previous_executable = None
    after_pipe = False
    for segment in segments:
        if len(segment) == 1 and segment[0] in _SEPARATORS | {"|&"}:
            after_pipe = segment[0] in ("|", "|&")
            continue
        argv = [a for a in segment if not _ENV_ASSIGN.match(a)] or segment
        executable = os.path.basename(argv[0]) if argv else ""
        if after_pipe and executable in _SHELLS and previous_executable in _DOWNLOADERS:
            decisions.append(_decision(DENY, "a downloaded script piped into a shell"))
        decisions.append(_segment(segment, root))
        previous_executable = executable
        after_pipe = False
    result = _worst(decisions)
    return {**result, "segments": len([s for s in segments if not (len(s) == 1 and s[0] in _SEPARATORS)])}


def decide_write(path: str, *, root: str | None = None, envelope: list[str] | None = None) -> dict:
    """allow / deny for a file write. `envelope` (glob list, relative to the
    root) is the set of paths the running change declared; None means no
    change is running and only the protected files are checked."""
    if _is_protected(path, root):
        return _decision(DENY, f"{path} is written only by the Spec Master core")
    if envelope is None:
        return _decision(ALLOW, "no running change")
    relative = path
    if root and os.path.isabs(path):
        relative = os.path.relpath(os.path.realpath(path), os.path.realpath(root))
    relative = relative.replace(os.sep, "/")
    if relative.startswith("../"):
        return _decision(DENY, f"{path} is outside the project")
    if any(fnmatch.fnmatch(relative, pattern) for pattern in envelope):
        return _decision(ALLOW, "inside the change envelope")
    return _decision(DENY, f"{relative} is outside the running change's envelope — widen or escalate the change first")
