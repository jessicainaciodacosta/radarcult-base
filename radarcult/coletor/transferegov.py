"""Coletor Playwright do Transferegov (spec-002, fase B).

Fluxo de um ciclo:
  1. consulta o robots.txt (aborta se bloquear ou se não puder ser lido por erro 5xx/rede);
  2. abre o portal no navegador (cookies e XSRF vêm da própria aplicação — spike-001 §2);
  3. lista os programas (POST listarComFiltro, paginado) com a sessão do navegador;
  4. para cada programa candidato, navega até a página de detalhe e INTERCEPTA a resposta
     JSON `GET .../programa/{id}`; se a interceptação não ocorrer, busca o mesmo JSON com
     `fetch` dentro da página (fallback, contabilizado no resumo);
  5. entrega o JSON a `processar_programa()` (parse → upsert). Falha em um item NÃO derruba
     o ciclo; 403/429, formato inesperado da listagem ou erros em sequência abortam.

NÃO verificado contra o portal real (a rede do ambiente de desenvolvimento não alcança o
Transferegov — spike-001 §1). Ver `tests/test_coletor_transferegov.py` para o que foi
testado (servidor local simulado) e o `CONTEXTO.md` para o que fica para o primeiro ciclo
real na máquina do dono. Hipóteses a confirmar no primeiro ciclo: a rota
`/ep-atos-prep-web/consultar-programa/{id}` dispara a chamada de detalhe; `currentPage`
começa em 1; o campo `recebendoProposta` existe na listagem.

Uso:  python -m radarcult.coletor.transferegov --db radarcult.db
Saída: resumo em JSON no stdout; logs no stderr.
Código de saída: 0 = ciclo completo sem erros; 1 = terminou, mas com erros de item ou
listagem incompleta; 2 = ciclo abortado (nada garantido sobre o estado da coleta).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from radarcult import database
from radarcult.coletor.parse import processar_programa

log = logging.getLogger("radarcult.coletor")

FONTE = "Transferegov"
BASE_PADRAO = "https://parcerias.transferegov.sistema.gov.br"
HOME = "/ep-atos-prep-web/home"
PAGINA_DETALHE = "/ep-atos-prep-web/consultar-programa/{id}"
API = "/ep/api/atos-prep"
API_SEG = "/ep/api/seguranca"
# Campos pedidos na listagem (a própria página do portal pede estes, capturado em 05/11/2026).
CAMPOS_LISTAGEM = ("id,codigo,nome,ano,situacao,unidade(id,tipo,nome,descricaoPadrao,situacao,codigoSiorg),"
                   "recebendoProposta,recebimentoPropostaNaoIniciado,recebimentoPropostaConcluido,"
                   "isPropostaViaSistemaExterno")
_CONTADOR = {"inserido": "inseridos", "atualizado": "atualizados", "inalterado": "inalterados"}


class AbortarCiclo(Exception):
    """Condição que interrompe o ciclo inteiro (403/429, formato inesperado, robots...)."""


class ErroItem(Exception):
    """Falha ao obter/processar UM programa; o ciclo segue para o próximo."""


@dataclass
class Config:
    base_url: str = BASE_PADRAO
    user_agent: str = "RadarCult/0.1 (coleta pessoal de editais; baixa frequência)"
    pagesize: int = 10   # o portal real lista 10 por página (observado); não sei se aceita mais
    max_paginas: int = 20
    apenas_recebendo: bool = True
    interceptar: bool = True
    respeitar_robots: bool = True
    pausa_s: float = 1.5
    timeout_ms: int = 30_000
    tentativas: int = 3
    espera_retry_s: float = 1.0
    max_erros_consecutivos: int = 5
    headless: bool = True


@dataclass
class Resumo:
    robots: str = ""
    paginas_lidas: int = 0
    listados: int = 0
    candidatos: int = 0
    inseridos: int = 0
    atualizados: int = 0
    inalterados: int = 0
    interceptados: int = 0
    via_fallback: int = 0
    listagem_completa: bool = False
    total_informado: int | None = None   # `pagina.totalResults` do portal; base do 'completo'
    erros: list = field(default_factory=list)
    abortado: str | None = None

    def codigo_saida(self) -> int:
        if self.abortado:
            return 2
        if self.erros or not self.listagem_completa:
            return 1
        return 0


_JS_FETCH = """
async ({url, metodo, corpo, xsrf}) => {
  const headers = {'Accept': 'application/json'};
  if (corpo !== null) headers['Content-Type'] = 'application/json';
  if (xsrf) headers['X-XSRF-TOKEN'] = xsrf;
  const r = await fetch(url, {
    method: metodo, credentials: 'include', headers,
    body: corpo !== null ? JSON.stringify(corpo) : undefined,
  });
  return {status: r.status, texto: await r.text()};
}
"""


async def _token(context) -> str | None:
    for c in await context.cookies():
        if c["name"] == "XSRF-TOKEN":
            return c["value"]
    return None


async def _chamar(page, cfg: Config, metodo: str, caminho: str, corpo=None):
    """Chama a API do portal com a sessão do navegador. Devolve o JSON decodificado."""
    ultima = "sem resposta"
    for tentativa in range(1, cfg.tentativas + 1):
        r = await page.evaluate(
            _JS_FETCH,
            {"url": caminho, "metodo": metodo, "corpo": corpo, "xsrf": await _token(page.context)},
        )
        status = r["status"]
        if status in (403, 429):
            raise AbortarCiclo(f"HTTP {status} em {caminho}: ciclo interrompido (spec-002)")
        if status >= 500:
            ultima = f"HTTP {status} em {caminho}"
            if tentativa < cfg.tentativas:
                await asyncio.sleep(cfg.espera_retry_s * 2 ** (tentativa - 1))
                continue
            raise ErroItem(f"{ultima} após {cfg.tentativas} tentativas")
        if status >= 400:
            raise ErroItem(f"HTTP {status} em {caminho}")
        try:
            return json.loads(r["texto"])
        except json.JSONDecodeError as exc:
            raise ErroItem(f"resposta de {caminho} não é JSON ({exc})") from exc
    raise ErroItem(ultima)


async def verificar_robots(context, cfg: Config) -> tuple[bool, str]:
    """Consulta o robots.txt. Devolve (permitido, motivo). 4xx = sem robots (permitido);
    5xx ou erro de rede = não prosseguir (RFC 9309, conservador)."""
    url = cfg.base_url.rstrip("/") + "/robots.txt"
    try:
        resp = await context.request.get(url, timeout=cfg.timeout_ms)
    except Exception as exc:  # noqa: BLE001 — qualquer falha de rede conta como inacessível
        return False, f"robots.txt inacessível ({type(exc).__name__}); ciclo abortado por precaução"
    if resp.status >= 500:
        return False, f"robots.txt respondeu HTTP {resp.status}; ciclo abortado por precaução"
    if resp.status >= 400:
        return True, f"sem robots.txt (HTTP {resp.status})"
    if "html" in resp.headers.get("content-type", "").lower():
        return True, "robots.txt devolveu HTML (provável SPA); tratado como inexistente — confira manualmente"
    rp = RobotFileParser()
    rp.parse((await resp.text()).splitlines())
    testados = [HOME, PAGINA_DETALHE.format(id=0), f"{API}/programa/listarComFiltro", f"{API}/programa/0"]
    bloqueados = [c for c in testados if not rp.can_fetch(cfg.user_agent, cfg.base_url.rstrip("/") + c)]
    if bloqueados:
        return False, f"robots.txt proíbe: {', '.join(bloqueados)}"
    return True, "robots.txt consultado: caminhos usados permitidos"


async def preparar_sessao(page, cfg: Config) -> None:
    """Abre o portal e garante o cookie XSRF (bootstrap do spike-001 §2)."""
    from playwright.async_api import Error as PlaywrightError

    try:
        await page.goto(cfg.base_url.rstrip("/") + HOME, wait_until="domcontentloaded", timeout=cfg.timeout_ms)
    except PlaywrightError as exc:
        raise AbortarCiclo(
            f"falha ao abrir o portal ({str(exc).splitlines()[0]}). "
            "Rode da máquina do dono: o spike-001 registrou bloqueios de rede em outros ambientes."
        ) from exc
    for _ in range(20):
        if await _token(page.context):
            return
        await asyncio.sleep(0.25)
    try:  # bootstrap explícito, como no spike
        await _chamar(page, cfg, "GET", f"{API_SEG}/auth/configuration")
    except ErroItem as exc:
        raise AbortarCiclo(f"bootstrap do XSRF falhou: {exc}") from exc
    if not await _token(page.context):
        raise AbortarCiclo("o portal não entregou o cookie XSRF-TOKEN")


async def listar_programas(page, cfg: Config, resumo: Resumo) -> tuple[list[dict], bool]:
    """Lê a listagem paginada. Devolve (entidades, completa).

    O portal pagina com `pagesize` e `currentpage` (minúsculas, 1-based) na URL E no corpo,
    como a própria página faz (capturado em 05/11/2026; `currentPage` é ignorado). A resposta
    traz `pagina.totalResults`. `completa` só é True quando o total de itens distintos lidos
    alcança `totalResults` (ou, sem esse campo, quando uma página vem vazia). Página repetida
    antes de atingir o total é ERRO: o ciclo aborta (antes virava 'completo' sem aviso).
    """
    vistos: dict = {}
    for pagina in range(1, cfg.max_paginas + 1):
        corpo = {"pagesize": cfg.pagesize, "currentpage": pagina, "idUnidade": None,
                 "idParametrizacaoEsteira": None, "fields": CAMPOS_LISTAGEM}
        caminho = f"{API}/programa/listarComFiltro?pagesize={cfg.pagesize}&currentpage={pagina}"
        try:
            dados = await _chamar(page, cfg, "POST", caminho, corpo)
        except ErroItem as exc:
            raise AbortarCiclo(f"listagem, página {pagina}: {exc}") from exc
        if not isinstance(dados, dict) or not isinstance(dados.get("entidades"), list):
            raise AbortarCiclo("formato da listagem inesperado (esperado {'entidades': [...]}); o portal pode ter mudado")
        resumo.paginas_lidas += 1
        info = dados.get("pagina")
        total = info.get("totalResults") if isinstance(info, dict) else None
        if isinstance(total, int):
            resumo.total_informado = total
        itens = [e for e in dados["entidades"] if isinstance(e, dict)]
        novos = [e for e in itens if e.get("id") not in vistos]
        for e in novos:
            vistos[e["id"]] = e
        if resumo.total_informado is not None and len(vistos) >= resumo.total_informado:
            return list(vistos.values()), True
        if not novos:
            if not itens and resumo.total_informado is None:
                return list(vistos.values()), True  # sem totalResults: página vazia encerra
            raise AbortarCiclo(
                f"paginação não avançou na página {pagina} (itens repetidos ou página vazia) com "
                f"{len(vistos)} de {resumo.total_informado} programas lidos; o portal pode ter mudado")
        await asyncio.sleep(cfg.pausa_s)
    completa = resumo.total_informado is not None and len(vistos) >= resumo.total_informado
    return list(vistos.values()), completa


def _eh_detalhe(url: str, prog_id) -> bool:
    return urlparse(url).path.endswith(f"{API}/programa/{prog_id}")


async def obter_detalhe(page, cfg: Config, prog_id) -> tuple[dict, str]:
    """Obtém o JSON do programa. Devolve (dados, modo) com modo em {'interceptado','fallback'}."""
    from playwright.async_api import Error as PlaywrightError

    dados, modo = None, "fallback"
    if cfg.interceptar:
        url = cfg.base_url.rstrip("/") + PAGINA_DETALHE.format(id=prog_id)
        try:
            async with page.expect_response(
                lambda r: r.request.method == "GET" and _eh_detalhe(r.url, prog_id),
                timeout=cfg.timeout_ms,
            ) as info:
                await page.goto(url, wait_until="domcontentloaded", timeout=cfg.timeout_ms)
            resposta = await info.value
            if resposta.status == 200:
                dados, modo = await resposta.json(), "interceptado"
        except (PlaywrightError, ValueError) as exc:  # timeout, navegação ou JSON inválido
            log.info("programa %s: interceptação não ocorreu (%s); usando fallback", prog_id, type(exc).__name__)
    if dados is None:
        dados = await _chamar(page, cfg, "GET", f"{API}/programa/{prog_id}")
    if not isinstance(dados, dict) or str(dados.get("id")) != str(prog_id) or not dados.get("codigo"):
        raise ErroItem(f"detalhe do programa {prog_id} sem id/codigo esperados; formato pode ter mudado")
    return dados, modo


async def _ciclo(conn, cfg: Config, pw) -> Resumo:
    resumo = Resumo()
    browser = await pw.chromium.launch(headless=cfg.headless)
    try:
        context = await browser.new_context(user_agent=cfg.user_agent, locale="pt-BR", timezone_id="America/Sao_Paulo")
        context.set_default_timeout(cfg.timeout_ms)
        page = await context.new_page()

        if cfg.respeitar_robots:
            permitido, resumo.robots = await verificar_robots(context, cfg)
            if not permitido:
                raise AbortarCiclo(resumo.robots)
        else:
            resumo.robots = "verificação de robots.txt desligada por configuração"

        await preparar_sessao(page, cfg)
        entidades, resumo.listagem_completa = await listar_programas(page, cfg, resumo)
        resumo.listados = len(entidades)
        if not entidades:
            raise AbortarCiclo("listagem vazia: portal sem programas ou formato mudou; nada foi alterado")

        if cfg.apenas_recebendo:
            if not any("recebendoProposta" in e for e in entidades):
                raise AbortarCiclo("listagem sem o campo 'recebendoProposta'; o portal pode ter mudado")
            candidatos = [e for e in entidades if e.get("recebendoProposta") is True]
        else:
            candidatos = entidades
        resumo.candidatos = len(candidatos)

        seguidos = 0
        for e in candidatos:
            pid = e["id"]
            try:
                dados, modo = await obter_detalhe(page, cfg, pid)
                resultado = processar_programa(conn, FONTE, dados)
                resumo.interceptados += modo == "interceptado"
                resumo.via_fallback += modo == "fallback"
                contador = _CONTADOR[resultado]
                setattr(resumo, contador, getattr(resumo, contador) + 1)
                seguidos = 0
            except AbortarCiclo:
                raise
            except Exception as exc:  # noqa: BLE001 — falha de item não derruba o ciclo
                resumo.erros.append({"id": pid, "erro": f"{type(exc).__name__}: {exc}"})
                log.warning("programa %s: %s", pid, exc)
                seguidos += 1
                if seguidos >= cfg.max_erros_consecutivos:
                    raise AbortarCiclo(f"{seguidos} erros seguidos; o portal pode ter mudado") from exc
            await asyncio.sleep(cfg.pausa_s)
    except AbortarCiclo as exc:
        resumo.abortado = str(exc)
        log.error("ciclo abortado: %s", exc)
    finally:
        await browser.close()
    return resumo


async def coletar(conn, cfg: Config | None = None) -> Resumo:
    """Executa um ciclo de coleta. `conn` deve vir de `database.connect` com migrações aplicadas."""
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        return await _ciclo(conn, cfg or Config(), pw)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Coletor Transferegov (spec-002)")
    ap.add_argument("--db", default=os.environ.get("DATABASE_PATH", "radarcult.db"))
    ap.add_argument("--base-url", default=BASE_PADRAO)
    ap.add_argument("--pagesize", type=int, default=Config.pagesize)
    ap.add_argument("--max-paginas", type=int, default=Config.max_paginas)
    ap.add_argument("--pausa", type=float, default=Config.pausa_s, help="segundos entre requisições")
    ap.add_argument("--todos", action="store_true", help="inclui programas que não estão recebendo propostas")
    ap.add_argument("--sem-interceptar", action="store_true", help="usa só fetch, sem navegar até o detalhe")
    ap.add_argument("--visivel", action="store_true", help="abre o navegador (depuração)")
    ap.add_argument("--contato", default="", help="e-mail/URL de contato anexado ao User-Agent")
    a = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(levelname)s %(message)s")
    cfg = Config(base_url=a.base_url, pagesize=a.pagesize, max_paginas=a.max_paginas, pausa_s=a.pausa,
                 apenas_recebendo=not a.todos, interceptar=not a.sem_interceptar, headless=not a.visivel)
    if a.contato:
        cfg.user_agent += f" contato: {a.contato}"

    conn = database.connect(Path(a.db))
    try:
        database.aplicar_migracoes(conn)
        resumo = asyncio.run(coletar(conn, cfg))
    finally:
        conn.close()
    print(json.dumps(asdict(resumo), ensure_ascii=False, indent=2))
    return resumo.codigo_saida()


if __name__ == "__main__":
    sys.exit(main())
