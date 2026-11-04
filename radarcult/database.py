"""Acesso ao SQLite do RadarCult (spec-001 v0.2).

- Toda conexão liga `PRAGMA foreign_keys = ON` (sem isso o ON DELETE CASCADE não funciona).
- Migrações aditivas: arquivos `NNN_nome.sql` em `migrations/`, aplicados em ordem e
  registrados em `schema_version`.
- `upsert_edital` implementa a regra da spec-001 §3.1 (identidade estável + detecção de
  retificação por `hash_conteudo`).
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = RAIZ / "migrations"
_PADRAO_MIGRACAO = re.compile(r"^(\d{3})_.+\.sql$")

# Campos que entram no hash de conteúdo: mudança em qualquer um conta como retificação.
CAMPOS_CONTEUDO = (
    "titulo",
    "orgao_emissor",
    "url_origem",
    "data_inicio_inscricao",
    "data_fim_inscricao",
    "ufs_elegiveis",
    "proponentes_elegiveis",
    "areas_atuacao",
    "texto_bruto",
    "status_edital",  # aberto -> encerrado também é mudança (sem isso o upsert devolvia 'inalterado')
)
STATUS_PADRAO = "aberto"  # só vale para quem chama upsert_edital sem status; o parser nunca o usa
# Campos que guardam arrays JSON (spec-001 §3.4).
CAMPOS_JSON = ("ufs_elegiveis", "proponentes_elegiveis", "areas_atuacao")
CAMPOS_OBRIGATORIOS = ("codigo_origem", "titulo", "url_origem")


def connect(caminho: str | Path = ":memory:") -> sqlite3.Connection:
    """Abre uma conexão com foreign keys ligadas e linhas acessíveis por nome."""
    conn = sqlite3.connect(str(caminho))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _versao_aplicada(conn: sqlite3.Connection) -> int:
    existe = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if not existe:
        return 0
    return conn.execute("SELECT COALESCE(MAX(versao), 0) FROM schema_version").fetchone()[0]


def aplicar_migracoes(conn: sqlite3.Connection, pasta: Path = MIGRATIONS_DIR) -> list[int]:
    """Aplica as migrações pendentes, em ordem. Devolve as versões aplicadas agora."""
    versao_atual = _versao_aplicada(conn)
    aplicadas: list[int] = []
    for arquivo in sorted(pasta.glob("*.sql")):
        m = _PADRAO_MIGRACAO.match(arquivo.name)
        if not m:
            continue
        versao = int(m.group(1))
        if versao <= versao_atual:
            continue
        try:
            conn.executescript(arquivo.read_text(encoding="utf-8"))
            conn.execute("INSERT OR IGNORE INTO schema_version (versao) VALUES (?)", (versao,))
            conn.commit()
        except Exception:
            # Uma migração pode ter desligado foreign_keys e aberto transação (ex.: recriar tabela).
            if conn.in_transaction:
                conn.rollback()
            conn.execute("PRAGMA foreign_keys = ON")
            raise
        conn.execute("PRAGMA foreign_keys = ON")  # garante o estado padrão após cada migração
        aplicadas.append(versao)
    return aplicadas


def hash_identificador(fonte_nome: str, codigo_origem: str) -> str:
    """Identidade estável do edital: SHA256(fonte + codigo_origem), sem a URL (spec-001 v0.2)."""
    return hashlib.sha256(f"{fonte_nome}|{codigo_origem}".encode("utf-8")).hexdigest()


def _serializar(valor):
    """Listas/dicts viram JSON; texto e None passam direto."""
    if valor is None or isinstance(valor, str):
        return valor
    return json.dumps(valor, ensure_ascii=False, sort_keys=True)


def hash_conteudo(dados: dict) -> str:
    """SHA256 dos campos relevantes: muda quando o edital é retificado."""
    relevante = {campo: _serializar(dados.get(campo)) for campo in CAMPOS_CONTEUDO}
    bruto = json.dumps(relevante, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def garantir_fonte(conn: sqlite3.Connection, nome: str, url_base: str, tipo_coleta: str) -> int:
    """Cria a fonte se não existir e devolve o id."""
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO fontes (nome, url_base, tipo_coleta) VALUES (?, ?, ?)",
            (nome, url_base, tipo_coleta),
        )
    return conn.execute("SELECT id FROM fontes WHERE nome = ?", (nome,)).fetchone()["id"]


def cancelar_alertas_pendentes(conn: sqlite3.Connection, edital_id: int) -> int:
    """Marca como 'cancelado' os alertas ainda pendentes do edital (spec-001 §3.3)."""
    cur = conn.execute(
        "UPDATE alertas SET status_envio = 'cancelado' "
        "WHERE edital_id = ? AND status_envio = 'pendente'",
        (edital_id,),
    )
    return cur.rowcount


def upsert_edital(conn: sqlite3.Connection, fonte_nome: str, dados: dict) -> str:
    """Insere ou atualiza um edital conforme a spec-001 §3.1.

    Devolve 'inserido', 'inalterado' ou 'atualizado'. Em 'atualizado': `status_ia`
    volta a 'pendente' (reprocessar IA) e, se o prazo mudou, os alertas pendentes
    são cancelados (o reagendamento é responsabilidade da spec-004).
    """
    fonte = conn.execute("SELECT id FROM fontes WHERE nome = ?", (fonte_nome,)).fetchone()
    if fonte is None:
        raise ValueError(f"fonte desconhecida: {fonte_nome!r} (use garantir_fonte)")
    for campo in CAMPOS_OBRIGATORIOS:
        if not dados.get(campo):
            raise ValueError(f"campo obrigatório ausente: {campo}")

    status = dados.get("status_edital") or STATUS_PADRAO
    h_id = hash_identificador(fonte_nome, str(dados["codigo_origem"]))
    h_cont = hash_conteudo({**dados, "status_edital": status})  # status normalizado entra no hash
    fim = dados.get("data_fim_inscricao")
    valores = {
        "orgao_emissor": dados.get("orgao_emissor"),
        "url_origem": dados["url_origem"],
        "titulo": dados["titulo"],
        "data_inicio_inscricao": dados.get("data_inicio_inscricao"),
        "data_fim_inscricao": fim,
        "prazo_desconhecido": 0 if fim else 1,
        "ufs_elegiveis": _serializar(dados.get("ufs_elegiveis")),
        "proponentes_elegiveis": _serializar(dados.get("proponentes_elegiveis")),
        "areas_atuacao": _serializar(dados.get("areas_atuacao")),
        "texto_bruto": dados.get("texto_bruto"),
        "dados_brutos_json": _serializar(dados.get("dados_brutos_json")),
        "status_edital": status,
    }

    with conn:
        atual = conn.execute(
            "SELECT id, hash_conteudo, data_fim_inscricao FROM editais WHERE hash_identificador = ?",
            (h_id,),
        ).fetchone()

        if atual is None:
            colunas = ["fonte_id", "hash_identificador", "hash_conteudo", "codigo_origem", *valores]
            conn.execute(
                f"INSERT INTO editais ({', '.join(colunas)}) "
                f"VALUES ({', '.join('?' for _ in colunas)})",
                [fonte["id"], h_id, h_cont, str(dados["codigo_origem"]), *valores.values()],
            )
            return "inserido"

        if atual["hash_conteudo"] == h_cont:
            return "inalterado"

        atribuicoes = ", ".join(f"{c} = ?" for c in valores)
        conn.execute(
            f"UPDATE editais SET hash_conteudo = ?, {atribuicoes}, status_ia = 'pendente', "
            "atualizado_em = CURRENT_TIMESTAMP WHERE id = ?",
            [h_cont, *valores.values(), atual["id"]],
        )
        if atual["data_fim_inscricao"] != fim:
            cancelar_alertas_pendentes(conn, atual["id"])
        return "atualizado"
