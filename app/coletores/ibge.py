"""IBGE: lista de municípios de MT, indicadores (Censo 2022, PIB) e malha geográfica.

APIs públicas, sem chave:
- Localidades: https://servicodados.ibge.gov.br/api/v1/localidades
- Agregados (SIDRA): https://servicodados.ibge.gov.br/api/v3/agregados
- Malhas: https://servicodados.ibge.gov.br/api/v3/malhas
"""
from __future__ import annotations

import json
from pathlib import Path

from . import baixar, json_em_cache

MALHA_LOCAL = Path(__file__).resolve().parent.parent / "recursos" / "malha_mt.geojson"
UF_MT = 51
BASE = "https://servicodados.ibge.gov.br/api"

# Censo 2022 - tabela 4714: população residente (93), área (6318), densidade (614)
TAB_CENSO, VARS_CENSO = 4714, {"93": "populacao", "6318": "area_km2", "614": "densidade"}
# PIB dos municípios - tabela 5938, variável 37 (mil reais, preços correntes)
TAB_PIB, VAR_PIB = 5938, "37"


def municipios() -> list[dict]:
    def obter():
        r = baixar(f"{BASE}/v1/localidades/estados/{UF_MT}/municipios")
        saida = []
        for m in r.json():
            imediata = (m.get("regiao-imediata") or {}).get("nome", "")
            intermed = ((m.get("regiao-imediata") or {}).get("regiao-intermediaria") or {}).get("nome", "")
            saida.append({"id": str(m["id"]), "nome": m["nome"], "regiao_imediata": imediata, "regiao_intermediaria": intermed})
        return sorted(saida, key=lambda x: x["id"])

    try:
        return json_em_cache("ibge", "municipios_mt.json", 24 * 30, obter)
    except Exception:  # noqa: BLE001 - sem internet: nomes e códigos da malha local
        malha = json.loads(MALHA_LOCAL.read_text(encoding="utf-8"))
        return sorted(({"id": f["properties"]["codarea"], "nome": f["properties"]["nome"],
                        "regiao_imediata": "", "regiao_intermediaria": ""} for f in malha["features"]),
                      key=lambda x: x["id"])


def _agregado(tabela: int, periodo: str, variaveis: str) -> list:
    url = f"{BASE}/v3/agregados/{tabela}/periodos/{periodo}/variaveis/{variaveis}"
    r = baixar(url, params={"localidades": f"N6[N3[{UF_MT}]]"}, timeout=120)
    r.raise_for_status()
    return r.json()


def _num(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None  # "-", "..." etc.


def indicadores() -> dict[str, dict]:
    """{codigo_ibge: {populacao, area_km2, densidade, pib_mil, pib_ano}}"""

    def obter():
        saida: dict[str, dict] = {}
        for var in _agregado(TAB_CENSO, "2022", "|".join(VARS_CENSO)):
            campo = VARS_CENSO.get(str(var["id"]))
            for serie in var["resultados"][0]["series"]:
                cod = serie["localidade"]["id"]
                valor = _num(next(iter(serie["serie"].values())))
                saida.setdefault(cod, {})[campo] = valor
        try:
            for var in _agregado(TAB_PIB, "-1", VAR_PIB):
                for serie in var["resultados"][0]["series"]:
                    cod = serie["localidade"]["id"]
                    ano, valor = next(iter(serie["serie"].items()))
                    d = saida.setdefault(cod, {})
                    d["pib_mil"] = _num(valor)
                    d["pib_ano"] = ano
        except Exception:  # noqa: BLE001 - PIB é opcional
            pass
        return saida

    return json_em_cache("ibge", "indicadores_mt.json", 24 * 30, obter)


def malha_mt() -> dict:
    """GeoJSON com os municípios de MT (qualidade mínima, leve)."""

    def obter():
        r = baixar(
            f"{BASE}/v3/malhas/estados/{UF_MT}",
            params={"formato": "application/vnd.geo+json", "qualidade": "minima", "intrarregiao": "municipio"},
            timeout=120,
        )
        r.raise_for_status()
        return r.json()

    try:
        return json_em_cache("ibge", "malha_mt.geojson", None, obter)
    except Exception:  # noqa: BLE001 - sem internet: usa a malha que vem com o programa
        return json.loads(MALHA_LOCAL.read_text(encoding="utf-8"))


def ranking(indic: dict[str, dict], campo: str) -> list[tuple[str, float]]:
    pares = [(cod, d[campo]) for cod, d in indic.items() if d.get(campo) is not None]
    return sorted(pares, key=lambda x: x[1], reverse=True)


def posicao(indic: dict[str, dict], campo: str, cod: str) -> int | None:
    for i, (c, _) in enumerate(ranking(indic, campo), start=1):
        if c == cod:
            return i
    return None
