"""Optional PR-opening step at the end of a Git Flow feature (roadmap item 10).

Deterministic and side-effect free apart from one local report file: this
module never runs git, gh, glab or az. It only

* decides whether a PR step applies (Git Flow + feature branch recorded +
  `validate` PASSED),
* renders the PR description (summary, acceptance criteria, phases,
  traceability matrix, final report) into
  `.spec-master/reports/pr-<feature-id>.md`, and
* returns a *directive* (argv) that the orchestrator may execute only after
  the user explicitly confirmed. Without `confirm=True` the answer is always
  `confirm_required` — opening a PR is never automatic.

Provider, base branch and remote-branch presence are read from evidence on
disk (`.git/config`, `.git/refs`, `packed-refs`, worktree `.git` files) or
from explicit arguments — never guessed from defaults.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import git_strategy  # noqa: E402
import traceability  # noqa: E402

try:  # the canonical phase order lives in state.py; keep a fallback copy
    from state import FEATURE_PHASES as _FEATURE_PHASES  # noqa: E402
except ImportError:  # pragma: no cover - state.py always ships with lib/
    _FEATURE_PHASES = ["specify", "clarify", "plan", "tasks", "analyze", "implement", "validate"]

PROVIDER_TOOLS = {"github": "gh", "gitlab": "glab", "azure": "az"}
BASE_CANDIDATES = ("develop", "main", "master")
AZURE_DESCRIPTION_LIMIT = 4000  # Azure DevOps rejects longer PR descriptions
FINAL_REPORT_EMBED_LIMIT = 20000  # keep the PR body well under GitHub's 65536
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
_SECTION_RE = re.compile(r'^\[\s*([^\s\]"]+)(?:\s+"((?:[^"\\]|\\.)*)")?\s*\]\s*(.*)$')
_ESCAPED_CHAR = re.compile(r"\\(.)")

CONFIRM_MESSAGE = (
    "Ask the user explicitly whether to open this pull request (show the title, "
    "head -> base and the description file). Do not open it unless the user says "
    "yes; then re-run `pr plan` with --confirm and execute the returned directive."
)


# --- git evidence (read-only, no subprocess) --------------------------------

def find_git_dirs(root: str | os.PathLike) -> tuple[Path, Path] | None:
    """Return (git_dir, common_dir) for the repo containing `root`, or None.

    Supports a plain `.git` directory and a `.git` *file* (`gitdir: ...`)
    as written for linked worktrees and submodules; a worktree's refs and
    config live in the common dir named by `<git_dir>/commondir`.
    """
    current = Path(root).resolve()
    for candidate in (current, *current.parents):
        dot_git = candidate / ".git"
        if dot_git.is_dir():
            git_dir = dot_git
        elif dot_git.is_file():
            try:
                content = dot_git.read_text(encoding="utf-8").strip()
            except OSError:
                return None
            if not content.lower().startswith("gitdir:"):
                return None
            target = Path(content.split(":", 1)[1].strip())
            git_dir = (target if target.is_absolute() else candidate / target).resolve()
        else:
            continue
        common_dir = git_dir
        commondir_file = git_dir / "commondir"
        if commondir_file.is_file():
            try:
                rel = commondir_file.read_text(encoding="utf-8").strip()
            except OSError:
                rel = ""
            if rel:
                common = Path(rel)
                common_dir = (common if common.is_absolute() else git_dir / common).resolve()
        return git_dir, common_dir
    return None


def _strip_inline_comment(value: str) -> str:
    out, quoted = [], False
    for ch in value:
        if ch == '"':
            quoted = not quoted
            continue
        if ch in "#;" and not quoted:
            break
        out.append(ch)
    return "".join(out).strip()


def parse_git_config(text: str) -> dict[str, dict[str, str]]:
    """Minimal git-config (INI dialect) parser.

    Returns {"<section>" or "<section> <subsection>": {key: value}}; section
    and key names are lower-cased (git treats them case-insensitively),
    subsection names keep their case. Later duplicates win.
    """
    sections: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        match = _SECTION_RE.match(line)
        if match:
            name = match.group(1).lower()
            sub = match.group(2)
            key = name if sub is None else name + " " + _ESCAPED_CHAR.sub(r"\1", sub)
            current = sections.setdefault(key, {})
            line = match.group(3).strip()
            if not line:
                continue
        if current is None:
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            current[k.strip().lower()] = _strip_inline_comment(v)
        else:
            current[line.lower()] = "true"
    return sections


def _read_git_config(common_dir: Path) -> dict[str, dict[str, str]]:
    try:
        return parse_git_config((common_dir / "config").read_text(encoding="utf-8"))
    except OSError:
        return {}


def _packed_refs(common_dir: Path) -> set[str]:
    try:
        text = (common_dir / "packed-refs").read_text(encoding="utf-8")
    except OSError:
        return set()
    refs = set()
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) == 2 and not line.startswith(("#", "^")):
            refs.add(parts[1])
    return refs


def ref_exists(common_dir: Path, ref: str) -> bool:
    """True if `ref` (e.g. refs/heads/develop) is a loose or packed ref."""
    return (common_dir / ref).is_file() or ref in _packed_refs(common_dir)


def origin_url(root: str | os.PathLike) -> tuple[str | None, str | None]:
    """(url, remote name) of remote "origin" — or of the only remote."""
    dirs = find_git_dirs(root)
    if dirs is None:
        return None, None
    config = _read_git_config(dirs[1])
    remotes = {k.split(" ", 1)[1]: v for k, v in config.items() if k.startswith("remote ") and v.get("url")}
    if "origin" in remotes:
        return remotes["origin"]["url"], "origin"
    if len(remotes) == 1:
        name, values = next(iter(remotes.items()))
        return values["url"], name
    return None, None


def remote_host(url: str) -> str:
    url = (url or "").strip()
    match = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://(?:[^@/]*@)?([^/:?#]+)", url)
    if match:
        return match.group(1).lower()
    match = re.match(r"^(?:[^@/]+@)?([^/:]+):", url)  # scp-like: git@host:org/repo.git
    if match:
        return match.group(1).lower()
    return ""


def redact_url(url: str | None) -> str | None:
    """Hide credentials in http(s) remotes (https://user:token@host -> https://***@host)."""
    if not url:
        return url
    return re.sub(r"^(https?://)[^@/]+@", r"\1***@", url, flags=re.IGNORECASE)


def detect_provider(url: str | None) -> str:
    host = remote_host(url or "")
    if not host:
        return "unknown"
    if "github.com" in host:
        return "github"
    if "gitlab" in host:
        return "gitlab"
    if "dev.azure.com" in host or "visualstudio.com" in host:
        return "azure"
    return "unknown"


def detect_base(root: str | os.PathLike, explicit: str | None = None) -> tuple[str | None, str]:
    """(base branch, evidence) — explicit arg, else develop, main, master."""
    if explicit:
        return explicit, "argument"
    dirs = find_git_dirs(root)
    if dirs is None:
        return None, "no git repository found"
    common_dir = dirs[1]
    candidates: list[str] = []
    # `git flow init` records `[gitflow "branch"] develop = <name>`
    config = _read_git_config(common_dir)
    gitflow_develop = (config.get("gitflow branch") or config.get("gitflow.branch") or {}).get("develop")
    if gitflow_develop:
        candidates.append(gitflow_develop)
    candidates.extend(c for c in BASE_CANDIDATES if c not in candidates)
    for name in candidates:
        if ref_exists(common_dir, f"refs/heads/{name}"):
            return name, f"local branch refs/heads/{name}"
    return None, "no local develop/main/master branch found"


# --- rendering ---------------------------------------------------------------

def _find_feature(state: dict, feature_id: str) -> dict:
    for feature in state.get("features", []) or []:
        if feature.get("id") == feature_id:
            return feature
    raise ValueError(f"unknown feature id: {feature_id}")


def _issue_id(feature: dict) -> str | None:
    for key in ("issue_id", "issue"):
        value = feature.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for text in (feature.get("branch"), feature.get("name"), feature.get("id")):
        if isinstance(text, str):
            found = git_strategy.extract_identifier(text)
            if found:
                return found
    return None


def build_title(feature: dict) -> str:
    name = (feature.get("name") or feature.get("id") or "").strip()
    issue = _issue_id(feature)
    if issue and issue not in name:
        return f"{name} ({issue})"
    return name


def body_path_for(root: str | os.PathLike, feature_id: str) -> Path:
    safe = _UNSAFE_FILENAME.sub("-", feature_id or "").strip("-.") or "feature"
    return Path(root) / ".spec-master" / "reports" / f"pr-{safe}.md"


def _cell(value) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _criterion_text(item) -> str:
    if isinstance(item, dict):
        return str(item.get("text") or item.get("criterion") or item.get("description") or "")
    return str(item)


def _quality_gate_rows(gates) -> list[str]:
    rows = []
    for gate in gates or []:
        if not isinstance(gate, dict):
            continue
        rows.append("| " + " | ".join(_cell(x) for x in (
            gate.get("name", ""), gate.get("result", ""), gate.get("exit_code", ""),
            "yes" if gate.get("blocking") else "no", gate.get("command", ""),
        )) + " |")
    return rows


def _spec_artifacts(root: Path, spec_directory: str | None) -> list[str]:
    if not spec_directory:
        return []
    directory = (root / spec_directory)
    if not directory.is_dir():
        return []
    entries = []
    for entry in sorted(directory.iterdir(), key=lambda p: p.name):
        if entry.name.startswith("."):
            continue
        entries.append(f"{spec_directory.rstrip('/')}/{entry.name}{'/' if entry.is_dir() else ''}")
    return entries


def render_body(root: str | os.PathLike, state: dict, state_path: str, feature: dict,
                *, title: str, head: str, base: str | None) -> str:
    root = Path(root)
    feature_id = feature.get("id", "")
    phases = feature.get("phases") or {}
    lines = [f"# {title}", ""]

    lines += ["## Summary", "", (feature.get("description") or "_No description recorded._").strip(), ""]
    lines.append(f"- Feature: `{feature_id}`")
    lines.append(f"- Branch: `{head}` → `{base}`" if base else f"- Branch: `{head}` → _(provider default branch)_")
    if feature.get("spec_directory"):
        lines.append(f"- Spec directory: `{feature['spec_directory']}`")
    sources = feature.get("source_requirements") or []
    if sources:
        lines.append("- Source requirements: " + ", ".join(f"`{s}`" for s in sources))
    lines.append("")

    criteria = [c for c in (_criterion_text(c).strip() for c in feature.get("acceptance_criteria") or []) if c]
    lines += ["## Acceptance Criteria", ""]
    if criteria:
        lines.append("_Verified by the Spec Master `validate` phase (PASSED)._")
        lines.append("")
        lines += [f"- [x] {c}" for c in criteria]
    else:
        lines.append("_No acceptance criteria recorded._")
    lines.append("")

    lines += ["## Phases", "", "| Phase | Status |", "|---|---|"]
    ordered = list(_FEATURE_PHASES) + [p for p in phases if p not in _FEATURE_PHASES]
    for phase in ordered:
        lines.append(f"| {phase} | {_cell(phases.get(phase, 'PENDING'))} |")
    lines.append("")

    rows = traceability.load_rows(state, state_path, feature=feature_id)
    matrix = traceability.render_rows(rows, title=f"Traceability Matrix — {feature_id}")
    if matrix.startswith("# "):
        matrix = "#" + matrix
    lines += [matrix.rstrip("\n"), ""]

    lines += ["## Final Report", ""]
    gates = feature.get("quality_gates") or state.get("quality_gates") or []
    validate_attempts = (state.get("attempts") or {}).get("validate") or []
    if not gates and validate_attempts:
        gates = (validate_attempts[-1] or {}).get("quality_gates") or []
    lines += ["### Quality Gates", ""]
    gate_rows = _quality_gate_rows(gates)
    if gate_rows:
        lines += ["| Gate | Result | Exit code | Blocking | Command |", "|---|---|---|---|---|", *gate_rows]
    else:
        lines.append("_No quality gate results recorded in state._")
    lines.append("")
    if validate_attempts:
        lines += ["### Validate Attempts", "", "| # | Status | Reason | Finished at |", "|---|---|---|---|"]
        for i, attempt in enumerate(validate_attempts, start=1):
            if isinstance(attempt, dict):
                lines.append("| " + " | ".join(_cell(x) for x in (
                    attempt.get("number", i), attempt.get("status", ""),
                    attempt.get("reason", ""), attempt.get("finished_at", ""),
                )) + " |")
        lines.append("")
    artifacts = _spec_artifacts(root, feature.get("spec_directory"))
    lines += ["### Spec Kit Artifacts", ""]
    lines += [f"- `{a}`" for a in artifacts] if artifacts else ["_No artifacts found under the spec directory._"]
    lines.append("")
    final_report = root / ".spec-master" / "reports" / "final-report.md"
    if final_report.is_file():
        try:
            report_text = final_report.read_text(encoding="utf-8").strip()
        except OSError:
            report_text = ""
        if report_text and len(report_text) <= FINAL_REPORT_EMBED_LIMIT:
            lines += ["<details>", "<summary>Spec Master final report</summary>", "", report_text, "",
                      "</details>", ""]
        elif report_text:
            lines += ["Full final report: `.spec-master/reports/final-report.md` "
                      "(too large to embed).", ""]

    lines += ["---", "",
              "_Generated by Spec Master (`pr plan`) from `.spec-master/state.json`. "
              "Opening this pull request required explicit user confirmation._", ""]
    return "\n".join(lines)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# --- directives --------------------------------------------------------------

def _azure_description(body: str, body_rel: str) -> tuple[str, bool]:
    if len(body) <= AZURE_DESCRIPTION_LIMIT:
        return body, False
    suffix = f"\n\n_(truncated — full description in `{body_rel}`)_"
    return body[: AZURE_DESCRIPTION_LIMIT - len(suffix)].rstrip() + suffix, True


def build_directive(provider: str, *, head: str, base: str | None, title: str,
                    body_path: Path, body: str, body_rel: str, draft: bool = False) -> dict:
    """Return {argv|None, manual?, requires, notes}. Never executed here."""
    notes: list[str] = []
    if provider == "github":
        argv = ["gh", "pr", "create"]
        if base:
            argv += ["--base", base]
        argv += ["--head", head, "--title", title, "--body-file", str(body_path)]
        if draft:
            argv.append("--draft")
    elif provider == "gitlab":
        # glab has no description-from-file flag: pass the body text itself.
        argv = ["glab", "mr", "create"]
        if base:
            argv += ["--target-branch", base]
        argv += ["--source-branch", head, "--title", title, "--description", body, "--yes"]
        if draft:
            argv.append("--draft")
    elif provider == "azure":
        description, truncated = _azure_description(body, body_rel)
        if truncated:
            notes.append(f"Azure DevOps limits PR descriptions to {AZURE_DESCRIPTION_LIMIT} characters; "
                         f"the description was truncated — the full text is in {body_rel}.")
        argv = ["az", "repos", "pr", "create", "--source-branch", head]
        if base:
            argv += ["--target-branch", base]
        argv += ["--title", title, "--description", description]
        if draft:
            argv += ["--draft", "true"]
    else:
        target = f"`{base}`" if base else "the repository's default branch"
        return {
            "argv": None,
            "manual": (f"Provider not detected from evidence. Open a pull request from `{head}` into {target} "
                       f"titled {title!r} on your hosting service and paste the contents of {body_rel} "
                       "as its description."),
            "requires": ["user_confirmed"],
            "notes": notes,
        }
    if not base:
        notes.append("Base branch not detected; the provider's default branch will be used "
                     "(pass --base to override).")
    return {"argv": argv, "requires": ["user_confirmed"], "notes": notes}


# --- entry point -------------------------------------------------------------

def plan_pr(root: str | os.PathLike, state: dict, state_path: str, feature_id: str, *,
            confirm: bool = False, base: str | None = None, remote_url: str | None = None,
            draft: bool = False) -> dict:
    """Plan (never perform) the optional PR step for one feature."""
    workflow = state.get("workflow")
    if workflow != "git-flow":
        reason = ("Trunk-Based Development: work lands on the trunk, no feature PR step."
                  if workflow == "trunk"
                  else "No workflow strategy recorded; the PR step only applies to Git Flow.")
        return {"action": "noop", "feature": feature_id, "workflow": workflow, "reason": reason}

    feature = _find_feature(state, feature_id)
    head = (feature.get("branch") or "").strip()
    if not head:
        return {"action": "blocked", "feature": feature_id,
                "reason": "No feature branch recorded in state (features[].branch); record the branch "
                          "created for this feature before planning a PR."}
    validate_status = (feature.get("phases") or {}).get("validate", "PENDING")
    if validate_status != "PASSED":
        return {"action": "blocked", "feature": feature_id,
                "reason": f"The validate phase must be PASSED before opening a PR (currently {validate_status})."}

    root_path = Path(root)
    base_branch, base_evidence = detect_base(root_path, base)
    if base_branch and base_branch == head:
        return {"action": "blocked", "feature": feature_id,
                "reason": f"Head and base are the same branch ({head}); nothing to propose."}

    if remote_url:
        url, remote_name, url_evidence = remote_url, None, "argument"
    else:
        url, remote_name = origin_url(root_path)
        url_evidence = f".git/config remote {remote_name!r}" if url else "no remote url found"
    provider = detect_provider(url)
    tool = PROVIDER_TOOLS.get(provider)

    dirs = find_git_dirs(root_path)
    remote_for_refs = remote_name or "origin"
    head_pushed = (ref_exists(dirs[1], f"refs/remotes/{remote_for_refs}/{head}") if dirs else None)

    title = build_title(feature)
    body = render_body(root_path, state, state_path, feature, title=title, head=head, base=base_branch)
    body_path = body_path_for(root_path, feature_id)
    _atomic_write(body_path, body)
    try:
        body_rel = str(body_path.resolve().relative_to(root_path.resolve()))
    except ValueError:
        body_rel = str(body_path)

    result = {
        "feature": feature_id,
        "title": title,
        "body_path": str(body_path),
        "base": base_branch,
        "base_evidence": base_evidence,
        "head": head,
        "provider": provider,
        "remote_url": redact_url(url),
        "remote_evidence": url_evidence,
        "tool": tool,
        "tool_available": bool(tool and shutil.which(tool)),
        "head_on_remote": head_pushed,
        "draft": draft,
    }

    if not confirm:
        return {"action": "confirm_required", **result, "message": CONFIRM_MESSAGE}

    directive = build_directive(provider, head=head, base=base_branch, title=title,
                                body_path=body_path, body=body, body_rel=body_rel, draft=draft)
    pre_directives = []
    if head_pushed is False and directive.get("argv"):
        pre_directives.append({
            "argv": ["git", "push", "-u", remote_for_refs, head],
            "requires": ["user_confirmed"],
            "reason": f"No refs/remotes/{remote_for_refs}/{head} found; push the feature branch first.",
        })
    notes = directive.pop("notes", [])
    if result["tool"] and not result["tool_available"]:
        notes.append(f"`{tool}` is not on PATH; install/authenticate it or open the PR manually "
                     f"with {body_rel} as the description.")
    return {
        "action": "open_pr",
        **result,
        "directive": directive,
        "pre_directives": pre_directives,
        "notes": notes,
        "message": "The user confirmed. Execute pre_directives (if any) then directive.argv exactly; "
                   "this core did not run anything.",
    }
