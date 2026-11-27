"""Gera o relatório em Excel (.xlsx): dados consolidados + uma aba por tabela."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from quiosque.formato import COLUNAS
from relatorio.analise import INSUFICIENTE, Resultado, Tabela
from relatorio.formatacao import data_br, decimal, eh_numero, inteiro, percentual

# Eurostec System para documentos Office: fonte Segoe UI, cabeçalho Blue-brand
# com texto branco em negrito, zebrado Surface, fios Border, total Bold Blue-brand.
FONTE_OFFICE = "Segoe UI"
AZUL = "0446A4"        # Blue-brand
AZUL_CARD = "00AEEF"   # Blue-card (marcador "/")
TEXTO = "323232"       # Text
MUDO = "575756"        # Text-catalog
BORDA = "EBEBEB"       # Border
ZEBRA = "FBFBFB"       # Surface

FONTE_PADRAO = Font(name=FONTE_OFFICE, size=10, color=TEXTO)
FONTE_TITULO = Font(name=FONTE_OFFICE, bold=True, size=14, color=AZUL)
FONTE_SUBTITULO = Font(name=FONTE_OFFICE, bold=True, size=12, color=AZUL)
FONTE_CABECALHO = Font(name=FONTE_OFFICE, bold=True, size=10, color="FFFFFF")
PREENCHIMENTO_CABECALHO = PatternFill("solid", fgColor=AZUL)
PREENCHIMENTO_ZEBRA = PatternFill("solid", fgColor=ZEBRA)
FONTE_NOTA = Font(name=FONTE_OFFICE, size=9, color=MUDO)
FONTE_INSUF = Font(name=FONTE_OFFICE, size=10, italic=True, color=MUDO)
FONTE_TOTAL = Font(name=FONTE_OFFICE, size=10, bold=True, color=AZUL)
FIO = Side(style="thin", color=BORDA)
FIO_TOTAL = Side(style="thin", color=AZUL)
BORDA_LINHA = Border(bottom=FIO)
BORDA_TOTAL = Border(top=FIO_TOTAL, bottom=FIO)


def _com_ponto(titulo: str) -> str:
    titulo = titulo.rstrip()
    return titulo if titulo.endswith((".", "?", "!")) else titulo + "."


def _item_lista(texto: str) -> CellRichText:
    """Item de lista com marcador "/" Bold Blue-card (nunca "•")."""
    return CellRichText(
        TextBlock(InlineFont(rFont=FONTE_OFFICE, b=True, color=AZUL_CARD, sz=10), "/ "),
        TextBlock(InlineFont(rFont=FONTE_OFFICE, color=TEXTO, sz=10), texto),
    )

FORMATOS_NUMERO = {
    "int": "#,##0",
    "dec1": "0.0",
    "dec": "0.00",
    "sinal": "+0.00;-0.00;0.00",
    "pct": "0%",
}

ABAS = [
    ("Respostas por ponto", "respostas_quiosque"),
    ("Respostas por dia", "respostas_dia"),
    ("Respostas dia x ponto", "respostas_dia_quiosque"),
    ("Respostas detalhadas", "respostas_detalhadas"),
    ("Participação", "participacao"),
    ("Participação por ponto", "participacao_quiosque"),
    ("Participação semanal", "participacao_semana"),
    ("Emoções por momento", "emocoes_momento"),
    ("Humor por momento", "humor_momento"),
    ("Humor dia x momento", "humor_dia_momento"),
    ("Respostas dia x momento", "respostas_dia_momento"),
    ("Variações do dia", "variacoes"),
    ("Variações por ponto", "variacoes_quiosque"),
    ("Clima - condição", "clima_condicao"),
    ("Clima - temperatura", "clima_temperatura"),
    ("Setores", "humor_setor"),
    ("Motivos", "motivos"),
    ("Motivos por emoção", "motivos_emocao"),
    ("Pergunta do dia", "pergunta_dia"),
]


def _texto_exibido(valor, formato: str) -> str:
    if isinstance(valor, str):
        return valor
    if not eh_numero(valor):
        return ""
    if formato == "int":
        return inteiro(valor)
    if formato in ("dec", "sinal"):
        return decimal(valor, 2, sinal=formato == "sinal")
    if formato == "dec1":
        return decimal(valor, 1)
    if formato == "pct":
        return percentual(valor)
    return str(valor)


def _ajustar_larguras(aba, larguras: dict[int, int], maximo: int = 60) -> None:
    for coluna, largura in larguras.items():
        aba.column_dimensions[get_column_letter(coluna)].width = max(8, min(maximo, largura + 2))


def _escrever_tabela(aba, tabela: Tabela) -> None:
    aba["A1"] = _com_ponto(tabela.titulo)
    aba["A1"].font = FONTE_TITULO
    if tabela.nota:
        aba["A2"] = tabela.nota
        aba["A2"].font = FONTE_NOTA
    linha_cab = 4
    df = tabela.dados
    larguras: dict[int, int] = {}
    for j, coluna in enumerate(df.columns, start=1):
        celula = aba.cell(row=linha_cab, column=j, value=str(coluna))
        celula.font = FONTE_CABECALHO
        celula.fill = PREENCHIMENTO_CABECALHO
        celula.alignment = Alignment(wrap_text=True, vertical="center")
        larguras[j] = min(len(str(coluna)), 28)
    for i, (_, linha) in enumerate(df.iterrows(), start=linha_cab + 1):
        total = str(linha.iloc[0]).startswith(("Todos", "Média dos"))
        zebra = (i - linha_cab) % 2 == 0 and not total
        for j, coluna in enumerate(df.columns, start=1):
            valor = linha[coluna]
            formato = tabela.formatos.get(coluna, "texto")
            if eh_numero(valor):
                valor = float(valor) if formato not in ("int",) else int(round(float(valor)))
            elif not isinstance(valor, str):
                valor = "" if valor is None else str(valor)
            celula = aba.cell(row=i, column=j, value=valor)
            celula.font = FONTE_TOTAL if total else FONTE_PADRAO
            celula.border = BORDA_TOTAL if total else BORDA_LINHA
            if zebra:
                celula.fill = PREENCHIMENTO_ZEBRA
            if isinstance(valor, (int, float)) and formato in FORMATOS_NUMERO:
                celula.number_format = FORMATOS_NUMERO[formato]
                celula.alignment = Alignment(horizontal="right", vertical="top")
            if valor == INSUFICIENTE:
                celula.font = FONTE_INSUF
                celula.alignment = Alignment(horizontal="center", vertical="top")
            elif isinstance(valor, str) and valor.startswith("<"):
                celula.font = Font(name=FONTE_OFFICE, size=10, color=MUDO, bold=total)
                celula.alignment = Alignment(horizontal="right", vertical="top")
            larguras[j] = max(larguras.get(j, 8), len(_texto_exibido(valor, formato)))
    _ajustar_larguras(aba, larguras, maximo=90)
    aba.row_dimensions[linha_cab].height = 32
    aba.freeze_panes = aba.cell(row=linha_cab + 1, column=2)


def _escrever_dados(aba, df) -> None:
    for j, coluna in enumerate(COLUNAS, start=1):
        celula = aba.cell(row=1, column=j, value=coluna)
        celula.font = FONTE_CABECALHO
        celula.fill = PREENCHIMENTO_CABECALHO
    inteiros = {"pontuacao", "codigo_tempo"}
    decimais = {"temperatura_c", "sensacao_termica_c", "precipitacao_mm"}
    for i, registro in enumerate(df[COLUNAS].itertuples(index=False), start=2):
        for j, (coluna, valor) in enumerate(zip(COLUNAS, registro), start=1):
            if coluna in inteiros or coluna in decimais:
                if eh_numero(valor):
                    valor = int(valor) if coluna in inteiros else float(valor)
                else:
                    valor = None
            elif coluna == "data" and isinstance(valor, date):
                pass
            elif valor is None or (isinstance(valor, float) and valor != valor):
                valor = None
            else:
                valor = str(valor)
            celula = aba.cell(row=i, column=j, value=valor)
            celula.font = FONTE_PADRAO
            if i % 2 == 1:
                celula.fill = PREENCHIMENTO_ZEBRA
            if coluna == "data" and isinstance(valor, date):
                celula.number_format = "dd/mm/yyyy"
            elif coluna in decimais and valor is not None:
                celula.number_format = "0.0"
    larguras = {
        "response_id": 38, "timestamp": 26, "kiosk_local": 24, "motivo": 30, "pergunta_do_dia": 46,
        "resposta_pergunta_do_dia": 14,
    }
    for j, coluna in enumerate(COLUNAS, start=1):
        aba.column_dimensions[get_column_letter(j)].width = larguras.get(coluna, max(11, len(coluna) + 2))
    aba.freeze_panes = "B2"
    if len(df):
        aba.auto_filter.ref = f"A1:{get_column_letter(len(COLUNAS))}{len(df) + 1}"


def _escrever_resumo(aba, r: Resultado, resumo: list[str], info_leitura: dict) -> None:
    aba["A1"] = CellRichText(
        TextBlock(InlineFont(rFont=FONTE_OFFICE, sz=16, color=AZUL), "Termômetro Emocional: "),
        TextBlock(InlineFont(rFont=FONTE_OFFICE, sz=16, b=True, color=AZUL),
                  f"relatório de {data_br(r.inicio)} a {data_br(r.fim)}."),
    )
    aba["A2"] = f"CIPA Eurostec · gerado em {datetime.now().strftime('%d/%m/%Y às %H:%M')}"
    aba["A2"].font = Font(name=FONTE_OFFICE, size=10, color=MUDO)
    aba["A3"] = CellRichText(
        TextBlock(InlineFont(rFont=FONTE_OFFICE, sz=10, b=True, color=AZUL), "Uso restrito à CIPA. "),
        TextBlock(InlineFont(rFont=FONTE_OFFICE, sz=10, color=AZUL),
                  "A aba “Dados” traz as respostas individuais (anônimas, sem nome, foto ou crachá) "
                  "e não deve ser divulgada."),
    )
    aba["A3"].fill = PatternFill("solid", fgColor="A7F432")  # destaque verde
    aba["A3"].alignment = Alignment(wrap_text=True, vertical="center")
    aba.merge_cells("A3:D3")
    aba.row_dimensions[3].height = 32

    k = r.kpis
    linha = 5
    aba.cell(row=linha, column=1, value="Indicadores.").font = FONTE_SUBTITULO
    indicadores = [
        ("Respostas", k["total"], "#,##0"),
        ("Pontos de coleta", k["pontos"], "0"),
        ("Dias úteis com coleta", k["dias_uteis_coleta"], "0"),
        ("Participação média (% do público esperado)", k["participacao_media"], "0%"),
        ("Índice de humor geral (−3 a +2)", k["indice_geral"], "+0.00;-0.00;0.00"),
        ("Emoções positivas", k["pct_positivas"], "0%"),
        ("Emoções negativas", k["pct_negativas"], "0%"),
    ]
    for rotulo, valor, formato in indicadores:
        linha += 1
        aba.cell(row=linha, column=1, value=rotulo).font = FONTE_PADRAO
        if isinstance(valor, str):  # '<5' ou 'dados insuficientes' (regra de anonimato)
            celula = aba.cell(row=linha, column=2, value=valor)
            celula.font = FONTE_INSUF
            celula.alignment = Alignment(horizontal="right")
        elif k["total"] < r.minimo and formato != "#,##0":
            celula = aba.cell(row=linha, column=2, value=INSUFICIENTE)
            celula.font = FONTE_INSUF
        else:
            celula = aba.cell(row=linha, column=2, value=valor)
            celula.number_format = formato
            celula.font = Font(name=FONTE_OFFICE, size=10, bold=True, color=AZUL)
            celula.alignment = Alignment(horizontal="right")

    linha += 2
    aba.cell(row=linha, column=1, value="Principais achados.").font = FONTE_SUBTITULO
    for frase in resumo:
        linha += 1
        celula = aba.cell(row=linha, column=1, value=_item_lista(frase))
        celula.alignment = Alignment(wrap_text=True, vertical="top")
        aba.merge_cells(start_row=linha, start_column=1, end_row=linha, end_column=4)
        aba.row_dimensions[linha].height = 15 * max(1, len(frase) // 110 + 1)

    linha += 2
    aba.cell(row=linha, column=1, value="Sobre os dados.").font = FONTE_SUBTITULO
    notas = [
        f"Arquivos CSV lidos: {len(info_leitura.get('arquivos_lidos', []))}; linhas lidas: "
        f"{info_leitura.get('linhas_lidas', 0)}; respostas repetidas consolidadas (mesmo response_id): "
        f"{info_leitura.get('duplicadas_removidas', 0)}.",
        f"Regra de anonimato: recortes com menos de {r.minimo} respostas aparecem como “{INSUFICIENTE}”; "
        f"categorias com 1 a {r.minimo - 1} respostas aparecem como “<{r.minimo}”, sem contagem nem percentual.",
        "Índice de humor = média das pontuações (Feliz e Animado +2, Neutro 0, Cansado e Preocupado −1, "
        "Triste e Bravo −2, Furioso −3).",
    ] + list(info_leitura.get("avisos", []))
    for nota in notas:
        linha += 1
        celula = aba.cell(row=linha, column=1, value=_item_lista(nota))
        celula.alignment = Alignment(wrap_text=True, vertical="top")
        aba.merge_cells(start_row=linha, start_column=1, end_row=linha, end_column=4)
        aba.row_dimensions[linha].height = 15 * max(1, len(nota) // 110 + 1)

    linha += 2
    aba.cell(row=linha, column=1, value="Abas deste arquivo.").font = FONTE_SUBTITULO
    linha += 1
    aba.cell(row=linha, column=1, value=_item_lista("Dados — todas as respostas consolidadas"))
    for nome, chave in ABAS:
        linha += 1
        aba.cell(row=linha, column=1, value=_item_lista(f"{nome} — {r.tabelas[chave].titulo}"))

    aba.column_dimensions["A"].width = 60
    aba.column_dimensions["B"].width = 16
    aba.column_dimensions["C"].width = 30
    aba.column_dimensions["D"].width = 30


def gerar_excel(r: Resultado, resumo: list[str], caminho: Path, info_leitura: dict) -> Path:
    livro = Workbook()
    aba_resumo = livro.active
    aba_resumo.title = "Resumo"
    _escrever_resumo(aba_resumo, r, resumo, info_leitura)
    _escrever_dados(livro.create_sheet("Dados"), r.df)
    for nome, chave in ABAS:
        _escrever_tabela(livro.create_sheet(nome), r.tabelas[chave])

    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    try:
        livro.save(caminho)
    except PermissionError:
        # O arquivo provavelmente está aberto no Excel: salva com outro nome.
        alternativo = caminho.with_name(f"{caminho.stem}_{datetime.now().strftime('%H%M%S')}{caminho.suffix}")
        livro.save(alternativo)
        return alternativo
    return caminho
