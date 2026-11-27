"""Testes da seção "Humor por setor" do relatório e do gerador de dados fictícios.

Cobrem: média por ponto de coleta × setor, regra de anonimato, taxa de
informação, setor vazio fora da média, total por setor, CSV antigo sem as
colunas novas, frase do resumo e as saídas HTML e Excel.
"""
from __future__ import annotations

import csv
import re
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "ferramentas"))

try:
    import openpyxl  # noqa: F401
    import pandas  # noqa: F401
    import plotly  # noqa: F401

    TEM_BIBLIOTECAS = True
except ImportError:  # pragma: no cover
    TEM_BIBLIOTECAS = False

MOTIVO_SKIP = "pandas/openpyxl/plotly não instalados (rode instalar.bat, opção do PC da CIPA)"
DIA = date(2026, 11, 16)  # segunda-feira
FIM = date(2026, 11, 20)
MENOS = "−"  # sinal de menos tipográfico, como o relatório escreve


def ponto(kiosk: str) -> str:
    return f"{kiosk} · Local {kiosk}"


def lote(kiosk: str, setor: str, emocoes: list[str], perguntado: str = "sim",
         momento: str = "chegada", dia: date = DIA) -> list[dict]:
    from auxiliar_relatorio import linha

    return [linha(momento, e, dia, kiosk=kiosk, setor=setor, setor_perguntado=perguntado)
            for e in emocoes]


def df_de(linhas: list[dict]):
    from auxiliar_relatorio import carregar, gravar

    with tempfile.TemporaryDirectory() as tmp:
        gravar(Path(tmp), linhas)
        return carregar(Path(tmp))


def config():
    from relatorio.configuracao import carregar_config

    return carregar_config(RAIZ, RAIZ / "nao_existe.json")  # sem arquivo: valores padrão


def tabela_setor(linhas: list[dict]):
    from relatorio.analise import analisar

    return analisar(df_de(linhas), config()).tabelas["humor_setor"].dados


def linha_setor(tab, ponto_: str, setor: str):
    sel = tab[(tab["Ponto de coleta"] == ponto_) & (tab["Setor"] == setor)]
    if len(sel) != 1:
        raise AssertionError(f"linha {ponto_!r} / {setor!r} ausente ou repetida:\n{tab}")
    return sel.iloc[0]


def gravar_csv_antigo(pasta: Path, linhas: list[dict]) -> None:
    """Grava no formato de antes da tela de setor (sem as colunas setor e setor_perguntado)."""
    from quiosque.formato import CODIFICACAO, COLUNAS, SEPARADOR, linha_para_texto, nome_arquivo_dia

    colunas = [c for c in COLUNAS if c not in ("setor", "setor_perguntado")]
    grupos: dict[tuple[str, str], list[dict]] = {}
    for l in linhas:
        grupos.setdefault((l["kiosk_id"], l["data"]), []).append(l)
    for (kiosk, data), grupo in grupos.items():
        with open(pasta / nome_arquivo_dia(kiosk, data), "w", encoding=CODIFICACAO, newline="") as arq:
            escritor = csv.DictWriter(arq, fieldnames=colunas, delimiter=SEPARADOR,
                                      lineterminator="\r\n", extrasaction="ignore")
            escritor.writeheader()
            for l in grupo:
                escritor.writerow(linha_para_texto(l))


@unittest.skipUnless(TEM_BIBLIOTECAS, MOTIVO_SKIP)
class TestMediaPorQuiosqueESetor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        linhas = (lote("Q02", "Produção", ["Feliz"] * 4 + ["Neutro"] * 2)
                  + lote("Q02", "Qualidade", ["Bravo"] * 5)
                  + lote("Q01", "Comercial", ["Neutro"] * 5))
        cls.tab = tabela_setor(linhas)

    def test_media_e_percentuais_por_quiosque_e_setor(self):
        producao = linha_setor(self.tab, ponto("Q02"), "Produção")
        self.assertEqual(producao["Respostas"], 6)
        self.assertAlmostEqual(producao["Índice de humor"], 4 / 3, places=6)
        self.assertEqual(producao["% positivas"], "<5")  # 4 positivas: categoria pequena, sem percentual
        self.assertEqual(producao["% negativas"], 0.0)  # zero negativas aparece como 0%

        qualidade = linha_setor(self.tab, ponto("Q02"), "Qualidade")
        self.assertEqual(qualidade["Respostas"], 5)
        self.assertEqual(qualidade["Índice de humor"], -2.0)
        self.assertEqual(qualidade["% negativas"], 1.0)

        comercial = linha_setor(self.tab, ponto("Q01"), "Comercial")
        self.assertEqual(comercial["Índice de humor"], 0.0)

    def test_setor_de_outro_quiosque_nao_mistura_grupos(self):
        self.assertEqual(len(self.tab), 3)
        self.assertEqual(set(self.tab["Ponto de coleta"]), {ponto("Q01"), ponto("Q02")})


