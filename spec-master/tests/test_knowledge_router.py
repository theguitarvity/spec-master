import pytest
import _pathfix

from knowledge.manifest import KnowledgeManifest
from knowledge.router import KnowledgeRouter
from knowledge import profiles


def _write(tmp_path, filename, id_, roles, category="foundations", tags=None,
           depth=None, content="body text here"):
    tags = tags or []
    depth = depth or {}
    lines = ["---", f"id: {id_}", "type: Principle", f"category: {category}"]
    lines.append("applicable_roles:")
    for r in roles:
        lines.append(f"  - {r}")
    lines.append("tags:")
    for t in tags:
        lines.append(f"  - {t}")
    if depth:
        lines.append("depth:")
        for k, v in depth.items():
            lines.append(f"  {k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append(content)
    (tmp_path / filename).write_text("\n".join(lines))


@pytest.fixture
def router(tmp_path):
    _write(tmp_path, "a.md", "principle.a", ["architect", "backend-dev"],
           category="architecture", tags=["scaling"], depth={"architect": "L4"},
           content="all about scaling systems")
    _write(tmp_path, "b.md", "principle.b", ["backend-dev"],
           category="foundations", tags=["testing"], depth={"backend-dev": "L2"},
           content="all about testing code")
    _write(tmp_path, "c.md", "principle.c", ["architect"],
           category="security", tags=["auth"], depth={"architect": "L2"},
           content="all about authentication")
    manifest = KnowledgeManifest(knowledge_root=tmp_path)
    return KnowledgeRouter(manifest)


def test_for_role_filters_by_applicability(router):
    modules = router.for_role("architect")
    ids = {m.id for m in modules}
    assert ids == {"principle.a", "principle.c"}


def test_for_role_resolves_team_model_alias(router):
    # "infra" isn't a role used in the fixture, but the alias resolution
    # itself must not raise, and should route through "infrastructure".
    modules = router.for_role("infra")
    assert modules == []


def test_for_role_respects_limit(router):
    modules = router.for_role("architect", limit=1)
    assert len(modules) == 1


def test_for_role_ranks_higher_depth_first(router):
    # principle.a is L4 for architect, principle.c is L2 for architect.
    modules = router.for_role("architect")
    assert modules[0].id == "principle.a"


def test_for_query_filters_by_role_and_keyword(router):
    modules = router.for_query("backend-dev", "testing")
    ids = {m.id for m in modules}
    assert ids == {"principle.b"}


def test_for_query_excludes_role_inapplicable_matches(router):
    # "authentication" only appears in principle.c, which isn't applicable
    # to backend-dev.
    modules = router.for_query("backend-dev", "authentication")
    assert modules == []


def test_for_context_falls_back_to_role_modules_without_keywords(router):
    modules = router.for_context("architect")
    ids = {m.id for m in modules}
    assert ids == {"principle.a", "principle.c"}


def test_for_context_with_keywords_narrows_selection(router):
    modules = router.for_context("architect", keywords=["scaling"])
    ids = {m.id for m in modules}
    assert "principle.a" in ids


def test_for_context_respects_module_budget(router):
    modules = router.for_context("architect", limit=1)
    assert len(modules) == 1


def test_budget_summary_reports_selection(router):
    modules = router.for_role("architect")
    summary = router.budget_summary(modules)
    assert summary["count"] == 2
    assert set(summary["ids"]) == {"principle.a", "principle.c"}
    assert set(summary["categories"]) == {"architecture", "security"}
    assert summary["total_content_chars"] > 0


def test_router_default_manifest_uses_real_knowledge_base():
    # No knowledge_root passed anywhere in the chain — this exercises the
    # auto-discovery path (manifest._find_knowledge_root) end to end.
    router = KnowledgeRouter()
    modules = router.for_role("architect", limit=3)
    assert len(modules) <= 3
    for m in modules:
        assert m.is_applicable_to("architect")
