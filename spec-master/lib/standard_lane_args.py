"""Argument parser for `cli.py standard` (Standard lane).

Kept apart from `standard_lane` so building the CLI parser does not import the
kernel, gates and discovery modules a simple command never uses (roadmap P6).
"""
from __future__ import annotations


def register(sub) -> None:
    parser = sub.add_parser("standard", help="Standard lane: begin, verify-pre, red, green (finish with `step end`)")
    parser.set_defaults(standard=True)
    actions = parser.add_subparsers(dest="standard_action", required=True)
    begin_p = actions.add_parser("begin", help="open a standard change (spec-lite + test-first)")
    begin_p.add_argument("--intent", required=True, help="the user's request, verbatim")
    begin_p.add_argument("--paths", default="", help="comma-separated files the change will touch")
    begin_p.add_argument("--test-command", dest="test_command", default=None)
    begin_p.add_argument("--spec-dir", dest="spec_dir", default=None)
    begin_p.add_argument("--confirm", action="append")
    begin_p.add_argument("--deny", action="append")
    begin_p.add_argument("--unresolved", type=int, default=0)
    pre_p = actions.add_parser("verify-pre", help="deterministic analyze: gate before implement")
    pre_p.add_argument("--spec-dir", dest="spec_dir", default=None, help="check a spec directory without a change")
    for name, text in (("red", "run the tests: they must fail"), ("green", "run the tests: they must pass")):
        run_p = actions.add_parser(name, help=text)
        run_p.add_argument("--test-command", dest="test_command", default=None)
    for action in actions.choices.values():
        action.add_argument("--path", default=".")
        action.add_argument("--change", default=None)
