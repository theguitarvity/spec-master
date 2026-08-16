Skeleton for the dynamically-built `/speckit.tasks` prompt per feature (CLAUDE.md §23).

---

/speckit.tasks

Gere as tasks de implementação da feature "{{feature_name}}" a partir do plano
técnico (specs/{{feature_dir}}/plan.md).

Cada task deve ser pequena, executável, ordenada, rastreável e verificável.

Todo acceptance criterion de app-features.md relativo a esta feature DEVE ter
ao menos uma task correspondente (verifique com a matriz de rastreabilidade).

Inclua obrigatoriamente tasks para:
- implementation
- unit tests
- integration/component tests quando requeridos pelo plano
- quality gates ({{quality_gate_commands}})
- regression validation
- documentation quando requerida pelas fontes
- cleanup/review

Se o projeto possuir regras verificáveis detectadas na constitution/tech-stack
(ex.: no console.log, no commented code, coverage >= X, lint zero-warning,
architecture tests), cada uma delas deve aparecer como task verificável:

{{verifiable_project_rules}}
