"""Cliente da API oficial de publicação do Instagram (Graph API).

Funciona com os dois tipos de login da Meta:
- Instagram Login  -> host graph.instagram.com (recomendado; não exige Página do Facebook)
- Facebook Login   -> host graph.facebook.com

Fluxo: cria o "contêiner" de mídia, espera ficar FINISHED e publica.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

import httpx


class ErroInstagram(Exception):
    pass


class Instagram:
    def __init__(self, ig_user_id: str, token: str, host: str = "graph.instagram.com", versao: str = "v26.0"):
        self.uid, self.token = ig_user_id, token
        self.base = f"https://{host}/{versao}"
        self.host = host

    def _req(self, metodo: str, caminho: str, **params):
        params["access_token"] = self.token
        url = f"{self.base}/{caminho.lstrip('/')}"
        r = httpx.request(metodo, url, params=params if metodo == "GET" else None,
                          data=params if metodo != "GET" else None, timeout=120)
        try:
            j = r.json()
        except ValueError:
            raise ErroInstagram(f"Resposta inválida ({r.status_code}): {r.text[:200]}")
        if "error" in j:
            e = j["error"]
            raise ErroInstagram(f"{e.get('message')} (código {e.get('code')}/{e.get('error_subcode', '-')})")
        return j

    # ------------------------------------------------------------ conta
    def quem_sou(self) -> dict:
        if self.host == "graph.instagram.com":
            return self._req("GET", "me", fields="user_id,username,account_type")
        return self._req("GET", self.uid, fields="id,username")

    def limite_publicacao(self) -> dict:
        j = self._req("GET", f"{self.uid}/content_publishing_limit", fields="quota_usage,config")
        dados = (j.get("data") or [{}])[0]
        return {"usado": dados.get("quota_usage", 0), "total": (dados.get("config") or {}).get("quota_total", 100)}

    # ------------------------------------------------------------ contêineres
    def _container(self, **params) -> str:
        return self._req("POST", f"{self.uid}/media", **params)["id"]

    def _esperar(self, cid: str, max_min: float = 6) -> None:
        fim = time.time() + max_min * 60
        while time.time() < fim:
            st = self._req("GET", cid, fields="status_code,status").get("status_code")
            if st in ("FINISHED", "PUBLISHED"):
                return
            if st in ("ERROR", "EXPIRED"):
                info = self._req("GET", cid, fields="status").get("status", "")
                raise ErroInstagram(f"Instagram não processou a mídia: {st} {info}")
            time.sleep(8)
        raise ErroInstagram("Tempo esgotado esperando o Instagram processar a mídia")

    def _publicar(self, cid: str) -> str:
        self._esperar(cid)
        return self._req("POST", f"{self.uid}/media_publish", creation_id=cid)["id"]

    def link(self, media_id: str) -> str:
        try:
            return self._req("GET", media_id, fields="permalink").get("permalink", "")
        except ErroInstagram:
            return ""

    # ------------------------------------------------------------ tipos de post
    def imagem(self, url: str, legenda: str) -> str:
        return self._publicar(self._container(image_url=url, caption=legenda))

    def carrossel(self, urls: list[str], legenda: str) -> str:
        filhos = [self._container(image_url=u, is_carousel_item="true") for u in urls[:10]]
        for f in filhos:
            self._esperar(f)
        return self._publicar(self._container(media_type="CAROUSEL", children=",".join(filhos), caption=legenda))

    def story(self, url: str, video: bool = False) -> str:
        chave = "video_url" if video else "image_url"
        return self._publicar(self._container(media_type="STORIES", **{chave: url}))

    def reel(self, url_video: str, legenda: str, url_capa: str | None = None) -> str:
        params = dict(media_type="REELS", video_url=url_video, caption=legenda, share_to_feed="true")
        if url_capa:
            try:
                return self._publicar(self._container(**params, cover_url=url_capa))
            except ErroInstagram as e:
                if "cover" not in str(e).lower():
                    raise
        return self._publicar(self._container(**params))

    # ------------------------------------------------------------ token
    def renovar_token(self) -> tuple[str, str]:
        """Só para Instagram Login. Retorna (novo_token, expira_em_iso)."""
        r = httpx.get("https://graph.instagram.com/refresh_access_token",
                      params={"grant_type": "ig_refresh_token", "access_token": self.token}, timeout=60)
        j = r.json()
        if "access_token" not in j:
            raise ErroInstagram(f"Não consegui renovar o token: {j}")
        expira = datetime.now() + timedelta(seconds=int(j.get("expires_in", 5184000)))
        return j["access_token"], expira.isoformat(timespec="minutes")
