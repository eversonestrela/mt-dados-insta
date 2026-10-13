"""Painel local (http://127.0.0.1:8765): revisão, aprovação, contas e configurações."""
from __future__ import annotations

import json
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import agendador, base, servidor_midia
from .base import MIDIA, PADRAO, RAIZ, agora, atualizar_post, cfg, cifrar, contas, db, log, salvar_cfg
from .coletores import agenda as agenda_csv
from .planejador import gerar_dia, regerar_arte, reescrever
from .publicacao import hospedagem
from .publicacao.publicador import cliente, publicar
from .texto import estilo, ia

PAUTAS_DISPONIVEIS = {
    "queimadas": "Queimadas do dia (feed + story) · INPE",
    "clima": "Tempo do dia (story) · Open-Meteo",
    "municipio": "Município do dia (carrossel) · IBGE",
    "municipio_reel": "Município do dia (reel) · IBGE",
    "ranking": "Rankings de municípios (feed) · IBGE",
    "diario": "Diário oficial (feed, exige Claude e revisão) · Querido Diário",
    "agenda": "Datas da sua agenda (feed) · dados/agenda.csv",
}
STATUS = {"revisao": "Para revisar", "aprovado": "Aprovado", "publicando": "Publicando", "publicado": "Publicado",
          "rejeitado": "Rejeitado", "erro": "Erro", "gerando": "Gerando"}
TIPOS = {"feed": "Feed", "carrossel": "Carrossel", "story": "Story", "reel": "Reel"}


@asynccontextmanager
async def ciclo(app_: FastAPI):
    base.iniciar_db()
    agenda_csv.garantir_arquivo()
    with db() as c:  # posts que ficaram presos se o programa fechou no meio
        c.execute("UPDATE posts SET status='erro', erro='Interrompido (programa fechado)' WHERE status IN ('gerando','publicando')")
    if cfg("hospedagem") == "url_publica":
        servidor_midia.iniciar()
    agendador.iniciar()
    yield
    agendador.parar()


app = FastAPI(title="MT em Dados", lifespan=ciclo)
app.mount("/static/fontes", StaticFiles(directory=base.FONTES), name="fontes")
app.mount("/static", StaticFiles(directory=RAIZ / "app" / "web" / "static"), name="static")
app.mount("/midia", StaticFiles(directory=MIDIA), name="midia")
tpl = Jinja2Templates(directory=RAIZ / "app" / "web" / "templates")
tpl.env.globals.update(STATUS=STATUS, TIPOS=TIPOS, PAUTAS=PAUTAS_DISPONIVEIS)


def _hora(iso: str | None) -> str:
    if not iso:
        return "-"
    try:
        d = datetime.fromisoformat(iso)
        hoje = datetime.now().date()
        return d.strftime("%H:%M") if d.date() == hoje else d.strftime("%d/%m %H:%M")
    except ValueError:
        return iso


tpl.env.filters["hora"] = _hora
tpl.env.filters["milhar"] = lambda v: f"{int(v or 0):,}".replace(",", ".")


def ir(url: str, msg: str = "", erro: bool = False) -> RedirectResponse:
    if msg:
        url += ("&" if "?" in url else "?") + ("erro=" if erro else "msg=") + quote(msg)
    return RedirectResponse(url, status_code=303)


def pagina(request: Request, nome: str, **ctx) -> HTMLResponse:
    ctx.update(request=request, msg=request.query_params.get("msg"), erro=request.query_params.get("erro"),
               uso=ia.uso(), ia_ativa=cfg("ia_ativa"))
    with db() as c:
        ctx["n_revisao"] = c.execute("SELECT COUNT(*) n FROM posts WHERE status='revisao'").fetchone()["n"]
        ctx["n_erro"] = c.execute("SELECT COUNT(*) n FROM posts WHERE status='erro'").fetchone()["n"]
    return tpl.TemplateResponse(request, nome, ctx)


def _posts(where: str = "1=1", params: tuple = (), limite: int = 200) -> list[dict]:
    with db() as c:
        linhas = c.execute(
            f"SELECT p.*, c.nome conta_nome, c.arroba FROM posts p JOIN contas c ON c.id=p.conta_id WHERE {where} "
            f"ORDER BY p.agendado_para LIMIT {limite}", params).fetchall()
    saida = []
    for r in linhas:
        p = dict(r)
        p["midias"] = json.loads(p["midias"] or "[]")
        p["avisos"] = json.loads(p["avisos"] or "[]")
        saida.append(p)
    return saida


