"""Agenda própria: datas que você mesmo cadastra em dados/agenda.csv.

Formato (separado por ponto e vírgula, com cabeçalho):
    data;titulo;texto;fonte
    08/04;Aniversário de Cuiabá;Cuiabá foi fundada em 8 de abril de 1719.;Prefeitura de Cuiabá

A data é DD/MM (repete todo ano) ou DD/MM/AAAA (só naquele dia).
"""
from __future__ import annotations

import csv
from datetime import date

from ..base import ARQ_AGENDA

MODELO = (
    "data;titulo;texto;fonte\n"
    "08/04;Aniversário de Cuiabá;Cuiabá foi fundada em 8 de abril de 1719, às margens do rio Cuiabá.;Prefeitura de Cuiabá\n"
)


def garantir_arquivo() -> None:
    if not ARQ_AGENDA.exists():
        ARQ_AGENDA.write_text(MODELO, encoding="utf-8")


def coletar(dia: date) -> list[dict]:
    garantir_arquivo()
    saida = []
    with ARQ_AGENDA.open(encoding="utf-8-sig", newline="") as f:
        for linha in csv.DictReader(f, delimiter=";"):
            d = (linha.get("data") or "").strip()
            partes = d.split("/")
            try:
                if len(partes) == 2 and (int(partes[0]), int(partes[1])) == (dia.day, dia.month):
                    saida.append(linha)
                elif len(partes) == 3 and date(int(partes[2]), int(partes[1]), int(partes[0])) == dia:
                    saida.append(linha)
            except ValueError:
                continue
    return saida
