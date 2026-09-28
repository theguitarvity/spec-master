# Emenda da constitution 2.0.0 (aprovada e aplicada)

**Estado:** aprovada pelo usuário em 2026-09-28 e aplicada no mesmo dia em
[`.specify/memory/constitution.md`](../../.specify/memory/constitution.md),
que passou da versão 1.0.0 para a 2.0.0. Esta página é o registro da decisão.
O texto anterior continua no histórico do git
(`git show 90bba0d:.specify/memory/constitution.md`).

## Por que existe

A seção *Governança* da proposta ([`proposal.md`](proposal.md), §5.8) diz que
trocar o fluxo padrão exige emendar o Princípio VII e a seção *Development
Workflow*. Antes desta emenda, qualquer mudança feita sem o Spec Kit violava
o espírito do VII, mesmo um patch de 3 linhas. A promoção por evidência nunca
dependeu dela, porque só cumpre o Princípio IV.

## O que mudou

| Trecho | 1.0.0 | 2.0.0 | Motivo |
|---|---|---|---|
| Princípio VII (corpo; o título fica) | O Spec Master nunca reimplementa um `speckit.*` e reaproveita as integrações do ecossistema | O Spec Master é dono do harness (triagem de lane, sequência de passos, evidência para fechar um passo, enforcement por hooks). O Spec Kit é o pack do lane Critical e o formato de troca, e nunca é reimplementado. Uma mudança só fecha sem artefatos do Spec Kit se a triagem determinística a pôs num lane mais leve (o agente nunca baixa um lane) e se ela passa pelas mesmas checagens de evidência (Princípio IV). O reaproveitamento das integrações continua obrigatório | Um patch pequeno não precisa do ciclo completo |
| Princípio VIII (uma frase a mais) | O gate precisa ser detectado a partir da configuração do repositório alvo | Mais: um gate que o próprio repositório declara em `.spec-master/gates.json` conta como configuração dele | Deixa explícito que `gates.json` não é gate hardcoded |
| *Development Workflow* (uma frase a mais) | Fases `speckit.*` nunca são simuladas nem escritas à mão | Mais: uma mudança que a triagem põe num lane sem Spec Kit produz os artefatos desse lane (change note, spec-lite), e eles nunca são apresentados como saída de fase do Spec Kit | Separa "não rodar o Spec Kit por decisão da triagem" de "fingir que rodou" |
| Versão | 1.0.0 | 2.0.0 | A redefinição de um princípio é uma mudança MAJOR |

## Diff estrutural (`constitution diff`)

A *Governança* pede que toda emenda passe pelo mesmo diff estrutural que o
Spec Master usa. Da versão 1.0.0 para a 2.0.0:

```bash
git show 90bba0d:.specify/memory/constitution.md > /tmp/constitution-1.0.0.md
python3 spec-master/lib/cli.py constitution diff \
  --existing /tmp/constitution-1.0.0.md \
  --proposed .specify/memory/constitution.md
```

Resultado (seções `UNCHANGED` omitidas):

| Seção | Classificação |
|---|---|
| VII. Reuse the Ecosystem Before Reimplementing It | `CONFLICT` |
| VIII. Auto-Detected Quality Gates, Never Hardcoded | `CONFLICT` |
| Development Workflow | `CONFLICT` |
| Governance | `CONFLICT` (só a linha de versão e data) |

Nenhum princípio foi removido. Os quatro `CONFLICT`s tocam cláusulas com
`MUST`/`never`; por isso a emenda só foi gravada depois da aprovação
explícita do usuário, como a *Governança* exige. O arquivo gravado foi
conferido contra o texto aprovado: as 15 seções saíram `UNCHANGED`.

## O que a aprovação libera (e o que não libera)

- **Libera:** propor o lane Standard como padrão para features S/M na onda 2,
  **se** o baseline medido mostrar não-inferioridade e ≥50% menos tokens
  (proposta, §7, go/no-go da onda 2).
- **Não libera:** nada muda de padrão só pela emenda. Patch e Standard
  continuam opt-in (`/spec-master --lane ...`) até as medições. O
  Princípio VI continua valendo: o modo `native` e os testes dele seguem
  intactos.
