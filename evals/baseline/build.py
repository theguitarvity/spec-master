#!/usr/bin/env python3
"""Build the baseline cases: one git repository per fixture, and the cases file.

    python3 evals/baseline/build.py --out DIR

For each case below, DIR/repos/<id> becomes a git repository with a single
commit whose hash depends only on the content (fixed author and dates). It
holds the fixture's files plus what a headless run cannot decide by asking:

- GitHub Spec Kit, initialized with `specify init --here --integration
  claude` at SPEC_KIT_REF, so the Spec Master arm never stops to offer the
  install (PROTOCOL.md Step 2);
- `.spec-master/state.json` with the git strategy already chosen (trunk) and
  the context file's fingerprint, so Step 0 resumes instead of asking
  "resume or restart".

Both arms start from that same commit. DIR/cases.json is the input of
`cli.py baseline plan|run --cases DIR/cases.json` (see lib/baseline.py).
Nothing here calls a model. `SPEC_KIT_SOURCE` overrides where uvx installs
Spec Kit from (a local checkout of the same tag works offline).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "spec-master" / "lib"))

import fingerprint  # noqa: E402
import state as state_mod  # noqa: E402

SPEC_KIT_REF = os.environ.get("SPEC_KIT_REF", "v0.16.4")  # the version init.sh pins
SPEC_KIT_SOURCE = os.environ.get("SPEC_KIT_SOURCE",
                                 f"git+https://github.com/github/spec-kit.git@{SPEC_KIT_REF}")
COMMIT_ENV = {"GIT_AUTHOR_NAME": "Spec Master baseline", "GIT_AUTHOR_EMAIL": "baseline@spec-master.invalid",
              "GIT_AUTHOR_DATE": "2026-09-29T12:00:00+00:00", "GIT_COMMITTER_NAME": "Spec Master baseline",
              "GIT_COMMITTER_EMAIL": "baseline@spec-master.invalid",
              "GIT_COMMITTER_DATE": "2026-09-29T12:00:00+00:00"}
SUITE = ["python3", "-m", "unittest", "discover", "-s", "tests", "-t", "."]
# Same tools and permission mode for every arm: the arms differ only in the prompt.
PERMISSION_MODE = "acceptEdits"
ALLOWED_TOOLS = ["Bash", "Read", "Edit", "Write", "Glob", "Grep", "Skill", "TodoWrite"]

CASES = {
    "bugfix-xs": {
        "description": "Paginação começa na página 2: correção de uma linha com teste de regressão.",
        "context": "BUG.md",
        "prompts": {
            "specmaster": "/spec-master BUG.md",
            "direct": "Corrija o bug descrito em BUG.md, com o teste de regressão que ele pede.",
        },
        "check": "bugfix_xs.py",
    },
}


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True,
                            env={**os.environ, **COMMIT_ENV})
    return result.stdout.strip()


def _spec_kit(repo: Path) -> None:
    subprocess.run(["uvx", "--from", SPEC_KIT_SOURCE, "specify", "init", "--here", "--integration", "claude",
                    "--script", "sh", "--ignore-agent-tools", "--force"],
                   cwd=repo, check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)


def _seed_state(repo: Path, context: str) -> None:
    state = state_mod.default_state(context, "trunk")
    state["fingerprint"] = fingerprint.compute([str(repo / context)])
    directory = repo / ".spec-master"
    directory.mkdir(exist_ok=True)
    state_mod.save(str(directory / "state.json"), state)
    state_mod.ensure_gitignore(str(directory))


def build_repo(case_id: str, spec: dict, out: Path) -> tuple[Path, str]:
    repo = out / "repos" / case_id
    if repo.exists():
        shutil.rmtree(repo)
    shutil.copytree(HERE / "fixtures" / case_id, repo, ignore=shutil.ignore_patterns("__pycache__"))
    _git(repo, "init", "-q", "-b", "main")
    _spec_kit(repo)
    _seed_state(repo, spec["context"])
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"Baseline case {case_id}")
    return repo, _git(repo, "rev-parse", "HEAD")


def build(out: Path) -> dict:
    cases = []
    for case_id, spec in CASES.items():
        repo, rev = build_repo(case_id, spec, out)
        cases.append({
            "id": case_id, "description": spec["description"], "repo": str(repo), "rev": rev,
            "prompts": spec["prompts"],
            "checks": [SUITE, ["python3", str(HERE / "checks" / spec["check"]), "--base", rev]],
            "permission_mode": PERMISSION_MODE, "allowed_tools": ALLOWED_TOOLS,
        })
    data = {"spec_kit": SPEC_KIT_REF, "cases": cases}
    (out / "cases.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", required=True, help="directory for repos/ and cases.json (outside this repo)")
    args = parser.parse_args(argv)
    out = Path(args.out).resolve()
    if out == REPO or REPO in out.parents:
        parser.error("--out must be outside the Spec Master repository: the cases are separate git repositories")
    out.mkdir(parents=True, exist_ok=True)
    data = build(out)
    print(json.dumps({"cases": out / "cases.json", "revisions": {c["id"]: c["rev"] for c in data["cases"]}},
                     default=str, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
