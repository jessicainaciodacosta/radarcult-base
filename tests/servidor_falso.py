"""Servidor HTTP local que SIMULA os endpoints do Transferegov descritos no spike-001 §2.

Serve para testar o coletor offline. NÃO é o portal real: o comportamento (XSRF, paginação,
rota da página de detalhe) é o que o spike e o parse.py permitem supor, nada além disso.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CAMPOS_LISTAGEM = ("id", "codigo", "nome", "ano", "situacao", "unidade", "recebendoProposta")


class Estado:
    def __init__(self, programas: dict, robots: str | None = None):
        self.programas = programas          # id -> JSON de detalhe (ordem de inserção = ordem da lista)
        self.robots = robots                # None => 404
        self.robots_status = None           # força um status (ex.: 503)
        self.listagem_status = 200
        self.listagem_vazia = False
        self.detalhe_falha: set = set()     # ids cujo detalhe responde 500
        self.pagina_sem_api = False         # página de detalhe NÃO chama a API (força o fallback)
        self.token = "tok-simulado-123"
        self.requisicoes: list = []         # (metodo, caminho, tinha_token_valido)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silencioso
        pass

    @property
    def estado(self) -> Estado:
        return self.server.estado

    def _enviar(self, status, corpo, tipo="application/json", extra=None):
        dados = corpo if isinstance(corpo, bytes) else (
            json.dumps(corpo, ensure_ascii=False).encode() if tipo == "application/json" else corpo.encode()
        )
        self.send_response(status)
        self.send_header("Content-Type", f"{tipo}; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self):  # noqa: N802
        e, p = self.estado, self.path.split("?")[0]
        e.requisicoes.append(("GET", p, None))
        if p == "/robots.txt":
            if e.robots_status:
                return self._enviar(e.robots_status, "erro", "text/plain")
            if e.robots is None:
                return self._enviar(404, "nao existe", "text/plain")
            return self._enviar(200, e.robots, "text/plain")
        if p == "/ep-atos-prep-web/home":
            return self._enviar(200, "<html><body>home<script>fetch('/ep/api/seguranca/auth/configuration',"
                                     "{credentials:'include'})</script></body></html>", "text/html")
        if p.startswith("/ep-atos-prep-web/consultar-programa/"):
            pid = p.rsplit("/", 1)[1]
            script = "" if e.pagina_sem_api else (
                f"<script>fetch('/ep/api/atos-prep/programa/{pid}',{{credentials:'include'}})</script>")
            return self._enviar(200, f"<html><body>programa {pid}{script}</body></html>", "text/html")
        if p == "/ep/api/seguranca/auth/configuration":
            return self._enviar(200, {"ok": True}, extra={"Set-Cookie": f"XSRF-TOKEN={e.token}; Path=/"})
        if p.startswith("/ep/api/atos-prep/programa/"):
            pid = p.rsplit("/", 1)[1]
            if pid.isdigit() and int(pid) in e.detalhe_falha:
                return self._enviar(500, {"erro": "falha simulada"})
            if pid.isdigit() and int(pid) in e.programas:
                return self._enviar(200, e.programas[int(pid)])
            return self._enviar(404, {"erro": "nao encontrado"})
        return self._enviar(404, "nao encontrado", "text/plain")

    def do_POST(self):  # noqa: N802
        e, p = self.estado, self.path.split("?")[0]
        tamanho = int(self.headers.get("Content-Length") or 0)
        corpo = json.loads(self.rfile.read(tamanho) or b"{}")
        token_ok = self.headers.get("X-XSRF-TOKEN") == e.token
        e.requisicoes.append(("POST", p, token_ok))
        if p != "/ep/api/atos-prep/programa/listarComFiltro":
            return self._enviar(404, {"erro": "nao encontrado"})
        if not token_ok:  # como no spike: sem o header XSRF a API devolve 400
            return self._enviar(400, {"erro": "xsrf ausente"})
        if e.listagem_status != 200:
            return self._enviar(e.listagem_status, {"erro": "simulado"})
        if e.listagem_vazia:
            return self._enviar(200, {"entidades": []})
        tam, pag = int(corpo.get("pagesize", 10)), int(corpo.get("currentPage", 1))
        todos = [{k: d.get(k) for k in CAMPOS_LISTAGEM} for d in e.programas.values()]
        return self._enviar(200, {"entidades": todos[(pag - 1) * tam: pag * tam]})


class ServidorFalso:
    def __init__(self, estado: Estado):
        self.estado = estado
        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._srv.estado = estado
        self.url = f"http://127.0.0.1:{self._srv.server_address[1]}"
        self._t = threading.Thread(target=self._srv.serve_forever, daemon=True)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *a):
        self._srv.shutdown()
        self._srv.server_close()
