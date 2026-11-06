"""Mapa SOMENTE LEITURA da listagem do Transferegov (não grava no banco, não abre detalhes).

Lê a lista completa (cerca de 10 chamadas, com pausa), salva `saidas/listagem.json` e imprime:
quantos programas estão recebendo propostas / não iniciados / concluídos, e quais títulos
mencionam temas culturais. Serve para medir a cobertura cultural da fonte.
Uso (raiz do projeto, venv ativo):  python scripts/mapear_listagem.py
"""
import argparse
import asyncio
import json
import re
from collections import Counter
from pathlib import Path

from radarcult.coletor.transferegov import BASE_PADRAO, Config, Resumo, listar_programas, preparar_sessao

TEMAS = re.compile(r"cultur|arte|art[ií]stic|patrim[oô]nio|museu|cinema|audiovisual|m[uú]sic|teatr|dan[cç]a|"
                   r"livro|leitura|bibliotec|folclor|carnaval|circo|ind[ií]gen|quilomb|afro", re.I)


def _estado(e: dict) -> str:
    if e.get("recebendoProposta") is True:
        return "recebendo propostas"
    if e.get("recebimentoPropostaNaoIniciado") is True:
        return "não iniciado"
    if e.get("recebimentoPropostaConcluido") is True:
        return "concluído"
    return "indeterminado"


async def main(base_url: str, pausa: float, saida: Path) -> None:
    from playwright.async_api import async_playwright

    cfg = Config(base_url=base_url, pausa_s=pausa)
    resumo = Resumo()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context(user_agent=cfg.user_agent, locale="pt-BR")
            page = await ctx.new_page()
            await preparar_sessao(page, cfg)
            entidades, completa = await listar_programas(page, cfg, resumo)
        finally:
            await browser.close()

    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(entidades, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"listados: {len(entidades)} | total informado: {resumo.total_informado} | completa: {completa}")
    print("por estado:", dict(Counter(_estado(e) for e in entidades)))
    print(f"\nTítulos com termos culturais ({TEMAS.pattern[:20]}...):")
    achou = False
    for e in entidades:
        nome = e.get("nome") or ""
        if TEMAS.search(nome):
            achou = True
            print(f"  [{_estado(e)}] {e.get('codigo')} | {nome} | {(e.get('unidade') or {}).get('nome')}")
    if not achou:
        print("  (nenhum título menciona os termos buscados)")
    print("\nÓrgãos (unidade) mais frequentes:")
    for nome, n in Counter(((e.get("unidade") or {}).get("nome") or "?") for e in entidades).most_common(8):
        print(f"  {n:3d}  {nome}")
    print(f"\nLista completa salva em {saida}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=BASE_PADRAO)
    ap.add_argument("--pausa", type=float, default=2.0)
    ap.add_argument("--saida", type=Path, default=Path("saidas/listagem.json"))
    a = ap.parse_args()
    asyncio.run(main(a.base_url, a.pausa, a.saida))
