-- 001_initial_schema.sql — RadarCult (spec-001 v0.2)
-- Datas/horas em UTC (YYYY-MM-DD HH:MM:SS). Prazos (DATE) = data local America/Sao_Paulo.
-- A aplicação deve executar `PRAGMA foreign_keys = ON;` em TODA conexão.

CREATE TABLE IF NOT EXISTS schema_version (
    versao INTEGER PRIMARY KEY,
    aplicada_em DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 1. FONTES
CREATE TABLE IF NOT EXISTS fontes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE,
    url_base TEXT NOT NULL,
    tipo_coleta TEXT NOT NULL CHECK (tipo_coleta IN ('scraping_playwright','api_rest','outro')),
    ativa INTEGER NOT NULL DEFAULT 1 CHECK (ativa IN (0,1)),
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 2. EDITAIS
CREATE TABLE IF NOT EXISTS editais (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fonte_id INTEGER NOT NULL REFERENCES fontes(id),
    hash_identificador TEXT NOT NULL UNIQUE,   -- SHA256(fonte + codigo_origem): identidade estável
    hash_conteudo TEXT,                        -- SHA256 do conteúdo relevante: detecta retificação
    codigo_origem TEXT,
    titulo TEXT NOT NULL,
    orgao_emissor TEXT,
    url_origem TEXT NOT NULL,

    -- Prazo CANÔNICO (campo estruturado da fonte). Alertas leem só daqui.
    data_inicio_inscricao DATE,
    data_fim_inscricao DATE,
    prazo_desconhecido INTEGER NOT NULL DEFAULT 0 CHECK (prazo_desconhecido IN (0,1)),

    -- Campos estruturados da fonte, filtráveis em SQL (arrays JSON)
    ufs_elegiveis TEXT,
    proponentes_elegiveis TEXT,
    areas_atuacao TEXT,

    texto_bruto TEXT,
    dados_brutos_json TEXT,                    -- resposta JSON integral da fonte (base das fixtures)

    status_ia TEXT NOT NULL DEFAULT 'pendente' CHECK (status_ia IN ('pendente','processado','erro')),
    status_edital TEXT NOT NULL DEFAULT 'aberto' CHECK (status_edital IN ('aberto','encerrado','cancelado')),
    coletado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
    atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_editais_prazo ON editais(status_edital, data_fim_inscricao);

-- 3. EXTRAÇÃO IA
CREATE TABLE IF NOT EXISTS extracoes_ia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    edital_id INTEGER NOT NULL UNIQUE REFERENCES editais(id) ON DELETE CASCADE,

    elegibilidade_resumo TEXT,
    valor_maximo_financiar REAL,
    prazo_final_formatado TEXT,
    mecanismo TEXT CHECK (mecanismo IS NULL OR mecanismo IN
        ('Verba Direta','Rouanet','ProAC','PNAB','Chamada Pública','Outro')),
    resumo_exigencias TEXT,

    confianca_score REAL CHECK (confianca_score IS NULL OR (confianca_score >= 0 AND confianca_score <= 1)),
    validado_por_regra INTEGER CHECK (validado_por_regra IS NULL OR validado_por_regra IN (0,1)),
    prazo_divergente INTEGER NOT NULL DEFAULT 0 CHECK (prazo_divergente IN (0,1)),
    modelo_ia TEXT,                            -- modelo REALMENTE usado (gateway pode alternar)
    bruto_json_ia TEXT,
    processado_em DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 4. PERFIS
CREATE TABLE IF NOT EXISTS perfis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_chat_id INTEGER NOT NULL UNIQUE,
    nome TEXT,
    tipo_proponente TEXT CHECK (tipo_proponente IS NULL OR tipo_proponente IN ('PF','PJ_SEM_FINS','MEI','COLETIVO')),
    uf TEXT DEFAULT 'SP',
    linguagens_artisticas TEXT,                -- array JSON
    faixa_valor_min REAL,
    faixa_valor_max REAL,
    atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 5. ALERTAS (um por edital + perfil + marco)
CREATE TABLE IF NOT EXISTS alertas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    edital_id INTEGER NOT NULL REFERENCES editais(id) ON DELETE CASCADE,
    perfil_id INTEGER NOT NULL REFERENCES perfis(id),
    tipo_alerta TEXT NOT NULL CHECK (tipo_alerta IN ('prazo_D10','prazo_D3','prazo_D1')),
    prazo_referencia DATE NOT NULL,            -- prazo usado ao agendar; se mudar, reagendar
    status_envio TEXT NOT NULL DEFAULT 'pendente' CHECK (status_envio IN ('pendente','enviado','falhou','cancelado')),
    agendado_para DATETIME NOT NULL,
    enviado_em DATETIME,
    mensagem_erro TEXT,
    UNIQUE (edital_id, perfil_id, tipo_alerta)
);
CREATE INDEX IF NOT EXISTS idx_alertas_fila ON alertas(status_envio, agendado_para);

-- 6. INTERAÇÕES (mede os critérios da spec-000 §3)
CREATE TABLE IF NOT EXISTS interacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    perfil_id INTEGER NOT NULL REFERENCES perfis(id),
    edital_id INTEGER REFERENCES editais(id) ON DELETE SET NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('consulta','abriu_resumo','relevante','descartado','inscrito')),
    duracao_segundos INTEGER,
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_interacoes_data ON interacoes(criado_em);

INSERT OR IGNORE INTO schema_version (versao) VALUES (1);
