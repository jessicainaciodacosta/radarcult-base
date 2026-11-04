# SPIKE-001 — Escolha da 1ª fonte de editais (evidências)

- **Data:** 24/10/2026
- **Método:** testes reais de rede (curl na máquina do dono + navegador da sessão),
  sem suposição. Objetivo: decidir a fonte 1 do MVP com dado, não com gosto.
- **Status:** evidências coletadas → decisão pendente de aprovação (spec-000 §6.1)

---

## 1. Alegações de conexão (rede daqui)

| Alvo | Resultado | Tentativas |
|---|---|---|
| `www.gov.br` | ✅ 200 | 1/1 |
| `www.cultura.sp.gov.br` | ✅ 200 (redireciona p/ `/sec_cultura`) | 1/1 |
| `www.sescsp.org.br` | ✅ 200 | 1/1 |
| `agenciabrasil.ebc.com.br` | ✅ 200 | 1/1 |
| `www.transferegov.br` (domínio do esboço) | ❌ **NXDOMAIN — não existe mais** | DNS público (dns.google): status 3, apex e www |
| `dadosabertos.in.gov.br` | ❌ NXDOMAIN | DNS público: status 3 |
| `pesquisa.in.gov.br` | ❌ SERVFAIL no DoH | DNS público: status 2 |
| `www.in.gov.br` (DOU) | ⚠️ **instável**: 502, 301, 000, 000, 000, 200 (12s) | 6 tentativas intercaladas |
| Navegador da sessão (túnel OC2) | ❌ `ERR_TUNNEL_CONNECTION_FAILED` em `in.gov.br`/`transferegov.br` antigo; ✅ gov.br, cultura.sp, sesc | — |

**Conclusão 1:** DOU/Imprensa Nacional é inacessível na maioria das tentativas daqui —
não serve como base de coleta agendada hoje. (Pode ser instabilidade temporária; retestar.)

**Conclusão 2:** o esboço citava `transferegov.br`, mas a plataforma **migrou**:
`www.transferegov.br` não resolve mais. Endereços novos confirmados por busca e acesso:

- `https://portal.transferegov.sistema.gov.br/portal/home` (portal de entrada)
- `https://parcerias.transferegov.sistema.gov.br/ep-atos-prep-web/home` (app "Atos
  Preparatórios" — acesso livre, sem login: *"Você tem acesso a pesquisa de dados em
  todas as funcionalidades através do menu lateral"*)

## 2. Transferegov — prova de conceito da coleta (feito, funcionando)

Toda a cadeia foi executada com sucesso **da máquina do dono, via curl, sem navegador**:

1. **Bootstrap do token (sem login):**
   `GET /ep/api/seguranca/auth/configuration` → 200 + `Set-Cookie: XSRF-TOKEN=<uuid>`
2. **Lista de programas:**
   `POST /ep/api/atos-prep/programa/listarComFiltro`
   - header `X-XSRF-TOKEN: <cookie>` (obrigatório — sem ele, **400**)
   - body JSON `{"pagesize":10,"currentPage":1,"fields":"id,codigo,nome,ano,situacao,..."}`
   - **GET nesse mesmo endpoint devolve 400** (só POST funciona)
   - resposta: `{"entidades":[{"id":182,"codigo":202600077,"nome":"Pronas/PCD - ...",
     "ano":2026,"situacao":{...},"unidade":{...},"recebendoProposta":true}, ...]}`
3. **Detalhe do programa:**
   `GET /ep/api/atos-prep/programa/{id}` → 200, com os campos críticos:
   - **prazo:** `dtaInicioRecebPropEsp` (2026-10-05), `dtaFimRecebPropEsp` (2026-10-26),
     `prazoParaCaptacao` (345 dias), `recebendoProposta`
   - **elegibilidade:** `requisitos`, `ufsHabilitadas`, `publicosAlvos`,
     `beneficiariosEspecificos`, `temBeneficiarioEspontaneo`/`EmendaParlamentar`,
     `areasAtuacao`, `cnaes`, `tipoInstrumento`
   - **texto p/ IA:** `objetivo`, `problema`, `resultadoEsperado`, `normas`, `anexos`
   - **valor:** não apareceu neste programa (ver §5 pendências)

**Veredito Transferegov: VIÁVEL.** Coleta estruturada, com prazo e elegibilidade em
campo, sem login, sem HTML frágil, 2 chamadas por ciclo.

## 3. Portal estadual (Cultura SP) — verificado

- ✅ Acessível (200), HTML simples.
- ❌ Home **sem nenhum link contendo "edital"** — os editais não estão em página
  previsível; exigiria mapear o portal de verdade (CMS/Plone, provavelmente com busca).
- Cobertura: só SP.

## 4. Concorrência achada no caminho (pesquisa de mercado)

**`editaisdobrasil.com`** (GVO Soluções Digitais) — já faz **radar de verbas do
Transferegov** + licitações (PNCP) + concursos + "fomento e bolsas", com:

- filtros por quem pode propor (prefeituras/estados/OSC/consórcios), área, estado;
- prazo com contagem ("até 31/12/2026 · faltam 68 dias");
- **"Meu radar"** (o que entra no radar e o que você recebe), "Meus pedidos"
  (resumos, lembretes e avisos pedidos), "EditalAI" (perguntas sobre editais);
- login contas salvos — freemium aparente.

Fontes declaradas por eles: *"arquivo de dados abertos do Transferegov, **não
atualizado desde 17/07/2026**"* + *"API oficial, lida todo dia"* (fundo a fundo) +
PNCP + diários oficiais. Achado útil: existe consulta legada com acesso guest:
`discricionarias.transferegov.sistema.gov.br/voluntarias/...ConsultarPrograma.do&Usr=guest&Pwd=guest`.

**Leitura:** mercado existe e já é servido — porém (a) foco deles é licitação/verba
de repasse, (b) o diferencial do RadarCult (elegibilidade por perfil do produtor
cultural + leitura de editais culturais via IA) **não** é o produto deles, e
(c) dado aberto oficial está defasado → quem lê a API diariamente ganha.

## 5. Pendências do spike (para a spec-002)

- [ ] Confirmar de onde vem **valor** do programa (abas "Plano de Trabalho"/"Contas" —
      endpoints a capturar) e o link de submissão.
- [ ] Mapear como filtrar só **Cultura / Direitos Humanos / Assistência**:
      `areasAtuacao`/`tipoInstrumento`/`unidade` (hoje: 131 programas abertos, só ~2 de
      Cultura — a maior parte é convênio de infra/agro; edital cultural puro
      (Funarte/Rouanet/Sec Cultura) **não passa por aqui**).
- [ ] Frequência de coleta + tratar `Unidade`/situações (Disponibilizado × Encerrado).
- [ ] Retestar DOU (`in.gov.br`) — hoje instável; se estabilizar, vira fonte 2
      (cobre Funarte/Rouanet/Secretarias que o Transferegov não tem).

## 6. Recomendação (falta aprovação na spec-000 §6.1)

**Fonte 1 = Transferegov**, por prova técnica: é a única candidata que passou hoje
ponta a ponta (rede + API + prazo + elegibilidade), com dado estruturado que reduz
erro de IA. **Risco assumido:** cobertura de editais culturais é pequena por lá →
fonte 2 (DOU quando estabilizar, ou portal de Secretaria de Cultura) entra na fase 2
e é o que traz Funarte/Rouanet.
