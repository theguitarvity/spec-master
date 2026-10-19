# Bug: a primeira página do catálogo pula produtos

Relatado pelo atendimento em 2026-09-29.

**O que acontece.** A listagem do catálogo começa na página 1, mas
`shop.catalog.page(produtos, 1)` devolve os itens da segunda página. Com 25
produtos e páginas de 10, a página 1 mostra os produtos 11 a 20, a página 3
volta vazia e os 10 primeiros produtos nunca aparecem.

**O que se espera.** A página 1 mostra os produtos 1 a 10, a página 2 os
produtos 11 a 20 e a página 3 os produtos 21 a 25. Uma página além do fim
continua vazia, e página 0 ou tamanho de página menor que 1 continuam
recusados.

**Critério de aceite.** A correção vem com um teste de regressão em `tests/`
que falha antes dela e passa depois, e a suíte continua verde:
`python3 -m unittest discover -s tests -t .`.
