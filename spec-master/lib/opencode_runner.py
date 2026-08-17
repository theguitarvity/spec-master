#!/usr/bin/env python3
"""Run one Spec Kit phase in a fresh, bounded OpenCode session.

The language model performs the semantic work, while this wrapper owns the
phase boundary, timeout, transcript, and artifact checks.  It intentionally
does not continue a prior chat: each phase gets only its explicit prompt and
the files the corresponding Spec Kit command chooses to read.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase_contracts import (  # noqa: E402
    PHASE_ARTIFACTS,
    changed_paths,
    forbidden_writes,
    placeholder_artifacts,
    snapshot,
    validate_artifacts,
    validate_transcript,
)


def run(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    prompt_path = Path(args.prompt_file).resolve()
    if not project.is_dir():
        raise ValueError(f"project directory not found: {project}")
    if not prompt_path.is_file():
        raise ValueError(f"prompt file not found: {prompt_path}")

    log_dir = project / ".spec-master" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    transcript_path = log_dir / f"{stamp}-{args.phase}.jsonl"
    lock_path = project / ".spec-master" / "run.lock"
    lock_path.write_text(args.phase + "\n", encoding="utf-8")

    prompt = prompt_path.read_text(encoding="utf-8")
    before = snapshot(project)
    command = [
        "opencode", "run", "--pure", "--format", "json",
        "--dir", str(project), "--agent", args.agent,
        "--model", args.model, "--command", f"speckit.{args.phase}",
        prompt,
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=project,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=args.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        transcript_path.write_text(output, encoding="utf-8")
        print(json.dumps({"status": "FAILED", "reason": "timeout", "phase": args.phase,
                          "transcript": str(transcript_path)}, ensure_ascii=False))
        return 124
    finally:
        lock_path.unlink(missing_ok=True)

    transcript_path.write_text(completed.stdout, encoding="utf-8")
    after = snapshot(project)
    changed = changed_paths(before, after)
    fake_markers = validate_transcript(completed.stdout)
    missing = validate_artifacts(project, args.phase)
    placeholders = placeholder_artifacts(project, args.phase)
    forbidden = forbidden_writes(changed, args.phase)
    required_changed = any(
        any(fnmatch.fnmatch(path, pattern) for path in changed)
        for pattern in PHASE_ARTIFACTS[args.phase]
    )
    status = "PASSED" if (
        completed.returncode == 0 and not fake_markers and not missing
        and not placeholders and not forbidden and required_changed
    ) else "FAILED"
    result = {
        "status": status,
        "phase": args.phase,
        "exit_code": completed.returncode,
        "fake_tool_markers": fake_markers,
        "missing_artifacts": missing,
        "placeholder_artifacts": placeholders,
        "changed_paths": changed,
        "forbidden_writes": forbidden,
        "required_artifact_changed": required_changed,
        "transcript": str(transcript_path),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if status == "PASSED" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spec-master-opencode-runner")
    parser.add_argument("--project", required=True)
    parser.add_argument("--phase", required=True, choices=tuple(PHASE_ARTIFACTS))
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--model", default="ollama-neon/qwen3-coder-agent:30b")
    parser.add_argument("--agent", default="spec-phase")
    parser.add_argument("--timeout", type=int, default=1800)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        return run(build_parser().parse_args(argv))
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "FAILED", "reason": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
