"""Gera o relatório em HTML (abre no navegador, funciona sem internet).

O plotly.js vai embutido no próprio arquivo, então o HTML pode ser
enviado por e-mail ou aberto de um pendrive.
"""
from __future__ import annotations

import base64
import html as _html
import sys
from datetime import date, datetime
from pathlib import Path

import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

from quiosque.formato import MOMENTOS
from relatorio.analise import INSUFICIENTE, Resultado, Tabela
from relatorio.formatacao import (
    data_br, decimal, eh_numero, inteiro, nome_momento, percentual,
)

# ------------------------------------------- identidade (Eurostec System)
# Cores da moldura da página (tokens oficiais). As cores das emoções e das
# séries dos gráficos ficam em suas próprias constantes, mais abaixo.
AZUL = "#0446a4"            # Blue-brand: títulos, cabeçalho de tabela, números
AZUL_CARD = "#00aeef"       # Blue-card: marcadores "/"
VERDE = "#a7f432"           # Green: destaque
TEXTO = "#323232"           # Text
TEXTO_CATALOGO = "#575756"  # Text-catalog: notas, rodapé, eixos
BORDA = "#ebebeb"           # Border: fios e contornos
FUNDO = "#fbfbfb"           # Surface: zebrado, painéis, fundo da página
SUPERFICIE = "#ffffff"      # White: fundo dos gráficos
GRADIENTE_INICIO = "#0aa1f4"  # Gradient-start (brilho dos cards de número)
GRADIENTE_FIM = "#02358e"     # Gradient-end
GRADE = BORDA
EIXO = TEXTO_CATALOGO
MUDO = TEXTO_CATALOGO
INSUF_FUNDO = FUNDO
INSUF_MAPA = "#d6d5cf"  # mapa de calor: cinza mais escuro que o meio da escala (para não confundir com 0)
OUTRAS = "#d6d5cf"  # segmento "Outras (<5 cada)" — mais claro que o cinza do Neutro
NOTA_OMITIDAS = "Categorias com menos de 5 respostas foram omitidas do gráfico (aparecem como “<5” na tabela)."
FONTE = '"Google Sans", "Segoe UI", system-ui, -apple-system, Arial, sans-serif'
PESOS_FONTE = [  # (peso, arquivo) — só pesos com arquivo real; nada de negrito sintetizado
    (400, "GoogleSans-Regular.woff2"),
    (500, "GoogleSans-Medium.woff2"),
    (600, "GoogleSans-SemiBold.woff2"),
    (700, "GoogleSans-Bold.woff2"),
]
LOGO_AZUL = "Eurostec-logo-azul.png"

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
        hoverlabel=dict(bgcolor=SUPERFICIE, bordercolor=BORDA, font=dict(family=FONTE, color=TEXTO, size=13)),
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


def com_ponto(titulo: str) -> str:
    """Títulos (h2, h3, painéis) terminam com ponto final (regra do Eurostec System)."""
    titulo = titulo.rstrip()
    return titulo if titulo.endswith((".", "?", "!")) else titulo + "."


def cartao(titulo: str, subtitulo: str, corpo: str, largura: str = "") -> str:
    sub = f'<p class="subtitulo">{subtitulo}</p>' if subtitulo else ""
    return f'<article class="cartao {largura}"><h3>{_esc(com_ponto(titulo))}</h3>{sub}{corpo}</article>'


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
                fig.add_annotation(x=m, y=dia, text="dados<br>insuficientes", showarrow=False,
                                   font=dict(color=TEXTO, size=11))
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
  --Blue-brand: #0446a4; --Blue-card: #00aeef; --Green: #a7f432;
  --Gradient-start: #0aa1f4; --Gradient-end: #02358e;
  --Text: #323232; --Text-catalog: #575756;
  --Border: #ebebeb; --Surface: #fbfbfb; --White: #ffffff;
  --font: "Google Sans", "Segoe UI", system-ui, -apple-system, Arial, sans-serif;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; background: var(--Surface); color: var(--Text); font-family: var(--font);
  font-size: 15px; line-height: 1.5; font-weight: 400; }
b, strong { font-weight: 700; }
h1, h2, h3 { font-weight: 700; }

