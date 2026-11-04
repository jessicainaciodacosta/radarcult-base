# Fixtures do Transferegov (spec-002)

Cada caso = uma pasta `fixtures/transferegov/<caso>/` com `snapshot.json` (ou `snapshot.html`)
e `expected.json`. Use `_modelo/` como ponto de partida.

## Casos mínimos sugeridos (sugestão, não vem de spec)

| Caso | Para quê |
|---|---|
| `com-prazo` | Caminho feliz: prazo de início e fim preenchidos |
| `prazo-prorrogado-v1` / `-v2` | Mesmo programa em duas versões; testa a retificação (spec-001 §3.1) |
| `sem-prazo` | Fonte não informa prazo: `data_fim_inscricao` nulo |
| `encerrado` | Situação diferente de aberto |
| `restrito-uf` | `ufs_elegiveis` com poucas UFs |
| `cultural` | Programa de Cultura/Direitos Humanos/Assistência |

## Antes de capturar

- Consultar o `robots.txt` do portal e anotar o resultado (spec-000 §7).
- Capturar da máquina do dono: o spike-001 registrou bloqueios de rede em outros ambientes.

## Privacidade e git

O `.gitignore` deste projeto **ignora `snapshot.*`** por padrão e versiona só `expected.json`
e este README. Motivo: o snapshot pode conter o texto integral do edital, e a spec-000 §7
proíbe republicá-lo; os termos de reuso do Transferegov não foram verificados. Se o
repositório for **privado** e você quiser versionar os snapshots, remova a regra
`fixtures/transferegov/*/snapshot.*` do `.gitignore`.
