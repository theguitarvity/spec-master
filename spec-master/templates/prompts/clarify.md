Skeleton for the dynamically-built `/speckit.clarify` step per feature (CLAUDE.md §21).

---

/speckit.clarify

Analise a specification de "{{feature_name}}" em busca de ambiguidades que
impactem implementação ou critérios de aceite.

Para cada ambiguidade encontrada, classifique como:

- RESOLVABLE_FROM_CONTEXT   -> resolva usando {{normalized_context_files}} e registre a decisão
- RESOLVABLE_FROM_CODEBASE  -> resolva inspecionando o código existente e registre a decisão
- SAFE_DEFAULT              -> resolva com o default mais conservador e registre a decisão
- USER_DECISION_REQUIRED    -> NÃO resolva; acumule para uma única pergunta ao usuário

Resolva automaticamente as três primeiras categorias sem interromper o fluxo.

Se existir ao menos uma USER_DECISION_REQUIRED, agrupe TODAS em uma única
mensagem no formato:

  Encontrei N decisões que alteram comportamento ou arquitetura e não podem
  ser resolvidas pelas fontes:
  1. ...
  2. ...

Nunca pergunte uma de cada vez. Após a resposta do usuário, continue
automaticamente do ponto interrompido — não reinicie specify/clarify.
