# Baseline: casos

Os casos que o `baseline` do core compara (fluxo do Spec Master contra um
agente trabalhando direto), como pede a
[proposta](../../docs/harness-reformulation/proposal.md). Cada caso é um
repositório git separado, criado a partir de `fixtures/<caso>/`; os dois
braços partem do mesmo commit e só mudam no prompt.

| Caso | Tarefa | Aceite |
|---|---|---|
| `bugfix-xs` | a página 1 do catálogo devolve a página 2 (`BUG.md`) | a suíte passa, `page` se comporta como o `BUG.md` descreve e o teste novo falha quando o bug volta ([`checks/bugfix_xs.py`](checks/bugfix_xs.py), fora do repositório do caso) |

O que o fixture já traz, porque uma execução headless não tem a quem
perguntar: o Spec Kit v0.16.4 inicializado (`specify init --here
--integration claude`) e o `.spec-master/state.json` com a estratégia trunk
e o fingerprint do `BUG.md`, para o protocolo retomar em vez de perguntar.

## Como rodar

```bash
# 1. repositórios dos casos e cases.json, fora deste repositório (não chama modelo)
python3 evals/baseline/build.py --out /tmp/sm-baseline

# 2. o braço specmaster usa o /spec-master global (não gasta nada)
./init.sh --engine-only

# 3. a matriz e o gasto no pior caso (não executa nada)
python3 spec-master/lib/cli.py baseline plan --cases /tmp/sm-baseline/cases.json --runs 1 --max-budget-usd 5

# 4. só com o OK explícito de quem paga: gasta dinheiro de verdade
python3 spec-master/lib/cli.py baseline run --cases /tmp/sm-baseline/cases.json --runs 1 \
  --max-budget-usd 5 --out /tmp/sm-baseline/results --yes
python3 spec-master/lib/cli.py baseline summarize --out /tmp/sm-baseline/results
```

`test_baseline_cases` constrói o caso sem o Spec Kit e confere que só uma
correção com teste de regressão passa no aceite.
