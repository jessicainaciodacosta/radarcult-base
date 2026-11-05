# Tarefa 002 — Limpeza das specs

Branch: `tarefa/002-specs`   |   Responsável: Claude (redação) e Jessica (aprovação)

## Objetivo
Deixar `docs/specs/` coerente com o código da `main`.

## Itens
1. **spec-001 v0.3:** incluir o status `em_breve` e as 7 tabelas do schema atual
   (`migrations/001` + `002`); registrar que a 001 não pode ser editada.
2. **spec-002:** copiar a versão aprovada para `docs/specs/spec-002-coletor-transferegov.md`.
   Ela não está no repositório; **Jessica precisa fornecer o texto aprovado**.
3. **spec-000:** revisar os itens do §6 e §9 que ficaram desatualizados.
4. **spike-001:** atualizar o status (o que já foi confirmado, o que ainda depende do primeiro
   ciclo real).
5. **CONTEXTO.md:** ajustar "Onde estamos" depois dos itens acima.

## Critérios de aceite
- [ ] Cada divergência spec × código aparece na lista da tarefa ou em `docs/decisoes.md`.
- [ ] Nenhuma decisão de produto tomada sem a Jessica.
- [ ] `python -m pytest -q` inalterado (a tarefa só mexe em `docs/` e `CONTEXTO.md`).