@unittest.skipUnless(TEM_BIBLIOTECAS, MOTIVO_SKIP)
class TestRegraDeAnonimato(unittest.TestCase):
    def test_grupo_com_4_respostas_e_dados_insuficientes(self):
        from relatorio.analise import INSUFICIENTE, analisar

        df = df_de(lote("Q01", "Assistência técnica", ["Feliz"] * 4))
        r = analisar(df, config())
        l = linha_setor(r.tabelas["humor_setor"].dados, ponto("Q01"), "Assistência técnica")
        self.assertEqual(l["Respostas"], "<5")
        self.assertEqual(l["Índice de humor"], INSUFICIENTE)
        self.assertEqual(l["% positivas"], INSUFICIENTE)
        self.assertEqual(l["% negativas"], INSUFICIENTE)
        self.assertEqual(r.graficos["humor_setor"]["valores"], [None])  # sem barra no gráfico

    def test_grupo_com_5_respostas_aparece(self):
        tab = tabela_setor(lote("Q01", "Comercial", ["Feliz"] * 5))
        l = linha_setor(tab, ponto("Q01"), "Comercial")
        self.assertEqual(l["Respostas"], 5)
        self.assertEqual(l["Índice de humor"], 2.0)

    def test_categoria_com_1_a_4_respostas_vira_menor_que_5(self):
        tab = tabela_setor(lote("Q01", "Comercial", ["Feliz"] * 5 + ["Triste"]))  # n = 6, 1 negativa
        l = linha_setor(tab, ponto("Q01"), "Comercial")
        self.assertEqual(l["% negativas"], "<5")  # sem percentual
        self.assertAlmostEqual(l["% positivas"], 5 / 6, places=6)


@unittest.skipUnless(TEM_BIBLIOTECAS, MOTIVO_SKIP)
class TestTaxaDeInformacao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        linhas = (lote("Q04", "Logística", ["Feliz"] * 8)            # 8 informaram
                  + lote("Q04", "", ["Neutro"] * 2)                  # 2 pularam
                  + lote("Q05", "Vendas", ["Feliz"] * 3)             # 3 informaram
                  + lote("Q05", "", ["Neutro"] * 7)                  # 7 pularam
                  + lote("Q06", "Compras", ["Feliz"] * 3)            # só 3 pessoas perguntadas
                  + lote("Q07", "", ["Neutro"] * 6, perguntado="não"))  # quiosque sem tela de setor
        cls.tab = tabela_setor(linhas)

    def test_taxa_com_percentual_quando_grupo_valido(self):
        self.assertAlmostEqual(linha_setor(self.tab, ponto("Q04"), "Logística")["Taxa de informação"], 0.8)

    def test_taxa_com_menos_de_5_informaram(self):
        self.assertEqual(linha_setor(self.tab, ponto("Q05"), "Vendas")["Taxa de informação"], "<5")

    def test_taxa_com_menos_de_5_perguntadas(self):
        from relatorio.analise import INSUFICIENTE

        self.assertEqual(linha_setor(self.tab, ponto("Q06"), "Compras")["Taxa de informação"], INSUFICIENTE)

    def test_quiosque_sem_tela_de_setor_fica_fora(self):
        self.assertNotIn(ponto("Q07"), set(self.tab["Ponto de coleta"]))


