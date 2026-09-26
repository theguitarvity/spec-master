import _pathfix  # noqa: F401

import os
import shutil
import tempfile
import unittest

import context_budget
import state as state_mod
import web_bundle


def _phases(**done):
    return {p: done.get(p, "PENDING") for p in state_mod.FEATURE_PHASES}


def _feature(fid="feat-a", spec_dir="specs/001-feat-a", **kw):
    feature = {
        "id": fid,
        "name": kw.pop("name", "Feature A"),
        "description": "Let users export their data.",
        "source_requirements": ["app-features.md#export"],
        "acceptance_criteria": ["Export produces a CSV", "Export is audited"],
        "dependencies": kw.pop("dependencies", []),
        "spec_directory": spec_dir,
        "status": "PENDING",
        "analyze_repair_cycles": 1,
        "phases": kw.pop("phases", _phases()),
    }
    feature.update(kw)
    return feature


def _write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class WebBundleTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.state = {
            "context": "docs/ctx.md",
            "features": [
                _feature(),
                _feature("feat-b", "specs/002-feat-b", name="Feature B", dependencies=["feat-a"]),
            ],
            "quality_gates": [{"name": "tests", "command": "pytest -q"}],
        }

    def tearDown(self):
        shutil.rmtree(self.root)

    def seed(self, *, context=True, constitution=True, spec=True, plan=True, tasks=True):
        if context:
            _write(self.root, ".spec-master/context/app-features.md", "# App Features\n\nEXPORT-FEATURE-DOC\n")
            _write(self.root, ".spec-master/context/tech-stack.md", "# Tech\n\nTECH-STACK-DOC\n")
            _write(self.root, ".spec-master/context/project-goals.md", "# Goals\n\nGOALS-DOC\n")
        if constitution:
            _write(self.root, ".specify/memory/constitution.md", "# Constitution\n\nCONSTITUTION-BODY\n")
        if spec:
            _write(self.root, "specs/001-feat-a/spec.md", "# Spec\n\nSPEC-BODY\n\n```python\nx = 1\n```\n")
        if plan:
            _write(self.root, "specs/001-feat-a/plan.md", "# Plan\n\nPLAN-BODY\n")
        if tasks:
            _write(self.root, "specs/001-feat-a/tasks.md", "# Tasks\n\n- [ ] T001 TASKS-BODY\n")

    def ids(self, entries):
        return [e["id"] for e in entries]


class CurrentPhaseTests(WebBundleTestCase):
    def test_first_pending_phase(self):
        self.assertEqual(web_bundle.current_phase(_feature()), "specify")
        self.assertEqual(web_bundle.current_phase(_feature(phases=_phases(specify="PASSED"))), "clarify")

    def test_skipped_counts_as_done(self):
        feature = _feature(phases=_phases(specify="PASSED", clarify="SKIPPED"))
        self.assertEqual(web_bundle.current_phase(feature), "plan")

    def test_running_failed_blocked_are_current(self):
        for status in ("RUNNING", "FAILED", "BLOCKED"):
            feature = _feature(phases=_phases(specify="PASSED", clarify=status))
            self.assertEqual(web_bundle.current_phase(feature), "clarify")

    def test_all_done_and_missing_phases(self):
        done = {p: "PASSED" for p in state_mod.FEATURE_PHASES}
        done["clarify"] = "SKIPPED"
        self.assertIsNone(web_bundle.current_phase(_feature(phases=done)))
        self.assertEqual(web_bundle.current_phase({"id": "x"}), "specify")


