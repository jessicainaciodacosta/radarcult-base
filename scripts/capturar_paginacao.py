"""Observa o que a PRÓPRIA página do Transferegov envia ao listar/paginar programas.

Abre um navegador VISÍVEL. Você navega à mão até a lista de programas e troca de página;
o script só imprime, para cada chamada a `listarComFiltro`: o corpo enviado, a URL e o
bloco `pagina` da resposta. Não imprime cabeçalhos nem cookies e não grava nada.
Uso: python scripts/capturar_paginacao.py     (encerra com Enter ou após 5 minutos)
"""
import argparse
import asyncio
import json

from radarcult.coletor.transferegov import BASE_PADRAO, HOME, Config


async def main(base_url: str, limite_s: int) -> None:
    from playwright.async_api import async_playwright

    cfg = Config(base_url=base_url)
    contador = {"n": 0}

    async def ao_responder(resp):
        req = resp.request
        if "listarComFiltro" not in req.url:
            return
        contador["n"] += 1
        try:
            dados = await resp.json()
            pagina = dados.get("pagina") if isinstance(dados, dict) else None
            ids = [e.get("id") for e in dados.get("entidades", [])] if isinstance(dados, dict) else []
        except Exception as exc:  # noqa: BLE001
            pagina, ids = f"(resposta ilegível: {exc})", []
        print(f"\n--- chamada {contador['n']}: {req.method} {req.url}")
        print("    corpo enviado:", req.post_data)
        print("    bloco 'pagina' da resposta:", json.dumps(pagina, ensure_ascii=False))
        print("    ids:", ids)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        try:
            ctx = await browser.new_context(user_agent=cfg.user_agent, locale="pt-BR")
            page = await ctx.new_page()
            page.on("response", lambda r: asyncio.ensure_future(ao_responder(r)))
            await page.goto(base_url.rstrip("/") + HOME, wait_until="domcontentloaded")
            print("Navegador aberto. No portal, vá até a LISTA de programas (consulta de programas),")
            print("troque para a página 2 e depois para a 3. Quando terminar, volte aqui e aperte Enter.")
            try:
                await asyncio.wait_for(asyncio.to_thread(input), timeout=limite_s)
            except (asyncio.TimeoutError, EOFError):
                print("(encerrado: tempo esgotado ou sem entrada)")
        finally:
            await browser.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=BASE_PADRAO)
    ap.add_argument("--limite", type=int, default=300, help="segundos de espera")
    a = ap.parse_args()
    asyncio.run(main(a.base_url, a.limite))
