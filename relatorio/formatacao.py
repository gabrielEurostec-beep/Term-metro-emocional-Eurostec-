"""Formatação de números no padrão brasileiro (vírgula decimal, ponto de milhar)."""
from __future__ import annotations

import math
from datetime import date

from quiosque.formato import NOMES_MOMENTOS

DIAS_SEMANA_TITULO = {
    "segunda": "Segunda",
    "terça": "Terça",
    "quarta": "Quarta",
    "quinta": "Quinta",
    "sexta": "Sexta",
    "sábado": "Sábado",
    "domingo": "Domingo",
}

NOMES_MOMENTOS_CURTOS = {
    "chegada": "Chegada",
    "saida_almoco": "Saída almoço",
    "volta_almoco": "Volta almoço",
    "saida_final": "Saída do dia",
}


def eh_numero(valor) -> bool:
    if isinstance(valor, bool):
        return False
    if isinstance(valor, (int, float)):
        return not (isinstance(valor, float) and math.isnan(valor))
    try:
        import numpy as np  # noqa: WPS433

        if isinstance(valor, np.integer):
            return True
        if isinstance(valor, np.floating):
            return not math.isnan(float(valor))
    except ImportError:  # pragma: no cover
        pass
    return False


def inteiro(n) -> str:
    return f"{int(round(float(n))):,}".replace(",", ".")


def decimal(x, casas: int = 2, sinal: bool = False) -> str:
    """1.234 -> '1,23' · com sinal=True: '+1,23' / '−1,23' (sinal de menos tipográfico)."""
    x = float(x)
    if abs(x) < 0.5 * 10 ** (-casas):
        x = 0.0
    texto = f"{x:+.{casas}f}" if sinal and x != 0 else f"{x:.{casas}f}"
    return texto.replace(".", ",").replace("-", "\u2212")


def percentual(fracao, casas: int = 0) -> str:
    return decimal(float(fracao) * 100, casas) + "%"


def data_br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def data_curta(d: date) -> str:
    return d.strftime("%d/%m")


def nome_momento(momento: str, curto: bool = False) -> str:
    if curto:
        return NOMES_MOMENTOS_CURTOS.get(momento, momento)
    return NOMES_MOMENTOS.get(momento, momento)


def nome_dia(dia: str) -> str:
    return DIAS_SEMANA_TITULO.get(dia, dia.capitalize())
