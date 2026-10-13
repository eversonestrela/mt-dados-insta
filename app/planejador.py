"""Monta a pauta do dia para cada conta: coleta dados, gera artes e legendas e põe na fila."""
from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timedelta

from .arte import pecas, video
from .arte.base import STORY
from .base import MIDIA, agora, cfg, conta as obter_conta, db, log, post as obter_post, salvar_cfg, atualizar_post
from .coletores import agenda, clima, diarios, ibge, queimadas
from .texto import redator
from .texto.redator import dinheiro_mil, n

PRIORIDADE = ["queimadas", "clima", "queimadas_story", "municipio", "ranking", "agenda", "diario", "municipio_reel"]


# ------------------------------------------------------------------ dados compartilhados do dia
class DadosDoDia:
    """Coleta uma vez por dia e reaproveita entre contas."""

    def __init__(self, dia: date):
        self.dia = dia
        self._cache: dict = {}

    def _pegar(self, chave, fn):
        if chave not in self._cache:
            try:
                self._cache[chave] = fn()
            except Exception as e:  # noqa: BLE001
                log(f"Coleta '{chave}' falhou: {e}", "erro")
                self._cache[chave] = None
        return self._cache[chave]

    def malha(self):
        return self._pegar("malha", ibge.malha_mt)

    def queimadas(self):
        def fn():
            ontem = self.dia - timedelta(days=1)
            r = queimadas.coletar(ontem)
            if not r:
                return None
            serie = queimadas.serie(ontem, 7)
            r["serie"] = serie
            anteriores = [v for d, v in serie if d < r["dia"]]
            r["ontem"] = anteriores[-1] if anteriores else None
            r["media7"] = round(sum(anteriores) / len(anteriores)) if anteriores else None
            return r
        return self._pegar("queimadas", fn)

    def clima(self):
        return self._pegar("clima", lambda: {"cidades": clima.coletar(self.dia)} if clima.cidades() else None)

    def municipios(self):
        return self._pegar("municipios", ibge.municipios)

    def indicadores(self):
        return self._pegar("indicadores", ibge.indicadores)

    def diarios(self):
        return self._pegar("diarios", lambda: diarios.coletar(self.dia))

    def agenda(self):
        return self._pegar("agenda", lambda: agenda.coletar(self.dia))


def dados_municipio(dd: DadosDoDia, cod: str) -> dict | None:
    muns = {m["id"]: m for m in (dd.municipios() or [])}
    if cod not in muns:
        return None
    m = muns[cod]
    ind = dd.indicadores() or {}
    i = ind.get(cod, {})
    tot_pop = sum(v.get("populacao") or 0 for v in ind.values())
    tot_pib = sum(v.get("pib_mil") or 0 for v in ind.values())
    return {
        "codigo": cod, "nome": m["nome"], "regiao_imediata": m.get("regiao_imediata"),
        "populacao": i.get("populacao"), "area_km2": i.get("area_km2"), "densidade": i.get("densidade"),
        "pib_mil": i.get("pib_mil"), "pib_ano": i.get("pib_ano"),
        "pos_pop": ibge.posicao(ind, "populacao", cod), "pos_area": ibge.posicao(ind, "area_km2", cod),
        "pos_pib": ibge.posicao(ind, "pib_mil", cod), "total_mun": len(muns),
        "pct_pop": round(100 * i["populacao"] / tot_pop, 1) if i.get("populacao") and tot_pop else None,
        "pct_pib": round(100 * i["pib_mil"] / tot_pib, 1) if i.get("pib_mil") and tot_pib else None,
    }


def proximo_municipio(ct: dict, dd: DadosDoDia) -> str | None:
    """Rodízio por conta: cada dia um município diferente, sem repetir até acabar a lista."""
    lista = [m["id"] for m in (dd.municipios() or [])]
    foco = [c.strip() for c in (ct.get("municipios_foco") or "").split(",") if c.strip()]
    if foco:
        lista = [c for c in lista if c in foco] or lista
    if not lista:
        return None
    chave = f"rodizio_municipio_{ct['id']}"
    pos = int(cfg(chave) or 0)
    salvar_cfg(chave, pos + 1)
    return lista[pos % len(lista)]


