"""Gera o relatório em HTML (abre no navegador, funciona sem internet).

O plotly.js vai embutido no próprio arquivo, então o HTML pode ser
enviado por e-mail ou aberto de um pendrive.
"""
from __future__ import annotations

import base64
import html as _html
from datetime import datetime
from pathlib import Path

import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

from quiosque.formato import MOMENTOS
from relatorio.analise import INSUFICIENTE, Resultado, Tabela
from relatorio.formatacao import (
    data_br, decimal, eh_numero, inteiro, nome_momento, percentual,
)

# --------------------------------------------------------------- identidade
AZUL = "#0446a4"
AZUL_CLARO = "#00aeef"
VERDE = "#a7f432"
TEXTO = "#323232"
FUNDO = "#fbfbfb"
SUPERFICIE = "#ffffff"
GRADE = "#e1e0d9"
EIXO = "#c3c2b7"
MUDO = "#6b6a66"
INSUF_FUNDO = "#efeeea"
INSUF_MAPA = "#d6d5cf"  # cinza mais escuro que o meio da escala (para não confundir com 0)
OUTRAS = "#d6d5cf"  # segmento "Outras (<5 cada)" — mais claro que o cinza do Neutro
NOTA_OMITIDAS = "Categorias com menos de 5 respostas foram omitidas do gráfico (aparecem como “<5” na tabela)."
FONTE = '"Segoe UI", system-ui, -apple-system, Roboto, Arial, sans-serif'

