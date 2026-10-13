"""Mapa de Mato Grosso desenhado a partir da malha do IBGE."""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

from .base import Tela


def _aneis(geom: dict):
    if geom["type"] == "Polygon":
        yield from geom["coordinates"]
    elif geom["type"] == "MultiPolygon":
        for poly in geom["coordinates"]:
            yield from poly


def _limites(malha: dict):
    xs, ys = [], []
    for f in malha["features"]:
        for anel in _aneis(f["geometry"]):
            for x, y in anel:
                xs.append(x)
                ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def desenhar(tela: Tela, caixa: tuple[int, int, int, int], malha: dict | None,
             pontos: list[tuple[float, float]] | None = None, realce: set[str] | None = None,
             raio_ponto: int = 5) -> None:
    """Desenha o mapa dentro da caixa (x0, y0, x1, y1), mantendo a proporção."""
    x0, y0, x1, y1 = caixa
    if malha:
        lon0, lat0, lon1, lat1 = _limites(malha)
    else:
        lon0, lat0, lon1, lat1 = -61.7, -18.1, -50.1, -7.3
    k = math.cos(math.radians((lat0 + lat1) / 2))
    larg_geo, alt_geo = (lon1 - lon0) * k, (lat1 - lat0)
    esc = min((x1 - x0) / larg_geo, (y1 - y0) / alt_geo)
    ox = x0 + ((x1 - x0) - larg_geo * esc) / 2
    oy = y0 + ((y1 - y0) - alt_geo * esc) / 2

    def proj(lon, lat):
        return ox + (lon - lon0) * k * esc, oy + (lat1 - lat) * esc

    # Desenha em 2x e reduz, para bordas suaves.
    S = 2
    camada = Image.new("RGBA", (tela.w * S, tela.h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    if malha:
        for f in malha["features"]:
            cod = str(f["properties"].get("codarea", ""))
            cor = tela.p.destaque if realce and cod in realce else tela.p.mapa
            for anel in _aneis(f["geometry"]):
                pts = [(px * S, py * S) for px, py in (proj(lo, la) for lo, la in anel)]
                if len(pts) > 2:
                    d.polygon(pts, fill=cor, outline=tela.p.mapa_borda, width=S)
    if pontos:
        r = raio_ponto * S
        cor = _rgba(tela.p.destaque, 170)
        for lon, lat in pontos:
            px, py = proj(lon, lat)
            d.ellipse([px * S - r, py * S - r, px * S + r, py * S + r], fill=cor)
    camada = camada.resize((tela.w, tela.h), Image.LANCZOS)
    tela.img.paste(camada, (0, 0), camada)
    tela.d = ImageDraw.Draw(tela.img)


def _rgba(hexcor: str, alfa: int):
    hexcor = hexcor.lstrip("#")
    return tuple(int(hexcor[i:i + 2], 16) for i in (0, 2, 4)) + (alfa,)
