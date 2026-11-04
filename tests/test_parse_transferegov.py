"""Harness do parser do Transferegov (spec-002).

Cada caso é uma pasta em `fixtures/transferegov/<caso>/` com:
  - `snapshot.json` ou `snapshot.html`  (o que foi capturado do portal)
  - `expected.json`                      (valores esperados do parse)
Pastas que começam com "_" (ex.: `_modelo`) são ignoradas.

Sem nenhuma fixture, os testes aparecem como "skipped". Com fixtures e `parse_programa`
ainda não implementado, falham (vermelho) — é o ponto de partida do HDD.
"""
import json
from pathlib import Path

import pytest

from radarcult.coletor.parse import CAMPOS_SAIDA, parse_programa

PASTA = Path(__file__).resolve().parent.parent / "fixtures" / "transferegov"
SNAPSHOTS = ("snapshot.json", "snapshot.html")


def _casos():
    if not PASTA.exists():
        return []
    casos = []
    for pasta in sorted(PASTA.iterdir()):
        if not pasta.is_dir() or pasta.name.startswith("_"):
            continue
        snapshot = next((pasta / n for n in SNAPSHOTS if (pasta / n).exists()), None)
        esperado = pasta / "expected.json"
        if snapshot and esperado.exists():
            casos.append(pytest.param(snapshot, esperado, id=pasta.name))
    return casos


def _ler_snapshot(caminho: Path):
    if caminho.suffix == ".json":
        return json.loads(caminho.read_text(encoding="utf-8"))
    return caminho.read_text(encoding="utf-8")


@pytest.mark.parametrize("snapshot,esperado", _casos())
def test_parse_programa(snapshot, esperado):
    resultado = parse_programa(_ler_snapshot(snapshot))
    esperado_dict = json.loads(esperado.read_text(encoding="utf-8"))

    # Regra de ouro (spec-000 §2): todo registro carrega o link do edital original.
    assert resultado.get("url_origem"), "url_origem ausente"

    # Todo campo de saída precisa ter valor esperado: o que não está no expected.json escapa do teste.
    faltando = [c for c in CAMPOS_SAIDA if c not in esperado_dict]
    assert not faltando, f"expected.json sem os campos {faltando}"

    for campo, valor in esperado_dict.items():
        if campo.startswith("_"):  # comentários do modelo
            continue
        assert resultado.get(campo) == valor, f"campo {campo!r} divergiu"
