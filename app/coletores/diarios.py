"""Diários oficiais municipais via Querido Diário (Open Knowledge Brasil).

API pública: https://api.queridodiario.ok.org.br - busca trechos por palavra-chave.
Nem todo município de MT está coberto; quando não houver resultado, a pauta é pulada.
"""
from __future__ import annotations

from datetime import date, timedelta

from ..base import cfg, log
from . import baixar, json_em_cache
from .ibge import municipios

URL = "https://api.queridodiario.ok.org.br/gazettes"


def coletar(dia: date, codigos: list[str] | None = None) -> list[dict]:
    codigos = codigos or [m["id"] for m in municipios()]
    termos = [t.strip() for t in str(cfg("diario_termos")).split(";") if t.strip()]
    achados: list[dict] = []
    for termo in termos:
        def obter(termo=termo):
            r = baixar(URL, params={
                "territory_ids": codigos,
                "published_since": (dia - timedelta(days=1)).isoformat(),
                "published_until": dia.isoformat(),
                "querystring": termo,
                "excerpt_size": 600, "number_of_excerpts": 2, "size": 10,
            })
            r.raise_for_status()
            return r.json()

        try:
            j = json_em_cache("diarios", f"{dia}_{termo}.json", 12, obter)
        except Exception as e:  # noqa: BLE001
            log(f"Querido Diário indisponível ({termo}): {e}", "aviso")
            continue
        for g in j.get("gazettes", []):
            for trecho in g.get("excerpts", [])[:2]:
                achados.append({
                    "municipio": g.get("territory_name"),
                    "codigo": g.get("territory_id"),
                    "data": g.get("date"),
                    "url": g.get("url"),
                    "termo": termo,
                    "trecho": " ".join(str(trecho).split()),
                })
    # remove repetidos
    vistos, unicos = set(), []
    for a in achados:
        chave = (a["codigo"], a["trecho"][:120])
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(a)
    return unicos
