"""Parser do Transferegov (spec-002).

`parse_programa` é uma função PURA: recebe o JSON de detalhe de um programa (dict, str ou bytes)
e devolve um dict com as chaves de `CAMPOS_SAIDA`. Sem rede, sem banco. É o que o harness
offline exercita. `processar_programa` = parse → upsert no banco.

Regras (baseadas em 3 programas reais, todos encerrados; ver CONTEXTO.md):

status_edital — decidido só por sinais explícitos do portal; NUNCA assume 'aberto':
  1. recebimentoPropostaConcluido verdadeiro  -> 'encerrado'
  2. recebimentoPropostaNaoIniciado verdadeiro -> 'em_breve'
  3. recebendoProposta verdadeiro (`is True`)  -> 'aberto'
  4. qualquer outro caso -> ValueError (status indeterminado): o item vira erro na coleta em
     vez de entrar no banco como aberto e disparar alertas. O significado dos campos é inferido
     pelo nome; 'cancelado' não é produzido porque os valores de `situacao` para cancelamento
     nunca foram vistos.

Prazo — usa UMA janela do portal, nunca mistura início de uma com fim de outra:
  1. janela 'Esp' completa (início e fim); 2. janela 'Parlamentar' completa;
  3. a primeira janela que tenha só o fim (guarda o fim, pois é o prazo que gera alertas);
  4. a primeira que tenha só o início; 5. nada -> (None, None).
  Quando as duas janelas estão completas, vale a 'Esp'. HIPÓTESE não confirmada: é a que
  corresponde a chamada aberta a proponentes espontâneos; conferir no portal.

Formato dos valores:
- datas: 'YYYY-MM-DD' como o portal entrega (não validadas) ou None;
- ufs_elegiveis, proponentes_elegiveis, areas_atuacao: listas (vazia = o portal não informou;
  NÃO significa "nenhuma UF"). Os itens de ufsHabilitadas passam como vierem: formato não visto;
- url_origem: link do programa (padrão de URL não verificado contra o portal).
"""
from __future__ import annotations

import json

URL_BASE = "https://parcerias.transferegov.sistema.gov.br"
URL_DETALHE = URL_BASE + "/ep-atos-prep-web/consultar-programa/{id}"
JANELAS = ("Esp", "Parlamentar")

CAMPOS_SAIDA = (
    "codigo_origem",
    "titulo",
    "orgao_emissor",
    "url_origem",
    "data_inicio_inscricao",
    "data_fim_inscricao",
    "ufs_elegiveis",
    "proponentes_elegiveis",
    "areas_atuacao",
    "texto_bruto",
    "status_edital",
)


def _como_dict(snapshot) -> dict:
    if isinstance(snapshot, (str, bytes)):
        try:
            snapshot = json.loads(snapshot)
        except ValueError as exc:  # JSONDecodeError e UnicodeDecodeError herdam de ValueError
            raise ValueError("snapshot não é JSON válido") from exc
    if not isinstance(snapshot, dict):
        raise ValueError(f"snapshot inválido: esperado objeto JSON, recebeu {type(snapshot).__name__}")
    return snapshot


def _lista(data: dict, chave: str, campo: str) -> list:
    """Valores de `campo` nos itens de `data[chave]`; tolera null, itens que não são objeto e campos vazios."""
    itens = data.get(chave)
    if not isinstance(itens, list):
        return []
    return [i[campo] for i in itens if isinstance(i, dict) and i.get(campo)]


def _janela_inscricao(data: dict) -> tuple:
    janelas = [(data.get(f"dtaInicioRecebProp{s}"), data.get(f"dtaFimRecebProp{s}")) for s in JANELAS]
    for inicio, fim in janelas:
        if inicio and fim:
            return inicio, fim
    for inicio, fim in janelas:
        if fim:
            return inicio, fim
    for inicio, fim in janelas:
        if inicio:
            return inicio, None
    return None, None


def _status(data: dict) -> str:
    if data.get("recebimentoPropostaConcluido"):
        return "encerrado"
    if data.get("recebimentoPropostaNaoIniciado"):
        return "em_breve"
    if data.get("recebendoProposta") is True:
        return "aberto"
    raise ValueError(
        f"status indeterminado no programa {data.get('codigo')!r}: nenhum sinal explícito de "
        "recebimento de propostas (concluído / não iniciado / recebendo)"
    )


def parse_programa(snapshot: str | bytes | dict) -> dict:
    """Converte o JSON de detalhe de um programa nos campos de `CAMPOS_SAIDA`."""
    data = _como_dict(snapshot)

    codigo = data.get("codigo")
    prog_id = data.get("id")
    unidade = data.get("unidade")
    inicio, fim = _janela_inscricao(data)
    ufs = data.get("ufsHabilitadas")
    partes = (data.get("objetivo"), data.get("problema"), data.get("resultadoEsperado"))

    return {
        "codigo_origem": str(codigo) if codigo else None,
        "titulo": (data.get("nome") or "").strip() or None,
        "orgao_emissor": unidade.get("nome") if isinstance(unidade, dict) else None,
        "url_origem": URL_DETALHE.format(id=prog_id) if prog_id else None,
        "data_inicio_inscricao": inicio,
        "data_fim_inscricao": fim,
        "ufs_elegiveis": list(ufs) if isinstance(ufs, list) else [],
        "proponentes_elegiveis": _lista(data, "atendidos", "descricao"),
        "areas_atuacao": _lista(data, "areasAtuacao", "nome"),
        "texto_bruto": " ".join(p.strip() for p in partes if isinstance(p, str) and p.strip()),
        "status_edital": _status(data),
    }


def processar_programa(conn, fonte_nome: str, snapshot: str | bytes | dict) -> str:
    """Processa um programa completo: parse → upsert no banco.

    Devolve o resultado do upsert: 'inserido', 'inalterado' ou 'atualizado'.
    Levanta ValueError se o snapshot for inválido ou o status for indeterminado
    (nada é gravado nesse caso).
    """
    from radarcult.database import garantir_fonte, upsert_edital

    dados = parse_programa(snapshot)  # antes de tocar no banco: erro de parse não deixa rastro
    garantir_fonte(conn, fonte_nome, URL_BASE, "scraping_playwright")
    return upsert_edital(conn, fonte_nome, {**dados, "dados_brutos_json": None})
