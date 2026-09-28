# Spec Master — Team Mode

> Loaded only when Team Mode is active (see `PROTOCOL.md`, Step 6). It adds
> roles, playbooks, workstreams, peer review and escalation routing around the
> same phase spine; it never replaces a phase or its gates.

## Setup and roles

Before entering per-feature execution, initialize Team Mode when the user
asked for it explicitly, when guided intake created the context, or when an
existing project adopted Team Mode:

1. `python3 spec-master/lib/cli.py team roles` to load the canonical delivery
   roles. The Spec Master remains the orchestrator; the Tech Lead Agent owns
   technical decomposition, internal code conflicts, and integration
   approval.
2. Before instantiating any role for a package, review, or gate decision,
   load its binding playbook — never improvise a role's practices from
   general knowledge: `python3 spec-master/lib/cli.py knowledge get
   playbook.<role-id>` (resolve team_model.py ids like `po`, `infra`,
   `ui-ux-brand` to their knowledge-base ids `product-owner`,
   `infrastructure`, `ux` first — `knowledge for-role` does this
   resolution automatically). Pull additional budgeted context for the
   specific task with `knowledge route --role <role-id> --keywords
   "<feature/task keywords>" --tech-stacks "<detected stack>"`. Playbooks
   define each role's concrete must-do/must-avoid practices, testing
   conventions, stack/tooling defaults, and escalation triggers — see
   `spec-master/knowledge/playbooks/*.md` (or `playbook.spec-master` for
   the orchestrator's own escalation-routing rules).
3. During/after `tasks`, call `python3 spec-master/lib/cli.py team
   workstreams --file <features-with-tasks.json>` and write the result to
   `.spec-master/workstreams.json`.
4. The workstream plan may expose safe parallel work, but each package must
   still respect feature dependencies, Spec Kit phase gates, and analyze
   repair rules.
5. Dev agents implement only assigned packages, per their playbook:
   - Backend Dev Agent: APIs, persistence, business rules, backend tests,
     integrations (`playbook.backend-dev`).
   - Frontend Dev Agent: screens, components, forms, UI state,
     accessibility, responsive behavior, UI tests (`playbook.frontend-dev`).
   - Fullstack Dev Agent: thin vertical slices and front/back integration
     (`playbook.fullstack-dev`).
   When a dev agent finds an architecture inconsistency or a candidate
   design-pattern decision that crosses its package (see
   `design.gof-patterns`), it does not resolve this unilaterally — it
   escalates to the Architect Agent per its playbook's Escalation
   Triggers, which routes to the Tech Lead to create a scoped, owned
   remediation package (see `playbook.architect`, `playbook.tech-lead`).
   The Scrum Master Agent folds that new package into the visible plan and
   metrics (`playbook.scrum-master`).
6. Every implementation package requires peer review by a different dev
   agent (`reviewer_agent`) before QA validation. The reviewer cannot be the
   package owner, and checks conformance against the owner's playbook, not
   just correctness.
7. QA validates behavior against acceptance criteria using its own test
   pyramid rules (`playbook.qa`: unit owned by the dev agent, backend
   integration tests stub external systems with WireMock, frontend
   component/E2E tests use Cypress). The Tech Lead resolves code conflicts,
   shared-file ownership, contract ordering, and final integration
   readiness. Spec Master records the result and controls workflow status.
8. When discovery or the feature set implies more than one independently
   deployable service, the Architect Agent proposes containerization and
   Kubernetes/Helm; the DevOps and Infrastructure Agents own the concrete
   CI/CD pipeline (any of GitHub Actions, Jenkins, Azure DevOps, Spinnaker,
   Nexus — pick from evidence, not default) and Terraform provisioning
   (`playbook.devops`, `playbook.infrastructure`). Do not propose this
   tooling for a single deployable service.

## Escalations and decision memory

When a role hits one of its playbook's escalation triggers, don't route it by
hand: `team escalate --path . --kind <kind> --raised-by <role> [--feature
<id>] [--summary "..."]` returns the playbook route (`chain`, `decided_by`,
`package_owner`, `adr_candidate`); `team routes` lists every kind. Once the
deciding role has decided, record it:

```
team resolve --path . --kind <kind> --raised-by <role> --decision "<what was decided>"
  [--decided-by <role>] [--rationale "..."] [--feature <id>] [--title "..."]
  [--alternative "<rejected option>" ...] [--adr-trigger <trigger> ...]
```

This writes a `Decision` node to the knowledge graph (`DECIDED_BY` the
deciding agent, `INFLUENCES` the feature node when it exists) — re-recording
the same decision is idempotent. ADR triggers (`new_external_provider`,
`new_core_data_model`, `security_privacy_change`, `boundary_change`,
`infra_change`, `rejected_alternatives`; `systemic_violation` escalations add
one automatically) also write an ADR file into the repository's existing ADR
directory (`docs/adr`, `docs/decisions`, …), or `.spec-master/adr/` when the
repository has none. Before a role acts, load its past decisions together
with its playbook: `knowledge for-role --role <role> --path .` (adds a
`decisions` list), or `team decisions --path . --role <role> | --feature <id>`.
