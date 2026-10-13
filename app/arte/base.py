"""Base visual: paleta, fontes e utilitários de desenho.

Estética de "jornal de dados": papel claro, tinta escura, uma cor de destaque,
tipografia editorial (Lora) + números em Inter. Nada de foto gerada por IA:
a imagem é o próprio dado (mapa, gráfico, número).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..base import FONTES

FEED = (1080, 1350)
STORY = (1080, 1920)
MARGEM = 84


@dataclass
class Paleta:
    fundo: str = "#F3EEE4"
    tinta: str = "#17140F"
    suave: str = "#6B6358"
    linha: str = "#CFC6B6"
    destaque: str = "#B4441C"
    verde: str = "#3E5C45"
    mapa: str = "#E6DFD1"
    mapa_borda: str = "#FFFFFF"

    @classmethod
    def escura(cls, destaque: str = "#E0673A") -> "Paleta":
        return cls(fundo="#16130F", tinta="#F3EEE4", suave="#A39A8C", linha="#3A342C",
                   destaque=destaque, verde="#7FA487", mapa="#2A2520", mapa_borda="#16130F")


ARQS = {
    "inter": "Inter-Regular.otf", "inter-medio": "Inter-Medium.otf", "inter-semi": "Inter-SemiBold.otf",
    "inter-negrito": "Inter-Bold.otf", "inter-extra": "Inter-ExtraBold.otf", "inter-black": "Inter-Black.otf",
    "lora": ("Lora-Variable.ttf", "Regular"), "lora-semi": ("Lora-Variable.ttf", "SemiBold"),
    "lora-negrito": ("Lora-Variable.ttf", "Bold"), "lora-italico": ("Lora-Italic-Variable.ttf", "Regular"),
}


@lru_cache(maxsize=128)
def fonte(nome: str, tamanho: int) -> ImageFont.FreeTypeFont:
    spec = ARQS[nome]
    if isinstance(spec, tuple):
        f = ImageFont.truetype(str(FONTES / spec[0]), tamanho)
        try:
            f.set_variation_by_name(spec[1])
        except Exception:  # noqa: BLE001
            pass
        return f
    return ImageFont.truetype(str(FONTES / spec), tamanho)


class Tela:
    def __init__(self, tamanho=FEED, paleta: Paleta | None = None):
        self.w, self.h = tamanho
        self.p = paleta or Paleta()
        self.img = Image.new("RGB", tamanho, self.p.fundo)
        self.d = ImageDraw.Draw(self.img)

    # ---------------------------------------------------------- texto
    def largura(self, texto: str, f) -> int:
        return int(self.d.textlength(texto, font=f))

    def quebrar(self, texto: str, f, largura_max: int) -> list[str]:
        linhas: list[str] = []
        for paragrafo in texto.split("\n"):
            atual = ""
            for palavra in paragrafo.split():
                teste = f"{atual} {palavra}".strip()
                if self.largura(teste, f) <= largura_max:
                    atual = teste
                else:
                    if atual:
                        linhas.append(atual)
                    atual = palavra
            linhas.append(atual)
        return linhas

    def texto(self, xy, texto: str, f, cor=None, largura_max: int | None = None, entrelinha: float = 1.18,
              alinhar: str = "esq", max_linhas: int | None = None) -> int:
        """Escreve (com quebra de linha). Retorna o y logo abaixo do texto."""
        x, y = xy
        cor = cor or self.p.tinta
        linhas = self.quebrar(texto, f, largura_max) if largura_max else texto.split("\n")
        if max_linhas and len(linhas) > max_linhas:
            linhas = linhas[:max_linhas]
            linhas[-1] = linhas[-1].rstrip(" ,.;:") + "…"
        altura = int(f.size * entrelinha)
        for l in linhas:
            lx = x
            if alinhar == "dir":
                lx = x - self.largura(l, f)
            elif alinhar == "centro":
                lx = x - self.largura(l, f) // 2
            self.d.text((lx, y), l, font=f, fill=cor)
            y += altura
        return y

    def caber(self, texto: str, nome_fonte: str, largura_max: int, max_linhas: int, tam_max: int, tam_min: int = 28):
        """Maior fonte em que o texto cabe em max_linhas."""
        for tam in range(tam_max, tam_min - 1, -4):
            f = fonte(nome_fonte, tam)
            if len(self.quebrar(texto, f, largura_max)) <= max_linhas:
                return f
        return fonte(nome_fonte, tam_min)

    def chapeu(self, y: int, texto: str, cor=None) -> int:
        """Rótulo pequeno em caixa alta, com espaçamento entre letras."""
        f = fonte("inter-negrito", 26)
        x = MARGEM
        cor = cor or self.p.destaque
        for ch in texto.upper():
            self.d.text((x, y), ch, font=f, fill=cor)
            x += self.largura(ch, f) + 3
        return y + 44

    def regua(self, y: int, cor=None, espessura: int = 2, x0: int | None = None, x1: int | None = None):
        self.d.line([(x0 or MARGEM, y), (x1 or self.w - MARGEM, y)], fill=cor or self.p.linha, width=espessura)

    def rodape(self, fonte_dados: str, arroba: str = ""):
        # Em story/reel, o Instagram cobre ~250px de baixo com a caixa de resposta.
        y = self.h - (300 if self.h > 1500 else MARGEM + 34)
        self.regua(y - 22)
        f = fonte("inter-medio", 24)
        self.texto((MARGEM, y), f"Fonte: {fonte_dados}", f, self.p.suave,
                   largura_max=self.w - 2 * MARGEM - (self.largura(arroba, f) + 30 if arroba else 0), max_linhas=1)
        if arroba:
            self.texto((self.w - MARGEM, y), arroba, fonte("inter-negrito", 24), self.p.tinta, alinhar="dir")

    # ---------------------------------------------------------- gráficos
    def barras(self, x: int, y: int, largura: int, itens: list[tuple[str, float, str]], altura_barra: int = 30,
               espaco: int = 70, destaque_primeiro: bool = True) -> int:
        """Barras horizontais. itens = [(rótulo, valor, valor_formatado)]."""
        if not itens:
            return y
        maximo = max(v for _, v, _ in itens) or 1
        f_rot, f_val = fonte("inter-semi", 28), fonte("inter-extra", 30)
        for i, (rot, v, txt) in enumerate(itens):
            self.texto((x, y), rot, f_rot, self.p.tinta, largura_max=largura - 160, max_linhas=1)
            self.texto((x + largura, y), txt, f_val, self.p.tinta, alinhar="dir")
            yb = y + 40
            self.d.rectangle([x, yb, x + largura, yb + altura_barra // 3], fill=self.p.mapa)
            cor = self.p.destaque if (i == 0 and destaque_primeiro) else self.p.suave
            self.d.rectangle([x, yb, x + max(6, int(largura * v / maximo)), yb + altura_barra // 3], fill=cor)
            y += espaco
        return y

    def serie(self, x: int, y: int, largura: int, altura: int, pontos: list[tuple[str, float]]):
        """Linha simples com os últimos dias e rótulo do primeiro e último valor."""
        if len(pontos) < 2:
            return
        vals = [v for _, v in pontos]
        vmax, vmin = max(vals), min(vals)
        amp = (vmax - vmin) or 1
        xs = [x + int(i * largura / (len(vals) - 1)) for i in range(len(vals))]
        ys = [y + altura - int((v - vmin) / amp * altura) for v in vals]
        self.d.line(list(zip(xs, ys)), fill=self.p.tinta, width=4, joint="curve")
        for xi, yi in zip(xs[:-1], ys[:-1]):
            self.d.ellipse([xi - 5, yi - 5, xi + 5, yi + 5], fill=self.p.tinta)
        self.d.ellipse([xs[-1] - 10, ys[-1] - 10, xs[-1] + 10, ys[-1] + 10], fill=self.p.destaque)
        f = fonte("inter-medio", 22)
        dia0, dia1 = pontos[0][0], pontos[-1][0]
        self.texto((x, y + altura + 16), f"{dia0[8:10]}/{dia0[5:7]}", f, self.p.suave)
        self.texto((x + largura, y + altura + 16), f"{dia1[8:10]}/{dia1[5:7]}", f, self.p.suave, alinhar="dir")

    def foto_cobrir(self, caminho: Path, caixa: tuple[int, int, int, int], escurecer: float = 0.0):
        """Cola uma foto REAL (sua) recortada para cobrir a caixa."""
        x0, y0, x1, y1 = caixa
        foto = Image.open(caminho).convert("RGB")
        alvo_w, alvo_h = x1 - x0, y1 - y0
        esc = max(alvo_w / foto.width, alvo_h / foto.height)
        foto = foto.resize((int(foto.width * esc) + 1, int(foto.height * esc) + 1), Image.LANCZOS)
        cx, cy = (foto.width - alvo_w) // 2, (foto.height - alvo_h) // 2
        foto = foto.crop((cx, cy, cx + alvo_w, cy + alvo_h))
        if escurecer:
            foto = Image.blend(foto, Image.new("RGB", foto.size, "#000000"), escurecer)
        self.img.paste(foto, (x0, y0))

    def salvar(self, caminho: Path) -> Path:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        # Instagram só aceita JPEG para imagens
        self.img.save(caminho, "JPEG", quality=93, optimize=True, progressive=True)
        return caminho
