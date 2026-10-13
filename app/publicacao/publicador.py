"""Publica os posts aprovados no horário e renova tokens."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta

from ..base import agora, atualizar_post, cifrar, conta as obter_conta, contas, db, log, post as obter_post, token_da_conta
from . import hospedagem
from .instagram import ErroInstagram, Instagram

_trava = threading.Lock()


def cliente(ct: dict) -> Instagram:
    if not ct.get("ig_user_id") or not token_da_conta(ct):
        raise ErroInstagram("Conta sem ID do Instagram ou sem token")
    return Instagram(ct["ig_user_id"], token_da_conta(ct), ct.get("api_host") or "graph.instagram.com",
                     ct.get("api_versao") or "v26.0")


def publicar(post_id: int) -> None:
    p = obter_post(post_id)
    if not p or p["status"] not in ("aprovado", "erro"):
        return
    ct = obter_conta(p["conta_id"])
    if not ct or not ct["ativa"]:
        return
    atualizar_post(post_id, status="publicando", erro=None)
    enviados: list[dict] = []
    try:
        ig = cliente(ct)
        lim = ig.limite_publicacao()
        if lim["usado"] >= lim["total"]:
            raise ErroInstagram(f"Limite de publicações da API atingido ({lim['usado']}/{lim['total']} em 24h)")

        def subir(rel: str) -> str:
            url, info = hospedagem.enviar(rel)
            enviados.append(info)
            return url

        midias = p["midias"]
        if not midias:
            raise ErroInstagram("Post sem mídia")
        if p["tipo"] == "feed":
            mid = ig.imagem(subir(midias[0]), p["legenda"])
        elif p["tipo"] == "carrossel":
            mid = ig.carrossel([subir(m) for m in midias], p["legenda"]) if len(midias) > 1 else ig.imagem(subir(midias[0]), p["legenda"])
        elif p["tipo"] == "story":
            mid = ig.story(subir(midias[0]), video=midias[0].endswith(".mp4"))
        elif p["tipo"] == "reel":
            capa = subir(midias[1]) if len(midias) > 1 else None
            mid = ig.reel(subir(midias[0]), p["legenda"], capa)
        else:
            raise ErroInstagram(f"Tipo desconhecido: {p['tipo']}")
        atualizar_post(post_id, status="publicado", ig_media_id=mid, link=ig.link(mid),
                       publicado_em=agora().isoformat(timespec="seconds"))
        log(f"Publicado: post {post_id} ({p['tipo']}/{p['pauta']}) na conta {ct['nome']}")
    except Exception as e:  # noqa: BLE001
        atualizar_post(post_id, status="erro", erro=str(e)[:800])
        log(f"Erro ao publicar post {post_id}: {e}", "erro")
    finally:
        for info in enviados:
            hospedagem.apagar(info)


def publicar_vencidos() -> None:
    """Roda a cada minuto: publica o que está aprovado e com horário vencido."""
    if not _trava.acquire(blocking=False):
        return
    try:
        limite = agora().replace(tzinfo=None).isoformat(timespec="minutes")
        with db() as c:
            ids = [r["id"] for r in c.execute(
                "SELECT p.id FROM posts p JOIN contas c ON c.id=p.conta_id "
                "WHERE p.status='aprovado' AND p.agendado_para<=? AND c.ativa=1 ORDER BY p.agendado_para",
                (limite,))]
        for pid in ids:
            publicar(pid)
    finally:
        _trava.release()


def renovar_tokens() -> None:
    """Tokens do Instagram Login valem 60 dias; renova quando faltam menos de 15."""
    for ct in contas(somente_ativas=True):
        if (ct.get("api_host") or "") != "graph.instagram.com" or not token_da_conta(ct):
            continue
        exp = ct.get("token_expira_em")
        try:
            vence = datetime.fromisoformat(exp) if exp else None
        except ValueError:
            vence = None
        if vence and vence - datetime.now() > timedelta(days=15):
            continue
        try:
            novo, expira = cliente(ct).renovar_token()
            with db() as c:
                c.execute("UPDATE contas SET token_cifrado=?, token_expira_em=?, token_atualizado_em=? WHERE id=?",
                          (cifrar(novo), expira, datetime.now().isoformat(timespec="minutes"), ct["id"]))
            log(f"Token renovado: {ct['nome']} (vale até {expira})")
        except Exception as e:  # noqa: BLE001
            log(f"Não consegui renovar o token de {ct['nome']}: {e}", "erro")
