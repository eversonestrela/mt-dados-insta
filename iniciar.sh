#!/usr/bin/env bash
# Mac / Linux
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Preparando o ambiente pela primeira vez..."
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
fi
echo "Painel em http://127.0.0.1:8765 (deixe este terminal aberto para os posts saírem)"
exec .venv/bin/python iniciar.py "$@"
