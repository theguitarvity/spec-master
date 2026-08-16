Skeleton for the dynamically-built `/speckit.analyze` prompt per feature (CLAUDE.md §24-25).

---

/speckit.analyze

Valide a consistência de "{{feature_name}}" através da cadeia:

  Context -> Spec -> Plan -> Tasks

Verifique no mínimo:

- Coverage: todo acceptance criterion possui task correspondente?
- Scope: existem tasks sem requisito correspondente?
- Constitution: plano ou tasks violam algum princípio de
  .specify/memory/constitution.md?
- Architecture: há arquivos protegidos sendo modificados?
- Testing: cada comportamento possui validação correspondente?
- Non-goals: alguma task invade explicitamente um non-goal listado em
  app-features.md/project-goals.md?
- Dependencies: a ordem de execução respeita {{feature_dependencies}}?
- Contradictions: spec, plan e tasks divergem entre si?

Classifique cada achado por severidade (CRITICAL/HIGH/MEDIUM/LOW).

Se houver achados CRITICAL ou HIGH: NÃO prossiga para implement. Direcione o
reparo ao artefato responsável (spec issue -> specification, plan issue ->
plan, task issue -> tasks) e execute analyze novamente. Ciclo atual:
{{repair_cycle}} de {{max_repair_cycles}} (consulte
`state analyze-cycle --action check`). Ao esgotar o teto, marque a feature
como BLOCKED e reporte ao usuário — nunca mascare o problema apenas alterando
o relatório do analyze.

Achados MEDIUM podem avançar somente se não alterarem comportamento,
segurança, integridade, acceptance criteria ou arquitetura normativa —
registre essa decisão explicitamente no state.
