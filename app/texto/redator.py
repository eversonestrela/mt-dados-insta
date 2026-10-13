"""Legendas: modelos escritos à mão (sem IA) + reescrita opcional pelo Claude.

Cada pauta tem:
- fatos(d): lista de fatos com números exatos (a única coisa que o Claude pode usar)
- legenda(d): texto-modelo, escrito em tom de jornalista local, com variações
"""
from __future__ import annotations

import random
from datetime import date

from . import estilo
from .ia import IAIndisponivel, gerar

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]
DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


# ------------------------------------------------------------------ formatação
def n(v, casas: int = 0) -> str:
    if v is None:
        return "-"
    s = f"{v:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def data_extenso(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} de {MESES[d.month - 1]}"


def dinheiro_mil(v_mil: float | None) -> str:
    """Valor em mil reais -> texto curto ("R$ 2,3 bilhões")."""
    if v_mil is None:
        return "-"
    reais = v_mil * 1000
    if reais >= 1e9:
        v = reais / 1e9
        return f"R$ {n(v, 1).removesuffix(',0')} {'bilhão' if v < 2 else 'bilhões'}"
    if reais >= 1e6:
        v = reais / 1e6
        return f"R$ {n(v, 1).removesuffix(',0')} {'milhão' if v < 2 else 'milhões'}"
    return f"R$ {n(reais, 0)}"


def _escolher(opcoes: list[str], semente) -> str:
    return random.Random(str(semente)).choice(opcoes)


# ------------------------------------------------------------------ pautas
def fatos_queimadas(d: dict) -> list[str]:
    f = [f"Data: {data_extenso(d['dia'])} de {d['dia'][:4]}",
         f"Focos de calor em Mato Grosso no dia: {n(d['total'])}",
         f"Satélite usado na contagem: {d['satelite']}",
         f"Municípios com pelo menos um foco: {n(d['municipios_afetados'])}"]
    for i, (mun, q) in enumerate(d["top_municipios"][:5], 1):
        f.append(f"{i}º município: {mun}, {n(q)} focos")
    if d.get("ontem") is not None:
        f.append(f"Focos no dia anterior: {n(d['ontem'])}")
    if d.get("media7") is not None:
        f.append(f"Média dos 7 dias anteriores: {n(d['media7'])}")
    return f


def legenda_queimadas(d: dict) -> str:
    total, dia = d["total"], data_extenso(d["dia"])
    if total == 0:
        return (f"Nenhum foco de calor foi detectado em Mato Grosso em {dia} pelo satélite {d['satelite']}, "
                "usado pelo INPE como referência.\n\nFonte: INPE, Programa Queimadas.\n\n#MatoGrosso #Queimadas")
    abertura = _escolher([
        f"Mato Grosso registrou {n(total)} focos de calor em {dia}.",
        f"Foram {n(total)} focos de calor em Mato Grosso em {dia}, segundo o INPE.",
        f"O satélite de referência do INPE contou {n(total)} focos de calor em Mato Grosso em {dia}.",
    ], d["dia"])
    partes = [abertura]
    if d["top_municipios"]:
        mun, q = d["top_municipios"][0]
        partes.append(_escolher([
            f"{mun} teve o maior número, com {n(q)}.",
            f"O município com mais focos foi {mun}: {n(q)}.",
        ], d["dia"] + "b"))
    if d.get("ontem") is not None:
        dif = total - d["ontem"]
        if dif > 0:
            partes.append(f"São {n(dif)} a mais que no dia anterior.")
        elif dif < 0:
            partes.append(f"São {n(-dif)} a menos que no dia anterior.")
        else:
            partes.append("O número ficou igual ao do dia anterior.")
    texto = " ".join(partes)
    texto += ("\n\nFoco de calor não é o mesmo que incêndio: é um ponto onde o satélite viu temperatura muito acima "
              "do entorno. Em geral, indica queimada.")
    if not d.get("satelite_e_referencia"):
        texto += f"\n\nObs.: neste dia não houve passagem do satélite de referência; a contagem usa o {d['satelite']}."
    texto += "\n\nFonte: INPE, Programa Queimadas.\n\n#MatoGrosso #Queimadas #Cerrado"
    return texto