METRICAS = [
    ("populacao", "Os 10 municípios mais populosos de Mato Grosso", "População", "IBGE, Censo 2022", lambda v: n(v)),
    ("pib_mil", "Os 10 maiores PIBs municipais de Mato Grosso", "Economia", "IBGE, PIB dos Municípios", dinheiro_mil),
    ("area_km2", "Os 10 maiores municípios de MT em área", "Território", "IBGE", lambda v: f"{n(v)} km²"),
    ("densidade", "Os 10 municípios com mais moradores por km² em MT", "Densidade", "IBGE, Censo 2022",
     lambda v: f"{n(v, 1)} hab/km²"),
]


def dados_ranking(dd: DadosDoDia, variante: int = 0) -> dict | None:
    ind = dd.indicadores()
    if not ind:
        return None
    nomes = {m["id"]: m["nome"] for m in (dd.municipios() or [])}
    campo, titulo, chapeu, fonte, fmt = METRICAS[(dd.dia.toordinal() + variante) % len(METRICAS)]
    top = ibge.ranking(ind, campo)[:10]
    if len(top) < 3:
        return None
    return {"titulo": titulo, "chapeu": f"Ranking · {chapeu}", "fonte": fonte,
            "itens": [[nomes.get(c, c), fmt(v), v] for c, v in top]}


# ------------------------------------------------------------------ criação dos posts
def _novo_post(ct: dict, dia: date, tipo: str, pauta: str, titulo: str, dados: dict, fonte: str,
               revisao_obrigatoria: bool = False) -> int:
    momento = datetime.now().isoformat(timespec="seconds")
    with db() as c:
        cur = c.execute(
            "INSERT INTO posts(conta_id,dia,tipo,pauta,titulo,dados,fonte,revisao_obrigatoria,status,criado_em,atualizado_em)"
            " VALUES(?,?,?,?,?,?,?,?, 'gerando', ?, ?)",
            (ct["id"], dia.isoformat(), tipo, pauta, titulo, json.dumps(_serializavel(dados), ensure_ascii=False),
             fonte, int(revisao_obrigatoria), momento, momento),
        )
        return cur.lastrowid


def _serializavel(d: dict) -> dict:
    copia = dict(d)
    copia.pop("pontos", None)  # milhares de coordenadas não precisam ir para o banco
    return copia


def _pasta(ct: dict, dia: date, post_id: int):
    p = MIDIA / dia.isoformat() / f"conta{ct['id']}" / f"post{post_id}"
    if p.exists():
        shutil.rmtree(p)
    p.mkdir(parents=True)
    return p


def _rel(caminhos) -> list[str]:
    return [str(p.relative_to(MIDIA)).replace("\\", "/") for p in caminhos]


