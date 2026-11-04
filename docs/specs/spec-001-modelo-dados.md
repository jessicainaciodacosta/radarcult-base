# SPEC-001 — Modelo de Dados (SQLite)

- **Status:** aprovada v0.2 (informado pelo dono em 01/11/2026) — mapeamento de campos da fonte ainda a confirmar com fixtures (§6)
- **Metodologia:** Spec-Driven Development (SDD).
- **Data:** 31/10/2026
- **Dependências:** `spec-000` (aprovada). Mapeamento de campos da fonte depende de
  fixtures reais (spec-002) — ver §6.
- **Texto canônico do schema:** `001_initial_schema.sql` (validado em SQLite em 31/10/2026).
  Esta spec explica as decisões; em caso de divergência, corrija os dois juntos.

## Mudanças em relação à v0.1

| # | Mudança | Motivo |
|---|---|---|
| 1 | `alertas.perfis_id` (FK sem coluna) → `alertas.perfil_id` real | A v0.1 declarava FK para coluna inexistente; erro no `CREATE TABLE`. |
| 2 | `INSERT OR IGNORE` → UPSERT com `hash_conteudo` | Prazo prorrogado/retificado não era atualizado; erro de prazo é falha crítica (spec-000 §7). |
| 3 | `hash_identificador` = SHA256(fonte + codigo_origem), sem a URL | A URL pode mudar; identidade deve ser estável. |
| 4 | Colunas estruturadas `ufs_elegiveis`, `proponentes_elegiveis`, `areas_atuacao` | Elegibilidade em texto livre não é filtrável em SQL. |
| 5 | Prazo canônico = `editais.data_fim_inscricao`; IA só como conferência (`prazo_divergente`) | Duas fontes da verdade para o prazo. |
| 6 | `validado_por_regra` em `extracoes_ia` | `confianca_score` auto-reportado por LLM é mal calibrado; checagem determinística é complementar. |
| 7 | `UNIQUE(edital_id, perfil_id, tipo_alerta)` + `prazo_referencia` + status `cancelado` | Evita alertas duplicados e permite reagendar quando o prazo muda. |
| 8 | Removido `novo_edital` de `tipo_alerta` | Fora do escopo do MVP (spec-000 §2/§4: só D-10/D-3/D-1). **Confirmar.** |
| 9 | Nova tabela `interacoes` | Spec-000 §3 exige "medir, não estimar"; faltava onde registrar. |
| 10 | `CHECK` nos enums, índices, `schema_version`, `dados_brutos_json`, mecanismo `PNAB`/`Outro` | Integridade, desempenho, migrações rastreáveis, base para fixtures. |

## 1. Objetivo

Definir o esquema SQLite do RadarCult MVP: `fontes`, `editais`, `extracoes_ia`, `perfis`,
`alertas`, `interacoes` e `schema_version` (7 tabelas; a spec-000 §9 listava 4 e deve ser atualizada).

## 2. Tabelas (resumo)

| Tabela | Papel |
|---|---|
| `schema_version` | Versão das migrações aplicadas. |
| `fontes` | Cadastro de fontes de coleta (MVP: Transferegov). |
| `editais` | Programa/edital coletado: identidade, prazo canônico, campos estruturados da fonte, JSON bruto, status. |
| `extracoes_ia` | Os 5 campos críticos + metadados de IA (modelo realmente usado, confiança, validação por regra, divergência de prazo). |
| `perfis` | Perfil do dono (tipo de proponente, UF, linguagens, faixa de valor). |
| `alertas` | Fila/histórico de alertas D-10/D-3/D-1, um por edital + perfil + marco. |
| `interacoes` | Consultas, aberturas de resumo, marcações relevante/descartado/inscrito, tempo de triagem. |

## 3. Regras de funcionamento

### 3.1 Coleta e deduplicação (UPSERT)
- Identidade: `hash_identificador = SHA256(fonte + codigo_origem)`.
- Conteúdo: `hash_conteudo = SHA256` dos campos relevantes (prazos, elegibilidade, texto).
- Ao recoletar: se o `hash_identificador` não existe → inserir. Se existe e `hash_conteudo` é igual → nada muda.
  Se existe e mudou → atualizar, `status_ia = 'pendente'` (reprocessar IA) e reagendar alertas (§3.3).