def fatos_clima(d: dict) -> list[str]:
    f = []
    for c in d["cidades"]:
        f.append(f"{c['cidade']}, {data_extenso(c['dia'])}: máxima {n(c['max'])} °C, mínima {n(c['min'])} °C, "
                 f"umidade mínima {n(c['umidade_min'])}%, chance de chuva {n(c['chuva_prob'])}%")
    return f


def legenda_clima(d: dict) -> str:
    c = d["cidades"][0]
    linhas = [f"Previsão para {c['cidade']} hoje: máxima de {n(c['max'])} °C e mínima de {n(c['min'])} °C."]
    if c.get("umidade_min") is not None and c["umidade_min"] < 30:
        linhas.append(f"A umidade pode cair para {n(c['umidade_min'])}%. Beba água e evite exercício ao ar livre à tarde.")
    if c.get("chuva_prob") is not None:
        linhas.append(f"Chance de chuva: {n(c['chuva_prob'])}%.")
    return " ".join(linhas) + "\n\nFonte: Open-Meteo."


def fatos_municipio(d: dict) -> list[str]:
    f = [f"Município: {d['nome']}", f"Região imediata (IBGE): {d.get('regiao_imediata') or '-'}"]
    if d.get("populacao"):
        f.append(f"População no Censo 2022: {n(d['populacao'])} habitantes, {d.get('pos_pop')}º maior de MT entre {d['total_mun']}")
        if d.get("pct_pop"):
            f.append(f"Parcela da população de MT: {n(d['pct_pop'], 1)}%")
    if d.get("area_km2"):
        f.append(f"Área: {n(d['area_km2'], 1)} km², {d.get('pos_area')}º maior de MT")
    if d.get("densidade") is not None:
        f.append(f"Densidade: {n(d['densidade'], 2)} habitantes por km²")
    if d.get("pib_mil"):
        f.append(f"PIB em {d.get('pib_ano')}: {dinheiro_mil(d['pib_mil'])}, {d.get('pos_pib')}º de MT")
        if d.get("pct_pib"):
            f.append(f"Parcela do PIB de MT: {n(d['pct_pib'], 1)}%")
    return f


def legenda_municipio(d: dict) -> str:
    nome = d["nome"]
    partes = [_escolher([
        f"{nome} é o município de hoje.",
        f"Hoje o assunto é {nome}.",
        f"Município do dia: {nome}.",
    ], nome)]
    if d.get("populacao"):
        partes.append(f"No Censo 2022, tinha {n(d['populacao'])} moradores, a {d['pos_pop']}ª maior população de Mato Grosso.")
    if d.get("area_km2"):
        partes.append(f"São {n(d['area_km2'], 0)} km² de área.")
    if d.get("pib_mil"):
        partes.append(f"O PIB de {d['pib_ano']} foi de {dinheiro_mil(d['pib_mil'])}, {d['pos_pib']}º lugar no estado.")
    texto = " ".join(partes)
    texto += "\n\nVocê mora ou já passou por lá? Conta nos comentários."
    texto += "\n\nFonte: IBGE (Censo 2022 e PIB dos Municípios)."
    tag = "#" + "".join(p.capitalize() for p in nome.replace("-", " ").split() if p.isalpha())
    return texto + f"\n\n#MatoGrosso {tag}"


def fatos_ranking(d: dict) -> list[str]:
    f = [f"Ranking: {d['titulo']}"]
    for i, item in enumerate(d["itens"], 1):  # item = [nome, texto_formatado, valor]
        f.append(f"{i}º {item[0]}: {item[1]}")
    return f


def legenda_ranking(d: dict) -> str:
    primeiro, segundo = d["itens"][0], d["itens"][1]
    texto = (f"{d['titulo']}. {primeiro[0]} lidera, seguido de {segundo[0]}. "
             f"Os dez primeiros estão na imagem.\n\nFonte: {d['fonte']}.\n\n#MatoGrosso")
    return texto


def fatos_diario(d: dict) -> list[str]:
    return [f"Município: {d['municipio']}", f"Data do diário: {d['data']}", f"Trecho original: {d['trecho']}"]


