"""Abre o painel do MT em Dados em http://127.0.0.1:8765"""
import sys
import threading
import webbrowser

if sys.version_info < (3, 11):
    sys.exit("Precisa do Python 3.11 ou mais novo. Baixe em https://www.python.org/downloads/")

from app.main import rodar  # noqa: E402

if "--sem-navegador" not in sys.argv:
    threading.Timer(2.5, lambda: webbrowser.open("http://127.0.0.1:8765")).start()
rodar()
