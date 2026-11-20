"""Formato dos dados gravados.

Este arquivo é o "contrato" comum entre o quiosque, a planilha Google
(Apps Script) e o relatório. Só usa a biblioteca padrão do Python.

CSV diário: dados/respostas_<kiosk_id>_<AAAA-MM-DD>.csv
  - UTF-8 com BOM, separador ";", quebra de linha do Windows
  - números decimais com vírgula (18,5) para o Excel em português
"""
from __future__ import annotations

import csv
import io
import os
import tempfile
from pathlib import Path

VERSAO_APP = "1.0.0"

COLUNAS = [
    "response_id",
    "kiosk_id",
    "kiosk_local",
    "timestamp",
    "data",
    "dia_semana",
    "hora",
    "momento",
    "momento_automatico",
    "emocao",
    "valencia",
    "pontuacao",
    "motivo",
    "pergunta_do_dia",
    "resposta_pergunta_do_dia",
    "temperatura_c",
    "sensacao_termica_c",
    "precipitacao_mm",
    "codigo_tempo",
    "condicao",
    "dia_ou_noite",
    "versao_app",
]

MOMENTOS = ["chegada", "saida_almoco", "volta_almoco", "saida_final"]
NOMES_MOMENTOS = {
    "chegada": "Chegada",
    "saida_almoco": "Saída para o almoço",
    "volta_almoco": "Volta do almoço",
    "saida_final": "Saída do dia",
}
# Índice = datetime.weekday() (segunda = 0)
DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
VALENCIAS = ["positiva", "neutra", "negativa"]
CONDICOES = ["sol", "nublado", "chuva", "outro"]

COLUNAS_DECIMAIS = {"temperatura_c", "sensacao_termica_c", "precipitacao_mm"}
COLUNAS_INTEIRAS = {"pontuacao", "codigo_tempo"}

SEPARADOR = ";"
CODIFICACAO = "utf-8-sig"  # UTF-8 com BOM (o Excel reconhece os acentos)


def nome_arquivo_dia(kiosk_id: str, data_iso: str) -> str:
    """Nome do CSV de um dia, ex.: respostas_Q01_2026-11-20.csv"""
    return f"respostas_{kiosk_id}_{data_iso}.csv"


def formatar_valor(coluna: str, valor) -> str:
    """Converte um valor para o texto gravado no CSV."""
    if valor is None or valor == "":
        return ""
    if coluna in COLUNAS_DECIMAIS:
        return f"{float(valor):.1f}".replace(".", ",")
    if coluna in COLUNAS_INTEIRAS:
        return str(int(float(str(valor).replace(",", "."))))
    return str(valor)


def interpretar_valor(coluna: str, texto: str):
    """Converte o texto do CSV de volta para número quando for o caso."""
    if texto is None:
        return ""
    texto = str(texto).strip()
    if texto == "":
        return ""
    try:
        if coluna in COLUNAS_DECIMAIS:
            return float(texto.replace(",", "."))
        if coluna in COLUNAS_INTEIRAS:
            return int(float(texto.replace(",", ".")))
    except ValueError:
        return ""
    return texto


def linha_para_texto(linha: dict) -> dict:
    return {c: formatar_valor(c, linha.get(c, "")) for c in COLUNAS}


def linha_de_texto(linha: dict) -> dict:
    return {c: interpretar_valor(c, linha.get(c, "")) for c in COLUNAS}


def gerar_conteudo_csv(linhas: list[dict]) -> str:
    buffer = io.StringIO()
    escritor = csv.DictWriter(
        buffer, fieldnames=COLUNAS, delimiter=SEPARADOR, lineterminator="\r\n",
        extrasaction="ignore",
    )
    escritor.writeheader()
    for linha in linhas:
        escritor.writerow(linha_para_texto(linha))
    return buffer.getvalue()


def escrever_csv(caminho: Path | str, linhas: list[dict]) -> None:
    """Grava o CSV inteiro de forma atômica (arquivo temporário + troca).

    Se o computador desligar no meio da gravação, o arquivo antigo continua
    íntegro. Pode lançar PermissionError se o arquivo estiver aberto em outro
    programa (ex.: Excel) — quem chama decide como tratar.
    """
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conteudo = gerar_conteudo_csv(linhas)
    fd, temporario = tempfile.mkstemp(prefix=".tmp_", suffix=".csv", dir=str(caminho.parent))
    try:
        with os.fdopen(fd, "w", encoding=CODIFICACAO, newline="") as arquivo:
            arquivo.write(conteudo)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, caminho)
    except BaseException:
        try:
            os.unlink(temporario)
        except OSError:
            pass
        raise


def ler_csv(caminho: Path | str) -> list[dict]:
    """Lê um CSV do quiosque (ou exportado da planilha) e devolve linhas tipadas.

    Detecta automaticamente o separador (";" ou ",").
    """
    caminho = Path(caminho)
    with open(caminho, "r", encoding=CODIFICACAO, newline="") as arquivo:
        conteudo = arquivo.read()
    if not conteudo.strip():
        return []
    primeira = conteudo.splitlines()[0]
    separador = ";" if primeira.count(";") >= primeira.count(",") else ","
    leitor = csv.DictReader(io.StringIO(conteudo), delimiter=separador)
    return [linha_de_texto(linha) for linha in leitor if linha.get("response_id")]