/* Cabeçalho (RelatorioCabecalho): logo azul acima do título; tudo derivado de T */
.cab { background: var(--White); }
.cab-in { --T: 28px; max-width: 1180px; margin: 0 auto; padding: 40px 20px 28px; }
.cab-logo { display: block; width: calc(var(--T) * 4.1); height: auto; }
.cab-t { margin: calc(var(--T) * 1) 0 0; font-size: var(--T); line-height: 1.3; font-weight: 400;
  color: var(--Blue-brand); letter-spacing: -.01em; }
.cab-t b { font-weight: 700; }
.cab-apoio { margin: 10px 0 0; color: var(--Text-catalog); font-size: 14px; line-height: 1.4; }

nav.sumario { position: sticky; top: 0; z-index: 10; background: var(--White);
  border-top: 1px solid var(--Border); border-bottom: 1px solid var(--Border); }
nav.sumario ul { max-width: 1180px; margin: 0 auto; padding: 0 8px; list-style: none; display: flex; gap: 2px; overflow-x: auto; }
nav.sumario a { display: block; padding: 11px 12px; color: var(--Blue-brand); text-decoration: none; font-weight: 500;
  white-space: nowrap; font-size: 14px; }
nav.sumario a:hover, nav.sumario a:focus { background: var(--Surface); text-decoration: underline; }

main { max-width: 1180px; margin: 0 auto; padding: 8px 20px 48px; }
section { margin-top: 40px; scroll-margin-top: 56px; }
h2 { color: var(--Blue-brand); font-size: 22px; line-height: 1.3; margin: 0 0 16px; }
h3 { margin: 0 0 4px; font-size: 16px; line-height: 1.35; color: var(--Blue-brand); }
.subtitulo { margin: 0 0 12px; color: var(--Text-catalog); font-size: 14px; }

/* Painéis: White + contorno Border, cantos 16px, sem faixa e sem sombra */
.cartao { background: var(--White); border: 1px solid var(--Border); border-radius: 16px; padding: 20px 22px; margin-bottom: 16px; }
.grade-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.grade-2 > .cartao { margin-bottom: 0; min-width: 0; }

/* Listas com marcador "/" Bold Blue-card */
.lst { list-style: none; margin: 0; padding: 0; }
.lst li { position: relative; padding-left: 18px; margin: 8px 0; line-height: 1.55; }
.lst li::before { content: "/"; position: absolute; left: 0; top: 0; font-weight: 700; color: var(--Blue-card); }
.lst .lst { margin-top: 4px; }

/* Cards de número: degradê de card, sem sombra, sem borda lateral */
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 16px; margin: 20px 0 0; }
.st { border-radius: 16px; padding: 20px 20px 18px; color: var(--White);
  background:
    radial-gradient(120% 95% at 100% 0%, rgba(10, 161, 244, .9) 0%, rgba(10, 161, 244, 0) 58%),
    linear-gradient(135deg, var(--Blue-brand) 0%, var(--Gradient-end) 100%); }
.st-n { font-size: 34px; line-height: 1.1; font-weight: 700; }
.st-n.txt { font-size: 20px; line-height: 1.25; }
.st-r { margin-top: 12px; display: flex; align-items: center; gap: 8px; font-size: 12px; line-height: 1.3;
  font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }
.st-r::before { content: ""; flex: none; width: 2px; height: 14px; background: var(--White); transform: skewX(-14.5deg); }
.st-nota { margin-top: 6px; font-size: 11px; line-height: 1.4; }

/* Destaque verde: um por página */
.dst { background: var(--Green); color: var(--Blue-brand); font-size: 13px; line-height: 19px;
  border-radius: 12px; padding: 12px 16px; margin: 16px 0 0; }
.dst b { font-weight: 700; }

/* Tabelas: cabeçalho Blue-brand, zebrado Surface, fios Border, total Bold Blue-brand */
.tabela-rolagem { overflow-x: auto; margin: 8px 0; }
table { border-collapse: separate; border-spacing: 0; width: 100%; font-size: 14px; font-variant-numeric: tabular-nums; }
th, td { padding: 8px 12px; border-bottom: 1px solid var(--Border); text-align: left; vertical-align: top; }
thead th { background: var(--Blue-brand); color: var(--White); font-weight: 600; border-bottom: 0; position: sticky; top: 0; }
thead th:first-child { border-top-left-radius: 8px; }
thead th:last-child { border-top-right-radius: 8px; }
tbody th { font-weight: 500; color: var(--Text); }
tbody tr:nth-child(even) th, tbody tr:nth-child(even) td { background: var(--Surface); }
.num { text-align: right; white-space: nowrap; }
td.insuf { color: var(--Text-catalog); text-align: center; white-space: nowrap; }
td.poucos { color: var(--Text-catalog); }
tbody tr.total th, tbody tr.total td { font-weight: 700; color: var(--Blue-brand); background: var(--White);
  border-top: 1px solid var(--Blue-brand); }
