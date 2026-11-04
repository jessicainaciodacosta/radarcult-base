# SPEC-000 — RadarCult: visão, MVP e regras de decisão

- **Status:** aprovada v1.0 — 31/10/2026
- **Metodologia:** Spec-Driven Development (SDD). Nenhum código é escrito sem spec
  aprovada. As specs 001+ só abrem depois desta estar marcada como aprovada.
- **Data:** 24/10/2026
- **Origem:** esboço em `RadarCult.txt` (raiz do projeto) — esta spec formaliza aquele esboço.

---

## 1. Problema (quem sofrem, e por quê)

Profissionais de captação e gestão de projetos (produtores culturais, captadores,
ONGs/coletivos, consultores) enfrentam 3 gargalos diários:

1. **Pulverização de fontes** — editais espalhados em Diários Oficiais (União/Estados/
   Municípios), Transferegov, portais de ONGs/fundações, Sesc/Sesi/Sebrae e redes sociais.
2. **Janelas curtas de inscrição** — 15 a 30 dias; descobrir o edital faltando 5 dias
   inviabiliza montar orçamento, certidões e portfólio.
3. **Leitura exaustiva de regulamentos** — dezenas de páginas para descobrir, no fim,
   que a entidade/região não é elegível.

## 2. Solução — o produto

Um **radar inteligente** que:

1. **Coleta** oportunidades de uma fonte (fase 1) → depois múltiplas (fase 2).
2. **Extrai os 5 campos críticos** de cada edital (contrato de dados v1):
   - **Elegibilidade**: quem pode se inscrever (PF, PJ sem fins lucrativos, MEI,
     coletivo sem CNPJ, etc.)
   - **Valor máximo** financiado
   - **Prazo final** + link direto do formulário/edital
   - **Mecanismo** (verba direta, Lei de Incentivo/Rouanet/ProAC, chamada pública)
   - **Resumo de exigências** curto (o que o proponente precisa ter em mão)
3. **Filtra por perfil** do usuário (região, linguagem artística, tipo de proponente,
   faixa de valor) — entrega só o onde o usuário **é elegível**.
4. **Alerta de prazo** via bot Telegram (lembretes D-10, D-3, D-1 do encerramento).

Regra de ouro: **todo resumo carrega sempre o link do edital original** — a IA pode
errar; o documento oficial manda. O radar orienta, não substitui a leitura final.

## 3. Usuário do MVP

**O próprio dono do projeto**, validando pessoalmente (decisão de 24/10/2026).

Critérios de validação (4 semanas de uso real):

- Usar o radar pelo menos **3x por semana** sem lembrar-se de que "é para testar";
- Encontrar **≥3 oportunidades relevantes** que ele não teria visto sem a ferramenta;
- Triagem de um edital novo leva **< 2 min** (já vem resumido e classificado);
- **Nenhum prazo relevante perdido** no período.

Medir, não estimar: nunca publicar percentual de economia de tempo sem número apurado.

## 4. Escopo do MVP

### ENTRA (fase 1)

- Coleta **agendada** da 1ª fonte (escolhida via spike-001, ver §6).
- Deduplicação de editais (identidade por URL/hash — o mesmo edital não aparece 2x).
- Extração IA dos 5 campos, com link original obrigatório e flag de confiança.
- **Bot Telegram individual (só o dono)**: busca por filtros, resumo do edital,
  alertas de prazo D-10 / D-3 / D-1.
- Banco SQLite com migrações aditivas.
- `iniciar.bat` (duplo-clique cria venv e sobe o bot — sem linha de comando).

### FICA DE FORA (não é MVP — não codar agora)

- Pagamento/assinatura/Pix, planos e freemium (fase comercial, depois de validar uso).
- Painel web (Streamlit) ou site público.
- Multiusuário / perfis de cliente.
- 2ª+ fontes (DOU/INLABS entra como fase 2, pós- spike consolidado).
- Alertas por e-mail, exportação CSV, monitoramento por palavra-chave de DOs.
- App mobile.

## 5. Decisões técnicas (já tomadas)

- **Reuso do motor Nova Visão Brasil** (padrões, não código do produto):
  `config.py`/`config.toml` (segredos × ajustes), `scheduler.py` (SQLite + migrações
  aditivas), `ai_handler.py` (Gemini com retry 3x e parse JSON tolerante),
  estrutura de handlers do `bot.py` + `job-queue` do python-telegram-bot,
  `iniciar.bat` + guarda de Python, `.env.example`, `CONTEXTO.md` como handoff.
- **Um único bot, dono único** no MVP (o freemium multiusuário do esboço é fase 3).
- Python + SQLite + Telegram + Gemini — mesma stack do projeto de produção
  (zero curva de aprendizagem, host simples).
- Ciclo por spec: spec → harness (fixtures + asserções) → código → evidência de passagem.

## 6. Decisão da fonte de dados — PENDENTE (spike-001)