- Padrão SQL validado: `INSERT ... ON CONFLICT(hash_identificador) DO UPDATE ... WHERE editais.hash_conteudo IS NOT excluded.hash_conteudo`.

### 3.2 Prazo canônico
- Fonte da verdade do prazo: `editais.data_fim_inscricao` (campo estruturado da fonte).
- `extracoes_ia.prazo_final_formatado` é só conferência. Se divergir do canônico → `prazo_divergente = 1`
  e o bot exibe aviso "confira no edital oficial".
- Alertas leem apenas `editais.data_fim_inscricao`. Com `prazo_desconhecido = 1`, não se criam alertas.

### 3.3 Alertas
- D-N é calculado pela **data local** (America/Sao_Paulo) do prazo; envio às 09:00 locais
  (12:00 UTC, assumindo UTC-3 sem horário de verão — confirmar na spec-004), gravado em UTC.
- Edital descoberto depois da data do marco (ex.: faltam 8 dias) → o marco D-10 **não** é criado.
- Prazo alterado (`prazo_referencia` ≠ `data_fim_inscricao`) → alertas `pendente` viram `cancelado`
  e são recriados com o novo prazo.
- `UNIQUE(edital_id, perfil_id, tipo_alerta)` impede duplicidade.

### 3.4 Elegibilidade e filtro
- O filtro do perfil (UF, tipo de proponente, área) roda em SQL sobre `ufs_elegiveis`,
  `proponentes_elegiveis` e `areas_atuacao` (arrays JSON preenchidos a partir da fonte).
- `elegibilidade_resumo` (IA) é apenas texto para leitura humana.

### 3.5 Validação por regra (`validado_por_regra`)
Checagens determinísticas, resultado 1/0: prazo da IA = prazo canônico; valor extraído aparece
no texto-fonte; mecanismo está na lista permitida. Detalhar na spec-003.

### 3.6 Padrões do banco
- Toda conexão executa `PRAGMA foreign_keys = ON;` (sem isso `ON DELETE CASCADE` não funciona).
- Datas/horas em UTC `YYYY-MM-DD HH:MM:SS`; prazos (`DATE`) em data local.
- Migrações aditivas numeradas (`001_...sql`, `002_...sql`), aplicadas na inicialização e registradas
  em `schema_version`. Definir em um único módulo (`database.py`) — a v0.1 citava também `scheduler.py`.
- `modelo_ia` registra o modelo **efetivamente usado**, pois o gateway multi-provedor pode alternar.

## 4. Critérios de aceite

- [ ] Schema aprovado pelo dono.
- [x] `001_initial_schema.sql` executa sem erro, é idempotente e passou nos testes de UNIQUE, CHECK, UPSERT e CASCADE (31/10/2026).
- [ ] Mapeamento da fonte → colunas confirmado contra fixture real (§6).
- [ ] Decisão sobre `novo_edital` registrada (removido no MVP).

## 5. Decisões em aberto

1. Manter `novo_edital` fora do MVP? (v0.2 assume que sim.)
2. Horário de envio dos alertas (v0.2 assume 09:00 locais).
3. Marco D-10 pulado quando o edital é descoberto tarde — aceitável, ou enviar um alerta único "faltam N dias"?

## 6. Dependência de fixtures (spec-002)

Os nomes de campos da fonte vêm do spike-001 (`dtaInicioRecebPropEsp`, `dtaFimRecebPropEsp`,
`ufsHabilitadas`, `publicosAlvos`, `areasAtuacao`). **O formato dos valores (lista, objeto, código)
não foi verificado em nenhum documento.** Antes de aprovar, capturar ao menos 1 JSON real de
`programa/{id}` e confirmar a conversão para as colunas `ufs_elegiveis`, `proponentes_elegiveis`
e `areas_atuacao`. O valor financiado também segue pendente (spike-001 §5), por isso
`valor_maximo_financiar` continua vindo da IA e anulável.
