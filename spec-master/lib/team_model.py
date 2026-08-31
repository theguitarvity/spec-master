"""Team Mode planning primitives for Spec Master.

This module keeps multi-agent coordination structural and deterministic. The
calling agent still performs semantic work, but these helpers define stable
roles, guided-intake questions, workstream planning, and peer-review
assignment rules that every adapter can rely on.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


AGENT_ROLES = [
    {
        "id": "po",
        "name": "Product Owner Agent",
        "lane": "product",
        "responsibilities": [
            "shape product value, scope, MVP, and prioritization",
            "turn unresolved business ambiguity into batched user decisions",
            "protect acceptance criteria from unsupported assumptions",
        ],
        "gates": ["value_clear", "scope_prioritized", "acceptance_criteria_traceable"],
    },
    {
        "id": "scrum-master",
        "name": "Scrum Master Agent",
        "lane": "delivery",
        "responsibilities": [
            "surface blockers, sequencing risks, and cross-squad dependencies",
            "identify safe parallel work that can start before implementation",
            "keep progress visible without changing technical decisions",
        ],
        "gates": ["blockers_declared", "dependencies_visible"],
    },
    {
        "id": "architect",
        "name": "Architect Agent",
        "lane": "technical-direction",
        "responsibilities": [
            "own system boundaries, integrations, and architectural trade-offs",
            "flag destructive or constitution-impacting architecture changes",
            "hand executable constraints to the tech lead",
        ],
        "gates": ["architecture_consistent", "integration_risks_classified"],
    },
    {
        "id": "tech-lead",
        "name": "Tech Lead Agent",
        "lane": "technical-execution",
        "responsibilities": [
            "break planned features into executable technical work packages",
            "assign work to backend, frontend, or fullstack dev agents",
            "resolve implementation conflicts and shared-code ownership",
            "approve integration after peer review and QA feedback",
        ],
        "gates": ["work_packages_owned", "conflicts_resolved", "integration_ready"],
    },
    {
        "id": "ui-ux-brand",
        "name": "UI/UX and Brand Agent",
        "lane": "experience",
        "responsibilities": [
            "define UX flows, screen map, interaction model, and accessibility criteria",
            "create brand direction, tone, palette, typography, and visual system",
            "guide frontend implementation without requiring external design tools",
        ],
        "gates": ["ux_flow_clear", "brand_direction_defined", "accessibility_considered"],
    },
    {
        "id": "backend-dev",
        "name": "Backend Dev Agent",
        "lane": "implementation",
        "responsibilities": [
            "implement APIs, persistence, business rules, integrations, and backend tests",
            "change only the assigned backend work package unless tech lead expands scope",
        ],
        "gates": ["backend_tests_defined", "contracts_respected"],
    },
    {
        "id": "frontend-dev",
        "name": "Frontend Dev Agent",
        "lane": "implementation",
        "responsibilities": [
            "implement screens, components, forms, client state, accessibility, and UI tests",
            "follow the UI/UX and Brand Agent's design-system artifacts",
        ],
        "gates": ["responsive_ui", "accessibility_checks", "design_system_followed"],
    },
    {
        "id": "fullstack-dev",
        "name": "Fullstack Dev Agent",
        "lane": "implementation",
        "responsibilities": [
            "implement thin vertical slices and resolve front/back integration gaps",
            "own end-to-end behavior when a package crosses implementation layers",
        ],
        "gates": ["e2e_flow_integrated", "cross_layer_contracts_respected"],
    },
    {
        "id": "qa",
        "name": "QA Agent",
        "lane": "quality",
        "responsibilities": [
            "derive test scenarios from acceptance criteria and risk",
            "validate implementation behavior and regression coverage",
            "block completion when criteria cannot be verified",
        ],
        "gates": ["test_scenarios_traceable", "blocking_regressions_absent"],
    },
    {
        "id": "devops",
        "name": "DevOps Agent",
        "lane": "operations",
        "responsibilities": [
            "evaluate CI/CD, deploy strategy, rollback, observability, and runtime config",
            "surface pipeline work that must happen before or alongside implementation",
        ],
        "gates": ["pipeline_ready", "rollback_defined", "observability_considered"],
    },
    {
        "id": "infra",
        "name": "Infrastructure Agent",
        "lane": "operations",
        "responsibilities": [
            "map infrastructure, provisioning, environments, secrets, and cost-sensitive resources",
            "identify setup tasks that unblock development and validation",
        ],
        "gates": ["environments_defined", "secrets_mapped", "provisioning_plan_clear"],
    },
    {
        "id": "security",
        "name": "Security Agent",
        "lane": "risk",
        "responsibilities": [
            "review auth, authorization, data sensitivity, threat model, and compliance risks",
            "block or escalate critical security ambiguity before implementation completes",
        ],
        "gates": ["sensitive_data_classified", "authz_risks_reviewed", "critical_risks_handled"],
    },
]


GUIDED_INTAKE_QUESTIONS = [
    {
        "id": "project_type",
        "question": "Que tipo de projeto voce quer criar?",
        "options": [
            "SaaS / sistema web",
            "App mobile",
            "API/backend",
            "Site institucional",
            "Ferramenta interna",
            "Produto com IA",
            "Outro / resposta livre",
        ],
        "owner_agent": "po",
        "required": True,
    },
    {
        "id": "target_user",
        "question": "Quem e o usuario principal ou cliente desse produto?",
        "options": [
            "Consumidor final",
            "Equipe interna",
            "Empresas / B2B",
            "Desenvolvedores",
            "Educacao / pesquisa",
            "Outro / resposta livre",
        ],
        "owner_agent": "po",
        "required": True,
    },
    {
        "id": "mvp_shape",
        "question": "Qual formato de MVP faz mais sentido agora?",
        "options": [
            "Fluxo principal completo",
            "Protótipo navegavel",
            "API funcional",
            "Automacao interna",
            "Landing page validavel",
            "Outro / resposta livre",
        ],
        "owner_agent": "po",
        "required": True,
    },
    {
        "id": "experience_direction",
        "question": "Qual direcao de experiencia e marca combina melhor?",
        "options": [
            "Profissional e confiavel",
            "Moderno e premium",
            "Divertido e acessivel",
            "Tecnico e minimalista",
            "Editorial / conteudo",
            "Outro / resposta livre",
        ],
        "owner_agent": "ui-ux-brand",
        "required": True,
    },
    {
        "id": "technical_preference",
        "question": "Existe stack ou restricao tecnica preferida?",
        "options": [
            "Usar stack existente do repositorio",
            "Web moderna fullstack",
            "Backend primeiro",
            "Frontend primeiro",
            "Sem preferencia",
            "Outro / resposta livre",
        ],
        "owner_agent": "architect",
        "required": False,
    },
    {
        "id": "delivery_strategy",
        "question": "Como voce quer organizar a entrega?",
        "options": [
            "Git Flow / feature branches",
            "Trunk-Based Development",
        ],
        "owner_agent": "scrum-master",
        "required": True,
    },
]


IMPLEMENTATION_AGENTS = ("backend-dev", "frontend-dev", "fullstack-dev")


@dataclass(frozen=True)
class WorkPackage:
    id: str
    feature_id: str
    title: str
    owner_agent: str
    depends_on: list[str]
    source_task: str | None = None
    reviewer_agent: str | None = None


def roles() -> list[dict]:
    """Return the canonical Team Mode roles."""
    return [dict(role) for role in AGENT_ROLES]


def guided_intake() -> dict:
    """Return the guided intake definition used when no context file exists."""
    return {
        "mode": "guided-intake",
        "output_context": ".spec-master/context.generated.md",
        "questions": [dict(question) for question in GUIDED_INTAKE_QUESTIONS],
    }


def adoption_plan() -> dict:
    """Return the migration checklist for projects already using Spec Master."""
    return {
        "mode": "team-adoption",
        "goal": "adapt an existing Spec Master workflow to Team Mode without restarting it",
        "inputs": [
            ".spec-master/state.json",
            ".spec-master/context/*.md",
            ".spec-master/reports/*.md",
            ".specify/memory/constitution.md",
            "specs/*/{spec,plan,tasks}.md",
        ],
        "outputs": [
            ".spec-master/team/roles.json",
            ".spec-master/workstreams.json",
            ".spec-master/team/adoption-report.md",
        ],
        "steps": [
            {
                "id": "inspect-current-state",
                "owner_agent": "spec-master",
                "action": "load the current state and identify completed, running, blocked, and pending phases",
                "mutation": "read-only",
            },
            {
                "id": "preserve-existing-decisions",
                "owner_agent": "po",
                "action": "mark existing context, acceptance criteria, git strategy, and constitution as authoritative unless the user changes them",
                "mutation": "read-only",
            },
            {
                "id": "map-team-roles",
                "owner_agent": "scrum-master",
                "action": "attach Team Mode roles to the current workflow and identify missing role-specific gates",
                "mutation": "additive",
            },
            {
                "id": "derive-workstreams",
                "owner_agent": "tech-lead",
                "action": "convert existing feature tasks into owned packages with peer reviewers and dependencies",
                "mutation": "additive",
            },
            {
                "id": "fill-experience-gap",
                "owner_agent": "ui-ux-brand",
                "action": "create UI/UX and brand artifacts only if the current project has a user-facing surface or unresolved brand direction",
                "mutation": "additive",
            },
            {
                "id": "review-operational-gaps",
                "owner_agent": "devops",
                "action": "map CI/CD, deploy, rollback, infra, secrets, and observability gaps without blocking completed phases retroactively",
                "mutation": "additive",
            },
            {
                "id": "resume-from-current-phase",
                "owner_agent": "spec-master",
                "action": "continue from the first incomplete phase; never restart solely because Team Mode was adopted",
                "mutation": "state-preserving",
            },
        ],
        "rules": [
            "adoption is additive and state-preserving by default",
            "completed Spec Kit phases stay completed unless fingerprint comparison marks a concrete artifact stale",
            "existing constitution principles are not rewritten without explicit user approval",
            "new Team Mode gates apply forward; they do not fail historical work unless they reveal an active blocker",
            "workstreams may split pending work, but cannot bypass specify, clarify, plan, tasks, analyze, implement, or validate",
        ],
    }


def _slug(value: str) -> str:
    chars: list[str] = []
    prev_dash = False
    for ch in value.lower():
        if ch.isalnum():
            chars.append(ch)
            prev_dash = False
        elif not prev_dash:
            chars.append("-")
            prev_dash = True
    return "".join(chars).strip("-") or "work"


def _infer_owner(text: str) -> str:
    lowered = text.lower()
    backend_terms = (
        "api",
        "backend",
        "server",
        "database",
        "db",
        "auth",
        "endpoint",
        "queue",
        "job",
        "integration",
    )
    frontend_terms = (
        "ui",
        "ux",
        "screen",
        "page",
        "component",
        "frontend",
        "form",
        "layout",
        "brand",
        "visual",
    )
    has_backend = any(term in lowered for term in backend_terms)
    has_frontend = any(term in lowered for term in frontend_terms)
    if has_backend and has_frontend:
        return "fullstack-dev"
    if has_backend:
        return "backend-dev"
    if has_frontend:
        return "frontend-dev"
    return "fullstack-dev"


def assign_peer_review(owner_agent: str) -> str:
    """Return a different dev agent to review the package owner's work."""
    if owner_agent == "backend-dev":
        return "fullstack-dev"
    if owner_agent == "frontend-dev":
        return "fullstack-dev"
    if owner_agent == "fullstack-dev":
        return "backend-dev"
    if owner_agent in IMPLEMENTATION_AGENTS:
        raise ValueError(f"unknown implementation owner: {owner_agent}")
    return "tech-lead"