@unittest.skipUnless(TEM_BIBLIOTECAS, MOTIVO_SKIP)
class TestSetorVazioESetorCompartilhado(unittest.TestCase):
    def test_setor_vazio_nao_entra_na_media(self):
        # 5 Triste com setor + 3 Feliz sem setor (pularam): a média é a dos 5.
        linhas = lote("Q02", "Produção", ["Triste"] * 5) + lote("Q02", "", ["Feliz"] * 3)
        tab = tabela_setor(linhas)
        l = linha_setor(tab, ponto("Q02"), "Produção")
        self.assertEqual(l["Respostas"], 5)
        self.assertEqual(l["Índice de humor"], -2.0)
        self.assertAlmostEqual(linha_setor(tab, ponto("Q02"), "Produção")["Taxa de informação"], 5 / 8)

    def test_total_so_para_setor_que_existe_em_dois_pontos(self):
        linhas = (lote("Q04", "Logística", ["Feliz"] * 5)
                  + lote("Q08", "Logística", ["Neutro"] * 5)
                  + lote("Q04", "Vendas", ["Feliz"] * 5))
        tab = tabela_setor(linhas)
        total = linha_setor(tab, "Todos os pontos", "Logística")
        self.assertEqual(total["Respostas"], 10)
        self.assertEqual(total["Índice de humor"], 1.0)
        self.assertEqual(len(tab[tab["Ponto de coleta"] == "Todos os pontos"]), 1)  # Vendas não tem total

    def test_sem_setor_compartilhado_nao_ha_total(self):
        tab = tabela_setor(lote("Q01", "Comercial", ["Feliz"] * 5) + lote("Q02", "Produção", ["Feliz"] * 5))
        self.assertNotIn("Todos os pontos", set(tab["Ponto de coleta"]))


@unittest.skipUnless(TEM_BIBLIOTECAS, MOTIVO_SKIP)
class TestCsvAntigoSemColunasDeSetor(unittest.TestCase):
    def test_csv_antigo_nao_quebra_e_nao_mostra_setor(self):
        from relatorio.analise import analisar
        from relatorio.leitura import carregar_pasta
        from relatorio.resumo import gerar_resumo

        linhas = lote("Q01", "", ["Feliz"] * 6) + lote("Q02", "", ["Triste"] * 6)
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            gravar_csv_antigo(pasta, linhas)
            cabecalho = next(pasta.glob("*.csv")).read_text(encoding="utf-8-sig").splitlines()[0]
            self.assertNotIn("setor", cabecalho)
            df = carregar_pasta(pasta).dados
        self.assertTrue((df["setor"] == "").all())
        r = analisar(df, config())
        self.assertTrue(r.tabelas["humor_setor"].dados.empty)
        self.assertFalse(r.graficos["humor_setor"]["tem_setor"])
        self.assertFalse(any("Entre os setores" in f for f in gerar_resumo(r)))

    def test_df_sem_as_colunas_de_setor(self):
        from relatorio.analise import analisar

        df = df_de(lote("Q01", "Comercial", ["Feliz"] * 5)).drop(columns=["setor", "setor_perguntado"])
        r = analisar(df, config())
        self.assertTrue(r.tabelas["humor_setor"].dados.empty)


@unittest.skipUnless(TEM_BIBLIOTECAS, MOTIVO_SKIP)
class TestFraseDoResumo(unittest.TestCase):
    def frases(self, linhas: list[dict]) -> str:
        from relatorio.analise import analisar
        from relatorio.resumo import gerar_resumo

        return " ".join(gerar_resumo(analisar(df_de(linhas), config())))

    def test_maior_e_menor_setor_so_entre_grupos_com_5_ou_mais(self):
        linhas = (lote("Q02", "Segurança", ["Feliz"] * 3 + ["Neutro"] * 2)  # média +1,20, n = 5
                  + lote("Q02", "Produção", ["Feliz"] * 4)                  # média +2,00, n = 4: fica de fora
                  + lote("Q01", "Administrativo", ["Triste"] * 5)           # média -2,00, n = 5
                  + lote("Q01", "Comercial", ["Neutro"] * 5))               # média 0,00, n = 5
        texto = self.frases(linhas)
        self.assertIn("melhor em Segurança (Q02), com índice +1,20", texto)
        self.assertIn(f"pior em Administrativo (Q01), com índice {MENOS}2,00", texto)
        self.assertNotIn("Produção", texto)

    def test_um_so_grupo_valido_nao_gera_frase_de_setor(self):
        texto = self.frases(lote("Q01", "Comercial", ["Neutro"] * 5) + lote("Q02", "Produção", ["Feliz"] * 4))
        self.assertNotIn("Entre os setores", texto)

    def test_sem_grupo_valido_nao_fala_de_setor(self):
        texto = self.frases(lote("Q01", "Assistência técnica", ["Feliz"] * 4))
        self.assertNotIn("Entre os setores", texto)
        self.assertNotIn("setor", texto.lower())