def renderizar(ct: dict, p: dict, dd: DadosDoDia, dados_completos: dict | None = None) -> list[str]:
    """(Re)gera a arte de um post a partir dos dados guardados."""
    dia = date.fromisoformat(p["dia"])
    d = dados_completos or p["dados"]
    pasta = _pasta(ct, dia, p["id"])
    pauta, tipo = p["pauta"], p["tipo"]
    if pauta == "queimadas":
        if "pontos" not in d:  # pontos não ficam no banco; recarrega do cache do INPE
            atual = dd.queimadas()
            d = {**d, "pontos": (atual or {}).get("pontos", [])}
        arqs = (pecas.queimadas_story if tipo == "story" else pecas.queimadas_feed)(d, ct, dd.malha(), pasta)
    elif pauta == "clima":
        arqs = pecas.clima_story(d, ct, pasta)
    elif pauta == "municipio" and tipo == "reel":
        slides = pecas.municipio_slides(d, ct, dd.malha(), STORY)
        imgs = [s.salvar(pasta / f"slide_{i + 1}.jpg") for i, s in enumerate(slides)]
        arqs = [video.slides_para_reel(imgs, pasta / "reel.mp4"), imgs[0]]  # vídeo + capa
    elif pauta == "municipio":
        arqs = pecas.municipio_carrossel(d, ct, dd.malha(), pasta)
    elif pauta == "ranking":
        arqs = pecas.ranking_feed(d, ct, pasta)
    elif pauta == "diario":
        titulo, corpo = pecas.resumo_para_arte(p.get("legenda") or "")
        arqs = pecas.texto_feed(f"Diário oficial · {d['municipio']}", titulo, corpo,
                                f"Diário oficial de {d['municipio']}, via Querido Diário", ct, pasta, "diario.jpg")
    elif pauta == "agenda":
        arqs = pecas.texto_feed("Hoje", d["titulo"], d["texto"], d.get("fonte") or "", ct, pasta, "agenda.jpg")
    else:
        raise ValueError(f"Pauta desconhecida: {pauta}")
    return _rel(arqs)


def _finalizar(ct: dict, post_id: int, dd: DadosDoDia, dados_completos: dict, usar_ia: bool = True) -> None:
    p = obter_post(post_id)
    try:
        legenda, por, avisos = "", "modelo", []
        if p["tipo"] != "story":  # story não tem legenda na API
            pauta_txt = "municipio" if p["pauta"] == "municipio" else p["pauta"]
            legenda, por, avisos = redator.redigir(pauta_txt, dados_completos, post_id, usar_ia=usar_ia)
        if p["pauta"] == "diario" and por != "claude":
            atualizar_post(post_id, status="rejeitado", erro="Diário oficial precisa do Claude para resumir; IA indisponível.",
                           avisos=avisos)
            return
        atualizar_post(post_id, legenda=legenda, texto_por=por, avisos=avisos)
        p = obter_post(post_id)
        midias = renderizar(ct, p, dd, dados_completos)
        auto = ct.get("auto_aprovar") and not p["revisao_obrigatoria"] and not avisos
        atualizar_post(post_id, midias=midias, status="aprovado" if auto else "revisao")
    except Exception as e:  # noqa: BLE001
        log(f"Post {post_id} ({p['pauta']}) falhou: {e}", "erro")
        atualizar_post(post_id, status="erro", erro=str(e)[:500])


