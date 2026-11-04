"""Regras do parser e da integração parse → banco, com snapshots MÍNIMOS escritos à mão.

Não usam dados reais do portal (os campos são os mesmos dos snapshots reais, os valores são
inventados). Cada teste documenta uma regra de radarcult/coletor/parse.py.
"""
import json

import pytest

from radarcult.coletor.parse import CAMPOS_SAIDA, parse_programa, processar_programa

FONTE = "Transferegov"


def _base(**mudancas):
    d = {
        "id": 1, "codigo": 202600001, "nome": "Programa X", "unidade": {"nome": "Unidade Y"},
        "recebendoProposta": True, "recebimentoPropostaConcluido": False,
        "recebimentoPropostaNaoIniciado": False,
        "dtaInicioRecebPropEsp": "2026-11-01", "dtaFimRecebPropEsp": "2026-11-30",
        "atendidos": [{"descricao": "Terceiro Setor"}], "areasAtuacao": [{"nome": "Cultura"}],
        "ufsHabilitadas": [], "objetivo": "O", "problema": "P", "resultadoEsperado": "R",
    }
    d.update(mudancas)
    return d


def _sem(d, *chaves):
    for c in chaves:
        d.pop(c, None)
    return d


# ---------- status ----------

@pytest.mark.parametrize("sinais,esperado", [
    (dict(recebendoProposta=True), "aberto"),
    (dict(recebendoProposta=False, recebimentoPropostaConcluido=True), "encerrado"),
    (dict(recebendoProposta=False, recebimentoPropostaNaoIniciado=True), "em_breve"),
    (dict(recebendoProposta=True, recebimentoPropostaConcluido=True), "encerrado"),  # concluído vence
])
def test_status_a_partir_de_sinais_explicitos(sinais, esperado):
    assert parse_programa(_base(**sinais))["status_edital"] == esperado


@pytest.mark.parametrize("mutacao", [
    lambda d: _sem(d, "recebendoProposta", "recebimentoPropostaConcluido", "recebimentoPropostaNaoIniciado"),
    lambda d: d.update(recebendoProposta=False),                    # tudo falso
    lambda d: _sem(d, "recebendoProposta"),                          # sem o sinal de 'aberto'
    lambda d: d.update(recebendoProposta="true"),                    # string não é booleano
    lambda d: d.update(recebendoProposta=None),
], ids=["sem-campos", "tudo-falso", "sem-recebendo", "string", "null"])
def test_status_indeterminado_nunca_vira_aberto(mutacao):
    d = _base()
    mutacao(d)
    with pytest.raises(ValueError, match="status indeterminado"):
        parse_programa(d)


# ---------- prazo ----------

def test_janela_esp_completa_tem_prioridade():
    d = _base(dtaInicioRecebPropParlamentar="2026-06-01", dtaFimRecebPropParlamentar="2026-06-30")
    r = parse_programa(d)
    assert (r["data_inicio_inscricao"], r["data_fim_inscricao"]) == ("2026-11-01", "2026-11-30")


def test_so_janela_parlamentar():
    d = _sem(_base(dtaInicioRecebPropParlamentar="2026-06-01", dtaFimRecebPropParlamentar="2026-06-30"),
             "dtaInicioRecebPropEsp", "dtaFimRecebPropEsp")
    r = parse_programa(d)
    assert (r["data_inicio_inscricao"], r["data_fim_inscricao"]) == ("2026-06-01", "2026-06-30")


def test_nunca_mistura_inicio_de_uma_janela_com_fim_de_outra():
    d = _base(dtaFimRecebPropEsp=None, dtaInicioRecebPropParlamentar=None, dtaFimRecebPropParlamentar="2026-12-31")
    r = parse_programa(d)  # início só na Esp, fim só na Parlamentar
    assert (r["data_inicio_inscricao"], r["data_fim_inscricao"]) == (None, "2026-12-31")


def test_janela_so_com_fim_mantem_o_fim():
    r = parse_programa(_base(dtaInicioRecebPropEsp=None))
    assert (r["data_inicio_inscricao"], r["data_fim_inscricao"]) == (None, "2026-11-30")


def test_janela_so_com_inicio_e_sem_datas():
    r = parse_programa(_base(dtaFimRecebPropEsp=None))
    assert (r["data_inicio_inscricao"], r["data_fim_inscricao"]) == ("2026-11-01", None)
    r = parse_programa(_sem(_base(), "dtaInicioRecebPropEsp", "dtaFimRecebPropEsp"))
    assert (r["data_inicio_inscricao"], r["data_fim_inscricao"]) == (None, None)


# ---------- nulos e formatos ----------

@pytest.mark.parametrize("chave", ["unidade", "areasAtuacao", "atendidos", "ufsHabilitadas", "objetivo", "problema", "resultadoEsperado"])
def test_campos_nulos_nao_quebram(chave):
    r = parse_programa(_base(**{chave: None}))
    assert r["codigo_origem"] == "202600001"


def test_listas_ignoram_itens_invalidos():
    r = parse_programa(_base(atendidos=[None, "x", {"descricao": ""}, {"descricao": "ONG"}], areasAtuacao="texto"))
    assert r["proponentes_elegiveis"] == ["ONG"] and r["areas_atuacao"] == []


def test_ufs_que_nao_e_lista_vira_lista_vazia():
    assert parse_programa(_base(ufsHabilitadas="SP"))["ufs_elegiveis"] == []


def test_texto_bruto_sem_espacos_duplicados_e_titulo_normalizado():
    r = parse_programa(_base(problema="", objetivo="  A  ", nome="  Título  "))
    assert r["texto_bruto"] == "A R" and r["titulo"] == "Título"


def test_saida_tem_exatamente_as_chaves_do_contrato():
    assert tuple(parse_programa(_base())) == CAMPOS_SAIDA


# ---------- tipos de entrada ----------

def test_aceita_texto_e_bytes_json():
    esperado = parse_programa(_base())
    assert parse_programa(json.dumps(_base())) == esperado
    assert parse_programa(json.dumps(_base(nome="Programação")).encode("utf-8"))["titulo"] == "Programação"


@pytest.mark.parametrize("entrada", ["não é json", b"\xff\xfe", "[1, 2]", [1, 2], None, 42])
def test_entrada_invalida_levanta_valueerror(entrada):
    with pytest.raises(ValueError):
        parse_programa(entrada)


# ---------- integração parse -> banco ----------

def test_em_breve_chega_ao_banco(conn):
    d = _base(recebendoProposta=False, recebimentoPropostaNaoIniciado=True)
    assert processar_programa(conn, FONTE, d) == "inserido"
    assert conn.execute("SELECT status_edital FROM editais").fetchone()[0] == "em_breve"


def test_aberto_para_encerrado_atualiza_o_banco(conn):
    assert processar_programa(conn, FONTE, _base()) == "inserido"
    fechado = _base(recebendoProposta=False, recebimentoPropostaConcluido=True)  # prazo e texto iguais
    assert processar_programa(conn, FONTE, fechado) == "atualizado"
    assert conn.execute("SELECT status_edital FROM editais").fetchone()[0] == "encerrado"


def test_mesmo_snapshot_duas_vezes_e_inalterado(conn):
    processar_programa(conn, FONTE, _base())
    assert processar_programa(conn, FONTE, _base()) == "inalterado"


def test_status_indeterminado_nao_grava_nada(conn):
    with pytest.raises(ValueError):
        processar_programa(conn, FONTE, _sem(_base(), "recebendoProposta"))
    assert conn.execute("SELECT COUNT(*) FROM editais").fetchone()[0] == 0
