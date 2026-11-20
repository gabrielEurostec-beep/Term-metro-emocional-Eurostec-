"""Leitura e consolidação dos CSVs.

Aceita, misturados na mesma pasta (e subpastas):
  - CSVs diários dos quiosques (";" e vírgula decimal, UTF-8 com BOM);
  - o CSV baixado da Planilha Google (Arquivo > Fazer download > CSV),
    que usa "," como separador e pode ter decimais com ponto ou vírgula
    e datas no formato 20/11/2026.

Respostas repetidas (mesmo response_id) são consolidadas em uma só,
mantendo a versão mais completa (com mais campos preenchidos).
"""
from __future__ import annotations

import csv
import io
import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from quiosque.formato import COLUNAS, DIAS_SEMANA, MOMENTOS, NOMES_MOMENTOS

PONTUACAO_PADRAO = {
    "Feliz": 2, "Animado": 2, "Neutro": 0, "Cansado": -1,
    "Preocupado": -1, "Triste": -2, "Bravo": -2, "Furioso": -3,
}
VALENCIA_PADRAO = {
    "Feliz": "positiva", "Animado": "positiva", "Neutro": "neutra",
    "Cansado": "negativa", "Preocupado": "negativa", "Triste": "negativa",
    "Bravo": "negativa", "Furioso": "negativa",
}
RESPOSTAS_PERGUNTA = ["Sim", "Mais ou menos", "Não"]

_DECIMAIS = ("temperatura_c", "sensacao_termica_c", "precipitacao_mm")
_INTEIROS = ("pontuacao", "codigo_tempo")


@dataclass
class ResultadoLeitura:
    dados: pd.DataFrame
    arquivos_lidos: list[Path] = field(default_factory=list)
    arquivos_ignorados: list[tuple[Path, str]] = field(default_factory=list)
    linhas_lidas: int = 0
    duplicadas_removidas: int = 0
    linhas_descartadas: int = 0
    avisos: list[str] = field(default_factory=list)


# ----------------------------------------------------------------- utilidades
def _sem_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def _normalizar_cabecalho(nome: str) -> str:
    nome = (nome or "").replace("﻿", "").strip().strip('"').strip()
    nome = _sem_acentos(nome).lower()
    nome = re.sub(r"[\s\-]+", "_", nome)
    return nome


def _decodificar(conteudo: bytes) -> str:
    for codificacao in ("utf-8-sig", "cp1252"):
        try:
            return conteudo.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return conteudo.decode("utf-8", errors="replace")


def _detectar_separador(cabecalho: str) -> str:
    contagens = {sep: cabecalho.count(sep) for sep in (";", ",", "\t")}
    return max(contagens, key=contagens.get)


def para_float(texto) -> float:
    """'18,4' -> 18.4 · '18.4' -> 18.4 · '1.234,5' -> 1234.5 · '' -> nan"""
    if texto is None:
        return math.nan
    if isinstance(texto, (int, float)):
        return float(texto)
    t = str(texto).strip().replace(" ", "").replace(" ", "")
    if not t:
        return math.nan
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    else:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return math.nan


_RE_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})")
_RE_BR = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})")


def para_data(texto: str, timestamp: str = "") -> date | None:
    for valor in (texto, timestamp):
        valor = (valor or "").strip()
        if not valor:
            continue
        m = _RE_ISO.match(valor)
        try:
            if m:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            m = _RE_BR.match(valor)
            if m:
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
    return None


_RE_HORA = re.compile(r"(\d{1,2}):(\d{2})(?::(\d{2}))?")


def para_hora(texto: str, timestamp: str = "") -> str:
    for valor in (texto, timestamp[11:] if len(timestamp or "") > 11 else ""):
        m = _RE_HORA.search(valor or "")
        if m:
            return f"{int(m.group(1)):02d}:{m.group(2)}:{m.group(3) or '00'}"
    return ""


_MOMENTOS_POR_NOME = {}
for _id, _nome in NOMES_MOMENTOS.items():
    _MOMENTOS_POR_NOME[_id] = _id
    _MOMENTOS_POR_NOME[_normalizar_cabecalho(_nome)] = _id


def normalizar_momento(texto: str) -> str:
    return _MOMENTOS_POR_NOME.get(_normalizar_cabecalho(texto or ""), "")


def normalizar_sim_nao(texto: str) -> str:
    t = _sem_acentos((texto or "").strip().lower())
    if t in ("sim", "s", "true", "verdadeiro", "1", "yes"):
        return "sim"
    if t in ("nao", "n", "false", "falso", "0", "no"):
        return "não"
    return ""


# ------------------------------------------------------------------- leitura
def ler_arquivo(caminho: Path) -> list[dict] | None:
    """Lê um CSV e devolve as linhas (dicionários de texto).

    Devolve None quando o arquivo não tem a coluna response_id
    (não é um arquivo do Termômetro).
    """
    texto = _decodificar(Path(caminho).read_bytes())
    if not texto.strip():
        return []
    cabecalho = texto.splitlines()[0]
    separador = _detectar_separador(cabecalho)
    leitor = csv.reader(io.StringIO(texto, newline=""), delimiter=separador)
    try:
        nomes = [_normalizar_cabecalho(n) for n in next(leitor)]
    except StopIteration:
        return []
    if "response_id" not in nomes:
        return None
    linhas = []
    for valores in leitor:
        if not any(v.strip() for v in valores):
            continue
        linha = {}
        for nome, valor in zip(nomes, valores):
            if nome:
                linha[nome] = (valor or "").strip()
        linhas.append(linha)
    return linhas


def _completude(linha: dict) -> int:
    return sum(1 for c in COLUNAS if str(linha.get(c, "")).strip() not in ("", "nan"))