@unittest.skipUnless(TEM_BIBLIOTECAS, MOTIVO_SKIP)
class TestSaidasHtmlEXlsx(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import gerar_dados_ficticios as g
        from relatorio.analise import analisar
        from relatorio.excel import gerar_excel
        from relatorio.html import gerar_html
        from relatorio.leitura import carregar_pasta, filtrar_periodo
        from relatorio.resumo import gerar_resumo

        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        g.gravar_quiosques(g.gerar(FIM, semente=11), base / "entrada")
        df = carregar_pasta(base / "entrada").dados
        info = {"arquivos_lidos": [], "linhas_lidas": 0, "duplicadas_removidas": 0, "avisos": []}
        cls.r = analisar(df, config())
        cls.html = gerar_html(cls.r, gerar_resumo(cls.r), base / "r.html", info, RAIZ).read_text(encoding="utf-8")
        cls.xlsx = gerar_excel(cls.r, gerar_resumo(cls.r), base / "r.xlsx", info)
        # Fim de semana: poucos setores têm 5 ou mais respostas, então vários grupos ficam em "dados insuficientes".
        fds = filtrar_periodo(df, date(2026, 10, 31), date(2026, 11, 1))
        cls.r_fds = analisar(fds, config())
        cls.html_fds = gerar_html(cls.r_fds, gerar_resumo(cls.r_fds), base / "fds.html", info, RAIZ).read_text(
            encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def secao(self, html: str) -> str:
        achado = re.search(r'<section id="setores">(.*?)</section>', html, flags=re.S)
        self.assertIsNotNone(achado, "seção de setores ausente")
        return achado.group(1)

    def test_html_tem_secao_ancora_e_anonimato(self):
        self.assertIn('href="#setores"', self.html)
        secao = self.secao(self.html)
        self.assertIn("Humor por setor.", secao)
        self.assertIn("Índice de humor por setor.", secao)
        self.assertIn("Taxa de informação", secao)
        self.assertIn("Recortes com menos de 5 respostas aparecem como “dados insuficientes”", secao)
        self.assertIn("Plotly.newPlot", secao)  # gráfico de barras
        self.assertNotIn("Nenhum setor informado neste período.", secao)

    def test_html_mostra_dados_insuficientes_no_fim_de_semana(self):
        from relatorio.analise import INSUFICIENTE

        secao = self.secao(self.html_fds)
        self.assertIn("dados insuficientes", secao)
        self.assertIn("&lt;5", secao)
        tab = self.r_fds.tabelas["humor_setor"].dados
        pequenos = tab[tab["Respostas"] == "<5"]  # grupo com 1 a 4 respostas
        self.assertGreaterEqual(len(pequenos), 1, "o fim de semana precisa ter pelo menos um grupo pequeno")
        self.assertTrue((pequenos["Índice de humor"] == INSUFICIENTE).all(), "grupo pequeno não mostra média")
        self.assertTrue((pequenos["% positivas"] == INSUFICIENTE).all(), "grupo pequeno não mostra percentual")

    def test_xlsx_tem_aba_setores_com_a_regra(self):
        from openpyxl import load_workbook

        livro = load_workbook(self.xlsx)
        self.assertIn("Setores", livro.sheetnames)
        aba = livro["Setores"]
        self.assertTrue(str(aba["A1"].value).startswith("Humor por setor"))
        cabecalho = [c.value for c in aba[4]]
        self.assertEqual(cabecalho, list(self.r.tabelas["humor_setor"].dados.columns))
        self.assertEqual(aba.cell(row=4, column=1).fill.fgColor.rgb[-6:], "0446A4")  # cabeçalho Blue-brand
        textos = [str(c.value) for linha in aba.iter_rows(min_row=5) for c in linha if c.value is not None]
        self.assertTrue(any("Q01" in t for t in textos))
        livro.close()

    def test_xlsx_fim_de_semana_nao_mostra_numero_pequeno(self):
        from openpyxl import load_workbook

        from relatorio.excel import gerar_excel
        from relatorio.resumo import gerar_resumo

        caminho = Path(self.tmp.name) / "fds.xlsx"
        info = {"arquivos_lidos": [], "linhas_lidas": 0, "duplicadas_removidas": 0, "avisos": []}
        gerar_excel(self.r_fds, gerar_resumo(self.r_fds), caminho, info)
        livro = load_workbook(caminho)
        valores = [c.value for linha in livro["Setores"].iter_rows(min_row=5) for c in linha]
        self.assertIn("<5", valores)
        self.assertIn("dados insuficientes", valores)
        self.assertFalse(any(isinstance(v, int) and 1 <= v <= 4 for v in valores))  # 1 a 4 nunca aparece
        livro.close()


@unittest.skipUnless(TEM_BIBLIOTECAS, MOTIVO_SKIP)
class TestSemNenhumSetor(unittest.TestCase):
    def test_secao_diz_nenhum_setor_informado(self):
        from relatorio.analise import analisar
        from relatorio.html import gerar_html
        from relatorio.leitura import carregar_pasta
        from relatorio.resumo import gerar_resumo

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            gravar_csv_antigo(base, lote("Q01", "", ["Feliz"] * 6))
            r = analisar(carregar_pasta(base).dados, config())
            info = {"arquivos_lidos": [], "linhas_lidas": 0, "duplicadas_removidas": 0, "avisos": []}
            html = gerar_html(r, gerar_resumo(r), base / "r.html", info, RAIZ).read_text(encoding="utf-8")
        achado = re.search(r'<section id="setores">(.*?)</section>', html, flags=re.S)
        self.assertIsNotNone(achado)
        self.assertIn("Nenhum setor informado neste período.", achado.group(1))
        self.assertNotIn("Plotly.newPlot", achado.group(1))


class TestGeradorComSetores(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import gerar_dados_ficticios as g
        from quiosque.formato import COLUNAS

        cls.g = g
        cls.COLUNAS = COLUNAS
        cls.linhas = g.gerar(FIM, semente=11)

    def test_colunas_de_setor_em_todas_as_linhas(self):
        self.assertEqual(set(self.linhas[0].keys()), set(self.COLUNAS))

    def test_tela_so_em_chegada_e_saida_e_so_nos_quiosques_com_setor(self):
        for l in self.linhas:
            if l["momento"] not in ("chegada", "saida_final") or l["kiosk_id"] not in self.g.SETORES:
                self.assertEqual(l["setor_perguntado"], "não", l)
                self.assertEqual(l["setor"], "", l)
            else:
                self.assertEqual(l["setor_perguntado"], "sim", l)

    def test_setor_informado_vem_da_lista_do_quiosque(self):
        for l in self.linhas:
            if l["setor"]:
                self.assertIn(l["setor"], self.g.SETORES[l["kiosk_id"]])

    def test_cerca_de_80_por_cento_informam(self):
        perguntadas = [l for l in self.linhas if l["setor_perguntado"] == "sim"]
        informaram = [l for l in perguntadas if l["setor"]]
        self.assertGreater(len(perguntadas), 1000)
        self.assertTrue(0.75 <= len(informaram) / len(perguntadas) <= 0.85)

    def test_cada_setor_tem_respostas_em_dias_uteis(self):
        uteis = {}
        for l in self.linhas:
            d = date.fromisoformat(l["data"])
            if l["setor"] and not self.g.eh_folga(d):
                uteis[(l["kiosk_id"], l["setor"])] = uteis.get((l["kiosk_id"], l["setor"]), 0) + 1
        for kiosk, setores in self.g.SETORES.items():
            for setor in setores:
                self.assertGreaterEqual(uteis.get((kiosk, setor), 0), 50, (kiosk, setor))

    def test_seguranca_e_qualidade_quase_nao_aparecem_em_alguns_fins_de_semana(self):
        inicio = FIM - timedelta(days=27)
        dias = [inicio + timedelta(days=i) for i in range(28)]
        for semana in self.g.SEMANAS_FDS_RAROS:  # mesma conta de semana do gerador
            fds = {d.isoformat() for d in dias if d.weekday() >= 5 and min(3, (d - inicio).days // 7) == semana}
            self.assertEqual(len(fds), 2)
            conta = sum(1 for l in self.linhas
                        if l["kiosk_id"] == "Q02" and l["setor"] in self.g.SETORES_RAROS_FDS
                        and l["data"] in fds)
            self.assertLess(conta, 5, f"semana {semana}: {conta} respostas")


if __name__ == "__main__":
    unittest.main()
