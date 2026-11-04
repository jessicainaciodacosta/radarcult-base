"""Migração 002 (status 'em_breve') e comportamento de `aplicar_migracoes`.

Teste de CAIXA-PRETA: não depende de como a 002 foi escrita. Usa uma cópia da 001
ORIGINAL (tests/data/001_original.sql, sem 'em_breve') para simular um banco que já existe
e aplica sobre ele as migrações reais do projeto. Se alguém editou a 001 no lugar em vez de
criar a 002, estes testes falham.
"""
import shutil
import sqlite3
from pathlib import Path

import pytest

from radarcult import database as db

ORIGINAL_001 = Path(__file__).parent / "data" / "001_original.sql"


def _banco_antigo(tmp_path):
    """Banco criado só com a 001 original (como um radarcult.db de execuções anteriores)."""
    pasta = tmp_path / "so001"
    pasta.mkdir()
    shutil.copy(ORIGINAL_001, pasta / "001_initial_schema.sql")
    conn = db.connect(tmp_path / "antigo.db")
    assert db.aplicar_migracoes(conn, pasta) == [1]
    return conn


def _popular(conn):
    conn.executescript(
        """
        INSERT INTO fontes (nome, url_base, tipo_coleta) VALUES ('Transferegov', 'https://x', 'scraping_playwright');
        INSERT INTO editais (fonte_id, hash_identificador, hash_conteudo, codigo_origem, titulo, url_origem,
                             data_fim_inscricao, status_edital)
        VALUES (1, 'h1', 'c1', '1', 'T1', 'https://x/1', '2026-11-20', 'aberto'),
               (1, 'h2', 'c2', '2', 'T2', 'https://x/2', '2026-11-25', 'encerrado');
        INSERT INTO perfis (telegram_chat_id) VALUES (1);
        INSERT INTO alertas (edital_id, perfil_id, tipo_alerta, prazo_referencia, agendado_para)
        VALUES (1, 1, 'prazo_D3', '2026-11-20', '2026-11-17 12:00:00');
        INSERT INTO extracoes_ia (edital_id, elegibilidade_resumo) VALUES (1, 'resumo');
        INSERT INTO interacoes (perfil_id, edital_id, tipo) VALUES (1, 1, 'consulta');
        """
    )
    conn.commit()


def _linhas(conn, tabela):
    return [dict(r) for r in conn.execute(f"SELECT * FROM {tabela} ORDER BY id")]


def test_banco_antigo_rejeita_em_breve_antes_da_migracao(tmp_path):
    """Pré-condição: confirma que o cenário do teste é real (a 001 original não aceita em_breve)."""
    conn = _banco_antigo(tmp_path)
    _popular(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE editais SET status_edital = 'em_breve' WHERE id = 1")


def test_migracao_atualiza_banco_existente_sem_perder_dados(tmp_path):
    conn = _banco_antigo(tmp_path)
    _popular(conn)
    antes = {t: _linhas(conn, t) for t in ("editais", "alertas", "extracoes_ia", "interacoes", "fontes", "perfis")}

    aplicadas = db.aplicar_migracoes(conn)

    assert 2 in aplicadas and 1 not in aplicadas
    for tabela, linhas in antes.items():
        assert _linhas(conn, tabela) == linhas, f"dados de {tabela} mudaram na migração"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert 2 in [r[0] for r in conn.execute("SELECT versao FROM schema_version")]


def test_apos_migracao_aceita_em_breve_e_continua_validando(tmp_path):
    conn = _banco_antigo(tmp_path)
    _popular(conn)
    db.aplicar_migracoes(conn)
    conn.execute("UPDATE editais SET status_edital = 'em_breve' WHERE id = 1")
    assert conn.execute("SELECT status_edital FROM editais WHERE id = 1").fetchone()[0] == "em_breve"
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE editais SET status_edital = 'qualquer_coisa' WHERE id = 1")
    with pytest.raises(sqlite3.IntegrityError):  # UNIQUE de hash_identificador preservado
        conn.execute(
            "INSERT INTO editais (fonte_id, hash_identificador, titulo, url_origem) VALUES (1, 'h1', 'dup', 'u')"
        )


def test_chaves_estrangeiras_continuam_ligadas_a_nova_tabela(tmp_path):
    """Se a recriação quebrasse as referências, o CASCADE/SET NULL deixaria de funcionar."""
    conn = _banco_antigo(tmp_path)
    _popular(conn)
    db.aplicar_migracoes(conn)
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.execute("DELETE FROM editais WHERE id = 1")
    assert conn.execute("SELECT COUNT(*) FROM alertas").fetchone()[0] == 0          # ON DELETE CASCADE
    assert conn.execute("SELECT COUNT(*) FROM extracoes_ia").fetchone()[0] == 0      # ON DELETE CASCADE
    assert conn.execute("SELECT edital_id FROM interacoes").fetchone()[0] is None    # ON DELETE SET NULL
    with pytest.raises(sqlite3.IntegrityError):  # FK de alertas -> editais ativa de novo
        conn.execute(
            "INSERT INTO alertas (edital_id, perfil_id, tipo_alerta, prazo_referencia, agendado_para) "
            "VALUES (999, 1, 'prazo_D1', '2026-11-20', '2026-11-19 12:00:00')"
        )


def test_indice_de_prazo_recriado(tmp_path):
    conn = _banco_antigo(tmp_path)
    db.aplicar_migracoes(conn)
    assert conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_editais_prazo'"
    ).fetchone()


def test_banco_novo_aplica_todas_e_e_idempotente():
    conn = db.connect(":memory:")
    aplicadas = db.aplicar_migracoes(conn)
    assert 1 in aplicadas and 2 in aplicadas
    assert db.aplicar_migracoes(conn) == []
    conn.execute("PRAGMA foreign_keys")
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_migracao_com_erro_faz_rollback_e_religa_foreign_keys(tmp_path):
    pasta = tmp_path / "migs"
    shutil.copytree(db.MIGRATIONS_DIR, pasta)
    (pasta / "999_quebrada.sql").write_text(
        "PRAGMA foreign_keys = OFF;\nBEGIN;\nCREATE TABLE temp_x (a);\n"
        "INSERT INTO tabela_que_nao_existe VALUES (1);\nCOMMIT;\nPRAGMA foreign_keys = ON;\n",
        encoding="utf-8",
    )
    conn = db.connect(":memory:")
    with pytest.raises(sqlite3.OperationalError):
        db.aplicar_migracoes(conn, pasta)
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1, "foreign_keys ficou desligado após o erro"
    assert not conn.in_transaction
    assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='temp_x'").fetchone() is None, "sem rollback"
    assert 999 not in [r[0] for r in conn.execute("SELECT versao FROM schema_version")]
