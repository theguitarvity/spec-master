"""Detect-then-instruct orchestration of existing Spec Kit tracker extensions.

Never a tracker client itself (Principle VII): this module only reads
`SKILL.md` manifests that are actually present on disk and reports what an
orchestrating agent should invoke. It performs no subprocess call, no
network call, and no tracker API call of any kind.
"""
from __future__ import annotations

import os

# Mirrors discovery.py's three known Spec Kit integration directories,
# substituting each platform's skill directory for its command directory.
_INTEGRATION_DIRS = (
    ("claude", os.path.join(".claude", "skills")),
    ("opencode", os.path.join(".opencode", "skill")),
    ("qwen", os.path.join(".qwen", "skill")),
)

# Keyword match against a skill's own declared name/description only -- never
# guessed from directory presence alone.
_TRACKER_KEYWORDS = {
    "jira": ("jira",),
    "azure_devops": ("azure devops", "azure-devops", "azure boards"),
    "linear": ("linear",),
    "github_issues": ("github issue", "github-issue"),
}


def _read_frontmatter(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    fields: dict = {}
    for line in text[3:end].splitlines():
        if not line or line[0] in " \t":
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in fields:
            fields[key] = value
    return fields


def _classify_tracker_type(name: str, description: str) -> str | None:
    haystack = f"{name} {description}".lower()
    for tracker_type, keywords in _TRACKER_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return tracker_type
    return None


def detect_tracker_extensions(root: str = ".") -> list[dict]:
    """Report Spec Kit tracker-orchestration skills actually installed under root.

    Evidence-based only: a skill directory with no SKILL.md, an unparsable
    SKILL.md, or a SKILL.md whose declared name/description matches no known
    tracker keyword is silently excluded -- never invented from directory
    presence alone.
    """
    root = os.path.abspath(root)
    extensions = []
    for integration, rel_dir in _INTEGRATION_DIRS:
        skills_dir = os.path.join(root, rel_dir)
        if not os.path.isdir(skills_dir):
            continue
        for skill_name in sorted(os.listdir(skills_dir)):
            manifest_path = os.path.join(skills_dir, skill_name, "SKILL.md")
            if not os.path.isfile(manifest_path):
                continue
            frontmatter = _read_frontmatter(manifest_path)
            if not frontmatter:
                continue
            description = frontmatter.get("description", "")
            name = frontmatter.get("name", skill_name)
            tracker_type = _classify_tracker_type(name, description)
            if tracker_type is None:
                continue
            extensions.append(
                {
                    "skill": skill_name,
                    "integration": integration,
                    "path": os.path.relpath(manifest_path, root),
                    "tracker_type": tracker_type,
                    "description": description,
                }
            )
    return extensions


def orchestrate(root: str = ".") -> dict:
    """Detect-then-instruct: name what to run, never run it.

    Absence of any tracker extension is a normal result (FR-005), not an
    error -- the caller's workflow continues unaffected.
    """
    extensions = detect_tracker_extensions(root)
    if not extensions:
        return {
            "orchestrated": False,
            "extensions": [],
            "invocations": [],
            "reason": (
                "no tracker extension detected under .claude/skills, "
                ".opencode/skill, .qwen/skill"
            ),
        }
    invocations = [
        {
            "skill": ext["skill"],
            "tracker_type": ext["tracker_type"],
            "command": f"/{ext['skill']}",
        }
        for ext in extensions
    ]
    return {
        "orchestrated": True,
        "extensions": extensions,
        "invocations": invocations,
        "reason": None,
    }
