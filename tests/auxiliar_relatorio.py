"""Funções de apoio para os testes do relatório (não é um teste)."""
from __future__ import annotations

import sys
import uuid
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from quiosque.formato import DIAS_SEMANA, escrever_csv, nome_arquivo_dia  # noqa: E402

PONTOS = {"Feliz": 2, "Animado": 2, "Neutro": 0, "Cansado": -1, "Preocupado": -1,
          "Triste": -2, "Bravo": -2, "Furioso": -3}
VALENCIA = {"Feliz": "positiva", "Animado": "positiva", "Neutro": "neutra"}


def linha(momento: str, emocao: str, data: date, kiosk: str = "Q01", hora: str = "07:30:00",
          motivo: str = "", pergunta: str = "", resposta: str = "", temperatura=None,
          condicao: str = "", response_id: str | None = None) -> dict:
    return {
        "response_id": response_id or str(uuid.uuid4()),
        "kiosk_id": kiosk,
        "kiosk_local": f"Local {kiosk}",
        "timestamp": f"{data.isoformat()}T{hora}-03:00",
        "data": data.isoformat(),
        "dia_semana": DIAS_SEMANA[data.weekday()],
        "hora": hora,
        "momento": momento,
        "momento_automatico": "sim",
        "emocao": emocao,
        "valencia": VALENCIA.get(emocao, "negativa"),
        "pontuacao": PONTOS[emocao],
        "motivo": motivo,
        "pergunta_do_dia": pergunta,
        "resposta_pergunta_do_dia": resposta,
        "temperatura_c": temperatura if temperatura is not None else "",
        "sensacao_termica_c": "",
        "precipitacao_mm": "",
        "codigo_tempo": "",
        "condicao": condicao,
        "dia_ou_noite": "dia" if condicao else "",
        "versao_app": "1.0.0",
    }


def gravar(pasta: Path, linhas: list[dict]) -> None:
    """Grava as linhas no formato dos quiosques (um CSV por quiosque por dia)."""
    grupos: dict[tuple[str, str], list[dict]] = {}
    for l in linhas:
        grupos.setdefault((l["kiosk_id"], l["data"]), []).append(l)
    for (kiosk, data), grupo in grupos.items():
        escrever_csv(Path(pasta) / nome_arquivo_dia(kiosk, data), grupo)


def carregar(pasta: Path):
    from relatorio.leitura import carregar_pasta

    return carregar_pasta(Path(pasta)).dados
