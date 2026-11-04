# AGENTS.md — regras de trabalho do RadarCult (leia antes de QUALQUER tarefa)

## Papéis

- **Dono (Jessica):** decide o produto, aprova specs e é a única com acesso de rede ao portal
  Transferegov (roda os ciclos reais).
- **Claude (diretor técnico e revisor):** escreve specs e testes de aceitação, revisa o que for
  entregue e não aceita "pronto" sem evidência.
- **opencode (implementação):** implementa o que a tarefa pede, só isso.

## Fonte da verdade

- O **repositório git** é a única fonte da verdade. Nada de cópias soltas de arquivos.
- Cada tarefa = um branch `tarefa/NNN-nome`, com commits pequenos. A `main` só recebe merge depois
  de `pytest` verde e revisão.
- As specs em `docs/specs/` mandam no código. Se o código precisar divergir da spec, **pare** e
  registre a dúvida em `docs/decisoes.md`; não decida sozinho.

## Regras de ouro

1. **Nada de "pronto / corrigido / funcionando" sem evidência.** Cole a saída completa de
   `python -m pytest -v` e de `git diff --stat main`. Se não rodou algo, escreva "não rodei".
2. **Nunca edite uma migração já aplicada** (`migrations/NNN_*.sql` existente). Mudou o schema →
   nova migração + teste que parte de um banco antigo.
3. **Não altere testes de aceitação nem `expected.json` para fazer um teste passar.** Se achar que o
   teste está errado, pare e explique. Os valores de `expected.json` são conferidos contra o JSON
   bruto do portal, nunca copiados da saída do parser.
4. **Respeite o escopo da tarefa:** mexa só nos arquivos listados nela. Não reescreva módulos que já
   existem e têm testes (ex.: `radarcult/coletor/transferegov.py`); proponha a mudança menor.
5. **Não invente dados do portal.** Campo, URL ou formato que não apareceu num snapshot real é
   desconhecido: levante erro ou registre; não use um padrão silencioso (ex.: assumir `aberto`).
6. **Sem segredos no repositório** (`.env`, chaves, tokens), nem em arquivos, nem em conversas.
7. Coleta responsável (spec-002): User-Agent honesto, respeitar o `robots.txt`, pausa entre
   requisições, parar em 403/429.

## Ciclo de uma tarefa

1. Ler `docs/tasks/NNN-*.md` (objetivo, escopo, testes de aceitação, fora de escopo).
2. Rodar os testes de aceitação: devem **falhar antes**. Anote quais.
3. Implementar o mínimo para passar e rodar a suíte inteira.
4. Entregar: branch + relatório no formato abaixo.
5. Esperar a revisão e corrigir os apontamentos no mesmo branch.

## Relatório de entrega (use este modelo)

```
Tarefa: NNN
Commits: <saída de git log --oneline main..HEAD>
Arquivos alterados: <saída de git diff --stat main>
Testes: <saída completa de pytest -v>
Não feito / dúvidas:
Decisões que tomei sem confirmar: <ideal: nenhuma>
```

## Comandos (Git Bash)

```
python -m pytest -v 2>&1 | tee saidas/pytest.txt     # evidência de testes
git status && git diff --stat main                    # evidência de mudanças
git bundle create saidas/repo.bundle --all            # levar o repositório inteiro ao revisor
```
`saidas/`, `.env`, `*.db` e `fixtures/transferegov/*/snapshot.*` ficam fora do git (ver `.gitignore`).
