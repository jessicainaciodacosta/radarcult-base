# Tarefa 001 — Reconciliar a árvore do opencode com a base (repositório)

Branch: `tarefa/001-reconciliar`   |   Responsável: opencode   |   Revisão: Claude

## Contexto
Existem duas árvores: a **base** (este repositório, `main`, 57 testes passam sem snapshots e 78 com)
e a árvore local do opencode (29 testes relatados, coletor próprio com `page.request`).
A base é a referência. Nada da árvore antiga entra na `main` sem passar pelos testes da base.

## Objetivo
Descobrir o que a árvore do opencode tem de diferente e trazer só o que for útil, em branches
separados, sem quebrar nenhum teste da base.

## Passos
1. Clonar este repositório num diretório NOVO. Não mexer na árvore antiga.
2. Rodar `python -m pytest -v` na base e guardar a saída em `saidas/pytest-base.txt`.
3. Copiar `tests/test_migracoes.py` e `tests/test_parse_casos_borda.py` para a árvore antiga
   (cópia, sem editar) e rodar. Registrar quais falham e por quê, em `docs/decisoes.md`.
4. Gerar a lista de diferenças: arquivos só existentes na árvore antiga, e arquivos com conteúdo
   diferente (`diff -rq`, ignorando `venv`, `.git`, `__pycache__`, `*.db`, `saidas`).
5. Para cada diferença que valha a pena trazer, abrir um branch próprio `tarefa/001-<assunto>`,
   com teste de aceitação antes do código.

## Fora de escopo
- Reescrever `radarcult/coletor/transferegov.py`, `radarcult/coletor/parse.py` ou `radarcult/database.py`.
- Criar `iniciar.bat` ou qualquer coisa de bot/Telegram (é a spec-004).
- Editar migrações existentes ou `expected.json`.
- Trazer o coletor antigo (`page.request`): o coletor do projeto é o da base. Se achar que o antigo
  tem algo melhor, descreva em `docs/decisoes.md` e espere decisão.

## Critérios de aceite
- [ ] `python -m pytest -v` na `main` continua com 57 passando e 2 pulados (78 com snapshots).
- [ ] `docs/decisoes.md` lista: testes de comportamento que falharam na árvore antiga, arquivos
      exclusivos dela e o que foi trazido ou descartado, com motivo.
- [ ] Nenhum arquivo de `migrations/` alterado.
- [ ] Relatório no formato do `AGENTS.md` (pytest -v completo e `git diff --stat main`).
