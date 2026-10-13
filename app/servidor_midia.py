"""Servidor mínimo que expõe APENAS a pasta dados/midia (modo "url_publica").

Roda em 127.0.0.1:8766. Sem listagem de pastas. É esta porta que você aponta no túnel,
nunca a do painel.
"""
from __future__ import annotations

import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from .base import MIDIA, log

PORTA = 8766


class _SoArquivos(SimpleHTTPRequestHandler):
    def list_directory(self, path):  # noqa: D401 - sem listagem
        self.send_error(404)
        return None

    def log_message(self, *args):
        pass


def iniciar() -> None:
    handler = partial(_SoArquivos, directory=str(MIDIA))
    srv = ThreadingHTTPServer(("127.0.0.1", PORTA), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f"Servidor de mídia em http://127.0.0.1:{PORTA} (somente a pasta dados/midia)")
