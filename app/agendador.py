"""Tarefas automáticas: gerar a pauta do dia, publicar no horário, renovar tokens."""
from __future__ import annotations

import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .base import agora, cfg, log
from .planejador import gerar_todas
from .publicacao.publicador import publicar_vencidos, renovar_tokens

_agendador: BackgroundScheduler | None = None


def _geracao_atrasada() -> None:
    """Se o PC estava desligado no horário da geração, gera ao abrir o programa."""
    hoje = agora()
    hh, mm = map(int, str(cfg("geracao_horario")).split(":"))
    passou = (hoje.hour, hoje.minute) >= (hh, mm)
    if passou and cfg("ultima_geracao") != hoje.date().isoformat():
        log("Gerando a pauta de hoje (o horário programado já passou).")
        gerar_todas()


def iniciar() -> None:
    global _agendador
    if _agendador:
        return
    fuso = cfg("fuso")
    hh, mm = map(int, str(cfg("geracao_horario")).split(":"))
    _agendador = BackgroundScheduler(timezone=fuso, job_defaults={"coalesce": True, "max_instances": 1,
                                                                    "misfire_grace_time": 3600})
    _agendador.add_job(gerar_todas, CronTrigger(hour=hh, minute=mm, timezone=fuso), id="gerar")
    _agendador.add_job(publicar_vencidos, "interval", minutes=1, id="publicar")
    _agendador.add_job(renovar_tokens, CronTrigger(hour=3, minute=17, timezone=fuso), id="tokens")
    _agendador.start()
    threading.Thread(target=_geracao_atrasada, daemon=True).start()
    log(f"Agendador iniciado: geração diária às {hh:02d}:{mm:02d} ({fuso}).")


def reprogramar_geracao() -> None:
    if not _agendador:
        return
    fuso = cfg("fuso")
    hh, mm = map(int, str(cfg("geracao_horario")).split(":"))
    _agendador.reschedule_job("gerar", trigger=CronTrigger(hour=hh, minute=mm, timezone=fuso))


def parar() -> None:
    global _agendador
    if _agendador:
        _agendador.shutdown(wait=False)
        _agendador = None
