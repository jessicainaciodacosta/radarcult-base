# CONTEXTO.md — RadarCult (handoff: sessões novas leem isto)

> Radar inteligente de editais (Cultura, Direitos Humanos, Assistência Social,
> Fomento) com filtro de elegibilidade, resumo dos 5 campos críticos via IA e
> alertas de prazo no Telegram. Origem: `RadarCult.txt` (esboço original).

## Onde estamos (leia primeiro)

- **Fase: spec-002 fase B — banco, parser e coletor prontos e testados OFFLINE; coletor ainda
  NÃO rodou no portal real.** Specs 000, 001 e 002 aprovadas (informado pelo dono). A spec-002
  aprovada ainda não está em `docs/specs/` (copiar para `docs/specs/spec-002-coletor-transferegov.md`).
- **78 testes passam** nesta árvore (banco, migrações, parser, casos de borda, coletor contra
  servidor simulado). O coletor foi testado só contra `tests/servidor_falso.py`: a rede do ambiente
  de desenvolvimento não alcança o Transferegov (spike-001 §1). Prova a lógica, não o portal.
- **Duas árvores em paralelo:** esta (referência) e a do `opencode` na máquina do dono. O opencode
  relatou 29 testes e um coletor próprio (`page.request`) — não vi esse código. O coletor de
  referência é `radarcult/coletor/transferegov.py` (robots, XSRF, interceptação, retry, 17 testes).
  **Reconciliar antes de seguir:** rodar `tests/test_migracoes.py` e `tests/test_parse_casos_borda.py`
  na árvore do opencode; são testes de comportamento e não dependem de quem implementou.
- Próximo marco: **primeiro ciclo real** na máquina do dono (checklist abaixo).

## Regra de migrações (aprendida na prática)

**Nunca editar uma migração já aplicada.** `aplicar_migracoes` pula versões ≤ à registrada em
`schema_version`; editar a 001 no lugar deixa bancos existentes com o schema antigo (o
`CHECK` rejeitaria `em_breve`). Mudança de schema = nova migração `NNN_*.sql`. O SQLite não altera
`CHECK` com `ALTER TABLE`: a 002 recria `editais` (PRAGMA foreign_keys OFF, copia, troca, recria
índice). `aplicar_migracoes` faz rollback e religa `foreign_keys` se uma migração falhar.
`tests/data/001_original.sql` é a 001 original, usada para simular bancos antigos.

## Regras do parser (`radarcult/coletor/parse.py`)

- **status_edital:** `recebimentoPropostaConcluido` → `encerrado`; senão `NaoIniciado` → `em_breve`;
  senão `recebendoProposta is True` → `aberto`; **senão ValueError** (nunca assume `aberto`; o item
  vira erro na coleta e nada é gravado). Significado dos campos inferido pelo nome. `cancelado`
  não é produzido: os valores de `situacao` para cancelamento nunca foram vistos.
- **Prazo:** usa uma janela completa (`Esp`, depois `Parlamentar`), nunca mistura início de uma com
  fim de outra; janela só com fim mantém o fim. Quando as duas estão completas vale a `Esp` —
  **hipótese não confirmada** (conferir no portal).
- `status_edital` entra no hash de conteúdo: aberto→encerrado agora é `atualizado`. Efeito único:
  no primeiro ciclo após esta mudança, editais já gravados serão marcados `atualizado` e
  `status_ia` volta a `pendente` (sem custo enquanto não houver IA).
- Aceita dict, str e bytes JSON; entrada inválida → ValueError. Listas toleram `null`.
- Todo campo de `CAMPOS_SAIDA` precisa estar no `expected.json` (o harness exige).

## Primeiro ciclo real (checklist)

```
playwright install chromium
python -m radarcult.coletor.transferegov --db radarcult.db --max-paginas 2 --pausa 2 --visivel
```
Hipóteses que só o portal real confirma:
1. a rota `/ep-atos-prep-web/consultar-programa/{id}` existe e dispara `GET .../programa/{id}`
   (resumo: `interceptados` × `via_fallback`; tudo em fallback = rota errada);
2. `listarComFiltro` aceita `pagesize`/`currentPage` (1-based) e devolve `recebendoProposta`;
3. o `robots.txt` do portal (o coletor aborta se proibir; resposta HTML de SPA é tratada como
   "sem robots" e avisada — conferir manualmente);
4. `ufsHabilitadas` não vazia: formato dos itens nunca visto;
5. o User-Agent honesto não é bloqueado (o dono informou que o UA de Chrome no código antigo
   era só cópia, não bloqueio real).
Saída: JSON no stdout; código 0 = completo, 1 = erros de item/listagem incompleta, 2 = abortado.

## Achados nos snapshots reais — situação

Resolvidos nesta árvore (com testes): status (1), datas de emenda parlamentar (2), `null` em
`unidade` (10), `status_edital` não chegava ao banco, 001 editada no lugar, entrada str/bytes.

Ainda abertos (decisão do dono ou dado que falta):
- **`atendidos` → proponente:** agora vem de `atendidos` ("Terceiro Setor"); semântica **não
  confirmada** e as categorias não mapeiam para `PF/PJ_SEM_FINS/MEI/COLETIVO` de `perfis.tipo_proponente`
  (falta tabela de equivalência).
- **`ufsHabilitadas`/`requisitos` vazios nos 3 snapshots:** vazio é ambíguo ("todas" × "nenhuma");
  o filtro por UF deve tratar `[]` como sem restrição até confirmar.
