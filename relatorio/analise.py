"""Cálculos do relatório e REGRA DE ANONIMATO.

Regra de anonimato (minimo_respostas_por_recorte, padrão 5):
  - Todo grupo sobre o qual se calcula um número (média, percentual,
    distribuição, taxa) com menos de 5 respostas aparece como
    "dados insuficientes".
  - Dentro de um grupo válido, nenhuma categoria com 1 a 4 respostas
    aparece como número: nem a contagem, nem o percentual — as duas
    viram "<5". Gráficos omitem essas categorias (ou as juntam em
    "Outras (<5 cada)") e o resumo em texto não as cita.

As funções `exibir_contagem`, `exibir_estatistica` e `exibir_fracao`
centralizam a regra; todas as tabelas do relatório (HTML e Excel) passam
por elas.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from quiosque.formato import DIAS_SEMANA, MOMENTOS
from relatorio.configuracao import conjunto_feriados
from relatorio.formatacao import data_br, data_curta, nome_dia, nome_momento
from relatorio.leitura import RESPOSTAS_PERGUNTA

INSUFICIENTE = "dados insuficientes"

ORDEM_PERGUNTAS = [
    "Conseguiu fazer suas pausas hoje?",
    "Você se sentiu seguro(a) no trabalho hoje?",
    "Você se sentiu respeitado(a) hoje?",
    "Teve as informações e ferramentas de que precisava?",
    "Sentiu-se sobrecarregado(a) hoje?",
]
CONDICOES = [("sol", "Sol"), ("nublado", "Nublado"), ("chuva", "Chuva"), ("outro", "Outro")]
FAIXAS_TEMPERATURA = ["< 10 °C", "10–15 °C", "15–20 °C", "20–25 °C", "25–30 °C", "> 30 °C"]
LIMITES_TEMPERATURA = [-math.inf, 10, 15, 20, 25, 30, math.inf]
VARIACOES = [
    ("Manhã", "chegada", "saida_almoco"),
    ("Almoço", "saida_almoco", "volta_almoco"),
    ("Tarde", "volta_almoco", "saida_final"),
    ("Dia inteiro", "chegada", "saida_final"),
]
CONTEXTOS_MOTIVO = [
    ("chegada", "negativa", "O que mais pesou?"),
    ("chegada", "positiva", "O que mais contribuiu?"),
    ("saida_final", "negativa", "O que mais pesou?"),
    ("saida_final", "positiva", "O que mais contribuiu?"),
]
LIMIAR_ESTAVEL = 0.10  # variações menores que isso (em pontos) são "estáveis"


# =========================================================== regra de anonimato
def rotulo_poucos(minimo: int = 5) -> str:
    return f"<{minimo}"


def grupo_suficiente(n, minimo: int = 5) -> bool:
    return int(n) >= minimo


def exibir_contagem(n, minimo: int = 5):
    """0 -> 0 · 1 a (mínimo-1) -> '<5' · mínimo ou mais -> o próprio número."""
    n = int(n)
    if n <= 0:
        return 0
    if n < minimo:
        return rotulo_poucos(minimo)
    return n


def exibir_estatistica(valor, n, minimo: int = 5):
    """Devolve o valor, ou 'dados insuficientes' se o grupo tiver menos de `minimo` respostas."""
    if int(n) < minimo or valor is None:
        return INSUFICIENTE
    if isinstance(valor, float) and math.isnan(valor):
        return INSUFICIENTE
    return valor


def exibir_fracao(contagem, total, minimo: int = 5):
    """Percentual de uma categoria dentro de um grupo.

    Grupo com menos de `minimo` respostas -> 'dados insuficientes';
    categoria com 1 a (mínimo-1) respostas -> '<5' (sem percentual);
    caso contrário, a fração (0 a 1).
    """
    total, contagem = int(total), int(contagem)
    if total < minimo:
        return INSUFICIENTE
    if 0 < contagem < minimo:
        return rotulo_poucos(minimo)
    return contagem / total


def categoria_visivel(contagem, minimo: int = 5) -> bool:
    """Categoria pode aparecer com número (0 ou pelo menos `minimo` respostas)."""
    return int(contagem) == 0 or int(contagem) >= minimo


def valor_grafico(valor, n, minimo: int = 5):
    """Versão para gráficos: None (ponto omitido) quando o grupo é insuficiente."""
    v = exibir_estatistica(valor, n, minimo)
    return None if v == INSUFICIENTE else float(v)


def media_por_grupo(df: pd.DataFrame, chaves: list[str], minimo: int = 5,
                    coluna: str = "pontuacao") -> pd.DataFrame:
    """Média e contagem por grupo, com a coluna 'exibir' já mascarada."""
    if df.empty:
        return pd.DataFrame(columns=chaves + ["n", "media", "exibir"])
    g = df.groupby(chaves, dropna=False)[coluna].agg(n="count", media="mean").reset_index()
    g["exibir"] = [exibir_estatistica(m, n, minimo) for m, n in zip(g["media"], g["n"])]
    return g


def distribuicao(serie: pd.Series, categorias: list[str], minimo: int = 5) -> dict:
    """Distribuição percentual de uma variável categórica dentro de um grupo.

    Devolve {"n": total, "valida": bool,
             "pct": {cat: fração|'<5'|INSUF}, "contagem": {cat: n|'<5'|INSUF},
             "bruto": {cat: n}}  (bruto é só para cálculos internos, nunca exibir).
    """
    n = int(len(serie))
    valida = n >= minimo
    contagens = serie.value_counts()
    pct, cont, bruto = {}, {}, {}
    for cat in categorias:
        c = int(contagens.get(cat, 0))
        bruto[cat] = c
        if valida:
            pct[cat] = exibir_fracao(c, n, minimo)
            cont[cat] = exibir_contagem(c, minimo)
        else:
            pct[cat] = INSUFICIENTE
            cont[cat] = INSUFICIENTE
    return {"n": n, "valida": valida, "pct": pct, "contagem": cont, "bruto": bruto}


# ================================================================== estruturas
@dataclass
class Tabela:
    chave: str
    titulo: str
    dados: pd.DataFrame
    formatos: dict = field(default_factory=dict)  # coluna -> int|dec|sinal|pct|texto
    nota: str = ""


@dataclass
class Resultado:
    df: pd.DataFrame
    config: dict
    minimo: int
    inicio: date
    fim: date
    rotulos_quiosques: dict
    kpis: dict = field(default_factory=dict)
    tabelas: dict = field(default_factory=dict)
    graficos: dict = field(default_factory=dict)
    brutos: dict = field(default_factory=dict)


def _ordem_emocoes(df: pd.DataFrame, config: dict) -> list[str]:
    presentes = list(dict.fromkeys(df["emocao"].tolist()))
    ordem = [e for e in config.get("ordem_emocoes", []) if e in presentes]
    return ordem + [e for e in presentes if e not in ordem]


def _dias_presentes(df: pd.DataFrame) -> list[str]:
    presentes = set(df["dia_semana"])
    return [d for d in DIAS_SEMANA if d in presentes]


def rotulos_quiosques(df: pd.DataFrame) -> dict:
    rotulos = {}
    for kiosk, grupo in df.groupby("kiosk_id"):
        locais = grupo["kiosk_local"].astype(str).str.strip()
        locais = locais[(locais != "") & (locais != "nan")]
        local = locais.mode().iat[0] if not locais.empty else ""
        rotulos[kiosk] = f"{kiosk} · {local}" if local else str(kiosk)
    return dict(sorted(rotulos.items()))


# ===================================================================== totais
def respostas_por_quiosque(df, rotulos, minimo) -> Tabela:
    linhas = []
    for kiosk, rotulo in rotulos.items():
        g = df[df["kiosk_id"] == kiosk]
        linha = {"Ponto de coleta": rotulo}
        for m in MOMENTOS:
            linha[nome_momento(m)] = exibir_contagem((g["momento"] == m).sum(), minimo)
        linha["Total"] = exibir_contagem(len(g), minimo)
        linha["Dias com coleta"] = int(g["data"].nunique())
        linhas.append(linha)
    total = {"Ponto de coleta": "Todos os pontos"}
    for m in MOMENTOS:
        total[nome_momento(m)] = exibir_contagem((df["momento"] == m).sum(), minimo)
    total["Total"] = exibir_contagem(len(df), minimo)
    total["Dias com coleta"] = int(df["data"].nunique())
    linhas.append(total)
    tabela = pd.DataFrame(linhas)
    formatos = {c: "int" for c in tabela.columns if c != "Ponto de coleta"}
    return Tabela("respostas_quiosque", "Respostas por ponto de coleta e momento", tabela, formatos)


def respostas_por_dia(df, rotulos, minimo) -> tuple[Tabela, Tabela, dict]:
    linhas, linhas_k = [], []
    grafico = {"datas": [], "totais": [], "exibir": [], "dia_semana": []}
    for d in sorted(df["data"].unique()):
        g = df[df["data"] == d]
        linha = {"Data": data_br(d), "Dia da semana": nome_dia(DIAS_SEMANA[d.weekday()])}
        for m in MOMENTOS:
            linha[nome_momento(m)] = exibir_contagem((g["momento"] == m).sum(), minimo)
        linha["Total"] = exibir_contagem(len(g), minimo)
        linhas.append(linha)
        linha_k = {"Data": data_br(d), "Dia da semana": nome_dia(DIAS_SEMANA[d.weekday()])}
        for kiosk, rotulo in rotulos.items():
            linha_k[rotulo] = exibir_contagem((g["kiosk_id"] == kiosk).sum(), minimo)
        linha_k["Total"] = exibir_contagem(len(g), minimo)
        linhas_k.append(linha_k)
        grafico["datas"].append(d)
        grafico["totais"].append(len(g) if len(g) >= minimo else None)
        grafico["exibir"].append(exibir_contagem(len(g), minimo))
        grafico["dia_semana"].append(nome_dia(DIAS_SEMANA[d.weekday()]))
    t1 = pd.DataFrame(linhas)
    t2 = pd.DataFrame(linhas_k)
    return (
        Tabela("respostas_dia", "Respostas por dia e momento", t1,
               {c: "int" for c in t1.columns if c not in ("Data", "Dia da semana")}),
        Tabela("respostas_dia_quiosque", "Respostas por dia e ponto de coleta", t2,
               {c: "int" for c in t2.columns if c not in ("Data", "Dia da semana")}),
        grafico,
    )


def respostas_detalhadas(df, rotulos, minimo) -> Tabela:
    """Contagem por ponto de coleta × dia × momento (formato longo, para o Excel)."""
    linhas = []
    for (kiosk, d, m), g in df.groupby(["kiosk_id", "data", "momento"]):
        linhas.append({
            "Ponto de coleta": rotulos.get(kiosk, kiosk),
            "Data": data_br(d),
            "Dia da semana": nome_dia(DIAS_SEMANA[d.weekday()]),
            "Momento": nome_momento(m),
            "Respostas": exibir_contagem(len(g), minimo),
            "_ordem": MOMENTOS.index(m),
            "_data": d,
        })
    tabela = pd.DataFrame(linhas)
    if not tabela.empty:
        tabela = tabela.sort_values(["Ponto de coleta", "_data", "_ordem"]).drop(columns=["_ordem", "_data"])
    return Tabela("respostas_detalhadas", "Respostas por ponto de coleta, dia e momento",
                  tabela.reset_index(drop=True), {"Respostas": "int"})


# =============================================================== participação
def participacao(df, config, rotulos, minimo) -> dict:
    util = df[df["dia_util"]]
    publico_padrao = int(config.get("publico_esperado_por_quiosque", 40))
    por_quiosque = config.get("publico_por_quiosque") or {}
    publico = {k: int(por_quiosque.get(k, publico_padrao)) for k in rotulos}
    total_funcionarios = int(config.get("funcionarios_total", 150))
    dias = util.groupby("kiosk_id")["data"].nunique().to_dict()
    base = sum(publico[k] * dias.get(k, 0) for k in rotulos)
    datas_uteis = int(util["data"].nunique())
    col_ref = f"Equivale a (% dos {total_funcionarios} funcionários)"

    linhas = []
    brutos = {}
    for m in MOMENTOS:
        n = int((util["momento"] == m).sum())
        taxa = n / base if base else math.nan
        media_dia = n / datas_uteis if datas_uteis else math.nan
        ref = media_dia / total_funcionarios if total_funcionarios else math.nan
        brutos[m] = {"n": n, "taxa": taxa, "media_dia": media_dia}
        linhas.append({
            "Momento": nome_momento(m),
            "Respostas (dias úteis)": exibir_contagem(n, minimo),
            "Média por dia útil": exibir_estatistica(media_dia, n, minimo),
            "Participação (% do público esperado)": exibir_estatistica(taxa, n, minimo),
            col_ref: exibir_estatistica(ref, n, minimo),
        })
    n_total = len(util)
    taxa_geral = n_total / (len(MOMENTOS) * base) if base else math.nan
    media_geral = n_total / datas_uteis / len(MOMENTOS) if datas_uteis else math.nan
    linhas.append({
        "Momento": "Média dos 4 momentos",
        "Respostas (dias úteis)": exibir_contagem(n_total, minimo),
        "Média por dia útil": exibir_estatistica(media_geral, n_total, minimo),
        "Participação (% do público esperado)": exibir_estatistica(taxa_geral, n_total, minimo),
        col_ref: exibir_estatistica(media_geral / total_funcionarios if total_funcionarios else math.nan,
                                    n_total, minimo),
    })
    t_momento = pd.DataFrame(linhas)

    # Por ponto de coleta × momento
    linhas_k = []
    for kiosk, rotulo in rotulos.items():
        g = util[util["kiosk_id"] == kiosk]
        base_k = publico[kiosk] * dias.get(kiosk, 0)
        linha = {
            "Ponto de coleta": rotulo,
            "Público esperado por dia": publico[kiosk],
            "Dias úteis com coleta": int(dias.get(kiosk, 0)),
        }
        for m in MOMENTOS:
            n = int((g["momento"] == m).sum())
            linha[nome_momento(m)] = exibir_estatistica(n / base_k if base_k else math.nan, n, minimo)
        linhas_k.append(linha)
    t_quiosque = pd.DataFrame(linhas_k)

    # Por semana
    linhas_s = []
    grafico = {"semanas": [], "rotulos": [], "por_momento": {m: [] for m in MOMENTOS}, "geral": []}
    for semana in sorted(util["semana"].unique()):
        us = util[util["semana"] == semana]
        dias_s = us.groupby("kiosk_id")["data"].nunique().to_dict()
        base_s = sum(publico[k] * dias_s.get(k, 0) for k in rotulos)
        rotulo = f"{data_curta(semana)} a {data_curta(semana + timedelta(days=4))}"
        linha = {"Semana": rotulo, "Dias úteis com coleta": int(us["data"].nunique())}
        for m in MOMENTOS:
            n = int((us["momento"] == m).sum())
            taxa = n / base_s if base_s else math.nan
            linha[nome_momento(m)] = exibir_estatistica(taxa, n, minimo)
            grafico["por_momento"][m].append(valor_grafico(taxa, n, minimo))
        n_s = len(us)
        taxa_s = n_s / (len(MOMENTOS) * base_s) if base_s else math.nan
        linha["Média dos 4 momentos"] = exibir_estatistica(taxa_s, n_s, minimo)
        grafico["geral"].append(valor_grafico(taxa_s, n_s, minimo))
        grafico["semanas"].append(semana)
        grafico["rotulos"].append(rotulo)
        linhas_s.append(linha)
    t_semana = pd.DataFrame(linhas_s)

    return {
        "tabela_momento": Tabela(
            "participacao", "Participação por momento", t_momento,
            {"Respostas (dias úteis)": "int", "Média por dia útil": "dec1",
             "Participação (% do público esperado)": "pct", col_ref: "pct"},
            nota=(f"Participação = respostas ÷ (público esperado × dias úteis com coleta). "
                  f"Público esperado: {publico_padrao} pessoas por ponto de coleta por dia. "
                  "Respostas de sábados, domingos e feriados não entram na taxa."),
        ),
        "tabela_quiosque": Tabela(
            "participacao_quiosque", "Participação por ponto de coleta e momento", t_quiosque,
            {**{nome_momento(m): "pct" for m in MOMENTOS},
             "Público esperado por dia": "int", "Dias úteis com coleta": "int"},
        ),
        "tabela_semana": Tabela(
            "participacao_semana", "Participação por semana", t_semana,
            {**{nome_momento(m): "pct" for m in MOMENTOS}, "Média dos 4 momentos": "pct",
             "Dias úteis com coleta": "int"},
        ),
        "grafico": grafico,
        "brutos": {"por_momento": brutos, "taxa_geral": taxa_geral, "n_util": n_total,
                   "base": base, "datas_uteis": datas_uteis, "publico": publico,
                   "semanal": list(zip(grafico["rotulos"], grafico["geral"]))},
    }


# ================================================================== emoções
def emocoes_por_momento(df, config, minimo) -> dict:
    ordem = _ordem_emocoes(df, config)
    linhas = []
    grafico = {"emocoes": ordem, "momentos": [], "pct": [], "contagem": [], "n": [],
               "outras": [], "outras_nomes": []}
    for m in MOMENTOS + ["todos"]:
        g = df if m == "todos" else df[df["momento"] == m]
        rotulo = "Todos os momentos" if m == "todos" else nome_momento(m)
        dist = distribuicao(g["emocao"], ordem, minimo)
        linha = {"Momento": rotulo, "Respostas": exibir_contagem(dist["n"], minimo)}
        for e in ordem:
            linha[e] = dist["pct"][e]
        linhas.append(linha)
        grafico["momentos"].append(rotulo)
        grafico["n"].append(dist["n"])
        # No gráfico, emoções com 1 a 4 respostas são juntadas em "Outras (<5 cada)".
        grafico["pct"].append(
            [dist["pct"][e] if isinstance(dist["pct"][e], float) else None for e in ordem]
            if dist["valida"] else None
        )
        grafico["contagem"].append([dist["contagem"][e] for e in ordem])
        pequenas = [e for e in ordem if dist["valida"] and not categoria_visivel(dist["bruto"][e], minimo)]
        grafico["outras"].append(sum(dist["bruto"][e] for e in pequenas) / dist["n"] if pequenas else None)
        grafico["outras_nomes"].append(pequenas)
    tabela = pd.DataFrame(linhas)
    return {
        "tabela": Tabela("emocoes_momento", "Distribuição das emoções por momento", tabela,
                         {"Respostas": "int", **{e: "pct" for e in ordem}}),
        "grafico": grafico,
    }


# ============================================================ índice de humor
def humor_por_momento(df, minimo) -> dict:
    linhas, brutos = [], {}
    for m in MOMENTOS + ["todos"]:
        g = df if m == "todos" else df[df["momento"] == m]
        n = len(g)
        media = g["pontuacao"].mean() if n else math.nan
        rotulo = "Todos os momentos" if m == "todos" else nome_momento(m)
        linhas.append({
            "Momento": rotulo,
            "Respostas": exibir_contagem(n, minimo),
            "Índice de humor": exibir_estatistica(media, n, minimo),
            "% positivas": exibir_fracao((g["valencia"] == "positiva").sum(), n, minimo),
            "% neutras": exibir_fracao((g["valencia"] == "neutra").sum(), n, minimo),
            "% negativas": exibir_fracao((g["valencia"] == "negativa").sum(), n, minimo),
        })
        brutos[m] = {"n": n, "media": media}
    tabela = pd.DataFrame(linhas)
    return {
        "tabela": Tabela("humor_momento", "Índice de humor por momento", tabela,
                         {"Respostas": "int", "Índice de humor": "sinal",
                          "% positivas": "pct", "% neutras": "pct", "% negativas": "pct"},
                         nota="Índice de humor = média das pontuações (Feliz e Animado +2, Neutro 0, "
                              "Cansado e Preocupado −1, Triste e Bravo −2, Furioso −3)."),
        "brutos": brutos,
    }


def humor_dia_semana_momento(df, minimo) -> dict:
    dias = _dias_presentes(df)
    stats = media_por_grupo(df, ["dia_semana", "momento"], minimo)
    por_dia = media_por_grupo(df, ["dia_semana"], minimo)
    por_momento = media_por_grupo(df, ["momento"], minimo)

    def busca(tab, filtros):
        sel = tab
        for col, val in filtros.items():
            sel = sel[sel[col] == val]
        if sel.empty:
            return 0, math.nan
        return int(sel["n"].iat[0]), float(sel["media"].iat[0])

    linhas = []
    z, n_matriz = [], []
    for d in dias:
        linha = {"Dia da semana": nome_dia(d)}
        z_linha, n_linha = [], []
        for m in MOMENTOS:
            n, media = busca(stats, {"dia_semana": d, "momento": m})
            linha[nome_momento(m)] = exibir_estatistica(media, n, minimo)
            z_linha.append(valor_grafico(media, n, minimo))
            n_linha.append(n)
        n, media = busca(por_dia, {"dia_semana": d})
        linha["Todos os momentos"] = exibir_estatistica(media, n, minimo)
        linhas.append(linha)
        z.append(z_linha)
        n_matriz.append(n_linha)
    total = {"Dia da semana": "Todos os dias"}
    geral = []
    for m in MOMENTOS:
        n, media = busca(por_momento, {"momento": m})
        total[nome_momento(m)] = exibir_estatistica(media, n, minimo)
        geral.append(valor_grafico(media, n, minimo))
    total["Todos os momentos"] = exibir_estatistica(df["pontuacao"].mean(), len(df), minimo)
    linhas.append(total)
    tabela = pd.DataFrame(linhas)
    formatos = {c: "sinal" for c in tabela.columns if c != "Dia da semana"}

    # contagens mascaradas para a tabela de apoio do mapa de calor
    linhas_n = []
    for d, n_linha in zip(dias, n_matriz):
        linha = {"Dia da semana": nome_dia(d)}
        for m, n in zip(MOMENTOS, n_linha):
            linha[nome_momento(m)] = exibir_contagem(n, minimo)
        linhas_n.append(linha)
    tabela_n = pd.DataFrame(linhas_n)

    return {
        "tabela": Tabela("humor_dia_momento", "Índice de humor por dia da semana e momento", tabela, formatos),
        "tabela_n": Tabela("respostas_dia_momento", "Respostas por dia da semana e momento", tabela_n,
                           {c: "int" for c in tabela_n.columns if c != "Dia da semana"}),
        "grafico": {"dias": [nome_dia(d) for d in dias], "dias_id": dias, "momentos": MOMENTOS,
                    "z": z, "n": n_matriz, "geral": geral},
    }


def variacoes_do_dia(df, rotulos, minimo) -> dict:
    """Variação média entre momentos, comparando as MÉDIAS de cada quiosque-dia.

    Como é anônimo, não dá para acompanhar a mesma pessoa. Para cada
    ponto de coleta e dia, calcula-se a média de cada momento; a variação
    daquele dia é a diferença entre as médias, usada só quando os dois
    momentos têm pelo menos `minimo` respostas. Depois tira-se a média
    dessas diferenças.
    """
    cols = ["kiosk_id", "data"]
    if df.empty:
        medias = contagens = pd.DataFrame()
    else:
        g = df.groupby(cols + ["momento"])["pontuacao"].agg(["mean", "count"])
        medias = g["mean"].unstack("momento")
        contagens = g["count"].unstack("momento").fillna(0)

    def calcular(filtro_kiosk=None):
        saida = {}
        for nome, de, para in VARIACOES:
            if medias.empty or de not in medias.columns or para not in medias.columns:
                saida[nome] = {"media": math.nan, "dias": 0}
                continue
            sel = pd.Series(True, index=medias.index)
            if filtro_kiosk is not None:
                sel &= medias.index.get_level_values("kiosk_id") == filtro_kiosk
            validos = sel & (contagens[de] >= minimo) & (contagens[para] >= minimo)
            difs = (medias[para] - medias[de])[validos]
            saida[nome] = {"media": float(difs.mean()) if len(difs) else math.nan, "dias": int(len(difs))}
        return saida

    geral = calcular()
    linhas = []
    for nome, de, para in VARIACOES:
        info = geral[nome]
        valido = info["dias"] > 0
        if not valido:
            leitura = INSUFICIENTE
        elif info["media"] > LIMIAR_ESTAVEL:
            leitura = "melhora"
        elif info["media"] < -LIMIAR_ESTAVEL:
            leitura = "piora"
        else:
            leitura = "estável"
        linhas.append({
            "Período": nome,
            "Cálculo": f"{nome_momento(para)} − {nome_momento(de)}",
            "Variação média": info["media"] if valido else INSUFICIENTE,
            "Dias considerados": info["dias"],
            "Leitura": leitura,
        })
    tabela = pd.DataFrame(linhas)

    linhas_k = []
    for kiosk, rotulo in rotulos.items():
        info_k = calcular(kiosk)
        linha = {"Ponto de coleta": rotulo}
        for nome, _, _ in VARIACOES:
            linha[nome] = info_k[nome]["media"] if info_k[nome]["dias"] > 0 else INSUFICIENTE
            linha[f"{nome} (dias)"] = info_k[nome]["dias"]
        linhas_k.append(linha)
    tabela_k = pd.DataFrame(linhas_k)
    formatos_k = {}
    for nome, _, _ in VARIACOES:
        formatos_k[nome] = "sinal"
        formatos_k[f"{nome} (dias)"] = "int"

    return {
        "tabela": Tabela(
            "variacoes", "Variações médias ao longo do dia", tabela,
            {"Variação média": "sinal", "Dias considerados": "int"},
            nota=(f"Para cada ponto de coleta e dia, compara-se a média de um momento com a do "
                  f"anterior, só quando os dois têm {minimo} ou mais respostas; depois, tira-se a "
                  f"média dessas diferenças. Variações entre −{str(LIMIAR_ESTAVEL).replace('.', ',')} "
                  f"e +{str(LIMIAR_ESTAVEL).replace('.', ',')} são consideradas estáveis."),
        ),
        "tabela_quiosque": Tabela("variacoes_quiosque", "Variações por ponto de coleta",
                                  tabela_k, formatos_k),
        "brutos": geral,
    }


# ===================================================================== clima
def humor_por_clima(df, minimo) -> dict:
    linhas_c, graf_c = [], {"rotulos": [], "valores": [], "n": []}
    for cod, rotulo in CONDICOES:
        g = df[df["condicao"] == cod]
        n = len(g)
        media = g["pontuacao"].mean() if n else math.nan
        linhas_c.append({
            "Condição do tempo": rotulo,
            "Respostas": exibir_contagem(n, minimo),
            "Índice de humor": exibir_estatistica(media, n, minimo),
            "% negativas": exibir_fracao((g["valencia"] == "negativa").sum(), n, minimo),
        })
        graf_c["rotulos"].append(rotulo)
        graf_c["valores"].append(valor_grafico(media, n, minimo))
        graf_c["n"].append(n)
    sem_info = int((~df["condicao"].isin([c for c, _ in CONDICOES])).sum())
    linhas_c.append({
        "Condição do tempo": "Sem informação (sem internet)",
        "Respostas": exibir_contagem(sem_info, minimo),
        "Índice de humor": exibir_estatistica(
            df.loc[~df["condicao"].isin([c for c, _ in CONDICOES]), "pontuacao"].mean() if sem_info else math.nan,
            sem_info, minimo),
        "% negativas": exibir_fracao(
            (df.loc[~df["condicao"].isin([c for c, _ in CONDICOES]), "valencia"] == "negativa").sum(),
            sem_info, minimo),
    })

    temperatura = df["temperatura_c"]
    faixas = pd.cut(temperatura, bins=LIMITES_TEMPERATURA, labels=FAIXAS_TEMPERATURA, right=False)
    linhas_t, graf_t = [], {"rotulos": [], "valores": [], "n": []}
    for faixa in FAIXAS_TEMPERATURA:
        g = df[faixas == faixa]
        n = len(g)
        media = g["pontuacao"].mean() if n else math.nan
        linhas_t.append({
            "Faixa de temperatura": faixa,
            "Respostas": exibir_contagem(n, minimo),
            "Índice de humor": exibir_estatistica(media, n, minimo),
            "% negativas": exibir_fracao((g["valencia"] == "negativa").sum(), n, minimo),
        })
        graf_t["rotulos"].append(faixa)
        graf_t["valores"].append(valor_grafico(media, n, minimo))
        graf_t["n"].append(n)

    formatos = {"Respostas": "int", "Índice de humor": "sinal", "% negativas": "pct"}
    return {
        "tabela_condicao": Tabela("clima_condicao", "Índice de humor por condição do tempo",
                                  pd.DataFrame(linhas_c), formatos,
                                  nota="Condição do tempo no momento da resposta (Open-Meteo)."),
        "tabela_temperatura": Tabela("clima_temperatura", "Índice de humor por faixa de temperatura",
                                     pd.DataFrame(linhas_t), formatos,
                                     nota="Faixas fechadas à esquerda: 10–15 °C inclui 10 °C e vai até 14,9 °C."),
        "grafico_condicao": graf_c,
        "grafico_temperatura": graf_t,
        "sem_informacao": sem_info,
    }


# ==================================================================== motivos
def motivos(df, config, minimo) -> dict:
    linhas = []
    grafico = []
    brutos = {}
    tem_motivo = df["motivo"].astype(str).str.strip().ne("") & df["motivo"].astype(str).ne("nan")
    for momento, valencia, pergunta in CONTEXTOS_MOTIVO:
        contexto = df[(df["momento"] == momento) & (df["valencia"] == valencia)]
        respondidos = contexto[tem_motivo.loc[contexto.index]] if len(contexto) else contexto
        n = len(respondidos)
        rotulo_ctx = f"{nome_momento(momento)} · emoções {valencia}s"
        item = {"titulo": f"{nome_momento(momento)} — {pergunta}", "subtitulo": f"Emoções {valencia}s",
                "momento": momento, "valencia": valencia, "n": n, "valido": n >= minimo, "itens": [],
                "omitidos": 0}
        if n < minimo:
            linhas.append({
                "Contexto": rotulo_ctx, "Pergunta": pergunta, "Motivo": INSUFICIENTE,
                "Respostas": exibir_contagem(n, minimo), "% dos motivos": INSUFICIENTE,
            })
        else:
            for motivo, c in respondidos["motivo"].value_counts().items():
                linhas.append({
                    "Contexto": rotulo_ctx, "Pergunta": pergunta, "Motivo": motivo,
                    "Respostas": exibir_contagem(c, minimo), "% dos motivos": exibir_fracao(c, n, minimo),
                })
                if categoria_visivel(c, minimo):
                    item["itens"].append({"motivo": motivo, "pct": c / n, "contagem": exibir_contagem(c, minimo)})
                else:
                    item["omitidos"] += 1  # 1 a 4 respostas: fica fora do gráfico
        item["taxa_resposta"] = exibir_fracao(n, len(contexto), minimo)
        grafico.append(item)
        brutos[(momento, valencia)] = item

    # Por emoção e momento
    linhas_e = []
    ordem = _ordem_emocoes(df, config)
    for momento in ("chegada", "saida_final"):
        for emocao in ordem:
            contexto = df[(df["momento"] == momento) & (df["emocao"] == emocao)]
            if contexto.empty or (contexto["valencia"] == "neutra").all():
                continue
            respondidos = contexto[tem_motivo.loc[contexto.index]]
            n = len(respondidos)
            # Só motivos com pelo menos `minimo` respostas são citados.
            contagens = respondidos["motivo"].value_counts()
            top = contagens[contagens >= minimo].head(3)
            if n >= minimo and len(top):
                texto = " · ".join(f"{m} ({round(c / n * 100)}%)" for m, c in top.items())
            else:
                texto = INSUFICIENTE
            linhas_e.append({
                "Momento": nome_momento(momento), "Emoção": emocao,
                "Respostas com motivo": exibir_contagem(n, minimo),
                "Principais motivos": texto,
            })
    return {
        "tabela": Tabela("motivos", "Principais motivos por momento", pd.DataFrame(linhas),
                         {"Respostas": "int", "% dos motivos": "pct"},
                         nota="Motivo é opcional e só é perguntado na chegada e na saída do dia "
                              f"(não é perguntado para Neutro). Motivos com menos de {minimo} respostas "
                              f"aparecem como “<{minimo}”, sem percentual."),
        "tabela_emocao": Tabela("motivos_emocao", "Principais motivos por emoção e momento",
                                pd.DataFrame(linhas_e), {"Respostas com motivo": "int"},
                                nota=f"Só aparecem motivos com {minimo} ou mais respostas."),
        "grafico": grafico,
        "brutos": brutos,
    }


# =========================================================== pergunta do dia
def pergunta_do_dia(df, config, minimo) -> dict:
    invertidas = set(config.get("perguntas_invertidas") or [])
    respondidas = df[
        df["resposta_pergunta_do_dia"].isin(RESPOSTAS_PERGUNTA)
        & df["pergunta_do_dia"].astype(str).str.strip().ne("")
    ]
    presentes = list(dict.fromkeys(respondidas["pergunta_do_dia"].tolist()))
    ordem = [p for p in ORDEM_PERGUNTAS if p in presentes] + [p for p in presentes if p not in ORDEM_PERGUNTAS]
    linhas, grafico = [], []
    for pergunta in ordem:
        g = respondidas[respondidas["pergunta_do_dia"] == pergunta]
        dist = distribuicao(g["resposta_pergunta_do_dia"], RESPOSTAS_PERGUNTA, minimo)
        invertida = pergunta in invertidas
        favoravel = "Não" if invertida else "Sim"
        desfavoravel = "Sim" if invertida else "Não"
        linhas.append({
            "Pergunta": pergunta,
            "Dias em que foi feita": int(g["data"].nunique()),
            "Respostas": exibir_contagem(dist["n"], minimo),
            "Sim": dist["pct"]["Sim"],
            "Mais ou menos": dist["pct"]["Mais ou menos"],
            "Não": dist["pct"]["Não"],
            "Resultado favorável": dist["pct"][favoravel],
            "Observação": "Aqui, “Sim” é o resultado desfavorável." if invertida else "",
        })
        grafico.append({
            "pergunta": pergunta, "n": dist["n"], "valida": dist["valida"], "invertida": invertida,
            # No gráfico, respostas com 1 a 4 pessoas são omitidas (None).
            "favoravel": (favoravel, dist["pct"][favoravel] if isinstance(dist["pct"][favoravel], float) else None),
            "meio": ("Mais ou menos", dist["pct"]["Mais ou menos"]
                     if isinstance(dist["pct"]["Mais ou menos"], float) else None),
            "desfavoravel": (desfavoravel, dist["pct"][desfavoravel]
                             if isinstance(dist["pct"][desfavoravel], float) else None),
            "omitidas": [r for r in RESPOSTAS_PERGUNTA
                         if dist["valida"] and not categoria_visivel(dist["bruto"][r], minimo)],
            "contagem": dist["contagem"],
        })
    tabela = pd.DataFrame(linhas, columns=["Pergunta", "Dias em que foi feita", "Respostas", "Sim",
                                           "Mais ou menos", "Não", "Resultado favorável", "Observação"])
    return {
        "tabela": Tabela("pergunta_dia", "Resultados da pergunta do dia", tabela,
                         {"Dias em que foi feita": "int", "Respostas": "int", "Sim": "pct",
                          "Mais ou menos": "pct", "Não": "pct", "Resultado favorável": "pct"},
                         nota="Feita na saída do dia, uma pergunta por dia em rodízio. "
                              "Respostas puladas não entram no cálculo. "
                              f"Respostas dadas por menos de {minimo} pessoas aparecem como “<{minimo}”."),
        "grafico": grafico,
    }


# ===================================================================== geral
def marcar_dias_uteis(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Dia útil = segunda a sexta, exceto feriados nacionais e feriados_extras."""
    df = df.copy()
    feriados = conjunto_feriados(config, {d.year for d in df["data"]})
    df["dia_util"] = df["data"].map(lambda d: d.weekday() < 5 and d not in feriados)
    return df


