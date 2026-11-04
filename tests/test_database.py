"""Testes do modelo de dados (spec-001 v0.2) — rodam offline, sem fixtures."""
import sqlite3

import pytest

from radarcult import database

FONTE = "Transferegov"


def _dados(**mudancas):
    base = {
        "codigo_origem": "202600077",
        "titulo": "Programa de teste",
        "orgao_emissor": "Órgão X",
        "url_origem": "https://exemplo.gov.br/programa/1",
        "data_inicio_inscricao": "2026-10-05",
        "data_fim_inscricao": "2026-10-26",
        "ufs_elegiveis": ["SP", "RJ"],
        "proponentes_elegiveis": ["PJ_SEM_FINS"],
        "areas_atuacao": ["Cultura"],
        "texto_bruto": "Objetivo e requisitos.",
    }
    base.update(mudancas)
    return base


def _edital(conn):
    return conn.execute("SELECT * FROM editais").fetchone()


def _perfil(conn):
    with conn:
        conn.execute("INSERT INTO perfis (telegram_chat_id) VALUES (1)")
    return conn.execute("SELECT id FROM perfis").fetchone()["id"]


def _alerta(conn, edital_id, perfil_id, tipo="prazo_D3", status="pendente"):
    with conn:
        conn.execute(
            "INSERT INTO alertas (edital_id, perfil_id, tipo_alerta, prazo_referencia, "
            "status_envio, agendado_para) VALUES (?, ?, ?, '2026-10-26', ?, '2026-10-23 12:00:00')",
            (edital_id, perfil_id, tipo, status),
        )


def test_migracoes_sao_idempotentes():
    c = database.connect(":memory:")
    aplicadas = database.aplicar_migracoes(c)
    assert aplicadas[:2] == [1, 2]
    assert database.aplicar_migracoes(c) == []
    tabelas = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"fontes", "editais", "extracoes_ia", "perfis", "alertas", "interacoes", "schema_version"} <= tabelas


def test_foreign_keys_ligadas(conn):
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_upsert_insere_e_ignora_repetido(conn):
    assert database.upsert_edital(conn, FONTE, _dados()) == "inserido"
    assert database.upsert_edital(conn, FONTE, _dados()) == "inalterado"
    assert conn.execute("SELECT COUNT(*) FROM editais").fetchone()[0] == 1


def test_identidade_nao_depende_da_url(conn):
    database.upsert_edital(conn, FONTE, _dados())
    resultado = database.upsert_edital(conn, FONTE, _dados(url_origem="https://exemplo.gov.br/novo"))
    assert resultado == "atualizado"  # mesmo edital, link corrigido
    assert conn.execute("SELECT COUNT(*) FROM editais").fetchone()[0] == 1
    assert _edital(conn)["url_origem"] == "https://exemplo.gov.br/novo"


def test_retificacao_de_prazo_atualiza_e_reprocessa_ia(conn):
    database.upsert_edital(conn, FONTE, _dados())
    with conn:
        conn.execute("UPDATE editais SET status_ia = 'processado'")
    resultado = database.upsert_edital(conn, FONTE, _dados(data_fim_inscricao="2026-11-30"))
    assert resultado == "atualizado"
    e = _edital(conn)
    assert e["data_fim_inscricao"] == "2026-11-30"
    assert e["status_ia"] == "pendente"


def test_retificacao_de_prazo_cancela_so_alertas_pendentes(conn):
    database.upsert_edital(conn, FONTE, _dados())
    eid, pid = _edital(conn)["id"], _perfil(conn)
    _alerta(conn, eid, pid, "prazo_D10", status="enviado")
    _alerta(conn, eid, pid, "prazo_D3", status="pendente")
    database.upsert_edital(conn, FONTE, _dados(data_fim_inscricao="2026-11-30"))
    status = {r["tipo_alerta"]: r["status_envio"] for r in conn.execute("SELECT * FROM alertas")}
    assert status == {"prazo_D10": "enviado", "prazo_D3": "cancelado"}


def test_mudanca_sem_alterar_prazo_nao_cancela_alertas(conn):
    database.upsert_edital(conn, FONTE, _dados())
    eid, pid = _edital(conn)["id"], _perfil(conn)
    _alerta(conn, eid, pid)
    database.upsert_edital(conn, FONTE, _dados(titulo="Título corrigido"))
    assert conn.execute("SELECT status_envio FROM alertas").fetchone()[0] == "pendente"


def test_alerta_duplicado_e_bloqueado(conn):
    database.upsert_edital(conn, FONTE, _dados())
    eid, pid = _edital(conn)["id"], _perfil(conn)
    _alerta(conn, eid, pid)
    with pytest.raises(sqlite3.IntegrityError):
        _alerta(conn, eid, pid)


def test_reagendamento_precisa_de_upsert_por_causa_do_unique(conn):
    """Alerta cancelado continua ocupando o UNIQUE: o reagendamento (spec-004) deve atualizar a linha."""
    database.upsert_edital(conn, FONTE, _dados())
    eid, pid = _edital(conn)["id"], _perfil(conn)
    _alerta(conn, eid, pid, status="cancelado")
    with pytest.raises(sqlite3.IntegrityError):
        _alerta(conn, eid, pid)  # inserir de novo falha
    with conn:
        conn.execute(
            "INSERT INTO alertas (edital_id, perfil_id, tipo_alerta, prazo_referencia, agendado_para) "
            "VALUES (?, ?, 'prazo_D3', '2026-11-30', '2026-11-27 12:00:00') "
            "ON CONFLICT(edital_id, perfil_id, tipo_alerta) DO UPDATE SET "
            "status_envio = 'pendente', prazo_referencia = excluded.prazo_referencia, "
            "agendado_para = excluded.agendado_para, enviado_em = NULL, mensagem_erro = NULL",
            (eid, pid),
        )
    a = conn.execute("SELECT * FROM alertas").fetchone()
    assert (a["status_envio"], a["prazo_referencia"]) == ("pendente", "2026-11-30")


def test_sem_prazo_marca_prazo_desconhecido(conn):
    database.upsert_edital(conn, FONTE, _dados(data_fim_inscricao=None))
    assert _edital(conn)["prazo_desconhecido"] == 1


def test_arrays_sao_gravados_como_json(conn):
    database.upsert_edital(conn, FONTE, _dados())
    assert _edital(conn)["ufs_elegiveis"] == '["SP", "RJ"]'


def test_campos_obrigatorios_e_fonte_desconhecida(conn):
    with pytest.raises(ValueError, match="url_origem"):
        database.upsert_edital(conn, FONTE, _dados(url_origem=""))
    with pytest.raises(ValueError, match="fonte desconhecida"):
        database.upsert_edital(conn, "Outra", _dados())


def test_apagar_edital_remove_alertas_em_cascata(conn):
    database.upsert_edital(conn, FONTE, _dados())
    eid, pid = _edital(conn)["id"], _perfil(conn)
    _alerta(conn, eid, pid)
    with conn:
        conn.execute("DELETE FROM editais WHERE id = ?", (eid,))
    assert conn.execute("SELECT COUNT(*) FROM alertas").fetchone()[0] == 0


def test_check_de_tipo_de_alerta(conn):
    database.upsert_edital(conn, FONTE, _dados())
    eid, pid = _edital(conn)["id"], _perfil(conn)
    with pytest.raises(sqlite3.IntegrityError):
        _alerta(conn, eid, pid, tipo="novo_edital")  # fora do escopo do MVP (spec-001 v0.2)
