Skeleton for the dynamically-built `/speckit.implement` prompt per feature (CLAUDE.md §26-27).

---

/speckit.implement

Execute exclusivamente as tasks aprovadas de "{{feature_name}}"
(specs/{{feature_dir}}/tasks.md), aprovadas por um `/speckit.analyze` sem
achados CRITICAL/HIGH pendentes.

Respeite:
- specification (specs/{{feature_dir}}/spec.md)
- plan (specs/{{feature_dir}}/plan.md)
- constitution (.specify/memory/constitution.md)
- repository instructions (CLAUDE.md/AGENTS.md quando existirem)
- app-features.md
- tech-stack.md

Não expanda o escopo durante a implementação.

Quando descobrir que a realidade do código não corresponde ao plano (ex.:
componente planejado não existe, responsabilidade está em outra camada,
alteração exige quebrar um contrato público, dependência não documentada):
PARE a task correspondente, classifique como SPEC_DRIFT, e siga o ciclo:

  implementation -> spec drift -> reassess -> update plan/spec quando
  justificado -> tasks -> analyze -> resume implementation

Nunca improvise uma solução que contradiga spec/plan sem passar por esse
ciclo. Toda alteração de spec/plan feita durante SPEC_DRIFT precisa manter
rastreabilidade (grave a mudança e a razão em `.spec-master/logs/workflow.md`).
