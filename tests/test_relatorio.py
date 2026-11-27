"""Teste de ponta a ponta do relatório com os dados fictícios.

Gera 2 quinzenas de dados fictícios (2 quiosques, ~150 pessoas), roda o
relatório como o gerar_relatorio.bat faria e confere HTML e Excel.
"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from collections import Counter
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
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
FIM = date(2026, 11, 20)


class TestDadosFicticios(unittest.TestCase):
    """O gerador precisa produzir dados realistas no formato do quiosque."""

    @classmethod
    def setUpClass(cls):
        import gerar_dados_ficticios as g

        cls.g = g
        cls.linhas = g.gerar(FIM, semente=7)

    def test_formato_e_volume(self):
        from quiosque.formato import COLUNAS

        self.assertGreater(len(self.linhas), 2500)
        self.assertEqual(set(self.linhas[0].keys()), set(COLUNAS))
        self.assertEqual({l["kiosk_id"] for l in self.linhas}, {"Q01", "Q02"})
        self.assertEqual(sum(q[2] for q in self.g.QUIOSQUES), 150)  # ~150 pessoas
        datas = sorted({l["data"] for l in self.linhas})
        self.assertLessEqual(datas[0], "2026-10-26")
        self.assertEqual(datas[-1] <= FIM.isoformat(), True)
        self.assertEqual(len({l["response_id"] for l in self.linhas}), len(self.linhas))

    def test_quatro_momentos_com_participacao_variada(self):
        por_momento = Counter(l["momento"] for l in self.linhas)
        self.assertEqual(set(por_momento), {"chegada", "saida_almoco", "volta_almoco", "saida_final"})
        self.assertGreater(por_momento["chegada"], por_momento["volta_almoco"] * 1.5)

    def test_regras_do_fluxo(self):
        for l in self.linhas:
            if l["motivo"]:
                self.assertIn(l["momento"], ("chegada", "saida_final"))
                self.assertNotEqual(l["valencia"], "neutra")
                self.assertIn(l["motivo"], self.g.MOTIVOS[(l["momento"], l["valencia"])])
            if l["pergunta_do_dia"]:
                self.assertEqual(l["momento"], "saida_final")
                d = date.fromisoformat(l["data"])
                self.assertEqual(l["pergunta_do_dia"], self.g.PERGUNTAS[d.toordinal() % 5][0])
        self.assertTrue(any(l["momento_automatico"] == "não" for l in self.linhas))
        self.assertTrue(any(l["condicao"] == "" for l in self.linhas))  # sem internet

    def test_adesao_cai_ao_longo_das_semanas(self):
        respostas, dias = Counter(), {}
        for l in self.linhas:
            d = date.fromisoformat(l["data"])
            if self.g.eh_folga(d):
                continue
            semana = d.isocalendar()[1]
            respostas[semana] += 1
            dias.setdefault(semana, set()).add(d)
        media = {s: respostas[s] / len(dias[s]) for s in respostas}  # respostas por dia útil
        semanas = sorted(media)
        self.assertGreaterEqual(len(semanas), 4)
        self.assertGreater(media[semanas[0]], media[semanas[-1]] * 1.05)

    def test_ha_recortes_pequenos_para_testar_o_anonimato(self):
        fins_de_semana = Counter((l["kiosk_id"], l["data"]) for l in self.linhas
                                 if self.g.eh_folga(date.fromisoformat(l["data"])))
        self.assertTrue(any(n < 5 for n in fins_de_semana.values()))


@unittest.skipUnless(TEM_BIBLIOTECAS, MOTIVO_SKIP)
class TestRelatorioCompleto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import gerar_dados_ficticios as g
        from relatorio.__main__ import main

        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.entrada = base / "entrada"
        cls.saida = base / "saida"
        cls.linhas = g.gerar(FIM, semente=11)
        g.gravar_quiosques(cls.linhas, cls.entrada)
        cls.repetidas = g.gravar_planilha(cls.linhas, cls.entrada, 11)
        saida_console = io.StringIO()
        with contextlib.redirect_stdout(saida_console):
            cls.codigo = main(["--entrada", str(cls.entrada), "--saida", str(cls.saida), "--nao-abrir"])
        cls.console = saida_console.getvalue()
        cls.html = next(cls.saida.glob("relatorio_*.html"), None)
        cls.xlsx = next(cls.saida.glob("relatorio_*.xlsx"), None)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_arquivos_gerados(self):
        self.assertEqual(self.codigo, 0, self.console)
        self.assertIsNotNone(self.html)
        self.assertIsNotNone(self.xlsx)
        self.assertRegex(self.html.name, r"^relatorio_\d{4}-\d{2}-\d{2}\.html$")
        self.assertRegex(self.xlsx.name, r"^relatorio_\d{4}-\d{2}-\d{2}\.xlsx$")
        self.assertIn("Relatório pronto", self.console)

    def test_html_tem_todas_as_secoes_e_funciona_offline(self):
        texto = self.html.read_text(encoding="utf-8")
        for secao in ("resumo", "participacao", "emocoes", "humor", "variacoes", "clima", "motivos", "pergunta"):
            self.assertIn(f'id="{secao}"', texto)
        for trecho in ("Participação por semana", "Distribuição das emoções por momento",
                       "Humor ao longo do dia", "Mapa de calor", "Como o humor muda entre os momentos",
                       "Por faixa de temperatura", "Resultados da pergunta do dia", "dados insuficientes"):
            self.assertIn(trecho, texto)
        # plotly.js vai embutido: nenhum script ou estilo é baixado da internet
        self.assertNotRegex(texto, r"<script[^>]*\bsrc=")
        self.assertNotRegex(texto, r"<link[^>]*\bhref=\"https?:")
        self.assertIn("plotly.js v", texto)
        self.assertGreater(texto.count("Plotly.newPlot"), 8)

    def test_excel_tem_dados_consolidados_e_abas(self):
        from openpyxl import load_workbook

        livro = load_workbook(self.xlsx, read_only=True)
        for aba in ("Resumo", "Dados", "Participação", "Participação semanal", "Emoções por momento",
                    "Humor por momento", "Humor dia x momento", "Variações do dia", "Clima - condição",
                    "Clima - temperatura", "Motivos", "Motivos por emoção", "Pergunta do dia",
                    "Respostas por ponto", "Respostas por dia", "Respostas detalhadas"):
            self.assertIn(aba, livro.sheetnames)
        dados = livro["Dados"]
        linhas = list(dados.iter_rows(min_row=2, values_only=True))
        # A planilha repetia respostas: o total consolidado deve bater com o gerado.
        self.assertEqual(len(linhas), len(self.linhas))
        self.assertEqual(len({l[0] for l in linhas}), len(self.linhas))
        resumo_texto = " ".join(str(c) for linha in livro["Resumo"].iter_rows(values_only=True) for c in linha if c)
        self.assertIn("restrito à CIPA", resumo_texto)
        livro.close()

    def test_console_informa_deduplicacao(self):
        self.assertIn(f"{self.repetidas} resposta(s) repetida(s)", self.console)

    def test_filtro_de_periodo(self):
        from relatorio.__main__ import main

        saida = Path(self.tmp.name) / "periodo"
        with contextlib.redirect_stdout(io.StringIO()) as buffer:
            codigo = main(["--entrada", str(self.entrada), "--saida", str(saida), "--nao-abrir",
                           "--inicio", "2026-11-09", "--fim", "2026-11-13"])
        self.assertEqual(codigo, 0)
        esperado = sum(1 for l in self.linhas if "2026-11-09" <= l["data"] <= "2026-11-13")
        self.assertIn(f"{esperado} resposta(s) no período de 09/11/2026 a 13/11/2026", buffer.getvalue())

    def test_pasta_vazia_da_mensagem_amigavel(self):
        from relatorio.__main__ import main

        vazia = Path(self.tmp.name) / "vazia"
        vazia.mkdir()
        with contextlib.redirect_stdout(io.StringIO()) as buffer:
            codigo = main(["--entrada", str(vazia), "--saida", str(vazia / "saida"), "--nao-abrir"])
        self.assertEqual(codigo, 1)
        self.assertIn("Nenhum arquivo CSV", buffer.getvalue())

    def test_resumo_em_texto(self):
        from relatorio.analise import analisar
        from relatorio.configuracao import carregar_config
        from relatorio.leitura import carregar_pasta
        from relatorio.resumo import gerar_resumo

        r = analisar(carregar_pasta(self.entrada).dados, carregar_config())
        frases = gerar_resumo(r)
        texto = " ".join(frases)
        self.assertIn("Período analisado", texto)
        self.assertIn("Participação média", texto)
        self.assertIn("adesão", texto)
        self.assertIn("Índice de humor geral", texto)
        self.assertIn("anonimato", texto)


if __name__ == "__main__":
    unittest.main()
