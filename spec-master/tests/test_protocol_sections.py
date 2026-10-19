"""P2: PROTOCOL.md sections on demand, and the full-cycle router."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import _pathfix  # noqa: F401
import cli
import protocol_sections as ps

REPO = Path(__file__).resolve().parents[2]
DOC = """# Title

intro

## 1. First

body one

```
# not a heading
```

### Step 6 — Per-feature workflow

step six body

#### Sub A

sub a body

#### Sub B

sub b body

## 2. Second

body two
"""


class ParseTests(unittest.TestCase):
    def test_headings_levels_and_sizes(self):
        sections = ps.parse(DOC)
        self.assertEqual([s.title for s in sections],
                         ["Title", "1. First", "Step 6 — Per-feature workflow", "Sub A", "Sub B", "2. Second"])
        self.assertEqual([s.level for s in sections], [1, 2, 3, 4, 4, 2])
        self.assertTrue(all(s.bytes > 0 for s in sections))

    def test_fenced_hash_is_not_a_heading(self):
        self.assertNotIn("not a heading", [s.title for s in ps.parse(DOC)])

    def test_own_body_stops_at_next_heading_tree_includes_children(self):
        sections = ps.parse(DOC)
        step = ps.find(sections, "Step 6")
        own = ps.render(DOC, step)
        tree = ps.render(DOC, step, tree=True)
        self.assertIn("step six body", own)
        self.assertNotIn("sub a body", own)
        self.assertIn("sub a body", tree)
        self.assertIn("sub b body", tree)
        self.assertNotIn("body two", tree)


class FindTests(unittest.TestCase):
    def test_exact_prefix_then_substring(self):
        sections = ps.parse(DOC)
        self.assertEqual(ps.find(sections, "sub a").title, "Sub A")
        self.assertEqual(ps.find(sections, "Step 6 — Per-feature workflow").level, 3)
        self.assertEqual(ps.find(sections, "per-feature").title, "Step 6 — Per-feature workflow")

    def test_unknown_lists_nothing_ambiguous_lists_candidates(self):
        sections = ps.parse(DOC)
        with self.assertRaises(ValueError) as ctx:
            ps.find(sections, "zzz")
        self.assertIn("no section", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            ps.find(sections, "sub")
        self.assertIn("Sub A", str(ctx.exception))
        self.assertIn("Sub B", str(ctx.exception))


class RealProtocolTests(unittest.TestCase):
    def setUp(self):
        self.text = (REPO / "spec-master" / "PROTOCOL.md").read_text(encoding="utf-8")
        self.sections = ps.parse(self.text)

    def test_every_step_is_addressable(self):
        for query in ("Step -1", "Step 0", "Step 1", "Step 2", "Step 3", "Step 4", "Step 5", "Step 6",
                      "Step 7", "Step 8"):
            self.assertIsNotNone(ps.find(self.sections, query), query)

    def test_router_is_small_and_names_every_step(self):
        router = (REPO / "spec-master" / "cards" / "full-cycle.md").read_bytes()
        self.assertLessEqual(len(router), 5120)
        text = router.decode("utf-8")
        for query in ("Step 0", "Step 6", "Step 7", "Step 8"):
            self.assertIn(f'protocol show --section "{query}', text)

    def test_every_router_section_query_resolves(self):
        import re
        text = (REPO / "spec-master" / "cards" / "full-cycle.md").read_text(encoding="utf-8")
        queries = re.findall(r'protocol show --section "([^"]+)"', text)
        self.assertGreater(len(queries), 8)
        for query in queries:
            ps.find(self.sections, query)

    def test_router_plus_largest_step_is_far_below_the_whole_protocol(self):
        router = (REPO / "spec-master" / "cards" / "full-cycle.md").stat().st_size
        biggest = max(len(ps.render(self.text, s, tree=False).encode("utf-8"))
                      for s in self.sections if s.title.startswith("Step"))
        self.assertLess(router + biggest, 0.4 * len(self.text.encode("utf-8")))

    def test_entrypoint_points_at_router_not_full_read(self):
        text = cli.entrypoint_text("full-cycle", "ctx.md")
        self.assertIn("cards/full-cycle.md", text)
        self.assertNotIn("in full", text)
        self.assertIn("card for the current step", text)
        self.assertLess(len(text.encode("utf-8")), 2600)


class CliTests(unittest.TestCase):
    def _run(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(list(argv))
        return code, buf.getvalue()

    def test_sections_lists_headings_with_bytes(self):
        code, out = self._run("protocol", "sections")
        self.assertEqual(code, 0)
        data = json.loads(out)
        titles = [s["title"] for s in data["sections"]]
        self.assertTrue(any(t.startswith("Step 6") for t in titles))
        self.assertTrue(all(s["bytes"] > 0 for s in data["sections"]))

    def test_show_prints_only_the_section(self):
        code, out = self._run("protocol", "show", "--section", "Step 7")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("### Step 7"))
        self.assertNotIn("### Step 8", out)

    def test_show_unknown_fails(self):
        code, out = self._run("protocol", "show", "--section", "nope-nope")
        self.assertEqual(code, 1)
        self.assertIn("error", json.loads(out))

    def test_custom_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.md")
            Path(path).write_text(DOC, encoding="utf-8")
            code, out = self._run("protocol", "show", "--section", "Sub B", "--file", path)
            self.assertEqual(code, 0)
            self.assertIn("sub b body", out)


if __name__ == "__main__":
    unittest.main()