- **`orgao_emissor`:** usa `unidade.nome` ("Secretaria-Executiva"); `unidadeSuperior`
  ("Ministério da Saúde") é mais informativo — decidir.
- **`areasAtuacao` é ruído para "Cultura"** (o 181, de saúde, lista "Difusão Cultural").
- **Valor do programa:** nenhum campo de valor nos snapshots (pendência do spike §5).
- **Link de submissão:** o 173 tem `urlPropostaSistemaExterno`; o parser ignora (spec-000 §2).
- **Fixtures:** os 3 programas reais estão encerrados; `programa-182-v1` e `v2` são idênticos.
  Faltam fixtures reais de programa **aberto** e de **retificação**. `url_origem` usa padrão de
  URL não verificado.
- **Ciclo de vida:** o coletor só busca `recebendoProposta=true`; programas que fecham ou somem da
  listagem continuam `aberto` no banco. Falta marcar `encerrado`.
- `em_breve` e alertas: a spec-004 deve decidir se há alerta antes da abertura.

## Riscos abertos

- **Cobertura cultural da fonte 1:** spike viu ~2 de 131 programas abertos de Cultura (um dia,
  critério não documentado); os 3 snapshots são de saúde. Medir com a listagem real.
- **robots.txt e termos de uso do Transferegov:** não verificados.
- **Playwright × bot:** coletor usa `async_playwright` e roda como processo separado; agendar fora
  do bot (spec-004) e avisar o dono pelo Telegram quando o código de saída for ≠ 0.
- **Reagendar alertas:** alerta `cancelado` ocupa o `UNIQUE(edital_id, perfil_id, tipo_alerta)`; a
  spec-004 deve usar `INSERT ... ON CONFLICT DO UPDATE` (há teste).
- **Segredos:** chaves rotacionadas (informado pelo dono). Confirmar que as antigas foram revogadas.

## Decisões já tomadas (não refazer sem conversar)

- **Usuário do MVP = o próprio dono**, validando 4 semanas (spec-000 §3).
- **Escopo MVP enxuto:** 1 fonte + extração IA + bot Telegram do dono + alertas.
- **Reuso de padrões** do `producao_nova_visao_brasil`; stack Python + SQLite + Telegram + Gemini.
- Metodologias: **SDD**, **Harness** (fixtures reais + asserções), **HDD**.
- Prazo canônico = campo estruturado da fonte; IA só confere (spec-001 §3.2).
- Status `em_breve` (e não `agendado`/`cancelado`) para programa que ainda não abriu.
- Coletor: navega no portal (sessão/XSRF do navegador), lista via `fetch` na página, **intercepta**
  o JSON do detalhe; `fetch` é fallback contabilizado. 403/429, robots proibido, listagem vazia ou
  formato inesperado **abortam**; falha de item não derruba o ciclo.
- User-Agent honesto (spec-002).
- `.gitignore` ignora `fixtures/transferegov/*/snapshot.*` (privacidade); revisável.

## Estrutura do projeto

```
RadarCult/
├── CONTEXTO.md  RadarCult.txt  .gitignore  .env.example  pyproject.toml  pytest.ini
├── docs/specs/   spec-000, spec-001 (spec-002 aprovada: copiar)      docs/spike/spike-001-fontes.md
├── migrations/   001_initial_schema.sql (original, não editar)  002_status_em_breve.sql
├── radarcult/
│   ├── database.py              # connect, migrações, upsert_edital, hashes
│   └── coletor/
│       ├── parse.py             # parse_programa + processar_programa (regras acima)
│       └── transferegov.py      # coletor Playwright + CLI
├── fixtures/transferegov/       # programa-182-v1/v2, 181, 173 (+ _modelo); snapshot.* fora do git
└── tests/
    ├── test_database.py  test_migracoes.py  test_parse_casos_borda.py
    ├── test_parse_transferegov.py     # harness guiado por fixtures reais
    ├── test_coletor_transferegov.py   # contra servidor simulado (tests/servidor_falso.py)
    └── data/001_original.sql          # 001 original, para simular bancos antigos
```

## Como rodar os testes (Git Bash no Windows)

```
python -m venv venv && source venv/Scripts/activate
pip install -r pyproject.toml
playwright install chromium
pytest
```
Os testes que usam `snapshot.json` reais são pulados se os arquivos não estiverem em `fixtures/`.

## Próximos passos (ordem)

1. Reconciliar com a árvore do opencode (rodar os testes de comportamento nela).
2. Copiar a spec-002 aprovada para `docs/specs/`.
3. Primeiro ciclo real (checklist) e registrar `robots.txt`, `interceptados` × `via_fallback` e a
   contagem de programas por área (mede a cobertura cultural).
4. Decidir os itens abertos acima (proponente, UF vazia, órgão, link de submissão).
5. Capturar fixtures reais de programa **aberto** e de retificação.
6. Ciclo de vida (marcar `encerrado`).
7. `spec-003` (extração IA) → `spec-004` (bot/alertas; agendar o coletor; avisar falhas).

## Armadilhas do ambiente

- Shell é **bash (Git Bash)**: nunca `2>nul`; `grep` nativo quebra — usar `python -c "import re;..."`.
- Portais gov.br com timeout na sessão de dev (24/10/2026) — testar na máquina do dono.
- Gemini free instável (503/429/504) — retry faz parte do padrão a reusar. Se usar o gateway
  multi-provedor, registrar o modelo realmente usado (`extracoes_ia.modelo_ia`).
- SQLite: `PRAGMA foreign_keys = ON` em toda conexão (`database.connect` faz isso).