class BuildTests(WebBundleTestCase):
    def test_detects_phase_and_includes_rendered_prompt(self):
        self.seed()
        result = web_bundle.build(self.root, self.state, "feat-a")
        md = result["markdown"]
        self.assertEqual(result["phase"], "specify")
        self.assertEqual(result["feature"], "feat-a")
        self.assertEqual(result["outputs"], ["specs/001-feat-a/spec.md"])
        self.assertIn("/speckit.specify --files .spec-master/context/app-features.md,", md)
        self.assertIn('Crie a specification da feature "Feature A"', md)
        self.assertIn("Objetivo: Let users export their data.", md)
        self.assertIn("- Export produces a CSV", md)
        self.assertNotIn("<!--", md)
        self.assertNotIn("Skeleton for the dynamically-built", md)  # template meta header stripped
        self.assertEqual(result["included"][0]["kind"], "prompt")
        self.assertEqual(result["included"][0]["id"], "templates/prompts/specify.md")
        self.assertEqual(result["tokens"], context_budget.estimate_tokens(md))

    def test_chat_ui_instructions(self):
        self.seed()
        md = web_bundle.build(self.root, self.state, "feat-a")["markdown"]
        self.assertIn("Paste this **entire** file", md)
        self.assertIn("**NO tool access**", md)
        self.assertIn("the complete content of `specs/001-feat-a/spec.md`", md)
        self.assertIn("save at that path", md)
        self.assertIn("state transition --feature feat-a --phase specify --status PASSED", md)
        self.assertTrue(md.rstrip().endswith("_End of Spec Master web bundle (feat-a / specify)._"))

    def test_unresolved_placeholders_stay_visible(self):
        self.seed()
        result = web_bundle.build(self.root, self.state, "feat-a")
        self.assertEqual(result["unresolved_placeholders"], ["constraints", "non_goals"])
        md = result["markdown"]
        self.assertIn("{{constraints}}", md)
        self.assertIn("### Unresolved placeholders", md)
        self.assertIn("- `{{non_goals}}`:", md)

    def test_feature_fields_fill_placeholders(self):
        self.seed()
        self.state["features"][0]["constraints"] = ["No new dependencies"]
        self.state["features"][0]["non_goals"] = []
        result = web_bundle.build(self.root, self.state, "feat-a")
        self.assertEqual(result["unresolved_placeholders"], [])
        self.assertIn("- No new dependencies", result["markdown"])
        self.assertIn("(none recorded in state)", result["markdown"])

    def test_spec_directory_replaces_feature_dir_paths(self):
        self.seed()
        self.state["features"][0]["spec_directory"] = "work/feat-a"
        result = web_bundle.build(self.root, self.state, "feat-a", phase="tasks")
        self.assertIn("(work/feat-a/plan.md)", result["markdown"])
        self.assertEqual(result["outputs"], ["work/feat-a/tasks.md"])

    def test_plan_and_implement_placeholders(self):
        self.seed()
        tasks = web_bundle.build(self.root, self.state, "feat-a", phase="tasks")
        self.assertIn("quality gates (`pytest -q`)", tasks["markdown"])
        self.assertEqual(tasks["unresolved_placeholders"], ["verifiable_project_rules"])
        analyze = web_bundle.build(self.root, self.state, "feat-b", phase="analyze")
        self.assertIn(f"Ciclo atual:\n1 de {state_mod.MAX_ANALYZE_REPAIR_CYCLES}", analyze["markdown"])
        self.assertIn("respeita `feat-a`?", analyze["markdown"])

    def test_artifacts_selected_per_phase(self):
        self.seed()
        specify = self.ids(web_bundle.build(self.root, self.state, "feat-a", phase="specify")["included"])
        self.assertNotIn("specs/001-feat-a/plan.md", specify)
        self.assertEqual(specify[2:], [".spec-master/context/app-features.md", ".spec-master/context/project-goals.md",
                                       ".spec-master/context/tech-stack.md", ".specify/memory/constitution.md",
                                       "specs/001-feat-a/spec.md"])
        tasks = self.ids(web_bundle.build(self.root, self.state, "feat-a", phase="tasks")["included"])
        self.assertEqual(tasks[2:5], ["specs/001-feat-a/plan.md", "specs/001-feat-a/spec.md",
                                      ".specify/memory/constitution.md"])
        implement = self.ids(web_bundle.build(self.root, self.state, "feat-a", phase="implement")["included"])
        self.assertEqual(implement[2], "specs/001-feat-a/tasks.md")
        self.assertEqual(implement[3:5], ["specs/001-feat-a/plan.md", "specs/001-feat-a/spec.md"])

    def test_feature_record_and_context_are_embedded(self):
        self.seed()
        md = web_bundle.build(self.root, self.state, "feat-a", phase="plan")["markdown"]
        self.assertIn("## Feature record", md)
        self.assertIn("- **ID:** `feat-a`", md)
        self.assertIn("1. Export produces a CSV", md)
        self.assertIn("### `specs/001-feat-a/spec.md`", md)
        self.assertIn("````markdown\n# Spec\n\nSPEC-BODY\n\n```python", md)  # fence longer than content fences
        self.assertIn("CONSTITUTION-BODY", md)
        self.assertLess(md.index("## Phase prompt: plan"), md.index("## Feature record"))
        self.assertLess(md.index("## Feature record"), md.index("## Context"))
        self.assertLess(md.index("## Context"), md.index("## Not included"))

    def test_budget_trimming_lists_omitted(self):
        self.seed()
        _write(self.root, "specs/001-feat-a/plan.md", "# Plan\n\n" + ("PLAN " * 4000))
        full = web_bundle.build(self.root, self.state, "feat-a", phase="tasks")
        budget = full["core_tokens"] + 400
        result = web_bundle.build(self.root, self.state, "feat-a", phase="tasks", token_budget=budget)
        omitted = self.ids(result["omitted"])
        self.assertIn("specs/001-feat-a/plan.md", omitted)
        self.assertEqual(result["omitted"][0]["reason"], "token_budget")
        self.assertIn("specs/001-feat-a/spec.md", self.ids(result["included"]))  # smaller item still fits
        self.assertLessEqual(result["tokens"] - context_budget.estimate_tokens(
            result["markdown"][result["markdown"].index("## Not included"):]), budget)
        md = result["markdown"]
        tail = md[md.index("## Not included"):]
        self.assertIn("**Omitted to fit the token budget**", tail)
        self.assertIn("- `specs/001-feat-a/plan.md`", tail)
        self.assertNotIn("PLAN PLAN", md)
        self.assertFalse(result["over_budget"])

    def test_core_over_budget_omits_every_item(self):
        self.seed()
        result = web_bundle.build(self.root, self.state, "feat-a", phase="plan", token_budget=10)
        self.assertTrue(result["over_budget"])
        self.assertEqual([e["kind"] for e in result["included"]], ["prompt", "feature"])
        self.assertIn("_No context items fit the budget._", result["markdown"])
        self.assertIn("## Phase prompt: plan", result["markdown"])

    def test_missing_files_tolerated(self):
        result = web_bundle.build(self.root, self.state, "feat-a", phase="analyze")
        missing = self.ids(result["missing"])
        self.assertEqual(missing, ["specs/001-feat-a/spec.md", "specs/001-feat-a/plan.md",
                                   "specs/001-feat-a/tasks.md", ".specify/memory/constitution.md",
                                   ".spec-master/context/*.md"])
        self.assertNotIn("specs/001-feat-a/research.md", missing)  # optional docs are not "missing"
        tail = result["markdown"][result["markdown"].index("## Not included"):]
        self.assertIn("**Not found in the project**", tail)
        self.assertIn("- `specs/001-feat-a/tasks.md` (Prior artifact: tasks.md): not found", tail)
        self.assertEqual(result["unresolved_placeholders"], [])
        self.assertIn("{{", web_bundle.build(self.root, self.state, "feat-a")["markdown"])  # no context files

    def test_raw_context_used_when_no_normalized_docs(self):
        _write(self.root, "docs/ctx.md", "RAW-CONTEXT")
        result = web_bundle.build(self.root, self.state, "feat-a")
        self.assertIn("docs/ctx.md", self.ids(result["included"]))
        self.assertIn("RAW-CONTEXT", result["markdown"])

    def test_deterministic_with_optional_timestamp(self):
        self.seed()
        a = web_bundle.build(self.root, self.state, "feat-a", phase="plan")
        b = web_bundle.build(self.root, self.state, "feat-a", phase="plan")
        self.assertEqual(a, b)
        self.assertNotIn("Generated at", a["markdown"])
        stamped = web_bundle.build(self.root, self.state, "feat-a", phase="plan", generated_at="2026-09-26T00:00:00Z")
        self.assertIn("- **Generated at:** 2026-09-26T00:00:00Z", stamped["markdown"])

    def test_warnings_for_out_of_order_or_done_phase(self):
        self.seed()
        result = web_bundle.build(self.root, self.state, "feat-a", phase="plan")
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("`clarify` is PENDING", result["warnings"][0])
        self.state["features"][0]["phases"] = _phases(specify="PASSED", clarify="SKIPPED", plan="PASSED")
        result = web_bundle.build(self.root, self.state, "feat-a", phase="plan")
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("already PASSED", result["warnings"][0])

    def test_validate_phase_uses_builtin_prompt(self):
        self.seed()
        result = web_bundle.build(self.root, self.state, "feat-a", phase="validate")
        self.assertEqual(result["outputs"], [".spec-master/reports/traceability.md",
                                             ".spec-master/reports/quality-gates.md"])
        self.assertEqual(result["included"][0]["id"], "(built-in validate prompt)")
        self.assertIn("NOT RUN", result["markdown"])

    def test_clarify_and_analyze_allow_no_changes(self):
        self.seed()
        for phase in ("clarify", "analyze"):
            self.assertIn("NO_CHANGES_REQUIRED", web_bundle.build(self.root, self.state, "feat-a", phase=phase)[
                "markdown"])

    def test_constitution_phase_without_feature(self):
        self.seed()
        _write(self.root, "CLAUDE.md", "REPO-INSTRUCTIONS")
        result = web_bundle.build(self.root, self.state, None, phase="constitution")
        self.assertIsNone(result["feature"])
        self.assertEqual(result["outputs"], [".specify/memory/constitution.md"])
        self.assertIn("- `CLAUDE.md`", result["markdown"])  # {{sources}}
        self.assertIn("A constitution already exists", result["markdown"])
        self.assertIn("CLAUDE.md", self.ids(result["included"]))

    def test_errors(self):
        with self.assertRaises(state_mod.StateError):
            web_bundle.build(self.root, self.state, "nope")
        with self.assertRaises(ValueError):
            web_bundle.build(self.root, self.state, "feat-a", phase="deploy")
        with self.assertRaises(ValueError):
            web_bundle.build(self.root, self.state, None, phase="plan")
        with self.assertRaises(ValueError):
            web_bundle.build(self.root, self.state, None)
        self.state["features"][0]["phases"] = {p: "PASSED" for p in state_mod.FEATURE_PHASES}
        with self.assertRaises(ValueError):
            web_bundle.build(self.root, self.state, "feat-a")

    def test_custom_templates_dir(self):
        templates = os.path.join(self.root, "tpl")
        _write(templates, "plan.md", "header\n---\n/speckit.plan {{feature_name}} {{mystery}}\n")
        result = web_bundle.build(self.root, self.state, "feat-a", phase="plan", templates_dir=templates)
        self.assertIn("/speckit.plan Feature A {{mystery}}", result["markdown"])
        self.assertEqual(result["unresolved_placeholders"], ["mystery"])
        self.assertIn("- `{{mystery}}`: not available in project state", result["markdown"])


class WriteTests(WebBundleTestCase):
    def test_default_path_and_atomic_write(self):
        self.seed()
        result = web_bundle.build(self.root, self.state, "feat-a", phase="plan")
        path = web_bundle.write(self.root, result)
        self.assertEqual(path, os.path.join(self.root, ".spec-master", "bundles", "feat-a-plan.md"))
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), result["markdown"])
        self.assertEqual(os.listdir(os.path.dirname(path)), ["feat-a-plan.md"])

    def test_explicit_output_and_project_constitution_name(self):
        self.seed()
        out = os.path.join(self.root, "elsewhere", "b.md")
        result = web_bundle.build(self.root, self.state, "feat-a")
        self.assertEqual(web_bundle.write(self.root, result, out), out)
        self.assertTrue(os.path.isfile(out))
        constitution = web_bundle.build(self.root, self.state, None, phase="constitution")
        self.assertTrue(web_bundle.write(self.root, constitution).endswith(
            os.path.join("bundles", "project-constitution.md")))

    def test_feature_id_is_sanitized(self):
        self.assertTrue(web_bundle.default_output_path(self.root, "../x y", "plan").endswith(
            os.path.join(".spec-master", "bundles", "x-y-plan.md")))


if __name__ == "__main__":
    unittest.main()
