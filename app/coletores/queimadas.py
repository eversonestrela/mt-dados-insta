"""INPE - Programa Queimadas: focos de calor do dia anterior em Mato Grosso.

Arquivo diário público (CSV, separado por vírgula):
https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/diario/Brasil/focos_diario_br_AAAAMMDD.csv

A contagem oficial do INPE usa um "satélite de referência" (hoje AQUA_M-T), para que a série
seja comparável ao longo dos anos. Os demais satélites (GOES, NOAA, NPP...) repetem os mesmos
focos várias vezes por dia, então somar tudo inflaria o número.
"""
from __future__ import annotations

import csv
import io
from collections import Counter
from datetime import date, timedelta

from ..base import cfg, db, log
from . import arquivo_cache, baixar

URL = "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/diario/Brasil/focos_diario_br_{:%Y%m%d}.csv"
GEOESTACIONARIOS = ("GOES", "MSG", "METEOSAT")


MINUSCULAS = {"de", "da", "do", "das", "dos", "e"}


def _nome(s: str) -> str:
    """'SÃO FÉLIX DO ARAGUAIA' -> 'São Félix do Araguaia'"""
    palavras = s.strip().lower().split()
    return " ".join(p if (i and p in MINUSCULAS) else p.capitalize() for i, p in enumerate(palavras))


def _csv_do_dia(dia: date) -> str | None:
    arq = arquivo_cache("inpe", f"focos_{dia:%Y%m%d}.csv")
    if arq.exists() and dia < date.today() - timedelta(days=1):
        return arq.read_text(encoding="utf-8")
    r = baixar(URL.format(dia), timeout=180)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    texto = r.content.decode("utf-8", errors="replace")
    # O arquivo do Brasil inteiro é grande; guarda só o cabeçalho e as linhas de MT.
    linhas = texto.splitlines()
    texto = "\n".join([linhas[0]] + [l for l in linhas[1:] if "MATO GROSSO" in l.upper()]) if linhas else ""
    arq.write_text(texto, encoding="utf-8")
    return texto


def _focos_mt(texto: str) -> list[dict]:
    leitor = csv.DictReader(io.StringIO(texto))
    return [l for l in leitor if (l.get("estado") or "").strip().upper() == "MATO GROSSO"]


def _escolher_satelite(focos: list[dict]) -> str | None:
    ref = cfg("satelite_referencia")
    sats = Counter(f["satelite"] for f in focos)
    if sats.get(ref):
        return ref
    # Sem passagem do satélite de referência: usa o polar com mais detecções e avisa no post.
    polares = [(s, n) for s, n in sats.items() if not s.upper().startswith(GEOESTACIONARIOS)]
    return max(polares, key=lambda x: x[1])[0] if polares else None


def coletar(dia: date) -> dict | None:
    """Resumo dos focos em MT no dia (horário GMT do INPE)."""
    texto = _csv_do_dia(dia)
    if texto is None:
        return None
    todos = _focos_mt(texto)
    sat = _escolher_satelite(todos) if todos else cfg("satelite_referencia")
    focos = [f for f in todos if f["satelite"] == sat]
    por_mun = Counter(_nome(f["municipio"]) for f in focos)
    por_bioma = Counter((f.get("bioma") or "").strip() for f in focos)
    pontos = []
    for f in focos:
        try:
            pontos.append((float(f["lon"]), float(f["lat"])))
        except (TypeError, ValueError):
            continue
    resumo = {
        "dia": dia.isoformat(),
        "satelite": sat,
        "satelite_e_referencia": sat == cfg("satelite_referencia"),
        "total": len(focos),
        "municipios_afetados": len(por_mun),
        "top_municipios": por_mun.most_common(8),
        "biomas": por_bioma.most_common(),
        "pontos": pontos,
    }
    with db() as c:
        c.execute(
            "INSERT INTO serie_queimadas(dia,total,satelite) VALUES(?,?,?) "
            "ON CONFLICT(dia) DO UPDATE SET total=excluded.total, satelite=excluded.satelite",
            (resumo["dia"], resumo["total"], sat),
        )
    return resumo


def serie(ate: date, dias: int = 7) -> list[tuple[str, int]]:
    """Últimos N dias (busca os que faltarem)."""
    saida = []
    for i in range(dias - 1, -1, -1):
        d = ate - timedelta(days=i)
        with db() as c:
            r = c.execute("SELECT total FROM serie_queimadas WHERE dia=?", (d.isoformat(),)).fetchone()
        if r is None:
            try:
                res = coletar(d)
                total = res["total"] if res else None
            except Exception as e:  # noqa: BLE001
                log(f"INPE: não consegui o dia {d}: {e}", "aviso")
                total = None
        else:
            total = r["total"]
        if total is not None:
            saida.append((d.isoformat(), total))
    return saida