def legenda_diario(d: dict) -> str:
    return (f"Publicado no diário oficial de {d['municipio']} ({d['data']}).\n\n"
            f"[RESUMO A ESCREVER: leia o trecho na aba Dados]\n\nFonte: diário oficial do município, via Querido Diário.")


def fatos_agenda(d: dict) -> list[str]:
    return [f"Título: {d['titulo']}", f"Texto: {d['texto']}", f"Fonte: {d.get('fonte', '')}"]


def legenda_agenda(d: dict) -> str:
    fonte = f"\n\nFonte: {d['fonte']}." if d.get("fonte") else ""
    return f"{d['titulo']}.\n\n{d['texto']}{fonte}\n\n#MatoGrosso"


PAUTAS = {
    "queimadas": (fatos_queimadas, legenda_queimadas),
    "clima": (fatos_clima, legenda_clima),
    "municipio": (fatos_municipio, legenda_municipio),
    "ranking": (fatos_ranking, legenda_ranking),
    "diario": (fatos_diario, legenda_diario),
    "agenda": (fatos_agenda, legenda_agenda),
}

# ------------------------------------------------------------------ Claude
SISTEMA = """Você escreve legendas de Instagram para um perfil independente de dados públicos de Mato Grosso.
Escreva como um jornalista local experiente escreveria: português do Brasil, direto, frases curtas, vocabulário comum de Cuiabá e do interior.

Regras obrigatórias:
- Use SOMENTE os números e fatos da lista FATOS. Não arredonde de forma diferente, não calcule porcentagens novas, não invente contexto, causas, nomes ou datas.
- Nunca use travessão (—). Use vírgula ou ponto.
- Sem emojis. Sem hashtags no meio do texto. No fim, no máximo 3 hashtags.
- Proibido: "além disso", "vale ressaltar", "vale destacar", "é importante", "em suma", "confira", "descubra", "mergulhe", "jornada", "fascinante", "crucial", "incrível", "não apenas... mas também", "você sabia".
- Nada de abertura genérica nem conclusão moral. Comece pelo dado mais forte.
- Não opine sobre governo, prefeitos ou partidos. Apenas informe.
- Termine com a linha "Fonte: ..." usando a fonte informada.
- Entre 300 e 700 caracteres, salvo se a tarefa pedir outro tamanho.
Responda apenas com a legenda pronta, sem comentários."""


def redigir(pauta: str, dados: dict, post_id: int | None = None, instrucao_extra: str = "",
            usar_ia: bool = True) -> tuple[str, str, list[str]]:
    """Retorna (legenda, 'claude'|'modelo', avisos)."""
    fatos_fn, legenda_fn = PAUTAS[pauta]
    fatos = fatos_fn(dados)
    base = legenda_fn(dados)
    avisos: list[str] = []
    if usar_ia:
        tarefa = "Reescreva a legenda-base com suas palavras, mantendo os fatos." if pauta != "diario" else (
            "Resuma o trecho do diário oficial em linguagem simples: o que foi publicado, por quem e o que muda "
            "para o morador. Se o trecho estiver confuso ou incompleto, responda exatamente: SEM_PAUTA")
        usuario = (f"TAREFA: {tarefa}\n{instrucao_extra}\n\nFATOS:\n- " + "\n- ".join(fatos) +
                   f"\n\nLEGENDA-BASE:\n{base}")
        try:
            texto = gerar(SISTEMA, usuario, f"legenda:{pauta}", post_id)
            if texto.strip() == "SEM_PAUTA":
                raise IAIndisponivel("Claude considerou o trecho sem conteúdo útil")
            texto = estilo.limpar(texto)
            inventados = estilo.numeros_inventados(texto, "\n".join(fatos) + base)
            if inventados:
                avisos.append("Claude usou números fora dos dados (" + ", ".join(inventados[:5]) +
                              "). Mantive o texto-modelo.")
            else:
                return texto, "claude", avisos + estilo.avisos(texto)
        except IAIndisponivel as e:
            avisos.append(f"Texto-modelo usado: {e}")
    texto = estilo.limpar(base)
    return texto, "modelo", avisos + estilo.avisos(texto)
