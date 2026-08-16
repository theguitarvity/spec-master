Skeleton for the dynamically-built `/speckit.specify` prompt per feature (CLAUDE.md §20).

---

/speckit.specify --files {{normalized_context_files}}

Crie a specification da feature "{{feature_name}}".

Objetivo: {{feature_objective}}

Utilize exclusivamente os requisitos associados a esta feature presentes nos
documentos fornecidos como fonte normativa. Requisitos de origem:

{{source_requirements}}

Critérios de aceite conhecidos (fonte: app-features.md):

{{acceptance_criteria}}

Constraints e regras arquiteturais aplicáveis (fonte: constitution.md, tech-stack.md):

{{constraints}}

Non-goals explícitos para esta feature:

{{non_goals}}

Dependências desta feature (já implementadas ou em andamento):

{{dependencies}}

Não invente critérios de aceite, arquivos, integrações ou comportamento não
sustentados pelas fontes. Toda inferência deve ser marcada como INFERRED,
DISCOVERED_FROM_CODEBASE ou UNRESOLVED — nunca silenciosamente promovida a
critério de aceite.

Mantenha rastreabilidade entre cada requisito e sua origem (grave em
`.spec-master/state.json` via `traceability add` para cada requisito coberto).