tbody tr.total td.insuf { font-weight: 400; color: var(--Text-catalog); }

.nota { color: var(--Text-catalog); font-size: 12px; line-height: 1.45; margin: 8px 0 0; }
.vazio { color: var(--Text-catalog); }
details { margin: 8px 0 0; }
summary { cursor: pointer; color: var(--Blue-brand); font-weight: 600; padding: 6px 0; }
.detalhes-corpo { padding: 4px 0 8px; }

/* Rodapé: fio Border, Text-catalog */
.rod { border-top: 1px solid var(--Border); background: var(--White); }
.rod-in { max-width: 1180px; margin: 0 auto; padding: 16px 20px; display: flex; justify-content: space-between;
  gap: 16px; flex-wrap: wrap; color: var(--Text-catalog); font-size: 11px; line-height: 1.4; }

@media (max-width: 900px) {
  .grade-2 { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 640px) {
  .cab-in { --T: 22px; padding: 28px 16px 20px; }
  main { padding: 8px 16px 32px; }
}
@media print {
  nav.sumario { display: none; }
  .cartao, .st { break-inside: avoid; }
}
"""

SCRIPT_PAGINA = """
(function () {
  // Título em dois pesos: se quebrar, a parte em negrito começa linha nova.
  function quebrarTitulo() {
    var t = document.querySelector(".cab-t");
    if (!t) return;
    var antiga = t.querySelector("br.auto");
    if (antiga) antiga.remove();
    var negrito = t.querySelector("b");
    var entrelinha = parseFloat(getComputedStyle(t).lineHeight);
    if (negrito && t.offsetHeight > entrelinha * 1.5) {
      var br = document.createElement("br");
      br.className = "auto";
      t.insertBefore(br, negrito);
    }
  }
  function reajustar() {
    quebrarTitulo();
    window.dispatchEvent(new Event("resize"));  // gráficos (plotly responsive)
  }
  var pronto = (document.fonts && document.fonts.ready) ? document.fonts.ready : Promise.resolve();
  window.addEventListener("load", function () { pronto.then(reajustar); });
  window.addEventListener("resize", quebrarTitulo);
  document.querySelectorAll("details").forEach(function (d) {
    d.addEventListener("toggle", function () { window.dispatchEvent(new Event("resize")); });
  });
})();
"""


def _raiz(raiz: Path | None) -> Path:
    if raiz:
        return Path(raiz)
    from relatorio.configuracao import raiz_projeto

    return raiz_projeto()


def localizar_fontes(raiz: Path | None = None) -> Path | None:
    """Pasta das fontes Google Sans (.woff2).

    Procura primeiro dentro do executável (sys._MEIPASS/quiosque/web/fontes)
    e depois na pasta do projeto (<raiz>/quiosque/web/fontes).
    """
    candidatos = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidatos.append(Path(meipass) / "quiosque" / "web" / "fontes")
    candidatos.append(_raiz(raiz) / "quiosque" / "web" / "fontes")
    for pasta in candidatos:
        if pasta.is_dir() and any((pasta / arquivo).is_file() for _, arquivo in PESOS_FONTE):
            return pasta
    return None


def localizar_logo(raiz: Path | None = None) -> Path | None:
    """Logo azul oficial: <raiz>/assets/ ou, no executável, sys._MEIPASS/assets/."""
    candidatos = [_raiz(raiz) / "assets" / LOGO_AZUL]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidatos.append(Path(meipass) / "assets" / LOGO_AZUL)
    for caminho in candidatos:
        if caminho.is_file() and caminho.stat().st_size > 0:
            return caminho
    return None


def _font_faces(raiz: Path | None) -> str:
    """Um @font-face por peso, com o arquivo real embutido (woff2 em base64)."""
    pasta = localizar_fontes(raiz)
    if pasta is None:
        return ""
    blocos = []
    for peso, arquivo in PESOS_FONTE:
        caminho = pasta / arquivo
        if not caminho.is_file():
            continue
        dados = base64.b64encode(caminho.read_bytes()).decode("ascii")
        blocos.append(
            '@font-face { font-family: "Google Sans"; font-style: normal; '
            f"font-weight: {peso}; font-display: block; "
            f'src: url(data:font/woff2;base64,{dados}) format("woff2"); }}'
        )
    return "\n".join(blocos)


def _logo(raiz: Path | None) -> str:
    """Logo oficial embutido. Se o arquivo não existir, o logo é omitido
    (o logo nunca é reconstruído com texto)."""
    caminho = localizar_logo(raiz)
    if caminho is None:
        return ""
    dados = base64.b64encode(caminho.read_bytes()).decode("ascii")
    return f'<img class="cab-logo" src="data:image/png;base64,{dados}" alt="Eurostec">'


def _periodo_titulo(inicio: date, fim: date) -> str:
    if inicio == fim:
        return f"relatório de {data_br(fim)}."
    if inicio.year == fim.year:
        return f"relatório de {inicio.strftime('%d/%m')} a {data_br(fim)}."
    return f"relatório de {data_br(inicio)} a {data_br(fim)}."


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
    cards = []
    for rotulo, valor, nota in itens:
        classe = "st-n" if len(valor) <= 8 else "st-n txt"
        nota_html = f'<div class="st-nota">{_esc(nota)}</div>' if nota else ""
        cards.append(f'<div class="st"><div class="{classe}">{_esc(valor)}</div>'
                     f'<div class="st-r">{_esc(rotulo)}</div>{nota_html}</div>')
    return '<div class="stats">' + "".join(cards) + "</div>"


def gerar_html(r: Resultado, resumo: list[str], caminho: Path, info_leitura: dict,
               raiz: Path | None = None) -> Path:
    t = r.tabelas
    agora = datetime.now()
    m = r.minimo

    secoes = []
    secoes.append(f"""
<section id="resumo">
  <h2>Resumo.</h2>
  <article class="cartao"><ul class="lst">{''.join(f'<li>{_esc(f)}</li>' for f in resumo)}</ul></article>
  {_kpis(r)}
  <p class="dst"><b>Relatório anônimo.</b> Não há nome, foto nem crachá. Recortes com menos de {m} respostas
  aparecem como “dados insuficientes”, e categorias com 1 a {m - 1} respostas aparecem como “&lt;{m}”, sem número nem percentual.</p>
</section>""")

    secoes.append(f"""
<section id="participacao">
  <h2>Participação.</h2>
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
  <h2>Emoções.</h2>
  {cartao("Distribuição das emoções por momento", "Percentual de cada emoção entre as respostas de cada momento.",
          grafico_emocoes(r) + _nota_outras(r) + detalhes("Ver tabela", tabela_html(t["emocoes_momento"])))}
</section>""")

    secoes.append(f"""
<section id="humor">
  <h2>Índice de humor.</h2>
  {cartao("Índice de humor por momento", "Média das pontuações: Feliz e Animado +2, Neutro 0, Cansado e Preocupado −1, Triste e Bravo −2, Furioso −3.",
          tabela_html(t["humor_momento"]))}
  {cartao("Humor ao longo do dia, por dia da semana", "Cada linha mostra os 4 momentos de um dia da semana. A linha preta é a média de todos os dias. Dias com poucos dados (como fins de semana) aparecem só na tabela.",
          grafico_humor_ao_longo_do_dia(r) + detalhes("Ver tabela", tabela_html(t["humor_dia_momento"])))}
  {cartao("Mapa de calor: dia da semana × momento", "Azul = humor melhor, vermelho = humor pior. O número pequeno é a quantidade de respostas.",
          grafico_mapa_calor(r) + detalhes("Ver tabelas", tabela_html(t["humor_dia_momento"]) + tabela_html(t["respostas_dia_momento"])))}
</section>""")

    secoes.append(f"""
<section id="variacoes">
  <h2>Variações do dia.</h2>
  {cartao("Como o humor muda entre os momentos", "Manhã = saída p/ almoço − chegada · Almoço = volta − saída p/ almoço · Tarde = saída do dia − volta do almoço · Dia = saída do dia − chegada.",
          grafico_variacoes(r) + tabela_html(t["variacoes"]) + detalhes("Por ponto de coleta", tabela_html(t["variacoes_quiosque"])))}
</section>""")

    secoes.append(f"""
<section id="clima">
  <h2>Humor e clima.</h2>
  <div class="grade-2">
  {cartao("Por condição do tempo", "", grafico_clima(r, "clima_condicao", "Condição do tempo") + detalhes("Ver tabela", tabela_html(t["clima_condicao"])), "meio")}
  {cartao("Por faixa de temperatura", "", grafico_clima(r, "clima_temperatura", "Temperatura no momento da resposta") + detalhes("Ver tabela", tabela_html(t["clima_temperatura"])), "meio")}
  </div>
  <p class="nota">O clima também muda ao longo do dia (manhãs mais frias, por exemplo). Use esta seção como indício, não como prova de causa.</p>
</section>""")

    secoes.append(f"""
<section id="motivos">
  <h2>Motivos.</h2>
  {graficos_motivos(r)}
  {cartao("Principais motivos por emoção e momento", "", tabela_html(t["motivos_emocao"]) + detalhes("Tabela completa de motivos", tabela_html(t["motivos"])))}
</section>""")

    secoes.append(f"""
<section id="pergunta">
  <h2>Pergunta do dia.</h2>
  {cartao("Resultados da pergunta do dia", "Feita na saída do dia. “Favorável” é “Sim”, exceto em “Sentiu-se sobrecarregado(a) hoje?”, onde favorável é “Não”.",
          grafico_pergunta_do_dia(r) + tabela_html(t["pergunta_dia"]))}
</section>""")

    ignorados = info_leitura.get("arquivos_ignorados", [])
    lista_ignorados = ""
    if ignorados:
        lista_ignorados = '<ul class="lst">' + "".join(
            f"<li>{_esc(Path(p).name)}: {_esc(motivo)}</li>" for p, motivo in ignorados) + "</ul>"
    avisos = "".join(f"<li>{_esc(a)}</li>" for a in info_leitura.get("avisos", []))
    secoes.append(f"""
<section id="notas">
  <h2>Como ler este relatório.</h2>
  <article class="cartao">
    <ul class="lst">
      <li><b>Índice de humor.</b> Média das pontuações das emoções (de −3 a +2). Acima de zero, predominam emoções positivas.</li>
      <li><b>Participação.</b> Respostas ÷ (público esperado × dias úteis com coleta). Público esperado: {_esc(r.config.get('publico_esperado_por_quiosque', 40))} pessoas por ponto de coleta, por dia, em cada momento. Sábados, domingos e feriados não entram na taxa.</li>
      <li><b>Variações.</b> Como a pesquisa é anônima, não é possível acompanhar a mesma pessoa. Compara-se a média de cada momento, no mesmo ponto de coleta e no mesmo dia, usando só dias em que os dois momentos têm {m} ou mais respostas.</li>
      <li><b>Anonimato.</b> Recortes com menos de {m} respostas aparecem como “dados insuficientes”; categorias com 1 a {m - 1} respostas aparecem como “&lt;{m}”, sem contagem nem percentual, e ficam fora dos gráficos (ou juntas em “Outras”).</li>
      <li><b>Arquivos lidos.</b> {len(info_leitura.get('arquivos_lidos', []))} arquivo(s) CSV, {inteiro(info_leitura.get('linhas_lidas', 0))} linha(s) lidas, {inteiro(info_leitura.get('duplicadas_removidas', 0))} resposta(s) repetida(s) consolidada(s) (mesmo response_id).</li>
      {f'<li><b>Arquivos ignorados.</b> {lista_ignorados}</li>' if lista_ignorados else ''}
      {avisos}
      <li><b>Uso interno.</b> Documento de uso interno da CIPA. Os dados são anônimos.</li>
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
<html lang="pt-BR" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relatório Termômetro Emocional</title>
<style>
{_font_faces(raiz)}
{CSS}</style>
<script>{get_plotlyjs()}</script>
</head>
<body>
<header class="cab"><div class="cab-in">
  {_logo(raiz)}
  <h1 class="cab-t">Termômetro Emocional: <b>{_esc(_periodo_titulo(r.inicio, r.fim))}</b></h1>
  <p class="cab-apoio">CIPA Eurostec · gerado em {agora.strftime('%d/%m/%Y às %H:%M')}</p>
</div></header>
<nav class="sumario" aria-label="Seções"><ul>{navegacao}</ul></nav>
<main>
{''.join(secoes)}
</main>
<footer class="rod"><div class="rod-in">
  <span>Eurostec | CIPA · Termômetro Emocional</span>
  <span>Alta performance nos define.</span>
</div></footer>
<script>{SCRIPT_PAGINA}</script>
</body>
</html>
"""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(pagina, encoding="utf-8")
    return caminho