def _em_segundo_plano(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()


# ====================================================================== painel
@app.get("/", response_class=HTMLResponse)
def painel(request: Request):
    hoje = agora().date().isoformat()
    proximos = _posts("p.status IN ('aprovado','revisao') AND p.agendado_para>=?",
                      (agora().replace(tzinfo=None).isoformat(timespec="minutes"),), 8)
    with db() as c:
        cont = {r["status"]: r["n"] for r in c.execute(
            "SELECT status, COUNT(*) n FROM posts WHERE dia=? GROUP BY status", (hoje,))}
    login = ia.status_login() if cfg("ia_ativa") and cfg("ia_provedor") == "claude_code" else None
    return pagina(request, "painel.html", proximos=proximos, cont=cont, contas=contas(), login=login,
                  ultima=cfg("ultima_geracao"), horario=cfg("geracao_horario"))


@app.post("/gerar")
def gerar_agora(conta_id: int = Form(...), forcar: str = Form("")):
    _em_segundo_plano(gerar_dia, conta_id, None, None, bool(forcar))
    return ir("/fila", "Gerando a pauta em segundo plano. Atualize a página em 1 ou 2 minutos.")


# ====================================================================== fila / revisão
@app.get("/fila", response_class=HTMLResponse)
def fila(request: Request, status: str = "revisao", conta: int | None = None):
    where, params = "p.status=?", [status]
    if status == "todos":
        where, params = "1=1", []
    if conta:
        where += " AND p.conta_id=?"
        params.append(conta)
    ordem_inv = status in ("publicado", "todos", "rejeitado")
    posts = _posts(where, tuple(params), 300)
    if ordem_inv:
        posts.reverse()
    return pagina(request, "fila.html", posts=posts, status=status, conta_sel=conta, contas=contas())


@app.post("/fila/aprovar-sem-avisos")
def aprovar_lote():
    with db() as c:
        r = c.execute("UPDATE posts SET status='aprovado' WHERE status='revisao' AND revisao_obrigatoria=0 "
                      "AND (avisos IS NULL OR avisos='[]')")
    return ir("/fila", f"{r.rowcount} post(s) aprovado(s).")


@app.get("/post/{pid}", response_class=HTMLResponse)
def ver_post(request: Request, pid: int):
    p = base.post(pid)
    if not p:
        return ir("/fila", "Post não encontrado", True)
    ct = base.conta(p["conta_id"])
    fatos = []
    try:
        from .texto.redator import PAUTAS
        fatos = PAUTAS[p["pauta"]][0](p["dados"])
    except Exception:  # noqa: BLE001
        pass
    estimativa = int((len(json.dumps(p["dados"], ensure_ascii=False)) + 2500) / 2.5 * 1.5) + int(cfg("ia_max_saida"))
    return pagina(request, "post.html", p=p, ct=ct, fatos=fatos, estimativa=estimativa,
                  limite=estilo.LIMITE_LEGENDA)


@app.post("/post/{pid}/salvar")
def salvar_post(pid: int, legenda: str = Form(""), agendado_para: str = Form(""), acao: str = Form("salvar")):
    p = base.post(pid)
    campos = {}
    if p["tipo"] != "story":
        legenda = legenda.replace("\r\n", "\n").strip()
        campos["legenda"] = legenda
        campos["avisos"] = estilo.avisos(legenda)
        if legenda != p["legenda"] and p["texto_por"] == "claude":
            campos["texto_por"] = "claude+você"
    if agendado_para:
        campos["agendado_para"] = agendado_para[:16]
    if acao == "aprovar":
        campos["status"] = "aprovado"
    elif acao == "rejeitar":
        campos["status"] = "rejeitado"
    elif acao == "revisao":
        campos["status"] = "revisao"
    atualizar_post(pid, **campos)
    if acao == "aprovar":
        return ir(_proximo_para_revisar(pid), "Aprovado. Será publicado no horário.")
    if acao == "rejeitar":
        return ir(_proximo_para_revisar(pid), "Rejeitado.")
    return ir(f"/post/{pid}", "Salvo.")


def _proximo_para_revisar(atual: int) -> str:
    with db() as c:
        r = c.execute("SELECT id FROM posts WHERE status='revisao' AND id!=? ORDER BY agendado_para LIMIT 1",
                      (atual,)).fetchone()
    return f"/post/{r['id']}" if r else "/fila"


@app.post("/post/{pid}/rapido")
def acao_rapida(pid: int, acao: str = Form(...)):
    atualizar_post(pid, status={"aprovar": "aprovado", "rejeitar": "rejeitado"}[acao])
    return ir("/fila")


@app.post("/post/{pid}/reescrever")
def reescrever_post(pid: int, instrucao: str = Form("")):
    try:
        reescrever(pid, instrucao.strip())
        p = base.post(pid)
        if p["texto_por"] == "claude":
            return ir(f"/post/{pid}", "Legenda reescrita pelo Claude.")
        return ir(f"/post/{pid}", "Não usei o Claude: " + "; ".join(p["avisos"][:1]), True)
    except Exception as e:  # noqa: BLE001
        return ir(f"/post/{pid}", f"Falhou: {e}", True)


@app.post("/post/{pid}/arte")
def nova_arte(pid: int):
    try:
        regerar_arte(pid)
        return ir(f"/post/{pid}", "Arte gerada de novo.")
    except Exception as e:  # noqa: BLE001
        return ir(f"/post/{pid}", f"Falhou: {e}", True)


@app.post("/post/{pid}/publicar")
def publicar_agora(pid: int):
    p = base.post(pid)
    if p["status"] not in ("aprovado", "erro", "revisao"):
        return ir(f"/post/{pid}", "Este post não pode ser publicado agora.", True)
    atualizar_post(pid, status="aprovado")
    _em_segundo_plano(publicar, pid)
    return ir(f"/post/{pid}", "Publicando… atualize a página em alguns segundos.")


# ====================================================================== contas
@app.get("/contas", response_class=HTMLResponse)
def ver_contas(request: Request, editar: int | None = None):
    atual = base.conta(editar) if editar else None
    if atual:
        atual["horarios_txt"] = ", ".join(json.loads(atual["horarios"] or "[]"))
        atual["pautas_lista"] = json.loads(atual["pautas"] or "[]")
    return pagina(request, "contas.html", contas=contas(), atual=atual)


@app.post("/contas/salvar")
def salvar_conta(conta_id: int | None = Form(None), nome: str = Form(...), arroba: str = Form(""),
                 ig_user_id: str = Form(""), api_host: str = Form("graph.instagram.com"),
                 api_versao: str = Form("v26.0"), token: str = Form(""), token_expira_em: str = Form(""),
                 ativa: str = Form(""), auto_aprovar: str = Form(""), horarios: str = Form(""),
                 pautas: list[str] = Form([]), municipios_foco: str = Form(""), cor_destaque: str = Form("#B4441C")):
    hs = []
    for h in horarios.replace(";", ",").split(","):
        h = h.strip()
        try:
            hh, mm = map(int, h.split(":"))
            hs.append(f"{hh:02d}:{mm:02d}")
        except ValueError:
            continue
    campos = {
        "nome": nome.strip(), "arroba": arroba.strip().lstrip("@"), "ig_user_id": ig_user_id.strip(),
        "api_host": api_host, "api_versao": api_versao.strip() or "v26.0", "ativa": int(bool(ativa)),
        "auto_aprovar": int(bool(auto_aprovar)), "horarios": json.dumps(sorted(hs) or ["09:00"]),
        "pautas": json.dumps(pautas), "municipios_foco": municipios_foco.strip(),
        "cor_destaque": cor_destaque or "#B4441C",
    }
    if token.strip():
        campos["token_cifrado"] = cifrar(token.strip())
        campos["token_atualizado_em"] = datetime.now().isoformat(timespec="minutes")
        campos["token_expira_em"] = token_expira_em[:16] if token_expira_em else ""
    with db() as c:
        if conta_id:
            sets = ", ".join(f"{k}=?" for k in campos)
            c.execute(f"UPDATE contas SET {sets} WHERE id=?", (*campos.values(), conta_id))
        else:
            campos["criada_em"] = datetime.now().isoformat(timespec="minutes")
            cols = ", ".join(campos)
            c.execute(f"INSERT INTO contas({cols}) VALUES({', '.join('?' * len(campos))})", tuple(campos.values()))
    return ir("/contas", "Conta salva.")


@app.post("/contas/{cid}/testar")
def testar_conta(cid: int):
    ct = base.conta(cid)
    try:
        ig = cliente(ct)
        eu = ig.quem_sou()
        if not ct.get("ig_user_id") and eu.get("user_id"):
            with db() as c:
                c.execute("UPDATE contas SET ig_user_id=? WHERE id=?", (str(eu["user_id"]), cid))
            ct["ig_user_id"] = str(eu["user_id"])
            ig = cliente(ct)
        lim = ig.limite_publicacao()
        return ir("/contas", f"Conectado como @{eu.get('username')}. Publicações nas últimas 24h: "
                             f"{lim['usado']} de {lim['total']}.")
    except Exception as e:  # noqa: BLE001
        return ir("/contas", f"Falhou: {e}", True)


@app.post("/contas/{cid}/excluir")
def excluir_conta(cid: int):
    with db() as c:
        c.execute("DELETE FROM posts WHERE conta_id=? AND status!='publicado'", (cid,))
        c.execute("UPDATE contas SET ativa=0 WHERE id=?", (cid,))
        c.execute("DELETE FROM contas WHERE id=? AND NOT EXISTS (SELECT 1 FROM posts WHERE conta_id=?)", (cid, cid))
    return ir("/contas", "Conta removida (ou desativada, se já tinha posts publicados).")


# ====================================================================== configurações
CAMPOS_CFG = {
    "ia_modelo": str, "ia_limite_diario": int, "ia_limite_mensal": int, "ia_max_saida": int,
    "ia_provedor": str, "claude_caminho": str, "geracao_horario": str, "posts_por_dia": int, "hospedagem": str,
    "cloudinary_cloud": str, "cloudinary_key": str, "url_publica_base": str, "satelite_referencia": str,
    "clima_cidades": str, "diario_termos": str, "fuso": str,
}


@app.get("/config", response_class=HTMLResponse)
def ver_config(request: Request):
    valores = {k: cfg(k) for k in CAMPOS_CFG}
    valores["tem_chave_api"] = bool(cfg("anthropic_chave"))
    valores["tem_segredo_cloudinary"] = bool(cfg("cloudinary_segredo"))
    login = ia.status_login(forcar=True) if cfg("ia_provedor") == "claude_code" else None
    return pagina(request, "config.html", v=valores, login=login, caminho_claude=ia.caminho_claude())


@app.post("/config/salvar")
async def salvar_config(request: Request):
    form = await request.form()
    horario_antes = cfg("geracao_horario")
    for k, tipo in CAMPOS_CFG.items():
        if k in form:
            bruto = str(form[k]).strip()
            try:
                salvar_cfg(k, tipo(bruto) if bruto != "" or tipo is str else PADRAO.get(k))
            except ValueError:
                return ir("/config", f"Valor inválido em {k}", True)
    salvar_cfg("ia_ativa", form.get("ia_ativa") == "1")
    if str(form.get("anthropic_chave", "")).strip():
        salvar_cfg("anthropic_chave", str(form["anthropic_chave"]).strip())
    if str(form.get("cloudinary_segredo", "")).strip():
        salvar_cfg("cloudinary_segredo", str(form["cloudinary_segredo"]).strip())
    if cfg("geracao_horario") != horario_antes:
        agendador.reprogramar_geracao()
    return ir("/config", "Configurações salvas. Mudanças de hospedagem valem ao reiniciar o programa.")


@app.post("/config/testar-claude")
def testar_claude():
    try:
        if cfg("ia_provedor") == "claude_code":
            st = ia.status_login(forcar=True)
            if not st["ok"]:
                return ir("/config", st["msg"], True)
        resposta = ia.gerar("Responda só com a palavra OK.", "Teste de conexão.", "teste")
        return ir("/config", f"Claude respondeu: {resposta[:40]}")
    except Exception as e:  # noqa: BLE001
        return ir("/config", f"Falhou: {e}", True)


@app.post("/config/testar-hospedagem")
def testar_hosp():
    try:
        return ir("/config", f"Hospedagem funcionando ({hospedagem.testar()[:60]}…)")
    except Exception as e:  # noqa: BLE001
        return ir("/config", f"Falhou: {e}", True)


# ====================================================================== uso e registro
@app.get("/uso", response_class=HTMLResponse)
def ver_uso(request: Request):
    with db() as c:
        linhas = [dict(r) for r in c.execute("SELECT * FROM uso_ia ORDER BY id DESC LIMIT 200")]
        por_dia = [dict(r) for r in c.execute(
            "SELECT dia, SUM(entrada) e, SUM(saida) s, COUNT(*) n FROM uso_ia GROUP BY dia ORDER BY dia DESC LIMIT 31")]
    return pagina(request, "uso.html", linhas=linhas, por_dia=por_dia)


@app.get("/registro", response_class=HTMLResponse)
def ver_registro(request: Request):
    with db() as c:
        linhas = [dict(r) for r in c.execute("SELECT * FROM log ORDER BY id DESC LIMIT 300")]
    return pagina(request, "registro.html", linhas=linhas)


def rodar() -> None:
    import uvicorn

    log("Abrindo o painel em http://127.0.0.1:8765")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
