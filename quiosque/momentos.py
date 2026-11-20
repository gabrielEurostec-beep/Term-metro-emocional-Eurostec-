"""Relógio, detecção automática do momento do dia e pergunta do dia."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from .config import DIAS_VALIDOS, minutos, minutos_fim
from .formato import DIAS_SEMANA, MOMENTOS

# O Brasil não tem horário de verão desde 2019. Se o Windows não tiver a base
# de fusos horários (o Python no Windows normalmente não tem), usamos UTC-3.
FUSO_RESERVA = timezone(timedelta(hours=-3), "BRT")


def obter_fuso(nome: str = "America/Sao_Paulo"):
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(nome)
    except Exception:  # ZoneInfoNotFoundError, ImportError
        return FUSO_RESERVA


def agora(config: dict) -> datetime:
    return datetime.now(obter_fuso(config.get("fuso_horario", "America/Sao_Paulo")))


def e_dia_util(momento_atual: datetime, config: dict) -> bool:
    """Dia com detecção automática: dias do expediente que não são feriado."""
    dias = config["expediente"]["dias"]
    nome_dia = DIAS_VALIDOS[momento_atual.weekday()]
    if nome_dia not in dias:
        return False
    return momento_atual.date().isoformat() not in set(config.get("feriados", []))


def detectar_momento(momento_atual: datetime, config: dict) -> str | None:
    """Devolve o momento pelo horário, ou None quando a pessoa deve escolher.

    Janelas: o início faz parte, o fim não (12:20 já é "volta_almoco").
    Fim "23:59" vale até a meia-noite. Fins de semana e feriados → None.
    """
    if not e_dia_util(momento_atual, config):
        return None
    minuto_do_dia = momento_atual.hour * 60 + momento_atual.minute
    for mid in MOMENTOS:
        janela = config["momentos"][mid]
        if minutos(janela["inicio"]) <= minuto_do_dia < minutos_fim(janela["fim"]):
            return mid
    return None


def pergunta_do_dia(dia: date, config: dict) -> dict | None:
    """Pergunta do dia em rodízio pela data (igual em todos os quiosques)."""
    pdd = config.get("pergunta_do_dia", {})
    perguntas = pdd.get("perguntas") or []
    if not pdd.get("ativa") or not perguntas:
        return None
    return perguntas[dia.toordinal() % len(perguntas)]


def dia_semana(momento_atual: datetime) -> str:
    return DIAS_SEMANA[momento_atual.weekday()]
