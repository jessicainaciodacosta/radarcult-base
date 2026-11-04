-- 002_status_em_breve.sql — adiciona 'em_breve' ao CHECK de editais.status_edital.
-- O SQLite não altera CHECK com ALTER TABLE: recria-se a tabela (procedimento oficial,
-- https://www.sqlite.org/lang_altertable.html#otheralter). A 001 NÃO é editada, para que
-- bancos já criados recebam a mudança por migração aditiva.
-- foreign_keys fica OFF só durante a recriação; as tabelas que referenciam editais
-- (alertas, extracoes_ia, interacoes) continuam apontando para o nome 'editais'.

PRAGMA foreign_keys = OFF;
BEGIN;

CREATE TABLE editais_novo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fonte_id INTEGER NOT NULL REFERENCES fontes(id),
    hash_identificador TEXT NOT NULL UNIQUE,
    hash_conteudo TEXT,
    codigo_origem TEXT,
    titulo TEXT NOT NULL,
    orgao_emissor TEXT,
    url_origem TEXT NOT NULL,

    data_inicio_inscricao DATE,
    data_fim_inscricao DATE,
    prazo_desconhecido INTEGER NOT NULL DEFAULT 0 CHECK (prazo_desconhecido IN (0,1)),

    ufs_elegiveis TEXT,
    proponentes_elegiveis TEXT,
    areas_atuacao TEXT,

    texto_bruto TEXT,
    dados_brutos_json TEXT,

    status_ia TEXT NOT NULL DEFAULT 'pendente' CHECK (status_ia IN ('pendente','processado','erro')),
    status_edital TEXT NOT NULL DEFAULT 'aberto' CHECK (status_edital IN ('aberto','em_breve','encerrado','cancelado')),
    coletado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
    atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO editais_novo (
    id, fonte_id, hash_identificador, hash_conteudo, codigo_origem, titulo, orgao_emissor,
    url_origem, data_inicio_inscricao, data_fim_inscricao, prazo_desconhecido,
    ufs_elegiveis, proponentes_elegiveis, areas_atuacao, texto_bruto, dados_brutos_json,
    status_ia, status_edital, coletado_em, atualizado_em
)
SELECT
    id, fonte_id, hash_identificador, hash_conteudo, codigo_origem, titulo, orgao_emissor,
    url_origem, data_inicio_inscricao, data_fim_inscricao, prazo_desconhecido,
    ufs_elegiveis, proponentes_elegiveis, areas_atuacao, texto_bruto, dados_brutos_json,
    status_ia, status_edital, coletado_em, atualizado_em
FROM editais;

DROP TABLE editais;
ALTER TABLE editais_novo RENAME TO editais;
CREATE INDEX IF NOT EXISTS idx_editais_prazo ON editais(status_edital, data_fim_inscricao);

INSERT OR IGNORE INTO schema_version (versao) VALUES (2);
COMMIT;
PRAGMA foreign_keys = ON;