# Rampa ordinal azul para os 4 momentos (validada: tom único, claridade crescente)
CORES_MOMENTOS = ["#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]
# Paleta categórica (ordem fixa) para os dias da semana
CORES_CATEGORICAS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6"]
# Polaridade (acima/abaixo de zero; favorável/desfavorável)
POSITIVO = "#2a78d6"
NEGATIVO = "#e34948"
NEUTRO_CINZA = "#c3c2b7"
ESCALA_DIVERGENTE = [
    [0.0, "#b3261e"], [0.25, "#eb8f8b"], [0.5, "#f0efec"], [0.75, "#86b6ef"], [1.0, "#1c5cab"],
]

CONFIG_PLOTLY = {
    "displaylogo": False,
    "responsive": True,
    "modeBarButtonsToRemove": [
        "zoom2d", "pan2d", "select2d", "lasso2d", "zoomIn2d", "zoomOut2d",
        "autoScale2d", "resetScale2d", "toggleSpikelines", "hoverClosestCartesian",
        "hoverCompareCartesian",
    ],
    "toImageButtonOptions": {"format": "png", "scale": 2},
}


# ================================================================ utilidades
def _esc(texto) -> str:
    return _html.escape(str(texto), quote=True)


def _cor_texto(fundo_hex: str) -> str:
    """Branco ou quase-preto, conforme a luminância da cor de fundo."""
    h = fundo_hex.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    lum = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    return "#ffffff" if lum < 0.36 else "#0b0b0b"


def _cor_escala(valor: float, limite: float) -> str:
    """Cor da escala divergente para um valor (para escolher a cor do texto)."""
    t = max(0.0, min(1.0, (valor + limite) / (2 * limite)))
    for (p0, c0), (p1, c1) in zip(ESCALA_DIVERGENTE, ESCALA_DIVERGENTE[1:]):
        if p0 <= t <= p1:
            f = (t - p0) / (p1 - p0) if p1 > p0 else 0
            a = [int(c0[i:i + 2], 16) for i in (1, 3, 5)]
            b = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
            return "#" + "".join(f"{round(x + (y - x) * f):02x}" for x, y in zip(a, b))
    return ESCALA_DIVERGENTE[-1][1]


def _layout_base(fig: go.Figure, altura: int, **extra) -> go.Figure:
    fig.update_layout(
        height=altura,
        margin=dict(l=10, r=20, t=40, b=10),
        paper_bgcolor=SUPERFICIE,
        plot_bgcolor=SUPERFICIE,
        font=dict(family=FONTE, color=TEXTO, size=13),
        separators=",.",
        hoverlabel=dict(bgcolor=SUPERFICIE, bordercolor=EIXO, font=dict(family=FONTE, color=TEXTO, size=13)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    font=dict(size=12), title=None, traceorder="normal"),
        barcornerradius=4,
        **extra,
    )
    fig.update_xaxes(showgrid=False, linecolor=EIXO, ticks="", automargin=True,
                     tickfont=dict(color=MUDO, size=12), title_font=dict(color=MUDO, size=12))
    fig.update_yaxes(gridcolor=GRADE, gridwidth=1, zeroline=False, linecolor=EIXO, automargin=True,
                     tickfont=dict(color=MUDO, size=12), title_font=dict(color=MUDO, size=12))
    return fig


def _sem_dados(fig: go.Figure, texto: str = "Dados insuficientes para este gráfico") -> go.Figure:
    fig.add_annotation(text=texto, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
                       font=dict(color=MUDO, size=14))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def _fig_html(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False, config=CONFIG_PLOTLY)


# =================================================================== tabelas
def _formatar(valor, formato: str) -> tuple[str, str]:
    """Devolve (texto, classe CSS)."""
    if isinstance(valor, str):
        if valor == INSUFICIENTE:
            return valor, "insuf"
        if valor.startswith("<"):
            return valor, "num poucos"
        return valor, ""
    if valor is None or not eh_numero(valor):
        return "", ""
    if formato == "int":
        return inteiro(valor), "num"
    if formato == "dec1":
        return decimal(valor, 1), "num"
    if formato == "dec":
        return decimal(valor, 2), "num"
    if formato == "sinal":
        return decimal(valor, 2, sinal=True), "num"
    if formato == "pct":
        return percentual(valor), "num"
    return str(valor), ""


def tabela_html(tabela: Tabela, classe: str = "") -> str:
    df = tabela.dados
    if df.empty:
        return '<p class="vazio">Sem dados para esta tabela.</p>'
    cab = "".join(
        f'<th scope="col" class="{"num" if tabela.formatos.get(c) in ("int", "dec", "dec1", "sinal", "pct") else ""}">'
        f"{_esc(c)}</th>"
        for c in df.columns
    )
    linhas = []
    for _, linha in df.iterrows():
        celulas = []
        for i, coluna in enumerate(df.columns):
            texto, css = _formatar(linha[coluna], tabela.formatos.get(coluna, "texto"))
            tag = "th" if i == 0 else "td"
            escopo = ' scope="row"' if i == 0 else ""
            celulas.append(f'<{tag}{escopo} class="{css}">{_esc(texto)}</{tag}>')
        css_linha = ' class="total"' if str(linha.iloc[0]).startswith(("Todos", "Média dos")) else ""
        linhas.append(f"<tr{css_linha}>{''.join(celulas)}</tr>")
    nota = f'<p class="nota">{_esc(tabela.nota)}</p>' if tabela.nota else ""
    return (
        f'<div class="tabela-rolagem {classe}"><table><thead><tr>{cab}</tr></thead>'
        f'<tbody>{"".join(linhas)}</tbody></table></div>{nota}'
    )


def detalhes(titulo: str, conteudo: str, aberto: bool = False) -> str:
    return (f'<details{" open" if aberto else ""}><summary>{_esc(titulo)}</summary>'
            f'<div class="detalhes-corpo">{conteudo}</div></details>')


def cartao(titulo: str, subtitulo: str, corpo: str, largura: str = "") -> str:
    sub = f'<p class="subtitulo">{subtitulo}</p>' if subtitulo else ""
    return f'<article class="cartao {largura}"><h3>{_esc(titulo)}</h3>{sub}{corpo}</article>'


# ================================================================== gráficos
def grafico_participacao_semanal(r: Resultado) -> str:
    g = r.graficos["participacao_semana"]
    fig = go.Figure()
    if not g["semanas"] or all(v is None for m in MOMENTOS for v in g["por_momento"][m]):
        return _fig_html(_sem_dados(_layout_base(fig, 320)))
    for cor, m in zip(CORES_MOMENTOS, MOMENTOS):
        valores = g["por_momento"][m]
        fig.add_trace(go.Scatter(
            x=g["rotulos"], y=valores, name=nome_momento(m), mode="lines+markers",
            line=dict(color=cor, width=2), marker=dict(size=9, color=cor, line=dict(color=SUPERFICIE, width=2)),
            hovertemplate="Semana %{x}<br>" + _esc(nome_momento(m)) + ": %{y:.0%}<extra></extra>",
            connectgaps=False,
        ))
    fig.add_trace(go.Scatter(
        x=g["rotulos"], y=g["geral"], name="Média dos 4 momentos", mode="lines+markers",
        line=dict(color=TEXTO, width=3), marker=dict(size=9, color=TEXTO, line=dict(color=SUPERFICIE, width=2)),
        hovertemplate="Semana %{x}<br>Média dos 4 momentos: %{y:.0%}<extra></extra>",
    ))
    _layout_base(fig, 360, hovermode="x unified")
    fig.update_yaxes(tickformat=".0%", range=[0, 1.02], title="Participação (% do público esperado)")
    fig.update_xaxes(title="Semana")
    return _fig_html(fig)


def grafico_respostas_dia(r: Resultado) -> str:
    g = r.graficos["respostas_dia"]
    fig = go.Figure()
    rotulos = [f"{d.strftime('%d/%m')}<br>{dia[:3]}" for d, dia in zip(g["datas"], g["dia_semana"])]
    exibir = [inteiro(v) if isinstance(v, int) else v for v in g["exibir"]]
    fig.add_trace(go.Bar(
        x=rotulos, y=g["totais"], marker=dict(color=AZUL), width=0.6, name="Respostas",
        customdata=exibir, hovertemplate="%{x}<br>Respostas: %{customdata}<extra></extra>",
    ))
    for rot, v, e in zip(rotulos, g["totais"], g["exibir"]):
        if v is None and e != 0:
            fig.add_annotation(x=rot, y=0, text=str(e), showarrow=False, yshift=10,
                               font=dict(color=MUDO, size=11))
    _layout_base(fig, 340, showlegend=False)
    fig.update_xaxes(tickangle=0, tickfont=dict(size=10))
    fig.update_yaxes(title="Respostas no dia (todos os pontos)")
    return _fig_html(fig)


def grafico_emocoes(r: Resultado) -> str:
    g = r.graficos["emocoes_momento"]
    cores = r.config.get("cores_emocoes", {})
    fig = go.Figure()
    linhas = g["momentos"]
    for j, emocao in enumerate(g["emocoes"]):
        cor = cores.get(emocao, "#9aa3ad")
        valores = [linha[j] if linha is not None and linha[j] is not None else None for linha in g["pct"]]
        textos = [percentual(v) if v is not None and v >= 0.07 else "" for v in valores]
        contagens = [str(c[j]) if not isinstance(c[j], int) else inteiro(c[j]) for c in g["contagem"]]
        fig.add_trace(go.Bar(
            y=linhas, x=valores, name=emocao, orientation="h",
            marker=dict(color=cor, line=dict(color=SUPERFICIE, width=2)),
            text=textos, textposition="inside", insidetextanchor="middle",
            textfont=dict(color=_cor_texto(cor), size=12), cliponaxis=False,
            customdata=contagens,
            hovertemplate="%{y} · " + _esc(emocao) + ": %{x:.0%} (respostas: %{customdata})<extra></extra>",
        ))
    if any(v is not None for v in g["outras"]):
        fig.add_trace(go.Bar(
            y=linhas, x=g["outras"], name=f"Outras (<{r.minimo} cada)", orientation="h",
            marker=dict(color=OUTRAS, line=dict(color=SUPERFICIE, width=2)),
            customdata=[", ".join(nomes) for nomes in g["outras_nomes"]],
            hovertemplate="%{y} · Outras: %{customdata}<br>(menos de " + str(r.minimo)
                          + " respostas cada)<extra></extra>",
        ))
    for rotulo, n, pct in zip(linhas, g["n"], g["pct"]):
        if pct is None:
            fig.add_annotation(y=rotulo, x=0.5, text=INSUFICIENTE, showarrow=False,
                               font=dict(color=MUDO, size=12), bgcolor=INSUF_FUNDO)
    _layout_base(fig, 120 + 56 * len(linhas), barmode="stack", bargap=0.45)
    fig.update_xaxes(tickformat=".0%", range=[0, 1], showgrid=True, gridcolor=GRADE)
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_layout(legend=dict(traceorder="normal"))
    return _fig_html(fig)


def _nota_outras(r: Resultado) -> str:
    if any(v is not None for v in r.graficos["emocoes_momento"]["outras"]):
        return (f'<p class="nota">Emoções com menos de {r.minimo} respostas em um momento foram juntadas '
                f'no segmento cinza “Outras (&lt;{r.minimo} cada)”, sem percentual.</p>')
    return ""


def grafico_humor_ao_longo_do_dia(r: Resultado) -> str:
    g = r.graficos["humor_dia_momento"]
    x = [nome_momento(m) for m in MOMENTOS]
    fig = go.Figure()
    cor_i = 0
    for dia, linha, ns in zip(g["dias"], g["z"], g["n"]):
        # Linhas com menos de 3 pontos válidos (ex.: fins de semana) ficam só na tabela.
        if sum(v is not None for v in linha) < 3:
            continue
        cor = CORES_CATEGORICAS[cor_i % len(CORES_CATEGORICAS)]
        cor_i += 1
        fig.add_trace(go.Scatter(
            x=x, y=linha, name=dia, mode="lines+markers", connectgaps=False,
            line=dict(color=cor, width=2), marker=dict(size=9, color=cor, line=dict(color=SUPERFICIE, width=2)),
            customdata=ns,
            hovertemplate=_esc(dia) + " · %{x}<br>Índice: %{y:+.2f} (respostas: %{customdata})<extra></extra>",
        ))
    if any(v is not None for v in g["geral"]):
        fig.add_trace(go.Scatter(
            x=x, y=g["geral"], name="Todos os dias", mode="lines+markers+text",
            line=dict(color=TEXTO, width=3), marker=dict(size=10, color=TEXTO, line=dict(color=SUPERFICIE, width=2)),
            text=["" for _ in x[:-1]] + ["Todos os dias"], textposition="middle right",
            textfont=dict(color=TEXTO, size=12),
            hovertemplate="Todos os dias · %{x}<br>Índice: %{y:+.2f}<extra></extra>",
        ))
    if not fig.data:
        return _fig_html(_sem_dados(_layout_base(fig, 380)))
    _layout_base(fig, 400)
    fig.update_yaxes(title="Índice de humor", zeroline=True, zerolinecolor=EIXO, zerolinewidth=1,
                     tickformat="+.1f")
    fig.update_xaxes(range=[-0.25, 3.7])
    return _fig_html(fig)


def grafico_mapa_calor(r: Resultado) -> str:
    g = r.graficos["humor_dia_momento"]
    x = [nome_momento(m) for m in MOMENTOS]
    y = g["dias"]
    fig = go.Figure()
    if not y:
        return _fig_html(_sem_dados(_layout_base(fig, 300)))
    validos = [v for linha in g["z"] for v in linha if v is not None]
    limite = max(1.0, round(max([abs(v) for v in validos] or [1]) + 0.05, 1))
    textos_hover = []
    for dia, linha, ns in zip(y, g["z"], g["n"]):
        textos_hover.append([
            f"{dia} · {m}<br>Índice: {decimal(v, 2, sinal=True)}<br>Respostas: {inteiro(n)}"
            if v is not None else f"{dia} · {m}<br>{INSUFICIENTE}"
            for m, v, n in zip(x, linha, ns)
        ])
    # células insuficientes: camada cinza por baixo
    fig.add_trace(go.Heatmap(
        x=x, y=y, z=[[0 if v is None else None for v in linha] for linha in g["z"]],
        colorscale=[[0, INSUF_MAPA], [1, INSUF_MAPA]], showscale=False, xgap=3, ygap=3,
        hoverinfo="text", text=textos_hover,
    ))
    fig.add_trace(go.Heatmap(
        x=x, y=y, z=g["z"], zmin=-limite, zmax=limite, zmid=0, colorscale=ESCALA_DIVERGENTE,
        xgap=3, ygap=3, hoverinfo="text", text=textos_hover,
        colorbar=dict(title=dict(text="Índice", side="top"), tickformat="+.1f", thickness=12, len=0.9,
                      outlinewidth=0),
    ))
    for dia, linha, ns in zip(y, g["z"], g["n"]):
        for m, v, n in zip(x, linha, ns):
            if v is None:
                fig.add_annotation(x=m, y=dia, text="<i>dados<br>insuficientes</i>", showarrow=False,
                                   font=dict(color="#45443f", size=11))
            else:
                cor = _cor_texto(_cor_escala(v, limite))
                fig.add_annotation(
                    x=m, y=dia, showarrow=False,
                    text=f"<b>{decimal(v, 2, sinal=True)}</b><br><span style='font-size:11px'>n={inteiro(n)}</span>",
                    font=dict(color=cor, size=14),
                )
    _layout_base(fig, 110 + 62 * len(y), showlegend=False)
    fig.update_yaxes(autorange="reversed", showgrid=False, ticks="")
    fig.update_xaxes(side="top", showline=False)
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
    return _fig_html(fig)


def _barras_polaridade(rotulos, valores, extras, titulo_eixo, horizontal=True, altura=300) -> go.Figure:
    fig = go.Figure()
    cores = [POSITIVO if (v or 0) >= 0 else NEGATIVO for v in valores]
    textos = [decimal(v, 2, sinal=True) if v is not None else "" for v in valores]
    if horizontal:
        fig.add_trace(go.Bar(
            y=rotulos, x=valores, orientation="h", marker=dict(color=cores), width=0.5,
            text=textos, textposition="outside", cliponaxis=False, textfont=dict(color=TEXTO),
            customdata=extras, hovertemplate="%{y}: %{x:+.2f}<br>%{customdata}<extra></extra>",
        ))
    else:
        fig.add_trace(go.Bar(
            x=rotulos, y=valores, marker=dict(color=cores), width=0.5,
            text=textos, textposition="outside", cliponaxis=False, textfont=dict(color=TEXTO),
            customdata=extras, hovertemplate="%{x}: %{y:+.2f}<br>%{customdata}<extra></extra>",
        ))
    for rot, v in zip(rotulos, valores):
        if v is None:
            if horizontal:
                fig.add_annotation(y=rot, x=0, text=INSUFICIENTE, showarrow=False, xanchor="left", xshift=6,
                                   font=dict(color=MUDO, size=11))
            else:
                fig.add_annotation(x=rot, y=0, text="dados<br>insuficientes", showarrow=False, yshift=18,
                                   font=dict(color=MUDO, size=11))
    validos = [abs(v) for v in valores if v is not None] or [0.5]
    lim = max(0.5, max(validos) * 1.35)
    _layout_base(fig, altura, showlegend=False)
    if horizontal:
        fig.update_xaxes(range=[-lim, lim], zeroline=True, zerolinecolor=EIXO, zerolinewidth=1,
                         tickformat="+.1f", showgrid=True, gridcolor=GRADE, title=titulo_eixo)
        fig.update_yaxes(autorange="reversed", showgrid=False)
    else:
        fig.update_yaxes(range=[-lim, lim], zeroline=True, zerolinecolor=EIXO, zerolinewidth=1,
                         tickformat="+.1f", title=titulo_eixo)
    return fig


def grafico_variacoes(r: Resultado) -> str:
    b = r.brutos["variacoes"]
    rotulos = list(b.keys())
    valores = [b[n]["media"] if b[n]["dias"] > 0 else None for n in rotulos]
    extras = [f"Base: {b[n]['dias']} dia(s) por ponto de coleta" for n in rotulos]
    fig = _barras_polaridade(rotulos, valores, extras, "Variação média do índice de humor", altura=280)
    return _fig_html(fig)


def grafico_clima(r: Resultado, chave: str, titulo_eixo: str) -> str:
    g = r.graficos[chave]
    extras = [f"Respostas: {inteiro(n) if n >= r.minimo else ('<' + str(r.minimo) if n else '0')}"
              for n in g["n"]]
    fig = _barras_polaridade(g["rotulos"], g["valores"], extras, "Índice de humor",
                             horizontal=False, altura=320)
    fig.update_xaxes(title=titulo_eixo)
    return _fig_html(fig)


def graficos_motivos(r: Resultado) -> str:
    blocos = []
    for item in r.graficos["motivos"]:
        cor = NEGATIVO if item["valencia"] == "negativa" else POSITIVO
        fig = go.Figure()
        if not item["valido"]:
            _layout_base(fig, 260, showlegend=False)
            _sem_dados(fig, INSUFICIENTE + f" (menos de {r.minimo} motivos informados)")
        elif not item["itens"]:
            _layout_base(fig, 260, showlegend=False)
            _sem_dados(fig, f"Nenhum motivo com {r.minimo} ou mais respostas")
        else:
            itens = item["itens"]
            rotulos = [i["motivo"] for i in itens]
            valores = [i["pct"] for i in itens]
            contagens = [inteiro(i["contagem"]) if isinstance(i["contagem"], int) else i["contagem"] for i in itens]
            fig.add_trace(go.Bar(
                y=rotulos, x=valores, orientation="h", marker=dict(color=cor), width=0.6,
                text=[percentual(v) for v in valores], textposition="outside", cliponaxis=False,
                textfont=dict(color=TEXTO, size=12), customdata=contagens,
                hovertemplate="%{y}: %{x:.0%} (respostas: %{customdata})<extra></extra>",
            ))
            _layout_base(fig, 70 + 34 * len(itens), showlegend=False)
            fig.update_xaxes(tickformat=".0%", range=[0, max(valores) * 1.25], showgrid=True, gridcolor=GRADE)
            fig.update_yaxes(autorange="reversed", showgrid=False)
            fig.update_layout(margin=dict(l=10, r=30, t=10, b=10))
        taxa = item["taxa_resposta"]
        sub = f"{_esc(item['subtitulo'])} · motivos informados: "
        sub += _esc(inteiro(item["n"]) if item["n"] >= r.minimo else (f"<{r.minimo}" if item["n"] else "0"))
        if isinstance(taxa, float):
            sub += f" ({percentual(taxa)} de quem foi perguntado)"
        nota = f'<p class="nota">{_esc(NOTA_OMITIDAS)}</p>' if item["omitidos"] else ""
        blocos.append(cartao(item["titulo"], sub, _fig_html(fig) + nota, "meio"))
    return f'<div class="grade-2">{"".join(blocos)}</div>'


def grafico_pergunta_do_dia(r: Resultado) -> str:
    itens = r.graficos["pergunta_dia"]
    fig = go.Figure()
    if not itens:
        return _fig_html(_sem_dados(_layout_base(fig, 240), "Nenhuma pergunta do dia respondida no período"))

    def quebrar(texto, largura=34):
        palavras, linhas, atual = texto.split(), [], ""
        for p in palavras:
            if len(atual) + len(p) + 1 > largura and atual:
                linhas.append(atual)
                atual = p
            else:
                atual = f"{atual} {p}".strip()
        linhas.append(atual)
        return "<br>".join(linhas)

    rotulos = [quebrar(i["pergunta"]) for i in itens]
    for chave, nome, cor in (("favoravel", "Favorável", POSITIVO), ("meio", "Mais ou menos", NEUTRO_CINZA),
                             ("desfavoravel", "Desfavorável", NEGATIVO)):
        valores = [i[chave][1] for i in itens]
        respostas = [i[chave][0] for i in itens]
        textos = [
            (f"{resp} {percentual(v)}" if v >= 0.22 else percentual(v) if v >= 0.06 else "") if v is not None else ""
            for resp, v in zip(respostas, valores)
        ]
        fig.add_trace(go.Bar(
            y=rotulos, x=valores, name=nome, orientation="h",
            marker=dict(color=cor, line=dict(color=SUPERFICIE, width=2)),
            text=textos, textposition="inside", insidetextanchor="middle",
            textfont=dict(color=_cor_texto(cor), size=12),
            customdata=respostas,
            hovertemplate="%{customdata}: %{x:.0%}<extra>" + nome + "</extra>",
        ))
    for rot, i in zip(rotulos, itens):
        if not i["valida"]:
            fig.add_annotation(y=rot, x=0.5, text=INSUFICIENTE, showarrow=False,
                               font=dict(color=MUDO, size=12), bgcolor=INSUF_FUNDO)
    _layout_base(fig, 110 + 70 * len(itens), barmode="stack", bargap=0.45)
    fig.update_xaxes(tickformat=".0%", range=[0, 1], showgrid=True, gridcolor=GRADE)
    fig.update_yaxes(autorange="reversed", showgrid=False)
    nota = f'<p class="nota">{_esc(NOTA_OMITIDAS)}</p>' if any(i["omitidas"] for i in itens) else ""
    return _fig_html(fig) + nota


# ===================================================================== página
CSS = """
:root {
  color-scheme: light;
  --azul: #0446a4; --azul-claro: #00aeef; --verde: #a7f432;
  --texto: #323232; --fundo: #fbfbfb; --cartao: #ffffff;
  --linha: #e1e0d9; --mudo: #6b6a66; --insuf: #efeeea;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; background: var(--fundo); color: var(--texto);
  font-family: "Segoe UI", system-ui, -apple-system, Roboto, Arial, sans-serif; font-size: 15px; line-height: 1.5; }
.topo { background: var(--azul); color: #fff; border-bottom: 6px solid var(--verde); }
.topo-interno { max-width: 1180px; margin: 0 auto; padding: 22px 20px; display: flex; gap: 20px; align-items: center; flex-wrap: wrap; }
.topo img { height: 52px; background: #fff; border-radius: 8px; padding: 6px 10px; }
.marca-texto { font-weight: 700; letter-spacing: .08em; background: #fff; color: var(--azul); border-radius: 8px; padding: 10px 14px; }
.topo h1 { margin: 0; font-size: 26px; line-height: 1.2; }
.topo p { margin: 4px 0 0; opacity: .92; }
nav.sumario { position: sticky; top: 0; z-index: 10; background: #fff; border-bottom: 1px solid var(--linha); }
nav.sumario ul { max-width: 1180px; margin: 0 auto; padding: 0 12px; list-style: none; display: flex; gap: 2px; overflow-x: auto; }
nav.sumario a { display: block; padding: 11px 12px; color: var(--azul); text-decoration: none; font-weight: 600; white-space: nowrap; font-size: 14px; }
nav.sumario a:hover, nav.sumario a:focus { background: #eef4fc; }
main { max-width: 1180px; margin: 0 auto; padding: 8px 20px 40px; }
section { margin-top: 28px; scroll-margin-top: 56px; }
h2 { color: var(--azul); font-size: 22px; margin: 0 0 12px; padding-bottom: 6px; border-bottom: 2px solid var(--azul-claro); }
h3 { margin: 0 0 4px; font-size: 16px; color: var(--texto); }
.subtitulo { margin: 0 0 10px; color: var(--mudo); font-size: 14px; }
.cartao { background: var(--cartao); border: 1px solid var(--linha); border-radius: 10px; padding: 16px 18px; margin-bottom: 16px; }
.grade-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.grade-2 > .cartao { margin-bottom: 0; min-width: 0; }
.achados { margin: 0; padding-left: 20px; }
.achados li { margin: 6px 0; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 16px 0; }
.kpi { background: var(--cartao); border: 1px solid var(--linha); border-left: 5px solid var(--azul); border-radius: 10px; padding: 12px 14px; }
.kpi .rotulo { color: var(--mudo); font-size: 13px; }
.kpi .valor { font-size: 30px; font-weight: 600; line-height: 1.2; color: var(--texto); }
.kpi .detalhe { color: var(--mudo); font-size: 12px; }
.aviso { background: #eef7d9; border: 1px solid #c9e98a; border-radius: 8px; padding: 10px 14px; font-size: 14px; }
.tabela-rolagem { overflow-x: auto; margin: 8px 0; }
table { border-collapse: collapse; width: 100%; font-size: 14px; font-variant-numeric: tabular-nums; }
th, td { padding: 7px 10px; border-bottom: 1px solid var(--linha); text-align: left; vertical-align: top; }
thead th { background: var(--azul); color: #fff; font-weight: 600; position: sticky; top: 0; }
tbody th { font-weight: 600; }
.num { text-align: right; white-space: nowrap; }
td.insuf { background: var(--insuf); color: var(--mudo); font-style: italic; text-align: center; white-space: nowrap; }
td.poucos { color: var(--mudo); }
tr.total th, tr.total td { background: #f4f7fc; font-weight: 600; }
tr.total td.insuf { font-weight: 400; }
.nota { color: var(--mudo); font-size: 13px; margin: 6px 0 0; }
.vazio { color: var(--mudo); font-style: italic; }
details { margin: 8px 0 0; }
summary { cursor: pointer; color: var(--azul); font-weight: 600; padding: 6px 0; }
.detalhes-corpo { padding: 4px 0 8px; }
.legenda-insuf { display: inline-block; background: var(--insuf); color: var(--mudo); font-style: italic; padding: 0 6px; border-radius: 4px; }
footer { max-width: 1180px; margin: 0 auto; padding: 20px; color: var(--mudo); font-size: 13px; border-top: 1px solid var(--linha); }
@media (max-width: 900px) {
  .grade-2 { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 640px) {
  .topo h1 { font-size: 21px; }
  main { padding: 8px 12px 32px; }
}
@media print {
  nav.sumario { display: none; }
  .cartao, .kpi { break-inside: avoid; }
}
"""


def _logo(raiz: Path | None) -> str:
    if raiz:
        caminho = raiz / "assets" / "logo.png"
        if caminho.exists() and caminho.stat().st_size > 0:
            dados = base64.b64encode(caminho.read_bytes()).decode("ascii")
            return f'<img src="data:image/png;base64,{dados}" alt="Eurostec">'
    return '<span class="marca-texto">EUROSTEC</span>'


def _pct_ou_texto(valor) -> str:
    return percentual(valor) if isinstance(valor, float) else str(valor)


def _kpis(r: Resultado) -> str:
    k = r.kpis
    part = k["participacao_media"]
    itens = [
        ("Respostas", inteiro(k["total"]), f"{k['pontos']} ponto(s) de coleta"),
        ("Dias úteis com coleta", inteiro(k["dias_uteis_coleta"]),
         f"{k['dias_coleta']} dia(s) no total"),
        ("Participação média", percentual(part) if part == part and k["total"] >= r.minimo else INSUFICIENTE,
         "do público esperado, por momento"),
        ("Índice de humor", decimal(k["indice_geral"], 2, sinal=True) if k["total"] >= r.minimo else INSUFICIENTE,
         "escala de −3 a +2"),
        ("Emoções positivas", _pct_ou_texto(k["pct_positivas"]),
         f"negativas: {_pct_ou_texto(k['pct_negativas'])}" if k["total"] >= r.minimo else ""),
    ]
    return '<div class="kpis">' + "".join(
        f'<div class="kpi"><div class="rotulo">{_esc(a)}</div><div class="valor">{_esc(b)}</div>'
        f'<div class="detalhe">{_esc(c)}</div></div>'
        for a, b, c in itens
    ) + "</div>"


def gerar_html(r: Resultado, resumo: list[str], caminho: Path, info_leitura: dict,
               raiz: Path | None = None) -> Path:
    t = r.tabelas
    agora = datetime.now()
    m = r.minimo

    secoes = []
    secoes.append(f"""
<section id="resumo">
  <h2>Resumo</h2>
  <article class="cartao"><ul class="achados">{''.join(f'<li>{_esc(f)}</li>' for f in resumo)}</ul></article>
  {_kpis(r)}
  <p class="aviso">Este relatório é anônimo: não há nome, foto nem crachá. Recortes com menos de {m} respostas
  aparecem como <span class="legenda-insuf">dados insuficientes</span> e categorias com 1 a {m - 1} respostas aparecem como “&lt;{m}”, sem número nem percentual.</p>
</section>""")

    secoes.append(f"""
<section id="participacao">
  <h2>Participação</h2>
  {cartao("Participação por semana", "Acompanhe se a adesão está caindo. Percentual do público esperado em cada momento.",
          grafico_participacao_semanal(r) + detalhes("Ver tabela", tabela_html(t["participacao_semana"])))}
  {cartao("Participação por momento", "", tabela_html(t["participacao"])
          + detalhes("Por ponto de coleta", tabela_html(t["participacao_quiosque"])))}
  {cartao("Respostas por dia", "Total de respostas de todos os pontos de coleta em cada dia.",
          grafico_respostas_dia(r)
          + detalhes("Respostas por dia e momento", tabela_html(t["respostas_dia"]))
          + detalhes("Respostas por dia e ponto de coleta", tabela_html(t["respostas_dia_quiosque"])))}
  {cartao("Respostas por ponto de coleta e momento", "", tabela_html(t["respostas_quiosque"]))}
</section>""")

    secoes.append(f"""
<section id="emocoes">
  <h2>Emoções</h2>
  {cartao("Distribuição das emoções por momento", "Percentual de cada emoção entre as respostas de cada momento.",
          grafico_emocoes(r) + _nota_outras(r) + detalhes("Ver tabela", tabela_html(t["emocoes_momento"])))}
</section>""")

    secoes.append(f"""
<section id="humor">
  <h2>Índice de humor</h2>
  {cartao("Índice de humor por momento", "Média das pontuações: Feliz e Animado +2, Neutro 0, Cansado e Preocupado −1, Triste e Bravo −2, Furioso −3.",
          tabela_html(t["humor_momento"]))}
  {cartao("Humor ao longo do dia, por dia da semana", "Cada linha mostra os 4 momentos de um dia da semana. A linha preta é a média de todos os dias. Dias com poucos dados (como fins de semana) aparecem só na tabela.",
          grafico_humor_ao_longo_do_dia(r) + detalhes("Ver tabela", tabela_html(t["humor_dia_momento"])))}
  {cartao("Mapa de calor: dia da semana × momento", "Azul = humor melhor, vermelho = humor pior. O número pequeno é a quantidade de respostas.",
          grafico_mapa_calor(r) + detalhes("Ver tabelas", tabela_html(t["humor_dia_momento"]) + tabela_html(t["respostas_dia_momento"])))}
</section>""")

    secoes.append(f"""
<section id="variacoes">
  <h2>Variações do dia</h2>
  {cartao("Como o humor muda entre os momentos", "Manhã = saída p/ almoço − chegada · Almoço = volta − saída p/ almoço · Tarde = saída do dia − volta do almoço · Dia = saída do dia − chegada.",
          grafico_variacoes(r) + tabela_html(t["variacoes"]) + detalhes("Por ponto de coleta", tabela_html(t["variacoes_quiosque"])))}
</section>""")

    secoes.append(f"""
<section id="clima">
  <h2>Humor e clima</h2>
  <div class="grade-2">
  {cartao("Por condição do tempo", "", grafico_clima(r, "clima_condicao", "Condição do tempo") + detalhes("Ver tabela", tabela_html(t["clima_condicao"])), "meio")}
  {cartao("Por faixa de temperatura", "", grafico_clima(r, "clima_temperatura", "Temperatura no momento da resposta") + detalhes("Ver tabela", tabela_html(t["clima_temperatura"])), "meio")}
  </div>
  <p class="nota">O clima também muda ao longo do dia (manhãs mais frias, por exemplo). Use esta seção como indício, não como prova de causa.</p>
</section>""")

    secoes.append(f"""
<section id="motivos">
  <h2>Motivos</h2>
  {graficos_motivos(r)}
  {cartao("Principais motivos por emoção e momento", "", tabela_html(t["motivos_emocao"]) + detalhes("Tabela completa de motivos", tabela_html(t["motivos"])))}
</section>""")

    secoes.append(f"""
<section id="pergunta">
  <h2>Pergunta do dia</h2>
  {cartao("Resultados da pergunta do dia", "Feita na saída do dia. “Favorável” é “Sim”, exceto em “Sentiu-se sobrecarregado(a) hoje?”, onde favorável é “Não”.",
          grafico_pergunta_do_dia(r) + tabela_html(t["pergunta_dia"]))}
</section>""")

    ignorados = info_leitura.get("arquivos_ignorados", [])
    lista_ignorados = ""
    if ignorados:
        lista_ignorados = "<ul>" + "".join(f"<li>{_esc(Path(p).name)}: {_esc(motivo)}</li>" for p, motivo in ignorados) + "</ul>"
    avisos = "".join(f"<li>{_esc(a)}</li>" for a in info_leitura.get("avisos", []))
    secoes.append(f"""
<section id="notas">
  <h2>Como ler este relatório</h2>
  <article class="cartao">
    <ul class="achados">
      <li><b>Índice de humor</b>: média das pontuações das emoções (de −3 a +2). Acima de zero, predominam emoções positivas.</li>
      <li><b>Participação</b>: respostas ÷ (público esperado × dias úteis com coleta). Público esperado: {_esc(r.config.get('publico_esperado_por_quiosque', 40))} pessoas por ponto de coleta, por dia, em cada momento. Sábados, domingos e feriados não entram na taxa.</li>
      <li><b>Variações</b>: como a pesquisa é anônima, não é possível acompanhar a mesma pessoa. Compara-se a média de cada momento, no mesmo ponto de coleta e no mesmo dia, usando só dias em que os dois momentos têm {m} ou mais respostas.</li>
      <li><b>Anonimato</b>: recortes com menos de {m} respostas aparecem como “dados insuficientes”; categorias com 1 a {m - 1} respostas aparecem como “&lt;{m}”, sem contagem nem percentual, e ficam fora dos gráficos (ou juntas em “Outras”).</li>
      <li><b>Arquivos lidos</b>: {len(info_leitura.get('arquivos_lidos', []))} arquivo(s) CSV, {inteiro(info_leitura.get('linhas_lidas', 0))} linha(s) lidas, {inteiro(info_leitura.get('duplicadas_removidas', 0))} resposta(s) repetida(s) consolidada(s) (mesmo response_id).</li>
      {f'<li><b>Arquivos ignorados</b>: {lista_ignorados}</li>' if lista_ignorados else ''}
      {avisos}
    </ul>
  </article>
</section>""")

    navegacao = "".join(
        f'<li><a href="#{a}">{_esc(b)}</a></li>'
        for a, b in [("resumo", "Resumo"), ("participacao", "Participação"), ("emocoes", "Emoções"),
                     ("humor", "Índice de humor"), ("variacoes", "Variações do dia"), ("clima", "Clima"),
                     ("motivos", "Motivos"), ("pergunta", "Pergunta do dia"), ("notas", "Como ler")]
    )
    pagina = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relatório Termômetro Emocional</title>
<style>{CSS}</style>
<script>{get_plotlyjs()}</script>
</head>
<body>
<header class="topo"><div class="topo-interno">
  {_logo(raiz)}
  <div>
    <h1>Termômetro Emocional — CIPA Eurostec</h1>
    <p>Relatório do período de {data_br(r.inicio)} a {data_br(r.fim)} · gerado em {agora.strftime('%d/%m/%Y às %H:%M')}</p>
  </div>
</div></header>
<nav class="sumario" aria-label="Seções"><ul>{navegacao}</ul></nav>
<main>
{''.join(secoes)}
</main>
<footer>Termômetro Emocional — CIPA Eurostec. Documento de uso interno da CIPA. Dados anônimos.</footer>
<script>
  // Reajusta os gráficos ao tamanho final da página (e ao abrir "Ver tabela").
  window.addEventListener("load", function () {{ window.dispatchEvent(new Event("resize")); }});
  document.querySelectorAll("details").forEach(function (d) {{
    d.addEventListener("toggle", function () {{ window.dispatchEvent(new Event("resize")); }});
  }});
</script>
</body>
</html>
"""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(pagina, encoding="utf-8")
    return caminho