def build_workstreams(features: list[dict]) -> dict:
    """Build deterministic work packages and parallel lanes from feature tasks.

    Each feature may provide `tasks` as strings or dictionaries with `id`,
    `title`, `owner_agent`, and `depends_on`. Missing owner/reviewer data is
    inferred conservatively, with the tech lead retaining integration control.
    """
    packages: list[WorkPackage] = []
    lanes: dict[str, list[str]] = defaultdict(list)

    for feature in features:
        feature_id = feature["id"]
        raw_tasks = feature.get("tasks") or [feature.get("name") or feature_id]
        previous_package_id: str | None = None
        for index, raw_task in enumerate(raw_tasks, start=1):
            if isinstance(raw_task, str):
                task_id = f"{feature_id}-{index:02d}-{_slug(raw_task)[:32]}"
                title = raw_task
                owner = _infer_owner(raw_task)
                depends_on = [previous_package_id] if previous_package_id else []
            else:
                title = raw_task.get("title") or raw_task.get("name") or raw_task["id"]
                task_id = raw_task.get("id") or f"{feature_id}-{index:02d}-{_slug(title)[:32]}"
                owner = raw_task.get("owner_agent") or _infer_owner(title)
                depends_on = list(raw_task.get("depends_on", []))
                if not depends_on and previous_package_id:
                    depends_on = [previous_package_id]

            reviewer = assign_peer_review(owner)
            package = WorkPackage(
                id=task_id,
                feature_id=feature_id,
                title=title,
                owner_agent=owner,
                depends_on=[dep for dep in depends_on if dep],
                source_task=title,
                reviewer_agent=reviewer,
            )
            packages.append(package)
            lanes[owner].append(package.id)
            previous_package_id = package.id

    return {
        "mode": "team",
        "orchestrator": "spec-master",
        "technical_owner": "tech-lead",
        "packages": [
            {
                "id": package.id,
                "feature_id": package.feature_id,
                "title": package.title,
                "owner_agent": package.owner_agent,
                "reviewer_agent": package.reviewer_agent,
                "depends_on": package.depends_on,
                "source_task": package.source_task,
            }
            for package in packages
        ],
        "lanes": dict(sorted(lanes.items())),
        "conflict_policy": {
            "owner": "tech-lead",
            "rules": [
                "one package owns each file family unless the tech lead explicitly splits it",
                "shared contracts are changed before consumers",
                "parallel dev agents cannot edit the same file without tech lead arbitration",
                "no implementation package is complete until a different dev agent reviews it",
                "the tech lead approves integration after peer review, QA, and blocking gates",
            ],
        },
    }
