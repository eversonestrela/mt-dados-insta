"""Peças prontas para cada pauta. Cada função devolve a lista de arquivos gerados."""
from __future__ import annotations

from pathlib import Path

from ..base import FOTOS
from ..texto.redator import data_extenso, dinheiro_mil, n
from . import mapa
from .base import FEED, MARGEM, STORY, Paleta, Tela, fonte


def _paleta(conta: dict, escura: bool = False) -> Paleta:
    cor = (conta or {}).get("cor_destaque") or "#B4441C"
    return Paleta.escura(cor) if escura else Paleta(destaque=cor)


def _arroba(conta: dict) -> str:
    a = (conta or {}).get("arroba") or ""
    return ("@" + a.lstrip("@")) if a else ""


def foto_real(codigo_ibge: str) -> tuple[Path, str] | None:
    """Foto sua (ou licenciada) em dados/fotos/<codigo_ibge>/. Crédito em credito.txt."""
    pasta = FOTOS / str(codigo_ibge)
    if not pasta.is_dir():
        return None
    fotos = sorted(p for p in pasta.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    if not fotos:
        return None
    cred = pasta / "credito.txt"
    return fotos[0], (cred.read_text(encoding="utf-8").strip() if cred.exists() else "")


# ====================================================================== QUEIMADAS
def queimadas_feed(d: dict, conta: dict, malha: dict | None, destino: Path) -> list[Path]:
    t = Tela(FEED, _paleta(conta))
    y = t.chapeu(MARGEM, f"Queimadas em MT · {data_extenso(d['dia'])}")
    y = t.texto((MARGEM - 6, y - 10), n(d["total"]), fonte("inter-black", 200), t.p.tinta, entrelinha=1.0)
    t.texto((MARGEM, y + 4), "focos de calor em um dia", fonte("lora-semi", 54), t.p.tinta)
    if d.get("ontem") is not None:
        dif = d["total"] - d["ontem"]
        txt = "igual ao dia anterior" if dif == 0 else f"{'+' if dif > 0 else '−'}{n(abs(dif))} em relação ao dia anterior"
        t.texto((MARGEM, y + 80), txt, fonte("inter-semi", 30), t.p.destaque if dif > 0 else t.p.verde)

    topo = y + 150
    mapa.desenhar(t, (MARGEM - 10, topo, 600, 1060), malha, d.get("pontos"), raio_ponto=5)
    xr = 650
    t.texto((xr, topo + 10), "Onde mais apareceram", fonte("inter-negrito", 28), t.p.tinta)
    itens = [(m, q, n(q)) for m, q in d["top_municipios"][:5]]
    t.barras(xr, topo + 70, t.w - MARGEM - xr, itens, espaco=88)

    serie = d.get("serie") or []
    if len(serie) >= 3:
        t.texto((MARGEM, 1078), f"Últimos {len(serie)} dias", fonte("inter-negrito", 24), t.p.suave)
        t.serie(MARGEM + 230, 1078, t.w - 2 * MARGEM - 230, 60, serie)
    t.rodape(f"INPE, Programa Queimadas (satélite {d['satelite']})", _arroba(conta))
    return [t.salvar(destino / "queimadas_feed.jpg")]


def queimadas_story(d: dict, conta: dict, malha: dict | None, destino: Path) -> list[Path]:
    t = Tela(STORY, _paleta(conta, escura=True))
    y = t.chapeu(260, f"Queimadas · {data_extenso(d['dia'])}")
    y = t.texto((MARGEM - 8, y), n(d["total"]), fonte("inter-black", 250), t.p.tinta, entrelinha=1.0)
    y = t.texto((MARGEM, y + 10), "focos de calor em\nMato Grosso", fonte("lora-semi", 70), t.p.tinta, entrelinha=1.1)
    mapa.desenhar(t, (MARGEM, y + 30, t.w - MARGEM, y + 540), malha, d.get("pontos"), raio_ponto=6)
    y += 590
    f_n, f_q = fonte("inter-semi", 40), fonte("inter-extra", 40)
    for mun, q in d["top_municipios"][:3]:
        t.texto((MARGEM, y), mun, f_n, t.p.tinta, largura_max=700, max_linhas=1)
        t.texto((t.w - MARGEM, y), n(q), f_q, t.p.destaque, alinhar="dir")
        y += 64
    t.rodape("INPE, Programa Queimadas", _arroba(conta))
    return [t.salvar(destino / "queimadas_story.jpg")]


# ====================================================================== CLIMA
def clima_story(d: dict, conta: dict, destino: Path) -> list[Path]:
    c = d["cidades"][0]
    seca = c.get("umidade_min") is not None and c["umidade_min"] < 30
    t = Tela(STORY, _paleta(conta, escura=False))
    y = t.chapeu(260, f"Tempo hoje · {c['cidade']}")
    t.texto((MARGEM, y + 10), "Máxima", fonte("inter-negrito", 34), t.p.suave)
    y = t.texto((MARGEM - 10, y + 50), f"{n(c['max'])}°", fonte("inter-black", 330), t.p.destaque, entrelinha=1.0)
    y = t.texto((MARGEM, y + 10), f"Mínima de {n(c['min'])}°", fonte("lora-semi", 72), t.p.tinta)
    y += 70
    t.regua(y)
    y += 50
    linhas = [("Umidade mínima", f"{n(c['umidade_min'])}%"), ("Chance de chuva", f"{n(c['chuva_prob'])}%"),
              ("Índice UV máximo", n(c.get("uv"), 0))]
    for rot, val in linhas:
        t.texto((MARGEM, y), rot, fonte("inter-semi", 44), t.p.tinta)
        t.texto((t.w - MARGEM, y), val, fonte("inter-extra", 44), t.p.tinta, alinhar="dir")
        y += 90
    if seca:
        y += 30
        t.d.rectangle([MARGEM, y, t.w - MARGEM, y + 220], fill=t.p.destaque)
        t.texto((MARGEM + 40, y + 36), "Ar muito seco", fonte("inter-extra", 46), "#FFFFFF")
        t.texto((MARGEM + 40, y + 100), "Beba água e evite exercícios ao ar livre entre 10h e 16h.",
                fonte("inter-medio", 34), "#FFFFFF", largura_max=t.w - 2 * MARGEM - 80)
    outras = d["cidades"][1:5]
    if outras and not seca:
        y += 40
        for o in outras:
            t.texto((MARGEM, y), o["cidade"], fonte("inter-semi", 40), t.p.tinta)
            t.texto((t.w - MARGEM, y), f"{n(o['max'])}° / {n(o['min'])}°", fonte("inter-extra", 40), t.p.tinta, alinhar="dir")
            y += 72
    t.rodape("Open-Meteo (previsão)", _arroba(conta))
    return [t.salvar(destino / "clima_story.jpg")]


# ====================================================================== MUNICÍPIO DO DIA
def _faixa_posicao(t: Tela, y: int, posicao: int | None, total: int, rotulo: str) -> int:
    """141 tracinhos, um por município, com o da vez em destaque."""
    if not posicao:
        return y
    x0, x1 = MARGEM, t.w - MARGEM
    passo = (x1 - x0) / total
    for i in range(total):
        x = x0 + i * passo
        alto = i + 1 == posicao
        t.d.rectangle([x, y + (0 if alto else 20), x + max(2, passo - 2), y + 60],
                      fill=t.p.destaque if alto else t.p.linha)
    t.texto((x0, y + 76), "1º", fonte("inter-medio", 22), t.p.suave)
    t.texto((x1, y + 76), f"{total}º", fonte("inter-medio", 22), t.p.suave, alinhar="dir")
    return t.texto((x0, y + 120), rotulo, fonte("inter-semi", 32), t.p.tinta, largura_max=x1 - x0)


def _slide_capa(d, conta, malha, tam) -> Tela:
    vertical = tam == STORY
    foto = foto_real(d["codigo"])
    t = Tela(tam, _paleta(conta, escura=bool(foto)))
    if foto:
        t.foto_cobrir(foto[0], (0, 0, t.w, t.h), escurecer=0.45)
        y = t.h - (900 if vertical else 620)
    else:
        caixa = (MARGEM, 380, t.w - MARGEM, t.h - 520) if vertical else (MARGEM + 220, 120, t.w - MARGEM, 760)
        mapa.desenhar(t, caixa, malha, realce={d["codigo"]})
        y = t.h - (700 if vertical else 560)
    y = t.chapeu(y, "Município do dia")
    f = t.caber(d["nome"], "lora-negrito", t.w - 2 * MARGEM, 2, 150 if vertical else 132, 64)
    y = t.texto((MARGEM, y), d["nome"], f, t.p.tinta, largura_max=t.w - 2 * MARGEM, entrelinha=1.05)
    if d.get("regiao_imediata"):
        t.texto((MARGEM, y + 14), f"Região de {d['regiao_imediata']}", fonte("inter-semi", 34), t.p.suave)
    credito = f"Foto: {foto[1]}" if foto and foto[1] else "IBGE"
    t.rodape(credito, _arroba(conta))
    return t


def _slide_numero(conta, tam, chapeu, numero, unidade, extra_linhas, faixa=None) -> Tela:
    vertical = tam == STORY
    t = Tela(tam, _paleta(conta))
    y = t.chapeu(360 if vertical else 250, chapeu)
    f_num = t.caber(numero, "inter-black", t.w - 2 * MARGEM, 1, 190 if vertical else 170, 90)
    y = t.texto((MARGEM - 6, y + 10), numero, f_num, t.p.tinta, entrelinha=1.0)
    y = t.texto((MARGEM, y + 6), unidade, fonte("lora-semi", 54), t.p.tinta, largura_max=t.w - 2 * MARGEM)
    y += 50
    for linha in extra_linhas:
        y = t.texto((MARGEM, y), linha, fonte("inter-medio", 36), t.p.suave, largura_max=t.w - 2 * MARGEM) + 16
    if faixa:
        _faixa_posicao(t, y + 70, *faixa)
    return t


def municipio_slides(d: dict, conta: dict, malha: dict | None, tam=FEED) -> list[Tela]:
    total = d.get("total_mun") or 141
    slides = [_slide_capa(d, conta, malha, tam)]
    if d.get("populacao"):
        s = _slide_numero(conta, tam, "Gente", n(d["populacao"]), "moradores no Censo 2022",
                          [f"{n(d['pct_pop'], 1)}% de quem mora em Mato Grosso"] if d.get("pct_pop") else [],
                          (d.get("pos_pop"), total, f"{d.get('pos_pop')}ª maior população entre os {total} municípios de MT"))
        s.rodape("IBGE, Censo 2022", _arroba(conta))
        slides.append(s)
    if d.get("area_km2"):
        extra = [f"Densidade: {n(d.get('densidade'), 2)} habitantes por km²"] if d.get("densidade") is not None else []
        s = _slide_numero(conta, tam, "Território", n(d["area_km2"], 0), "quilômetros quadrados", extra,
                          (d.get("pos_area"), total, f"{d.get('pos_area')}º em área no estado"))
        s.rodape("IBGE, Censo 2022", _arroba(conta))
        slides.append(s)
    if d.get("pib_mil"):
        s = _slide_numero(conta, tam, "Economia", dinheiro_mil(d["pib_mil"]), f"de PIB em {d.get('pib_ano')}",
                          [f"{n(d['pct_pib'], 1)}% de toda a economia de Mato Grosso"] if d.get("pct_pib") else [],
                          (d.get("pos_pib"), total, f"{d.get('pos_pib')}º maior PIB de Mato Grosso"))
        s.rodape("IBGE, PIB dos Municípios", _arroba(conta))
        slides.append(s)
    return slides


def municipio_carrossel(d, conta, malha, destino: Path) -> list[Path]:
    return [s.salvar(destino / f"municipio_{i + 1}.jpg") for i, s in enumerate(municipio_slides(d, conta, malha, FEED))]


# ====================================================================== RANKING
def ranking_feed(d: dict, conta: dict, destino: Path) -> list[Path]:
    t = Tela(FEED, _paleta(conta))
    y = t.chapeu(MARGEM, d.get("chapeu", "Ranking"))
    f = t.caber(d["titulo"], "lora-negrito", t.w - 2 * MARGEM, 2, 76, 48)
    y = t.texto((MARGEM, y), d["titulo"], f, t.p.tinta, largura_max=t.w - 2 * MARGEM, entrelinha=1.08)
    itens = [(f"{i}. {nome}", valor, txt) for i, (nome, txt, valor) in enumerate(d["itens"][:10], 1)]
    t.barras(MARGEM, y + 60, t.w - 2 * MARGEM, itens, espaco=78)
    t.rodape(d["fonte"], _arroba(conta))
    return [t.salvar(destino / "ranking.jpg")]


# ====================================================================== DIÁRIO OFICIAL / AGENDA
def texto_feed(chapeu: str, titulo: str, corpo: str, fonte_dados: str, conta: dict, destino: Path,
               nome_arq: str) -> list[Path]:
    t = Tela(FEED, _paleta(conta))
    y = t.chapeu(MARGEM, chapeu)
    f = t.caber(titulo, "lora-negrito", t.w - 2 * MARGEM, 4, 84, 50)
    y = t.texto((MARGEM, y + 6), titulo, f, t.p.tinta, largura_max=t.w - 2 * MARGEM, entrelinha=1.08)
    y += 30
    t.regua(y, t.p.destaque, 6, MARGEM, MARGEM + 120)
    y += 50
    if corpo:
        t.texto((MARGEM, y), corpo, fonte("inter-medio", 36), t.p.tinta, largura_max=t.w - 2 * MARGEM,
                entrelinha=1.42, max_linhas=max(1, (t.h - 240 - y) // 51))
    t.rodape(fonte_dados, _arroba(conta))
    return [t.salvar(destino / nome_arq)]


def resumo_para_arte(legenda: str) -> tuple[str, str]:
    """Primeira frase vira título; o resto (sem fonte/hashtags) vira corpo."""
    corpo = []
    for par in legenda.split("\n\n"):
        p = par.strip()
        if not p or p.startswith("#") or p.lower().startswith("fonte"):
            continue
        corpo.append(p)
    texto = " ".join(corpo)
    if ". " in texto:
        titulo, resto = texto.split(". ", 1)
        return titulo + ".", resto
    return texto, ""