def gerar_dia(conta_id: int, dia: date | None = None, dd: DadosDoDia | None = None, forcar: bool = False) -> int:
    ct = obter_conta(conta_id)
    dia = dia or agora().date()
    dd = dd or DadosDoDia(dia)
    if not forcar:
        with db() as c:
            ja = c.execute("SELECT COUNT(*) n FROM posts WHERE conta_id=? AND dia=? AND status!='rejeitado'",
                           (conta_id, dia.isoformat())).fetchone()["n"]
        if ja:
            log(f"Conta {ct['nome']}: dia {dia} já tem {ja} posts; nada gerado.")
            return 0
    pautas = set(json.loads(ct.get("pautas") or "[]"))
    planos: list[tuple[str, str, str, str, dict, str, bool]] = []  # (ordem, tipo, pauta, titulo, dados, fonte, revisao)

    if "queimadas" in pautas and (q := dd.queimadas()):
        planos.append(("queimadas", "feed", "queimadas", f"Queimadas {q['dia']}", q, "INPE", False))
        planos.append(("queimadas_story", "story", "queimadas", f"Queimadas (story) {q['dia']}", q, "INPE", False))
    if "clima" in pautas and (cl := dd.clima()):
        planos.append(("clima", "story", "clima", f"Tempo {dia}", cl, "Open-Meteo", False))
    if "municipio" in pautas and (cod := proximo_municipio(ct, dd)) and (m := dados_municipio(dd, cod)):
        planos.append(("municipio", "carrossel", "municipio", f"Município: {m['nome']}", m, "IBGE", False))
    if "municipio_reel" in pautas and (cod := proximo_municipio(ct, dd)) and (m := dados_municipio(dd, cod)):
        planos.append(("municipio_reel", "reel", "municipio", f"Reel: {m['nome']}", m, "IBGE", False))
    if "ranking" in pautas and (r := dados_ranking(dd)):
        planos.append(("ranking", "feed", "ranking", r["titulo"], r, r["fonte"], False))
    if "agenda" in pautas:
        for item in dd.agenda() or []:
            planos.append(("agenda", "feed", "agenda", item["titulo"], dict(item), item.get("fonte", ""), False))
    if "diario" in pautas and cfg("ia_ativa"):
        foco = {c.strip() for c in (ct.get("municipios_foco") or "").split(",") if c.strip()}
        achados = [a for a in (dd.diarios() or []) if not foco or a["codigo"] in foco]
        if achados:
            a = max(achados, key=lambda x: len(x["trecho"]))
            planos.append(("diario", "feed", "diario", f"Diário oficial: {a['municipio']}", a, "Querido Diário", True))

    # completa o mínimo do dia com rankings de outras métricas
    variante = 1
    while len(planos) < int(cfg("posts_por_dia")) and variante < len(METRICAS):
        r = dados_ranking(dd, variante)
        variante += 1
        if r and r["titulo"] not in {p[3] for p in planos}:
            planos.append(("ranking", "feed", "ranking", r["titulo"], r, r["fonte"], False))

    planos.sort(key=lambda p: PRIORIDADE.index(p[0]) if p[0] in PRIORIDADE else 99)
    horarios = sorted(json.loads(ct.get("horarios") or '["09:00"]'))
    criados = 0
    for i, (_, tipo, pauta, titulo, dados, fonte, revisao) in enumerate(planos):
        post_id = _novo_post(ct, dia, tipo, pauta, titulo, dados, fonte, revisao)
        if i < len(horarios):
            hh, mm = map(int, horarios[i].split(":"))
            quando = datetime.combine(dia, datetime.min.time()).replace(hour=hh, minute=mm)
        else:
            hh, mm = map(int, horarios[-1].split(":"))
            quando = datetime.combine(dia, datetime.min.time()).replace(hour=hh, minute=mm) + timedelta(minutes=40 * (i - len(horarios) + 1))
        atualizar_post(post_id, agendado_para=quando.isoformat(timespec="minutes"))
        _finalizar(ct, post_id, dd, dados)
        criados += 1
    log(f"Conta {ct['nome']}: {criados} posts gerados para {dia}.")
    return criados


def gerar_todas(dia: date | None = None) -> None:
    from .base import contas
    dia = dia or agora().date()
    dd = DadosDoDia(dia)
    for ct in contas(somente_ativas=True):
        try:
            gerar_dia(ct["id"], dia, dd)
        except Exception as e:  # noqa: BLE001
            log(f"Falha ao gerar o dia da conta {ct['nome']}: {e}", "erro")
    salvar_cfg("ultima_geracao", dia.isoformat())


# ------------------------------------------------------------------ ações da revisão
def reescrever(post_id: int, instrucao: str = "") -> None:
    p = obter_post(post_id)
    ct = obter_conta(p["conta_id"])
    dados = p["dados"]
    legenda, por, avisos = redator.redigir(p["pauta"], dados, post_id, instrucao_extra=instrucao)
    atualizar_post(post_id, legenda=legenda, texto_por=por, avisos=avisos)
    if p["pauta"] == "diario":
        p = obter_post(post_id)
        atualizar_post(post_id, midias=renderizar(ct, p, DadosDoDia(date.fromisoformat(p["dia"]))))


def regerar_arte(post_id: int) -> None:
    p = obter_post(post_id)
    ct = obter_conta(p["conta_id"])
    atualizar_post(post_id, midias=renderizar(ct, p, DadosDoDia(date.fromisoformat(p["dia"]))))