Candidatas a confrontar no spike (até 1 dia de trabalho):

| Candidata | Forte | Fraco |
|---|---|---|
| Transferegov | Dado estruturado (prazo/valor em campo) | JS pesado; nem toda cultura está lá |
| DOU / INLABS | Dado aberto oficial, sem HTML frágil | Texto denso; exige filtro + IA; muitos não-editais |
| Portal estadual/municipal de cultura | HTML simples, alto sinal | Pouca cobertura |

Critérios de escolha: (a) acessibilidade daqui, (b) estrutura dos dados, (c) cobertura
de cultura/direitos humanos/assistência, (d) esforço de manutenção.

> Resultado registrado em `docs/spike/spike-001-fontes.md` e copiado para cá
> em §6.1 — **nada de escolher por gosto, só por evidência.**

### 6.1 Resultado do spike (24/10/2026 — ver `docs/spike/spike-001-fontes.md`)

- **Transferegov: ✅ VIÁVEL (recomendado como fonte 1).** Domínio antigo do esboço
  (`www.transferegov.br`) morreu — é `parcerias.transferegov.sistema.gov.br`. API
  JSON pública descoberta e **provada com curl**: bootstrap de cookie XSRF
  (`auth/configuration`) + `POST programa/listarComFiltro` (GET dá 400) +
  `GET programa/{id}` traz **prazo** (`dtaInicioRecebPropEsp`/`dtaFimRecebPropEsp`),
  **elegibilidade** (`requisitos`, `ufsHabilitadas`, `publicosAlvos`) e texto para IA.
- **DOU/Imprensa Nacional: ⚠️ instável daqui** (6 tentativas: 502, 301, 3x000, 1x200);
  `dadosabertos.in.gov.br` fora do ar (NXDOMAIN). Candidata à fonte 2 **só quando
  estabilizar** — é a fonte dos editais culturais (Funarte/Rouanet) que o
  Transferegov não tem.
- **Cultura SP: ✅ acessível, ❌ sem editais na home** — exigiria mapeamento próprio;
  cobertura só de SP.
- **Concorrência:** `editaisdobrasil.com` já faz radar de verbas do Transferegov
  (licitações/repasses + "meu radar" + lembretes + IA), **não** curadoria de edital
  cultural para produtor — nicho do RadarCult segue aberto, mas validar em uso real.

**Recomendação:** fonte 1 = Transferegov (única que passou ponta a ponta hoje),
aceitando o risco de cobertura cultural pequena (hoje ~2 de 131 programas abertos
são de Cultura) — mitigação: fase 2 traz DOU/Secretarias.

**Decisão aprovada (31/10/2026):** Fonte 1 = Transferegov. Coleta via web scraping
(Playwright) para prática/portfólio, não via API direta, mesmo com API disponível.

## 7. Riscos e armadilhas conhecidas

- **Rede:** portais gov.br deram timeout na sessão de dev (24/10/2026) → spike roda
  no navegador do dono; se o bloqueio for de rede doméstica, adiar e escolher por
  alternativa acessível.
- **Erro de IA em prazo/valor é falha crítica** → harness de regressão com fixtures
  de editais reais; exibir sempre "confira no edital oficial" com o link.
- **Scraping responsável:** frequência baixa (1-2x/dia), User-Agent honesto,
  respeitar robots.txt; republicar só resumo próprio, nunca texto integral do edital.
- **Concorrência:** agregadores de editais já existem — o diferencial defendido é
  **filtro de elegibilidade por perfil + alerta de prazo**, não o acervo. Validar com
  uso real do MVP.
- **Custo de IA:** Gemini free é instável (retry já resolvido no padrão reusado);
  extração roda 1x por edital novo (não por consulta).

## 8. Critérios de aceite desta spec

- [x] Dono leu e aprovou (status → **aprovada**)
- [x] §6.1 preenchido com resultado do spike e fonte 1 escolhida
- [x] Escopo IN/OUT (§4) aceito — qualquer item novo vira nova spec

## 9. Ordem das próximas specs

1. `spec-001` — modelo de dados (tabelas `editais`, `fontes`, `perfis`, `alertas`)
2. `spec-002` — coletor da fonte 1 + corpus de fixtures + asserções (harness)
3. `spec-003` — extração IA dos 5 campos + harness de saída
4. `spec-004` — bot Telegram: consulta por filtro + alertas de prazo
5. (fase 2) — 2ª fonte, painel web, exportação

## 10. Precificação (hipótese do esboço — registro, fora do MVP)

| Plano | Valor apontado | Momento |
|---|---|---|
| Gratuito (canal, 3-5 editais/semana) | R$ 0 | fase comercial |
| Pro (alertas + filtros) | R$ 39–59/mês | fase comercial |
| Equipes/Agências (CSV, DOs monitoradas) | R$ 149–299/mês | fase comercial |

Não se cobra nada antes do MVP provar uso real (§3).
