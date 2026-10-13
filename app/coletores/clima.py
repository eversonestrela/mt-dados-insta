"""Clima do dia (previsão) via Open-Meteo - gratuito e sem chave.

Fonte: https://open-meteo.com (agrega modelos meteorológicos públicos). O post cita
"Open-Meteo" como fonte, porque não é dado oficial do INMET.
"""
from __future__ import annotations

from datetime import date

from ..base import cfg
from . import baixar, json_em_cache

URL = "https://api.open-meteo.com/v1/forecast"


def cidades() -> list[tuple[str, float, float]]:
    saida = []
    for item in str(cfg("clima_cidades")).split("|"):
        partes = [p.strip() for p in item.split(";")]
        if len(partes) == 3:
            saida.append((partes[0], float(partes[1]), float(partes[2])))
    return saida


def coletar(dia: date) -> list[dict]:
    resultado = []
    for nome, lat, lon in cidades():
        def obter(lat=lat, lon=lon):
            r = baixar(URL, params={
                "latitude": lat, "longitude": lon, "timezone": "America/Cuiaba",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,relative_humidity_2m_min,uv_index_max",
                "start_date": dia.isoformat(), "end_date": dia.isoformat(),
            })
            r.raise_for_status()
            return r.json()

        j = json_em_cache("clima", f"{nome}_{dia}.json", 6, obter)
        d = j.get("daily", {})

        def v(k):
            lst = d.get(k) or [None]
            return lst[0]

        resultado.append({
            "cidade": nome, "dia": dia.isoformat(),
            "max": v("temperature_2m_max"), "min": v("temperature_2m_min"),
            "chuva_prob": v("precipitation_probability_max"),
            "umidade_min": v("relative_humidity_2m_min"), "uv": v("uv_index_max"),
        })
    return resultado
