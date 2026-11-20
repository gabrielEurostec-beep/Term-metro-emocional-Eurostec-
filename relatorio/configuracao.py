"""Configuração do relatório (config/relatorio.json) e localização das pastas."""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

PADRAO = {
    "publico_esperado_por_quiosque": 40,
    "publico_por_quiosque": {},
    "funcionarios_total": 150,
    "feriados_extras": [],
    "minimo_respostas_por_recorte": 5,
    "pasta_entrada": "entrada_relatorio",
    "pasta_saida": "relatorios",
    "ordem_emocoes": ["Feliz", "Animado", "Neutro", "Cansado", "Preocupado", "Triste", "Bravo", "Furioso"],
    "cores_emocoes": {
        "Feliz": "#23863a",
        "Animado": "#0b78b8",
        "Neutro": "#9aa3ad",
        "Cansado": "#7a5fb0",
        "Preocupado": "#c98a00",
        "Triste": "#2f62c4",
        "Bravo": "#e8650f",
        "Furioso": "#b02525",
    },
    "perguntas_invertidas": ["Sentiu-se sobrecarregado(a) hoje?"],
    "abrir_ao_terminar": True,
}


def raiz_projeto() -> Path:
    """Pasta principal do Termômetro (onde ficam config/, dados/, relatorios/...).

    - Rodando pelo Python: a pasta acima de relatorio/.
    - Rodando pelo executável (PyInstaller): a pasta do .exe; se o .exe
      estiver dentro de "bin", a pasta acima dela.
    """
    if getattr(sys, "frozen", False):
        pasta = Path(sys.executable).resolve().parent
        if pasta.name.lower() == "bin":
            pasta = pasta.parent
        return pasta
    return Path(__file__).resolve().parent.parent


def carregar_config(raiz: Path | None = None, caminho: Path | None = None) -> dict:
    """Lê config/relatorio.json. Chaves ausentes recebem o valor padrão."""
    raiz = raiz or raiz_projeto()
    caminho = caminho or (raiz / "config" / "relatorio.json")
    config = json.loads(json.dumps(PADRAO))  # cópia profunda
    if caminho.exists():
        try:
            lido = json.loads(caminho.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as erro:
            raise ValueError(
                f"Não consegui ler {caminho}: {erro}. Confira se o arquivo é um JSON válido."
            ) from erro
        for chave, valor in lido.items():
            if chave.startswith("_"):
                continue
            config[chave] = valor
    # Garante que todas as emoções conhecidas tenham cor.
    cores = dict(PADRAO["cores_emocoes"])
    cores.update(config.get("cores_emocoes") or {})
    config["cores_emocoes"] = cores
    config["minimo_respostas_por_recorte"] = max(1, int(config.get("minimo_respostas_por_recorte", 5)))
    return config


def resolver_pasta(valor: str | Path, raiz: Path) -> Path:
    pasta = Path(valor).expanduser()
    if not pasta.is_absolute():
        pasta = raiz / pasta
    return pasta


# ------------------------------------------------------------------ feriados
FERIADOS_FIXOS = [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)]


def pascoa(ano: int) -> date:
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def feriados_nacionais(ano: int) -> set[date]:
    feriados = {date(ano, mes, dia) for mes, dia in FERIADOS_FIXOS}
    feriados.add(pascoa(ano) - timedelta(days=2))  # Sexta-feira Santa
    return feriados


def conjunto_feriados(config: dict, anos) -> set[date]:
    feriados: set[date] = set()
    for ano in set(anos):
        feriados |= feriados_nacionais(int(ano))
    for texto in config.get("feriados_extras") or []:
        try:
            feriados.add(date.fromisoformat(str(texto).strip()[:10]))
        except ValueError:
            continue
    return feriados
