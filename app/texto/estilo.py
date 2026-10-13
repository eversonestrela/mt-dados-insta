"""Filtro "anti-cara-de-IA" para legendas em português.

Duas funções:
- limpar(): corrige automaticamente vícios fáceis (travessão, emojis em excesso, espaços).
- avisos(): aponta o que ainda soa artificial, para você revisar antes de aprovar.
"""
from __future__ import annotations

import re
import unicodedata

# Expressões que denunciam texto gerado por IA ou "marketing genérico" em PT-BR.
EXPRESSOES = [
    "além disso", "vale ressaltar", "vale destacar", "vale lembrar", "é importante destacar",
    "é importante ressaltar", "é importante lembrar", "em suma", "em resumo", "em síntese",
    "mergulhe", "mergulhar", "desvende", "desvendar", "jornada", "fascinante", "crucial",
    "fundamental para", "no cenário atual", "nos dias de hoje", "em um mundo", "num mundo",
    "não apenas", "mas também", "descubra", "confira", "incrível", "vibrante", "rica história",
    "rico patrimônio", "potencializar", "alavancar", "impulsionar", "transformador",
    "fique por dentro", "você sabia que", "sem dúvida", "inegável", "notável", "tapeçaria",
    "um verdadeiro", "uma verdadeira", "repleto de", "repleta de", "cativante", "encantador",
    "imperdível", "não perca", "explore", "embarque", "celebrar a", "testemunho de",
    "papel crucial", "desempenha um papel", "abrangente", "robusto", "ecossistema",
]

EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF⭐⬆↔-↪]"
)
HASHTAG = re.compile(r"#\w+", re.UNICODE)
MAX_HASHTAGS = 4
MAX_EMOJIS = 1
LIMITE_LEGENDA = 2200  # limite do Instagram


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def limpar(texto: str) -> str:
    t = texto.strip()
    # aspas e markdown que vazam de modelos de linguagem
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"^#{1,6}\s+", "", t, flags=re.M)  # títulos markdown, não hashtags
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.M)
    # travessão vira vírgula (ou ponto quando abre frase)
    t = re.sub(r"\s*[—–]\s*", ", ", t)
    t = re.sub(r",\s*,", ",", t)
    # emojis: mantém no máximo MAX_EMOJIS
    vistos = 0

    def _emoji(m):
        nonlocal vistos
        vistos += 1
        return m.group(0) if vistos <= MAX_EMOJIS else ""

    t = EMOJI.sub(_emoji, t)
    t = re.sub(r"️", "", t) if vistos > MAX_EMOJIS else t
    # hashtags: mantém as primeiras MAX_HASHTAGS
    tags = HASHTAG.findall(t)
    if len(tags) > MAX_HASHTAGS:
        for tag in tags[MAX_HASHTAGS:]:
            t = t.replace(tag, "", 1)
    # exclamações repetidas
    t = re.sub(r"!{2,}", "!", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()[:LIMITE_LEGENDA]


def avisos(texto: str) -> list[str]:
    lista = []
    base = _sem_acento(texto.lower())
    for exp in EXPRESSOES:
        if re.search(r"\b" + re.escape(_sem_acento(exp)) + r"\b", base):
            lista.append(f'Expressão com cara de IA: "{exp}"')
    if "—" in texto or "–" in texto:
        lista.append("Tem travessão (—), marca comum de texto de IA")
    if texto.count("!") > 1:
        lista.append("Muitas exclamações")
    frases = [f for f in re.split(r"[.!?]\s", texto) if f.strip()]
    longas = [f for f in frases if len(f.split()) > 32]
    if longas:
        lista.append(f"{len(longas)} frase(s) muito longa(s)")
    # estrutura de "três adjetivos" típica de IA: "rápido, eficiente e moderno"
    if re.search(r"\b\w+, \w+ e \w+\b", texto) and len(re.findall(r"\b\w+, \w+ e \w+\b", texto)) >= 2:
        lista.append("Muitas enumerações de três itens seguidas")
    if len(HASHTAG.findall(texto)) > MAX_HASHTAGS:
        lista.append("Hashtags demais")
    if len(texto) > LIMITE_LEGENDA:
        lista.append("Legenda acima do limite do Instagram (2.200 caracteres)")
    return lista


# ------------------------------------------------------------- checagem de números
NUM = re.compile(r"\d[\d.,]*")


def _normalizar_num(s: str) -> str:
    s = s.strip(".,")
    return s.replace(".", "").replace(",", "")


def numeros_inventados(texto: str, permitidos: str) -> list[str]:
    """Números que aparecem no texto mas não existem nos dados fornecidos.

    Compara apenas os dígitos (ignora separador de milhar/decimal), para pegar
    números que a IA tenha criado do nada.
    """
    ok = {_normalizar_num(n) for n in NUM.findall(permitidos)}
    suspeitos = []
    for n in NUM.findall(HASHTAG.sub("", texto)):
        d = _normalizar_num(n)
        if not d or len(d) == 1:  # dígitos soltos (1 a 9) costumam ser palavras como "1 dia"
            continue
        # aceita o número exato ou um arredondamento dele (ex.: 1.234 -> "1,2 mil")
        if d not in ok and not any(x.startswith(d) for x in ok):
            suspeitos.append(n.strip(".,"))
    return suspeitos
