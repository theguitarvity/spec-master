# Patch {change_id} — implement

Intent [EXPLICIT]: {intent}
Declared files: {envelope}

1. Implement in this session, touching only the declared files (tests are
   always allowed). Need another file? `python3 spec-master/lib/cli.py step
   widen --path . --paths <file>` — it re-triages, and the lane may go up.
2. Every acceptance check needs a test that covers it; write the test first
   when you can.
3. Write the change note `{note_path}` (about 1 KB, rules in `core.md`):

       Intent: <the request, verbatim> [EXPLICIT]
       - [EXPLICIT] <acceptance check from the request> (test: <test file>)
       - [DISCOVERED_FROM_CODEBASE] <fact> at `<file>:<line>` (test: <test file>)
       Files: <the files you changed>
{bugfix_block}
4. Run `python3 spec-master/lib/cli.py step end --path .`. Fix what it
   reports and run it again; the change is done only at `status: PASSED`.