def carregar_pasta(pasta: Path, ordem_emocoes: list[str] | None = None) -> ResultadoLeitura:
    """Lê todos os .csv da pasta (inclusive subpastas) e consolida."""
    pasta = Path(pasta)
    resultado = ResultadoLeitura(dados=pd.DataFrame())
    ordem_emocoes = ordem_emocoes or list(PONTUACAO_PADRAO)
    emocoes_canonicas = {e.lower(): e for e in ordem_emocoes}
    emocoes_canonicas.update({e.lower(): e for e in PONTUACAO_PADRAO if e.lower() not in emocoes_canonicas})

    arquivos = sorted(p for p in pasta.rglob("*") if p.is_file() and p.suffix.lower() == ".csv")
    brutas: list[dict] = []
    for caminho in arquivos:
        if caminho.name.startswith(".tmp_"):
            continue
        try:
            linhas = ler_arquivo(caminho)
        except (OSError, csv.Error) as erro:
            resultado.arquivos_ignorados.append((caminho, f"não foi possível ler ({erro})"))
            continue
        if linhas is None:
            resultado.arquivos_ignorados.append((caminho, "não tem a coluna response_id"))
            continue
        resultado.arquivos_lidos.append(caminho)
        for i, linha in enumerate(linhas):
            linha["_arquivo"] = caminho.name
            linha["_ordem"] = len(brutas)
            brutas.append(linha)

    resultado.linhas_lidas = len(brutas)
    validas: list[dict] = []
    descartadas = 0
    for linha in brutas:
        rid = linha.get("response_id", "").strip()
        momento = normalizar_momento(linha.get("momento", ""))
        emocao = emocoes_canonicas.get(linha.get("emocao", "").strip().lower(), linha.get("emocao", "").strip())
        timestamp = linha.get("timestamp", "")
        data = para_data(linha.get("data", ""), timestamp)
        if not rid or not momento or not emocao or data is None:
            descartadas += 1
            continue
        normal = {c: linha.get(c, "") for c in COLUNAS}
        normal["response_id"] = rid
        normal["momento"] = momento
        normal["emocao"] = emocao
        normal["data"] = data
        normal["dia_semana"] = DIAS_SEMANA[data.weekday()]
        normal["hora"] = para_hora(linha.get("hora", ""), timestamp)
        normal["momento_automatico"] = normalizar_sim_nao(linha.get("momento_automatico", ""))
        for coluna in _DECIMAIS:
            normal[coluna] = para_float(linha.get(coluna, ""))
        for coluna in _INTEIROS:
            normal[coluna] = para_float(linha.get(coluna, ""))
        if math.isnan(normal["pontuacao"]):
            normal["pontuacao"] = float(PONTUACAO_PADRAO.get(emocao, math.nan))
        valencia = (linha.get("valencia", "") or "").strip().lower()
        normal["valencia"] = valencia if valencia in ("positiva", "neutra", "negativa") else VALENCIA_PADRAO.get(emocao, "")
        normal["condicao"] = (linha.get("condicao", "") or "").strip().lower()
        normal["dia_ou_noite"] = (linha.get("dia_ou_noite", "") or "").strip().lower()
        resposta = (linha.get("resposta_pergunta_do_dia", "") or "").strip()
        for opcao in RESPOSTAS_PERGUNTA:
            if _sem_acentos(resposta.lower()) == _sem_acentos(opcao.lower()):
                resposta = opcao
        normal["resposta_pergunta_do_dia"] = resposta
        normal["_completude"] = _completude(linha)
        normal["_ordem"] = linha["_ordem"]
        normal["_arquivo"] = linha["_arquivo"]
        validas.append(normal)

    resultado.linhas_descartadas = descartadas
    if descartadas:
        resultado.avisos.append(
            f"{descartadas} linha(s) foram ignoradas por estarem incompletas "
            "(sem response_id, momento, emoção ou data)."
        )
    if not validas:
        return resultado

    df = pd.DataFrame(validas)
    antes = len(df)
    df = (
        df.sort_values(["_completude", "_ordem"], ascending=[False, True])
        .drop_duplicates(subset="response_id", keep="first")
        .sort_values(["data", "hora", "kiosk_id"])
        .reset_index(drop=True)
    )
    resultado.duplicadas_removidas = antes - len(df)
    df["pontuacao"] = df["pontuacao"].astype(float)
    df["data_dt"] = pd.to_datetime(df["data"])
    df["semana"] = df["data"].map(lambda d: d - timedelta(days=d.weekday()))
    df["dia_util"] = df["data"].map(lambda d: d.weekday() < 5)
    df["kiosk_id"] = df["kiosk_id"].astype(str).str.strip().replace("", "(sem id)")
    resultado.dados = df
    return resultado


def filtrar_periodo(df: pd.DataFrame, inicio: date | None, fim: date | None) -> pd.DataFrame:
    if df.empty:
        return df
    filtro = pd.Series(True, index=df.index)
    if inicio:
        filtro &= df["data"] >= inicio
    if fim:
        filtro &= df["data"] <= fim
    return df[filtro].reset_index(drop=True)


def ler_data_argumento(texto: str | None) -> date | None:
    if not texto:
        return None
    d = para_data(texto)
    if d is None:
        raise ValueError(f"Data inválida: {texto!r}. Use o formato AAAA-MM-DD (ex.: 2026-11-20).")
    return d


__all__ = [
    "ResultadoLeitura", "carregar_pasta", "filtrar_periodo", "ler_arquivo",
    "para_float", "para_data", "ler_data_argumento", "PONTUACAO_PADRAO",
    "VALENCIA_PADRAO", "RESPOSTAS_PERGUNTA",
]