def analisar(df: pd.DataFrame, config: dict) -> Resultado:
    minimo = int(config.get("minimo_respostas_por_recorte", 5))
    df = marcar_dias_uteis(df, config)
    rotulos = rotulos_quiosques(df)
    resultado = Resultado(
        df=df, config=config, minimo=minimo,
        inicio=min(df["data"]), fim=max(df["data"]),
        rotulos_quiosques=rotulos,
    )
    t = resultado.tabelas
    g = resultado.graficos
    b = resultado.brutos

    t["respostas_quiosque"] = respostas_por_quiosque(df, rotulos, minimo)
    t_dia, t_dia_k, g["respostas_dia"] = respostas_por_dia(df, rotulos, minimo)
    t["respostas_dia"] = t_dia
    t["respostas_dia_quiosque"] = t_dia_k
    t["respostas_detalhadas"] = respostas_detalhadas(df, rotulos, minimo)

    p = participacao(df, config, rotulos, minimo)
    t["participacao"] = p["tabela_momento"]
    t["participacao_quiosque"] = p["tabela_quiosque"]
    t["participacao_semana"] = p["tabela_semana"]
    g["participacao_semana"] = p["grafico"]
    b["participacao"] = p["brutos"]

    e = emocoes_por_momento(df, config, minimo)
    t["emocoes_momento"] = e["tabela"]
    g["emocoes_momento"] = e["grafico"]

    h = humor_por_momento(df, minimo)
    t["humor_momento"] = h["tabela"]
    b["humor_momento"] = h["brutos"]

    hd = humor_dia_semana_momento(df, minimo)
    t["humor_dia_momento"] = hd["tabela"]
    t["respostas_dia_momento"] = hd["tabela_n"]
    g["humor_dia_momento"] = hd["grafico"]

    v = variacoes_do_dia(df, rotulos, minimo)
    t["variacoes"] = v["tabela"]
    t["variacoes_quiosque"] = v["tabela_quiosque"]
    b["variacoes"] = v["brutos"]

    c = humor_por_clima(df, minimo)
    t["clima_condicao"] = c["tabela_condicao"]
    t["clima_temperatura"] = c["tabela_temperatura"]
    g["clima_condicao"] = c["grafico_condicao"]
    g["clima_temperatura"] = c["grafico_temperatura"]
    b["clima_sem_info"] = c["sem_informacao"]

    mo = motivos(df, config, minimo)
    t["motivos"] = mo["tabela"]
    t["motivos_emocao"] = mo["tabela_emocao"]
    g["motivos"] = mo["grafico"]
    b["motivos"] = mo["brutos"]

    pq = pergunta_do_dia(df, config, minimo)
    t["pergunta_dia"] = pq["tabela"]
    g["pergunta_dia"] = pq["grafico"]

    util = df[df["dia_util"]]
    resultado.kpis = {
        "total": len(df),
        "pontos": len(rotulos),
        "dias_coleta": int(df["data"].nunique()),
        "dias_uteis_coleta": int(util["data"].nunique()),
        "respostas_fora_dias_uteis": int((~df["dia_util"]).sum()),
        "participacao_media": p["brutos"]["taxa_geral"],
        "indice_geral": float(df["pontuacao"].mean()),
        # fração, ou '<5' / 'dados insuficientes' pela regra de anonimato
        "pct_positivas": exibir_fracao((df["valencia"] == "positiva").sum(), len(df), minimo),
        "pct_negativas": exibir_fracao((df["valencia"] == "negativa").sum(), len(df), minimo),
        "momento_automatico_nao": int((df["momento_automatico"] == "não").sum()),
    }
    return resultado
