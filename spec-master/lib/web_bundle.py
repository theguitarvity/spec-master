"""Portable "web bundle" for chat UIs without CLI/tool access (roadmap item 13).

`build()` assembles ONE pasteable Markdown document for a feature's current
(or a chosen) phase:

- a header + usage instructions for the human and hard rules for the chat
  assistant (it has NO tool access, so it must return every deliverable file
  in full, with the path to save it at);
- the phase prompt rendered from `templates/prompts/<phase>.md` — the same
  templates PROTOCOL.md tells agents to fill — with every `{{placeholder}}`
  that project state can answer filled in; the rest stay visibly
  `{{unresolved}}` and are listed with a hint;
- the feature record from state.json;
- prior-phase artifacts, the constitution, and the normalized context docs,
  prioritized per phase and trimmed with `context_budget.budget_items()`;
- an explicit "Not included" list (budget-omitted and not-found items), so
  nothing is dropped silently.

Deliverable paths and phase policies are derived from `phase_contracts`
(the guarded-mode contract), not re-declared here. Output is deterministic:
the only time-dependent line is the optional `generated_at`.
Pure stdlib; no LLM, no network, never writes outside `.spec-master/bundles/`
unless an explicit output path is given.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import tempfile
from pathlib import Path

import context_budget
import phase_contracts
import state as state_mod

BUNDLE_FORMAT_VERSION = 1
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "prompts"
BUNDLES_RELDIR = os.path.join(".spec-master", "bundles")
CONTEXT_DIR = ".spec-master/context"
CONSTITUTION_PATH = phase_contracts.PHASE_ARTIFACTS["constitution"][0]
INSTRUCTION_FILES = ("CLAUDE.md", "AGENTS.md")

PHASES = ("constitution",) + tuple(state_mod.FEATURE_PHASES)
DONE_STATUSES = ("PASSED", "SKIPPED")

# Context sources per phase, most important first. "file.md" = a prior
# artifact in the feature's spec directory; a trailing "?" marks it optional
# (the phase's own previous output, or a doc Spec Kit does not always
# produce), which is NOT reported as missing when absent.
PHASE_SOURCES = {
    "constitution": ("constitution?", "context", "instructions?"),
    "specify": ("context", "constitution", "spec.md?"),
    "clarify": ("spec.md", "context", "constitution"),
    "plan": ("spec.md", "constitution", "context", "plan.md?", "research.md?", "data-model.md?"),
    "tasks": ("plan.md", "spec.md", "data-model.md?", "research.md?", "constitution", "context", "tasks.md?"),
    "analyze": ("spec.md", "plan.md", "tasks.md", "constitution", "data-model.md?", "research.md?", "context"),
    "implement": ("tasks.md", "plan.md", "spec.md", "data-model.md?", "research.md?", "constitution",
                  "instructions?", "context"),
    "validate": ("spec.md", "plan.md", "tasks.md", "constitution", "context"),
}

# Normalized context docs: per-phase preference, then any other *.md A-Z.
CONTEXT_DOC_ORDER = {
    "specify": ("app-features.md", "project-goals.md", "tech-stack.md"),
    "plan": ("tech-stack.md", "app-features.md", "project-goals.md"),
    "implement": ("tech-stack.md", "app-features.md", "project-goals.md"),
}
DEFAULT_CONTEXT_DOC_ORDER = ("app-features.md", "tech-stack.md", "project-goals.md")

UNRESOLVED_HINTS = {
    "discovered_conventions": "repository conventions come from `discovery scan`; they are not stored in state",
    "verifiable_project_rules": "verifiable rules (lint, coverage, architecture tests) derived from the "
                                "constitution/tech-stack; not stored in state",
    "quality_gate_commands": "quality gate commands come from `gates detect`; state.json records none",
    "constraints": "constraints for this feature (constitution.md, tech-stack.md); the feature record "
                   "has no `constraints` field",
    "non_goals": "explicit non-goals (app-features.md / project-goals.md); the feature record has no "
                 "`non_goals` field",
    "normalized_context_files": "no normalized context docs found in .spec-master/context/",
    "feature_dir": "the feature has no `spec_directory` in state",
    "feature_objective": "the feature record has no `description`",
    "source_requirements": "the feature record has no `source_requirements`",
    "acceptance_criteria": "the feature record has no `acceptance_criteria`",
    "sources": "no normalized context docs or repository instruction files were found",
}

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
_HTML_COMMENT_RE = re.compile(r"[ \t]*<!--.*?-->[ \t]*\n?", re.DOTALL)
_BACKTICK_RUN_RE = re.compile(r"`+")


# ------------------------------------------------------------------ helpers

def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def _posix(rel: str) -> str:
    return rel.replace(os.sep, "/")


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.") or "feature"


def _fence(text: str) -> str:
    longest = max((len(run) for run in _BACKTICK_RUN_RE.findall(text)), default=0)
    return "`" * max(3, longest + 1)


def _bullets(values) -> str:
    return "\n".join(f"- {v}" for v in values)


def current_phase(feature: dict) -> str | None:
    """First feature phase that is neither PASSED nor SKIPPED (None = all done)."""
    phases = feature.get("phases") or {}
    for phase in state_mod.FEATURE_PHASES:
        if phases.get(phase, "PENDING") not in DONE_STATUSES:
            return phase
    return None


def _spec_dir(feature: dict | None) -> str | None:
    value = (feature or {}).get("spec_directory")
    return _posix(os.path.normpath(value)) if value else None


def _feature_dir_value(spec_dir: str | None) -> str | None:
    if not spec_dir:
        return None
    return spec_dir[len("specs/"):] if spec_dir.startswith("specs/") else os.path.basename(spec_dir)


def _context_docs(root: str, phase: str) -> list[str]:
    directory = os.path.join(root, CONTEXT_DIR)
    try:
        names = sorted(n for n in os.listdir(directory)
                       if n.endswith(".md") and os.path.isfile(os.path.join(directory, n)))
    except OSError:
        return []
    preferred = CONTEXT_DOC_ORDER.get(phase, DEFAULT_CONTEXT_DOC_ORDER)
    ordered = [n for n in preferred if n in names] + [n for n in names if n not in preferred]
    return [f"{CONTEXT_DIR}/{n}" for n in ordered]


def _instruction_files(root: str) -> list[str]:
    return [name for name in INSTRUCTION_FILES if os.path.isfile(os.path.join(root, name))]


def expected_outputs(phase: str, feature: dict | None) -> list[str]:
    """Deliverable paths, derived from phase_contracts.PHASE_ARTIFACTS.

    `specs/*` becomes the feature's spec directory; `.specify/feature.json`
    (Spec Kit's own pointer file, written by its scripts) is not something a
    chat assistant authors. For inspect-or-update phases (clarify, analyze)
    these are the files the assistant MAY return, not files it must return.
    """
    spec_dir = _spec_dir(feature) or "specs/<feature-directory>"
    outputs = []
    for pattern in phase_contracts.PHASE_ARTIFACTS[phase]:
        if pattern == ".specify/feature.json":
            continue
        outputs.append(pattern.replace("specs/*", spec_dir))
    return outputs


# ------------------------------------------------------------ prompt render

def _placeholder_values(root: str, state: dict, feature: dict | None, phase: str) -> dict:
    feature = feature or {}
    values: dict[str, str] = {}
    context_docs = _context_docs(root, phase)
    spec_dir = _spec_dir(feature)

    if feature.get("name") or feature.get("id"):
        values["feature_name"] = str(feature.get("name") or feature.get("id"))
    if feature.get("description"):
        values["feature_objective"] = str(feature["description"])
    if _feature_dir_value(spec_dir):
        values["feature_dir"] = _feature_dir_value(spec_dir)
    if context_docs:
        values["normalized_context_files"] = ",".join(context_docs)

    def listed(key: str, empty: str) -> None:
        if key in feature and feature[key] is not None:
            items = feature[key] if isinstance(feature[key], list) else [feature[key]]
            values[key] = _bullets(items) if items else empty

    listed("source_requirements", "(none recorded in state)")
    listed("acceptance_criteria", "(none recorded in state — do not invent any; mark inferred criteria "
                                  "as INFERRED)")
    listed("constraints", "(none recorded in state)")
    listed("non_goals", "(none recorded in state)")

    if "dependencies" in feature:
        deps = feature.get("dependencies") or []
        by_id = {f.get("id"): f for f in state.get("features", [])}
        described = []
        for dep in deps:
            other = by_id.get(dep) or {}
            label = f"`{dep}`"
            if other.get("name"):
                label += f" — {other['name']}"
            if other.get("status"):
                label += f" (status: {other['status']})"
            described.append(label)
        values["dependencies"] = _bullets(described) if described else "(none)"
        values["feature_dependencies"] = ", ".join(f"`{d}`" for d in deps) if deps else "(no dependencies)"

    if feature:
        values["repair_cycle"] = str(feature.get("analyze_repair_cycles", 0))
    values["max_repair_cycles"] = str(state_mod.MAX_ANALYZE_REPAIR_CYCLES)

    commands = [g.get("command") for g in state.get("quality_gates") or []
                if isinstance(g, dict) and g.get("command")]
    if commands:
        values["quality_gate_commands"] = ", ".join(f"`{c}`" for c in commands)

    sources = list(context_docs) + _instruction_files(root)
    if sources:
        values["sources"] = _bullets(f"`{s}`" for s in sources)
    if os.path.isfile(os.path.join(root, CONSTITUTION_PATH)):
        values["existing_constitution_note"] = (
            f"A constitution already exists at `{CONSTITUTION_PATH}` (included under Context). Preserve "
            "rules that are still valid, apply ADDITION/MODIFICATION changes, and list every CONFLICT or "
            "REMOVAL_CANDIDATE for the user instead of applying it."
        )
    else:
        values["existing_constitution_note"] = f"No constitution exists yet at `{CONSTITUTION_PATH}`: create it."

    # Any other placeholder the feature record answers directly (e.g. a
    # `discovered_conventions` or `verifiable_project_rules` field).
    for key, value in feature.items():
        if key not in values and isinstance(value, (str, list)) and value:
            values[key] = _bullets(value) if isinstance(value, list) else value
    return values


def _template_body(text: str) -> str:
    """Drop the meta header (up to the first `---` line) and HTML comments."""
    lines = text.splitlines()
    if "---" in (line.strip() for line in lines):
        idx = next(i for i, line in enumerate(lines) if line.strip() == "---")
        lines = lines[idx + 1:]
    body = _HTML_COMMENT_RE.sub("", "\n".join(lines))
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def _validate_fallback(feature_name: str) -> str:
    return (
        "(Spec Master `validate` phase — there is no Spec Kit command or prompt template for it.)\n\n"
        f"Valide a entrega de \"{feature_name}\": o fluxo normal executa os quality gates do projeto "
        "(build, lint, testes, SAST), o que exige execução de comandos. Sem acesso a ferramentas, NÃO "
        "declare nenhum gate como aprovado. Produza a matriz de rastreabilidade requisito -> spec -> plan "
        "-> tasks a partir dos artefatos abaixo e um relatório de quality gates que liste os comandos a "
        "executar, todos marcados como NOT RUN."
    )


def render_prompt(root: str, state: dict, feature: dict | None, phase: str,
                  templates_dir: str | os.PathLike | None = None) -> dict:
    """Render `templates/prompts/<phase>.md` for a feature.

    Returns {"text", "template" (path or None), "unresolved": [names]}.
    `specs/{{feature_dir}}` becomes the feature's real spec_directory, so a
    feature stored outside `specs/` still gets correct paths.
    """
    templates_dir = Path(templates_dir) if templates_dir else TEMPLATES_DIR
    template_path = templates_dir / f"{phase}.md"
    raw = _read(str(template_path))
    values = _placeholder_values(root, state, feature, phase)
    if raw is None:
        name = values.get("feature_name", "{{feature_name}}")
        return {"text": _validate_fallback(name) if phase == "validate" else
                f"(No prompt template found at {template_path.name}.)", "template": None, "unresolved": []}
    body = _template_body(raw)
    spec_dir = _spec_dir(feature)
    if spec_dir:
        body = re.sub(r"specs/\{\{\s*feature_dir\s*\}\}", spec_dir, body)
    unresolved: list[str] = []

    def substitute(match: re.Match) -> str:
        name = match.group(1)
        if name in values:
            return values[name]
        if name not in unresolved:
            unresolved.append(name)
        return match.group(0)

    text = _PLACEHOLDER_RE.sub(substitute, body)
    try:
        template_label = _posix(os.path.relpath(template_path, TEMPLATES_DIR.parent.parent))
    except ValueError:
        template_label = str(template_path)
    return {"text": text, "template": template_label, "unresolved": unresolved}


# ------------------------------------------------------------ context items

def _candidate_items(root: str, state: dict, feature: dict | None, phase: str,
                     warnings: list[str]) -> tuple[list[dict], list[dict]]:
    """(found items in priority order, missing items). Items: id/kind/label/content."""
    found: list[dict] = []
    missing: list[dict] = []
    seen: set[str] = set()
    spec_dir = _spec_dir(feature)

    def add(rel: str, kind: str, label: str, optional: bool) -> None:
        rel = _posix(rel)
        if rel in seen:
            return
        seen.add(rel)
        text = _read(os.path.join(root, rel))
        if text is None or not text.strip():
            if not optional:
                missing.append({"id": rel, "kind": kind, "label": label, "reason": "not found"})
            return
        found.append({"id": rel, "kind": kind, "label": label, "content": text})

    for source in PHASE_SOURCES[phase]:
        optional = source.endswith("?")
        source = source.rstrip("?")
        if source == "constitution":
            add(CONSTITUTION_PATH, "constitution", "Project constitution", optional)
        elif source == "instructions":
            for name in _instruction_files(root):
                add(name, "instructions", "Repository instructions for agents", True)
        elif source == "context":
            docs = _context_docs(root, phase)
            for rel in docs:
                add(rel, "context", "Normalized context document", False)
            if not docs:
                raw = state.get("context")
                if raw and os.path.isfile(os.path.join(root, raw)):
                    add(os.path.normpath(raw), "context",
                        "Original context file (no normalized docs in .spec-master/context/)", True)
                else:
                    missing.append({"id": f"{CONTEXT_DIR}/*.md", "kind": "context",
                                    "label": "Normalized context documents", "reason": "not found"})
        else:  # a prior artifact in the feature's spec directory
            if not spec_dir:
                if not optional:
                    missing.append({"id": f"<spec_directory>/{source}", "kind": "artifact",
                                    "label": f"Prior artifact {source}", "reason": "feature has no spec_directory"})
                continue
            add(f"{spec_dir}/{source}", "artifact", f"Prior artifact: {source}", optional)
    if not spec_dir and phase != "constitution" and feature is not None:
        warnings.append("The feature has no `spec_directory` in state; prior artifacts cannot be located "
                        "and deliverable paths are placeholders.")
    return found, missing


def _section(item: dict) -> str:
    text = item["content"].rstrip("\n")
    fence = _fence(text)
    lang = "markdown" if item["id"].endswith(".md") else ""
    return f"### `{item['id']}`\n\n_{item['label']}_\n\n{fence}{lang}\n{text}\n{fence}\n"


# ------------------------------------------------------------- document

def _feature_record(feature: dict | None) -> str:
    if feature is None:
        return "Project-level phase: no feature selected."
    lines = [f"- **ID:** `{feature['id']}`"]
    if feature.get("name"):
        lines.append(f"- **Name:** {feature['name']}")
    if feature.get("spec_directory"):
        lines.append(f"- **Spec directory:** `{_spec_dir(feature)}`")
    if feature.get("status"):
        lines.append(f"- **Status:** {feature['status']}")
    deps = feature.get("dependencies") or []
    lines.append(f"- **Dependencies:** {', '.join(f'`{d}`' for d in deps) if deps else '(none)'}")
    phases = feature.get("phases") or {}
    if phases:
        lines.append("- **Phases:** " + ", ".join(
            f"{p}={phases.get(p, 'PENDING')}" for p in state_mod.FEATURE_PHASES))
    if feature.get("description"):
        lines += ["", "**Description**", "", str(feature["description"])]
    criteria = feature.get("acceptance_criteria") or []
    if criteria:
        lines += ["", "**Acceptance criteria**", ""]
        lines += [f"{i}. {c}" for i, c in enumerate(criteria, 1)]
    requirements = feature.get("source_requirements") or []
    if requirements:
        lines += ["", "**Source requirements**", "", _bullets(f"`{r}`" for r in requirements)]
    known = {"id", "name", "spec_directory", "status", "dependencies", "phases", "description",
             "acceptance_criteria", "source_requirements"}
    extra = {k: v for k, v in feature.items() if k not in known and v not in (None, "", [], {})}
    if extra:
        dumped = json.dumps(extra, indent=2, ensure_ascii=False, sort_keys=True)
        fence = _fence(dumped)
        lines += ["", "**Other recorded fields**", "", f"{fence}json", dumped, fence]
    return "\n".join(lines)


def _deliverable_rules(phase: str, outputs: list[str], spec_dir: str | None) -> list[str]:
    paths = ", ".join(f"`{p}`" for p in outputs)
    policy = phase_contracts.PHASE_POLICY[phase]
    rules = []
    if phase == "analyze":
        rules.append("Deliverable: the findings report in your answer, each finding classified "
                     "CRITICAL/HIGH/MEDIUM/LOW with the artifact responsible for it. If a CRITICAL/HIGH finding "
                     f"needs a repair, also return the complete repaired file(s) among {paths}; the user then "
                     "runs a new analyze cycle with a fresh bundle. If there are no findings and nothing to "
                     "repair, start your answer with `NO_CHANGES_REQUIRED`.")
    elif phase == "clarify":
        rules.append(f"Deliverable: if the spec needs changes, the complete updated {paths}. If it does not, "
                     "start your answer with `NO_CHANGES_REQUIRED` and say why. If any question is "
                     "USER_DECISION_REQUIRED, ask all of them in one message and stop there.")
    elif policy == "execute":
        rules.append(f"Deliverable: every source/test file needed for the tasks, each complete with its "
                     f"repository path, plus the complete updated {paths} with finished tasks checked "
                     "(`- [x]`). You cannot see the codebase: when a task depends on code that is not in "
                     "this document, ask for that file instead of guessing its contents.")
    elif phase == "validate":
        rules.append(f"Deliverable: the complete content of {paths}. You cannot run commands, so never "
                     "report a quality gate as passed: list each gate command as NOT RUN.")
    else:
        rules.append(f"Deliverable: the complete content of {paths}, as Markdown for the user to save at "
                     "that path. If a current version is included under Context, return the full updated "
                     "file, not a diff.")
        if phase == "plan" and spec_dir:
            rules.append(f"You may also return the Spec Kit design docs `{spec_dir}/research.md` and "
                         f"`{spec_dir}/data-model.md` when the plan needs them.")
    return rules


def _core_document(*, feature: dict | None, phase: str, outputs: list[str], prompt: dict,
                   token_budget: int, generated_at: str | None, warnings: list[str]) -> tuple[str, str]:
    """(everything before the context sections, the feature-record block)."""
    fid = feature["id"] if feature else None
    title_name = (feature.get("name") or fid) if feature else "Project constitution"
    command = "Spec Master validate phase" if phase == "validate" else f"Spec Kit `/speckit.{phase}`"
    spec_dir = _spec_dir(feature)
    out = [f"# Spec Master web bundle: {title_name} / {phase}", ""]
    if feature:
        out.append(f"- **Feature:** `{fid}`")
    out += [
        f"- **Phase:** `{phase}` ({command})",
        f"- **Deliverable:** {', '.join(f'`{p}`' for p in outputs)}",
        f"- **Context budget:** {token_budget} tokens (estimated at ~{context_budget.ESTIMATED_CHARS_PER_TOKEN} "
        f"characters per token)",
        f"- **Bundle format:** v{BUNDLE_FORMAT_VERSION}",
    ]
    if generated_at:
        out.append(f"- **Generated at:** {generated_at}")

    transition = (f"`python3 spec-master/lib/cli.py state transition --feature {fid} --phase {phase} "
                  f"--status PASSED`" if fid and phase != "constitution" else
                  "the Spec Master CLI (see PROTOCOL.md)")
    out += [
        "", "## How to use this bundle", "",
        "1. Paste this **entire** file into a chat assistant as one message. Do not trim it.",
        "2. The assistant has no access to your files or terminal; its answer must contain the complete "
        "content of each deliverable file, each preceded by the path to save it at.",
        "3. Review the answer, save each file at its path, then record the result with "
        f"{transition}.",
        "4. Anything listed under **Not included** at the end was left out (token budget or not found). "
        "Paste it in a follow-up message if the assistant asks for it.",
        "", "## Instructions for the assistant", "",
        f"You are running the **{phase}** phase of a Spec Kit workflow orchestrated by Spec Master, from a "
        "plain chat UI.",
        "",
        "- You have **NO tool access**: no file system, shell, web, or slash commands. Do not claim to have "
        "read, run, created, or saved anything. Everything you may rely on is in this document; the first "
        "line of the phase prompt names a Spec Kit command, and you act as that command yourself.",
    ]
    out += [f"- {rule}" for rule in _deliverable_rules(phase, outputs, spec_dir)]
    out += [
        "- Output format: for every file, a line `File: <path>` followed by the complete file content in "
        "one fenced block (use a longer fence, such as four backticks, if the content itself contains "
        "fences). Never abbreviate with \"...\", \"unchanged\", or \"same as before\".",
        "- Do not invent requirements, files, integrations, or acceptance criteria that this document "
        "does not support. Mark every inference as INFERRED, DISCOVERED_FROM_CODEBASE, or UNRESOLVED.",
        "- Placeholders still written as `{{name}}` could not be filled from project state: treat them as "
        "UNRESOLVED and do not guess their values.",
        "- Where the phase prompt asks you to run a command or update `.spec-master/` files (state, "
        "traceability, logs), do not pretend to: end your answer with a short **Follow-up for the CLI** "
        "list of what the user should record.",
        "- If something under **Not included** is needed, ask for it instead of guessing its content.",
    ]
    if warnings:
        out += ["", "**Warnings**", ""] + [f"- {w}" for w in warnings]

    out += ["", f"## Phase prompt: {phase}", ""]
    if prompt["template"]:
        out += [f"_Rendered from `{prompt['template']}`._", ""]
    out.append(prompt["text"])
    if prompt["unresolved"]:
        out += ["", "### Unresolved placeholders", ""]
        out += [f"- `{{{{{name}}}}}`: {UNRESOLVED_HINTS.get(name, 'not available in project state')}"
                for name in prompt["unresolved"]]
    record = _feature_record(feature)
    out += ["", "## Feature record", "", record, "", "## Context", ""]
    return "\n".join(out) + "\n", record


def _trailer(omitted: list[dict], missing: list[dict], fid: str | None, phase: str) -> str:
    out = ["## Not included", ""]
    if not omitted and not missing:
        out.append("Nothing was left out: every available context item fits the budget.")
    if omitted:
        out += ["**Omitted to fit the token budget** (paste on request):", ""]
        out += [f"- `{i['id']}` ({i['label']}, ~{i['estimated_tokens']} tokens)" for i in omitted]
    if missing:
        if omitted:
            out.append("")
        out += ["**Not found in the project**:", ""]
        out += [f"- `{i['id']}` ({i['label']}): {i['reason']}" for i in missing]
    out += ["", "---", "", f"_End of Spec Master web bundle ({fid or 'project'} / {phase})._", ""]
    return "\n".join(out)


def build(root: str, state: dict, feature_id: str | None, phase: str | None = None,
          token_budget: int = context_budget.DEFAULT_TOKEN_BUDGET, *,
          generated_at: str | None = None, templates_dir: str | os.PathLike | None = None) -> dict:
    """Assemble the bundle; see the module docstring.

    `token_budget` bounds the whole document except the short "Not included"
    trailer. The header, instructions, phase prompt, and feature record are
    always kept (if they alone exceed the budget, `over_budget` is True and
    every context item is omitted). Context items are whole files: they are
    offered to `context_budget.budget_items()` in priority order with the
    remaining budget, so a large item may be omitted while a smaller,
    lower-priority one still fits.

    Raises state.StateError for an unknown feature and ValueError for an
    unknown phase, a missing feature on a feature phase, or a feature with
    no pending phase when `phase` is not given.
    """
    if token_budget < 0:
        raise ValueError("token_budget cannot be negative")
    feature = state_mod.find_feature(state, feature_id) if feature_id else None
    if phase is None:
        if feature is None:
            raise ValueError("a feature id is required to detect the current phase")
        phase = current_phase(feature)
        if phase is None:
            raise ValueError(f"feature '{feature_id}' has no pending phase (all PASSED/SKIPPED); "
                             "pass a phase explicitly")
    if phase not in PHASES:
        raise ValueError(f"unknown phase {phase!r}; expected one of {list(PHASES)}")
    if feature is None and phase != "constitution":
        raise ValueError(f"phase '{phase}' needs a feature id")

    root = os.path.abspath(root)
    warnings: list[str] = []
    if feature is not None and phase in state_mod.FEATURE_PHASES:
        phases = feature.get("phases") or {}
        idx = state_mod.FEATURE_PHASES.index(phase)
        if idx > 0:
            prev = state_mod.FEATURE_PHASES[idx - 1]
            if phases.get(prev, "PENDING") not in DONE_STATUSES:
                warnings.append(f"The previous phase `{prev}` is {phases.get(prev, 'PENDING')}; the state "
                                f"machine will refuse to pass `{phase}` until it is PASSED or SKIPPED.")
        if phases.get(phase) in DONE_STATUSES:
            warnings.append(f"Phase `{phase}` is already {phases[phase]}; this bundle re-runs it.")

    found, missing = _candidate_items(root, state, feature, phase, warnings)
    outputs = expected_outputs(phase, feature)
    prompt = render_prompt(root, state, feature, phase, templates_dir=templates_dir)

    core, record = _core_document(feature=feature, phase=phase, outputs=outputs, prompt=prompt,
                                  token_budget=token_budget, generated_at=generated_at, warnings=warnings)
    core_tokens = context_budget.estimate_tokens(core)
    remaining = max(0, token_budget - core_tokens)

    sections = [{"id": i["id"], "kind": i["kind"], "label": i["label"], "content": _section(i)} for i in found]
    budget = context_budget.budget_items(sections, token_budget=remaining)
    selected, omitted = budget["selected"], budget["omitted"]

    body = "\n".join(s["content"] for s in selected) if selected else "_No context items fit the budget._\n"
    markdown = core + body + "\n" + _trailer(omitted, missing, feature["id"] if feature else None, phase)

    def public(entry: dict, **extra) -> dict:
        return {"id": entry["id"], "kind": entry["kind"], "estimated_tokens": entry["estimated_tokens"], **extra}

    included = [
        {"id": prompt["template"] or f"(built-in {phase} prompt)", "kind": "prompt",
         "estimated_tokens": context_budget.estimate_tokens(prompt["text"])},
    ]
    if feature is not None:
        included.append({"id": f"feature:{feature['id']}", "kind": "feature",
                         "estimated_tokens": context_budget.estimate_tokens(record)})
    included += [public(s) for s in selected]

    return {
        "markdown": markdown,
        "phase": phase,
        "feature": feature["id"] if feature else None,
        "outputs": outputs,
        "included": included,
        "omitted": [public(s, reason="token_budget") for s in omitted],
        "missing": [{"id": m["id"], "kind": m["kind"], "reason": m["reason"]} for m in missing],
        "unresolved_placeholders": prompt["unresolved"],
        "warnings": warnings,
        "tokens": context_budget.estimate_tokens(markdown),
        "token_budget": token_budget,
        "core_tokens": core_tokens,
        "over_budget": core_tokens > token_budget,
    }


# ------------------------------------------------------------------- write

def default_output_path(root: str, feature_id: str | None, phase: str) -> str:
    name = f"{_slug(feature_id) if feature_id else 'project'}-{phase}.md"
    return os.path.join(root, BUNDLES_RELDIR, name)


def write(root: str, result: dict, output: str | None = None) -> str:
    """Atomically write the bundle; default `<root>/.spec-master/bundles/<feature>-<phase>.md`."""
    path = output or default_output_path(root, result.get("feature"), result["phase"])
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".md", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(result["markdown"])
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return path
