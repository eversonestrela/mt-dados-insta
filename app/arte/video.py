"""Reels: transforma os slides verticais em vídeo MP4 (H.264 + áudio mudo).

Usa o ffmpeg que vem no pacote imageio-ffmpeg, então não precisa instalar nada.
Vai sem música de propósito: trilha com direitos autorais derruba o post. Se quiser
áudio do Instagram, adicione pelo app depois de publicado.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import imageio_ffmpeg

SEG_POR_SLIDE = 3.6
TRANSICAO = 0.5


def slides_para_reel(imagens: list[Path], destino: Path) -> Path:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    destino.parent.mkdir(parents=True, exist_ok=True)
    args = [ffmpeg, "-y", "-loglevel", "error"]
    for img in imagens:
        args += ["-loop", "1", "-t", f"{SEG_POR_SLIDE}", "-framerate", "30", "-i", str(img)]
    args += ["-f", "lavfi", "-t", f"{SEG_POR_SLIDE * len(imagens)}", "-i", "anullsrc=r=44100:cl=stereo"]

    filtros = []
    for i in range(len(imagens)):
        # leve aproximação contínua (2%) para o vídeo não parecer estático
        filtros.append(
            f"[{i}:v]scale=1080:1920,setsar=1,"
            f"zoompan=z='min(1+0.0002*on,1.02)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30,"
            f"format=yuv420p[v{i}]"
        )
    atual = "v0"
    deslocamento = SEG_POR_SLIDE - TRANSICAO
    for i in range(1, len(imagens)):
        saida = f"x{i}"
        filtros.append(f"[{atual}][v{i}]xfade=transition=fade:duration={TRANSICAO}:offset={deslocamento:.2f}[{saida}]")
        atual = saida
        deslocamento += SEG_POR_SLIDE - TRANSICAO
    duracao = deslocamento + TRANSICAO
    audio_idx = len(imagens)
    args += ["-filter_complex", ";".join(filtros), "-map", f"[{atual}]", "-map", f"{audio_idx}:a",
             "-t", f"{duracao:.2f}", "-c:v", "libx264", "-profile:v", "high", "-preset", "medium", "-crf", "20",
             "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "128k", "-shortest",
             "-movflags", "+faststart", str(destino)]
    subprocess.run(args, check=True, capture_output=True)
    return destino
