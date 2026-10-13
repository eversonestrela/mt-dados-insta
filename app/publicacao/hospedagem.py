"""Coloca as mídias numa URL pública (exigência do Instagram) e apaga depois de publicar.

Opções:
- cloudinary: plano gratuito; o app envia o arquivo e remove após a publicação.
- url_publica: o app serve SOMENTE a pasta dados/midia na porta 8766, e você expõe
  essa porta com um túnel (ex.: Cloudflare Tunnel) e informa o endereço base.
  Nunca exponha a porta do painel (8765).
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

import httpx

from ..base import MIDIA, cfg


class ErroHospedagem(Exception):
    pass


def _assinar(params: dict, segredo: str) -> str:
    base = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hashlib.sha1((base + segredo).encode()).hexdigest()


def enviar(rel: str) -> tuple[str, dict]:
    """Recebe caminho relativo a dados/midia. Retorna (url_publica, info_para_apagar)."""
    caminho = MIDIA / rel
    modo = cfg("hospedagem")
    if modo == "url_publica":
        base = (cfg("url_publica_base") or "").rstrip("/")
        if not base.startswith("https://"):
            raise ErroHospedagem("Configure a URL pública base (precisa começar com https://)")
        return f"{base}/{rel}", {}
    cloud, chave, segredo = cfg("cloudinary_cloud"), cfg("cloudinary_key"), cfg("cloudinary_segredo")
    if not (cloud and chave and segredo):
        raise ErroHospedagem("Cloudinary não configurado (nome da nuvem, API key e API secret)")
    tipo = "video" if caminho.suffix.lower() in (".mp4", ".mov") else "image"
    params = {"timestamp": int(time.time()), "folder": "mt-em-dados"}
    params["signature"] = _assinar(params, segredo)
    params["api_key"] = chave
    with caminho.open("rb") as f:
        r = httpx.post(f"https://api.cloudinary.com/v1_1/{cloud}/{tipo}/upload", data=params,
                       files={"file": (caminho.name, f)}, timeout=300)
    if r.status_code >= 300:
        raise ErroHospedagem(f"Cloudinary recusou o envio: {r.text[:300]}")
    j = r.json()
    return j["secure_url"], {"public_id": j["public_id"], "tipo": tipo}


def apagar(info: dict) -> None:
    if not info or cfg("hospedagem") != "cloudinary":
        return
    cloud, chave, segredo = cfg("cloudinary_cloud"), cfg("cloudinary_key"), cfg("cloudinary_segredo")
    params = {"public_id": info["public_id"], "timestamp": int(time.time())}
    params["signature"] = _assinar(params, segredo)
    params["api_key"] = chave
    try:
        httpx.post(f"https://api.cloudinary.com/v1_1/{cloud}/{info['tipo']}/destroy", data=params, timeout=60)
    except Exception:  # noqa: BLE001 - se falhar, o arquivo só fica lá; não é crítico
        pass


def testar() -> str:
    """Envia e apaga uma imagem pequena para validar a configuração."""
    from PIL import Image

    teste = MIDIA / "_teste_hospedagem.jpg"
    Image.new("RGB", (64, 64), "#B4441C").save(teste, "JPEG")
    url, info = enviar(teste.relative_to(MIDIA).as_posix())
    r = httpx.get(url, timeout=30)
    apagar(info)
    teste.unlink(missing_ok=True)
    if r.status_code != 200:
        raise ErroHospedagem(f"O arquivo foi enviado, mas a URL respondeu {r.status_code}")
    return url
