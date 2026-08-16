Skeleton for the dynamically-built `/speckit.constitution` prompt (CLAUDE.md §15-16).
Fill every `{{placeholder}}` from the normalized context + repository instructions
before executing. Never invent a source not listed in `{{sources}}`.

---

/speckit.constitution

Construa ou atualize a constituição deste projeto utilizando como fontes normativas:

{{sources}}
<!-- e.g.: .spec-master/context/project-goals.md, app-features.md, tech-stack.md,
     CLAUDE.md, AGENTS.md, convenções detectadas no repositório -->

Transforme as regras arquiteturais, técnicas e de qualidade encontradas nessas
fontes em princípios normativos verificáveis.

Não introduza tecnologias, regras ou restrições não sustentadas pelas fontes.

Preserve regras existentes que continuem válidas.

{{existing_constitution_note}}
<!-- if a constitution already exists at .specify/memory/constitution.md, include the
     constitution_diff.py classification (UNCHANGED/ADDITION/MODIFICATION/CONFLICT/
     REMOVAL_CANDIDATE) here and instruct: apply ADDITION/MODIFICATION automatically,
     STOP and ask the user before applying any CONFLICT or REMOVAL_CANDIDATE. -->

Produza o Sync Impact Report conforme o formato utilizado pelo Spec Kit.

Classifique cada princípio novo como EXPLICIT, INFERRED, DISCOVERED_FROM_CODEBASE
ou UNRESOLVED, referenciando a fonte concreta.
