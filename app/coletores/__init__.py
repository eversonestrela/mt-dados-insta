"""Coletores de dados públicos. Cada um baixa, guarda em cache e devolve dados limpos."""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

from ..base import CACHE, log

UA = "MT-em-Dados/1.0 (projeto local de divulgacao de dados publicos)"


def baixar(url: str, *, params: dict | None = None, timeout: float = 60, tentativas: int = 3) -> httpx.Response:
    ultimo_erro: Exception | None = None
    for i in range(tentativas):
        try:
            r = httpx.get(url, params=params, timeout=timeout, headers={"User-Agent": UA}, follow_redirects=True)
            if r.status_code == 404:
                return r
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001
            ultimo_erro = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"Falha ao baixar {url}: {ultimo_erro}")


def arquivo_cache(fonte: str, nome: str) -> Path:
    p = CACHE / fonte
    p.mkdir(parents=True, exist_ok=True)
    return p / nome


def json_em_cache(fonte: str, nome: str, validade_horas: float | None, obter):
    """Lê do cache se ainda válido; senão chama obter() e salva."""
    arq = arquivo_cache(fonte, nome)
    if arq.exists():
        idade_h = (time.time() - arq.stat().st_mtime) / 3600
        if validade_horas is None or idade_h < validade_horas:
            return json.loads(arq.read_text(encoding="utf-8"))
    try:
        dados = obter()
    except Exception as e:  # noqa: BLE001
        if arq.exists():
            log(f"{fonte}: usando cache antigo ({e})", "aviso")
            return json.loads(arq.read_text(encoding="utf-8"))
        raise
    arq.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    return dados
