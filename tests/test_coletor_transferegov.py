"""Testes do coletor contra um servidor local SIMULADO (tests/servidor_falso.py).

O que estes testes provam: a lógica do coletor (XSRF, paginação, filtro, interceptação,
fallback, idempotência, retificação, falha por item, robots, 403/429, listagem vazia).
O que NÃO provam: que o portal real se comporta assim — isso só o primeiro ciclo real
na máquina do dono confirma.

Os dados de detalhe vêm das fixtures reais (fixtures/transferegov/). Como os 3 snapshots
reais estão todos ENCERRADOS (recebendoProposta=false), os testes marcam 182 e 181 como
abertos NA CÓPIA servida pelo servidor falso — é uma simulação, não dado real.
"""
import asyncio
import copy
import json
from pathlib import Path

import pytest

pytest.importorskip("playwright")

from radarcult.coletor.transferegov import Config, coletar  # noqa: E402
from tests.servidor_falso import Estado, ServidorFalso  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "transferegov"
CASOS = {182: "programa-182-v1", 181: "programa-181", 173: "programa-173"}

if not all((FIXTURES / pasta / "snapshot.json").exists() for pasta in CASOS.values()):
    pytest.skip("fixtures reais ausentes (snapshots são ignorados pelo git)", allow_module_level=True)


def _programas():
    progs = {pid: json.loads((FIXTURES / pasta / "snapshot.json").read_text(encoding="utf-8"))
             for pid, pasta in CASOS.items()}
    for pid in (182, 181):  # SIMULAÇÃO (ver docstring): sinais coerentes de "recebendo propostas"
        progs[pid].update(recebendoProposta=True, recebimentoPropostaConcluido=False,
                          recebimentoPropostaNaoIniciado=False)
    return progs


@pytest.fixture
def servidor():
    estado = Estado(copy.deepcopy(_programas()))
    with ServidorFalso(estado) as srv:
        yield srv


def _cfg(srv, **kw):
    base = dict(base_url=srv.url, pausa_s=0, espera_retry_s=0, timeout_ms=3000, respeitar_robots=True)
    base.update(kw)
    return Config(**base)


def _rodar(conn, srv, **kw):
    return asyncio.run(coletar(conn, _cfg(srv, **kw)))


def _contar(conn):
    return conn.execute("SELECT COUNT(*) FROM editais").fetchone()[0]


def test_ciclo_completo_filtra_so_os_recebendo_propostas(conn, servidor):
    r = _rodar(conn, servidor)
    assert r.abortado is None and r.erros == []
    assert (r.listados, r.candidatos, r.inseridos) == (3, 2, 2)
    assert r.interceptados == 2 and r.via_fallback == 0
    assert r.listagem_completa is True and r.codigo_saida() == 0
    codigos = {row["codigo_origem"] for row in conn.execute("SELECT codigo_origem FROM editais")}
    assert codigos == {"202600077", "202600076"}  # 173 (encerrado) ficou de fora


def test_listagem_exige_token_xsrf(conn, servidor):
    _rodar(conn, servidor)
    posts = [t for m, p, t in servidor.estado.requisicoes if m == "POST"]
    assert posts and all(posts)  # todo POST levou o XSRF-TOKEN que o portal entregou


def test_segundo_ciclo_e_idempotente(conn, servidor):
    _rodar(conn, servidor)
    r = _rodar(conn, servidor)
    assert (r.inseridos, r.atualizados, r.inalterados) == (0, 0, 2)
    assert _contar(conn) == 2


def test_prazo_retificado_atualiza_o_edital(conn, servidor):
    _rodar(conn, servidor)
    servidor.estado.programas[182]["dtaFimRecebPropEsp"] = "2026-11-30"
    r = _rodar(conn, servidor)
    assert (r.atualizados, r.inalterados) == (1, 1)
    row = conn.execute("SELECT data_fim_inscricao, status_ia FROM editais WHERE codigo_origem='202600077'").fetchone()
    assert (row["data_fim_inscricao"], row["status_ia"]) == ("2026-11-30", "pendente")


def test_fallback_quando_a_pagina_nao_dispara_a_api(conn, servidor):
    servidor.estado.pagina_sem_api = True
    r = _rodar(conn, servidor, timeout_ms=1200)
    assert r.abortado is None and r.inseridos == 2
    assert (r.interceptados, r.via_fallback) == (0, 2)


def test_sem_interceptar_usa_so_fetch(conn, servidor):
    r = _rodar(conn, servidor, interceptar=False)
    assert (r.inseridos, r.interceptados, r.via_fallback) == (2, 0, 2)


def test_falha_em_um_item_nao_derruba_o_ciclo(conn, servidor):
    servidor.estado.detalhe_falha = {181}
    r = _rodar(conn, servidor)
    assert r.abortado is None and r.inseridos == 1
    assert len(r.erros) == 1 and r.erros[0]["id"] == 181
    assert r.codigo_saida() == 1
    assert _contar(conn) == 1


def test_erros_em_sequencia_abortam_o_ciclo(conn, servidor):
    servidor.estado.detalhe_falha = {182, 181}
    r = _rodar(conn, servidor, max_erros_consecutivos=2)
    assert r.abortado and "erros seguidos" in r.abortado and r.codigo_saida() == 2


def test_paginacao_le_todas_as_paginas(conn, servidor):
    r = _rodar(conn, servidor, pagesize=1)
    assert r.listados == 3 and r.listagem_completa and r.inseridos == 2
    assert r.paginas_lidas == 4  # 3 páginas com itens + a 4ª (vazia), que encerra a leitura


def test_max_paginas_deixa_a_listagem_incompleta(conn, servidor):
    r = _rodar(conn, servidor, pagesize=1, max_paginas=1)
    assert r.listados == 1 and r.listagem_completa is False and r.codigo_saida() == 1


def test_todos_inclui_programas_encerrados(conn, servidor):
    r = _rodar(conn, servidor, apenas_recebendo=False)
    assert r.candidatos == 3 and r.inseridos == 3


def test_robots_que_bloqueia_aborta_antes_de_coletar(conn, servidor):
    servidor.estado.robots = "User-agent: *\nDisallow: /ep/api/\n"
    r = _rodar(conn, servidor)
    assert r.abortado and "proíbe" in r.abortado
    assert _contar(conn) == 0
    assert not any(m == "POST" for m, _, _ in servidor.estado.requisicoes)


def test_robots_permissivo_segue(conn, servidor):
    servidor.estado.robots = "User-agent: *\nDisallow: /admin/\n"
    r = _rodar(conn, servidor)
    assert r.abortado is None and r.inseridos == 2


def test_robots_com_erro_5xx_aborta_por_precaucao(conn, servidor):
    servidor.estado.robots_status = 503
    r = _rodar(conn, servidor)
    assert r.abortado and "503" in r.abortado and _contar(conn) == 0


def test_http_429_na_listagem_aborta(conn, servidor):
    servidor.estado.listagem_status = 429
    r = _rodar(conn, servidor)
    assert r.abortado and "429" in r.abortado and _contar(conn) == 0


def test_listagem_vazia_aborta_sem_alterar_o_banco(conn, servidor):
    servidor.estado.listagem_vazia = True
    r = _rodar(conn, servidor)
    assert r.abortado and "listagem vazia" in r.abortado and _contar(conn) == 0


def test_portal_inacessivel_aborta_com_mensagem_util(conn):
    r = asyncio.run(coletar(conn, Config(base_url="http://127.0.0.1:9", pausa_s=0, timeout_ms=1500,
                                         respeitar_robots=False)))
    assert r.abortado and "máquina do dono" in r.abortado
