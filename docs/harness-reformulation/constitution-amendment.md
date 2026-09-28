# Proposta de emenda da constitution (não aplicada)

**Estado:** proposta, aguardando decisão explícita do usuário.
`.specify/memory/constitution.md` **não foi alterado**. O texto completo
proposto está em [`constitution-proposed.md`](constitution-proposed.md).

## Por que existe

A seção *Governança* da proposta ([`proposal.md`](proposal.md), §5.8) diz que
trocar o fluxo padrão exige emendar o Princípio VII e a seção *Development
Workflow*. Até essa decisão:

- os lanes Patch e Standard ficam opt-in (`/spec-master --lane ...`);
- o Spec Kit continua sendo o fluxo padrão para qualquer feature;
- a promoção por evidência já está implementada e **não depende da emenda**,
  porque só cumpre o Princípio IV, que já está em vigor.

## O que muda

| Trecho | Hoje | Proposto | Motivo |
|---|---|---|---|
| Princípio VII (corpo; o título fica) | O Spec Master nunca reimplementa um `speckit.*` e reaproveita as integrações do ecossistema | O Spec Master é dono do harness (triagem de lane, sequência de passos, evidência para fechar um passo, enforcement por hooks). O Spec Kit é o pack do lane Critical e o formato de troca, e nunca é reimplementado. Uma mudança só fecha sem artefatos do Spec Kit se a triagem determinística a pôs num lane mais leve (o agente nunca baixa um lane) e se ela passa pelas mesmas checagens de evidência (Princípio IV). O reaproveitamento das integrações continua obrigatório | Hoje, qualquer mudança sem Spec Kit viola o espírito do VII, mesmo um patch de 3 linhas |
| Princípio VIII (uma frase a mais) | O gate precisa ser detectado a partir da configuração do repositório alvo | Mais: um gate que o próprio repositório declara em `.spec-master/gates.json` conta como configuração dele | Deixa explícito que `gates.json` (já implementado) não é gate hardcoded |
| *Development Workflow* (uma frase a mais) | Fases `speckit.*` nunca são simuladas nem escritas à mão | Mais: uma mudança que a triagem põe num lane sem Spec Kit produz os artefatos desse lane (change note, spec-lite), e eles nunca são apresentados como saída de fase do Spec Kit | Separa "não rodar o Spec Kit por decisão da triagem" de "fingir que rodou" |
| Versão | 1.0.0 | 2.0.0 | A redefinição de um princípio é uma mudança MAJOR |

## Diff estrutural (`constitution diff`)

A *Governança* pede que qualquer emenda passe pelo mesmo diff estrutural que o
Spec Master usa:

```bash
python3 spec-master/lib/cli.py constitution diff \
  --existing .specify/memory/constitution.md \
  --proposed docs/harness-reformulation/constitution-proposed.md
```

Resultado (seções `UNCHANGED` omitidas):

| Seção | Classificação |
|---|---|
| VII. Reuse the Ecosystem Before Reimplementing It | `CONFLICT` |
| VIII. Auto-Detected Quality Gates, Never Hardcoded | `CONFLICT` |
| Development Workflow | `CONFLICT` |
| Governance | `CONFLICT` (só a linha de versão e data) |

Nenhum princípio é removido. Os quatro `CONFLICT`s tocam cláusulas com
`MUST`/`never`, então, pela própria *Governança*, a emenda só pode ser gravada
com **aprovação explícita do usuário**.

## O que a aprovação libera (e o que não libera)

- **Libera:** propor o lane Standard como padrão para features S/M na onda 2,
  **se** o baseline medido mostrar não-inferioridade e ≥50% menos tokens
  (proposta, §7, go/no-go da onda 2).
- **Não libera:** nada muda de padrão só pela emenda. A troca continua
  dependendo das medições. O Princípio VI continua valendo: o modo `native` e
  os testes dele seguem intactos.
- **Sem aprovação:** Patch e Standard continuam opt-in e o ganho vem das
  correções da onda 0, do enforcement por hooks e do Patch opt-in (proposta,
  §9, riscos).

## Como aplicar, se aprovada

1. Copiar `constitution-proposed.md` sobre `.specify/memory/constitution.md`,
   trocando `<date of approval>` pela data da aprovação.
2. Rodar de novo o `constitution diff` acima: o resultado esperado é
   `UNCHANGED` em todas as seções, contra o arquivo proposto.
3. Registrar a decisão (`team decisions` ou um ADR) com o link desta página.
