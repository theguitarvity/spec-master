Skeleton for the dynamically-built `/speckit.plan` prompt per feature (CLAUDE.md §22).

---

/speckit.plan

Gere o plano técnico da feature "{{feature_name}}".

Utilize:
- specification (specs/{{feature_dir}}/spec.md)
- clarifications resolvidas
- constitution (.specify/memory/constitution.md)
- tech-stack.md
- convenções detectadas no repositório ({{discovered_conventions}})

Para cada mudança proposta indique:
- componente afetado;
- responsabilidade;
- razão;
- testes necessários;
- riscos;
- requisito/critério de aceite atendido (referencie o Requirement ID).

Respeite a constitution e a arquitetura existente. Preserve backward
compatibility quando requerida pelas fontes. Defina estratégia de testes e
mecanismos de validação. Não introduza refatorações não necessárias ao
cumprimento da feature. Não amplie escopo além de {{feature_name}}.
