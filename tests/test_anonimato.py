"""Testes da REGRA DE ANONIMATO do relatório.

- Grupo com menos de 5 respostas -> "dados insuficientes".
- Dentro de um grupo válido, categoria com 1 a 4 respostas -> "<5" no lugar
  da contagem E do percentual; fica fora dos gráficos (ou vai para
  "Outras (<5 cada)") e não é citada no resumo.
- Exatamente 5 respostas -> o número aparece.
"""
from __future__ import annotations

import math
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import pandas  # noqa: F401

    TEM_PANDAS = True
except ImportError:  # pragma: no cover
    TEM_PANDAS = False

MOTIVO_SKIP = "pandas não está instalado (rode instalar.bat, opção do PC da CIPA)"
SEGUNDA = date(2026, 11, 16)
TERCA = date(2026, 11, 17)


def verificar_percentuais(teste: unittest.TestCase, r) -> None:
    """Nenhum percentual exibido pode representar de 1 a 4 pessoas.

    Na tabela de motivos, "Respostas" é a contagem da própria categoria (precisa ser >= 5
    sempre que houver percentual); nas demais, é o total do grupo (percentual × total
    precisa dar 0 ou >= 5).
    """
    motivos = r.tabelas["motivos"].dados
    for contagem, valor in zip(motivos["Respostas"], motivos["% dos motivos"]):
        if isinstance(valor, float):
            teste.assertIsInstance(contagem, (int, float))
            teste.assertGreaterEqual(contagem, 5)
    for chave, tabela in r.tabelas.items():
        df = tabela.dados
        if "Respostas" not in df.columns or chave == "motivos":
            continue
        for coluna, formato in tabela.formatos.items():
            if formato != "pct" or coluna not in df.columns:
                continue
            for total, valor in zip(df["Respostas"], df[coluna]):
                if isinstance(valor, float) and isinstance(total, (int, float)) and not isinstance(total, bool):
                    pessoas = round(valor * total)
                    teste.assertFalse(1 <= pessoas <= 4, f"{chave}/{coluna}: {valor:.0%} de {total} = {pessoas} pessoa(s)")


@unittest.skipUnless(TEM_PANDAS, MOTIVO_SKIP)
class TestFuncoesDaRegra(unittest.TestCase):
    def setUp(self):
        from relatorio import analise

        self.a = analise

    def test_contagem(self):
        a = self.a
        self.assertEqual(a.exibir_contagem(0), 0)
        for n in (1, 2, 3, 4):
            self.assertEqual(a.exibir_contagem(n), "<5")
        self.assertEqual(a.exibir_contagem(5), 5)
        self.assertEqual(a.exibir_contagem(120), 120)

    def test_estatistica(self):
        a = self.a
        for n in (0, 1, 4):
            self.assertEqual(a.exibir_estatistica(0.7, n), a.INSUFICIENTE)
        self.assertEqual(a.exibir_estatistica(0.7, 5), 0.7)
        self.assertEqual(a.exibir_estatistica(math.nan, 50), a.INSUFICIENTE)
        self.assertIsNone(a.valor_grafico(0.7, 4))
        self.assertEqual(a.valor_grafico(0.7, 5), 0.7)

    def test_minimo_configuravel(self):
        a = self.a
        self.assertEqual(a.exibir_contagem(2, minimo=3), "<3")
        self.assertEqual(a.exibir_estatistica(1.0, 2, minimo=3), a.INSUFICIENTE)
        self.assertEqual(a.exibir_estatistica(1.0, 3, minimo=3), 1.0)

    def test_distribuicao(self):
        import pandas as pd

        a = self.a
        quatro = a.distribuicao(pd.Series(["Feliz"] * 3 + ["Triste"]), ["Feliz", "Triste"])
        self.assertFalse(quatro["valida"])
        self.assertEqual(quatro["pct"]["Feliz"], a.INSUFICIENTE)
        self.assertEqual(quatro["contagem"]["Triste"], a.INSUFICIENTE)

        cinco = a.distribuicao(pd.Series(["Feliz"] * 4 + ["Triste"]), ["Feliz", "Triste", "Bravo"])
        self.assertTrue(cinco["valida"])
        self.assertEqual(cinco["pct"]["Feliz"], "<5")  # 4 respostas: nem contagem, nem percentual
        self.assertEqual(cinco["contagem"]["Feliz"], "<5")
        self.assertEqual(cinco["pct"]["Triste"], "<5")  # 1 resposta
        self.assertEqual(cinco["contagem"]["Triste"], "<5")
        self.assertEqual(cinco["contagem"]["Bravo"], 0)
        self.assertEqual(cinco["pct"]["Bravo"], 0.0)

        sete = a.distribuicao(pd.Series(["Feliz"] * 6 + ["Triste"]), ["Feliz", "Triste"])
        self.assertAlmostEqual(sete["pct"]["Feliz"], 6 / 7)
        self.assertEqual(sete["contagem"]["Feliz"], 6)
        self.assertEqual(sete["pct"]["Triste"], "<5")  # 1 pessoa: 14% não pode aparecer

    def test_fracao(self):
        a = self.a
        self.assertEqual(a.exibir_fracao(3, 4), a.INSUFICIENTE)  # grupo pequeno
        self.assertEqual(a.exibir_fracao(1, 7), "<5")  # categoria pequena
        self.assertEqual(a.exibir_fracao(4, 100), "<5")
        self.assertAlmostEqual(a.exibir_fracao(5, 10), 0.5)
        self.assertEqual(a.exibir_fracao(0, 10), 0.0)
        self.assertTrue(a.categoria_visivel(0))
        self.assertFalse(a.categoria_visivel(3))
        self.assertTrue(a.categoria_visivel(5))


@unittest.skipUnless(TEM_PANDAS, MOTIVO_SKIP)
class TestRegraNasTabelas(unittest.TestCase):
    """Monta dados pequenos de propósito e confere cada tabela do relatório."""

    @classmethod
    def setUpClass(cls):
        from auxiliar_relatorio import carregar, gravar, linha
        from relatorio.analise import analisar
        from relatorio.configuracao import carregar_config

        linhas = []
        # Segunda: chegada com 5 (exatamente o mínimo), saída p/ almoço com 4 (insuficiente)
        linhas += [linha("chegada", "Feliz", SEGUNDA) for _ in range(3)]
        linhas += [linha("chegada", "Cansado", SEGUNDA, motivo="Sono/cansaço") for _ in range(2)]
        linhas += [linha("saida_almoco", "Feliz", SEGUNDA, hora="11:55:00") for _ in range(4)]
        # Terça: chegada com 6, saída p/ almoço com 5 -> variação válida neste dia
        linhas += [linha("chegada", "Triste", TERCA, motivo="Saúde/dor") for _ in range(6)]
        linhas += [linha("saida_almoco", "Neutro", TERCA, hora="11:55:00") for _ in range(5)]
        # Saída do dia: pergunta do dia com 4 respostas (insuficiente)
        linhas += [linha("saida_final", "Neutro", TERCA, hora="17:10:00",
                         pergunta="Conseguiu fazer suas pausas hoje?", resposta="Sim") for _ in range(4)]
        cls.tmp = tempfile.TemporaryDirectory()
        gravar(Path(cls.tmp.name), linhas)
        df = carregar(Path(cls.tmp.name))
        cls.r = analisar(df, carregar_config())
        from relatorio import analise

        cls.INSUF = analise.INSUFICIENTE

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _linha(self, chave, coluna, valor):
        df = self.r.tabelas[chave].dados
        return df[df[coluna] == valor].iloc[0]

    def test_humor_por_momento(self):
        chegada = self._linha("humor_momento", "Momento", "Chegada")  # 11 respostas
        self.assertNotEqual(chegada["Índice de humor"], self.INSUF)
        self.assertEqual(chegada["% positivas"], "<5")  # 3 pessoas felizes
        self.assertAlmostEqual(chegada["% negativas"], 8 / 11)
        self.assertEqual(chegada["% neutras"], 0.0)
        saida = self._linha("humor_momento", "Momento", "Saída do dia")  # 4 respostas
        self.assertEqual(saida["Índice de humor"], self.INSUF)
        self.assertEqual(saida["% neutras"], self.INSUF)
        self.assertEqual(saida["Respostas"], "<5")

    def test_mapa_de_calor_dia_por_momento(self):
        segunda = self._linha("humor_dia_momento", "Dia da semana", "Segunda")
        self.assertAlmostEqual(segunda["Chegada"], (3 * 2 + 2 * -1) / 5)  # exatamente 5 -> mostra
        self.assertEqual(segunda["Saída para o almoço"], self.INSUF)  # 4 -> insuficiente
        self.assertEqual(segunda["Volta do almoço"], self.INSUF)  # 0 -> insuficiente
        g = self.r.graficos["humor_dia_momento"]
        i = g["dias"].index("Segunda")
        self.assertIsNone(g["z"][i][1])  # ponto omitido no gráfico
        self.assertIsNotNone(g["z"][i][0])
        contagens = self._linha("respostas_dia_momento", "Dia da semana", "Segunda")
        self.assertEqual(contagens["Saída para o almoço"], "<5")
        self.assertEqual(contagens["Chegada"], 5)

    def test_distribuicao_emocoes(self):
        saida = self._linha("emocoes_momento", "Momento", "Saída do dia")
        self.assertEqual(saida["Neutro"], self.INSUF)
        chegada = self._linha("emocoes_momento", "Momento", "Chegada")
        self.assertAlmostEqual(chegada["Triste"], 6 / 11)
        self.assertEqual(chegada["Feliz"], "<5")  # 3 respostas
        self.assertEqual(chegada["Cansado"], "<5")  # 2 respostas

    def test_motivos(self):
        motivos = self.r.tabelas["motivos"].dados
        neg = motivos[motivos["Contexto"].str.startswith("Chegada · emoções negativas")]
        # 8 motivos informados: Sono/cansaço (2) e Saúde/dor (6)
        sono = neg[neg["Motivo"] == "Sono/cansaço"].iloc[0]
        self.assertEqual(sono["Respostas"], "<5")
        self.assertEqual(sono["% dos motivos"], "<5")  # sem percentual
        saude = neg[neg["Motivo"] == "Saúde/dor"].iloc[0]
        self.assertEqual(saude["Respostas"], 6)
        pos = motivos[motivos["Contexto"].str.startswith("Chegada · emoções positivas")].iloc[0]
        self.assertEqual(pos["Motivo"], self.INSUF)  # nenhum motivo positivo informado
        por_emocao = self.r.tabelas["motivos_emocao"].dados
        cansado = por_emocao[(por_emocao["Emoção"] == "Cansado")].iloc[0]
        self.assertEqual(cansado["Principais motivos"], self.INSUF)  # só 2 motivos
        triste = por_emocao[(por_emocao["Emoção"] == "Triste")].iloc[0]
        self.assertIn("Saúde/dor", triste["Principais motivos"])

    def test_variacoes(self):
        manha = self._linha("variacoes", "Período", "Manhã")
        # Segunda tem saída p/ almoço com 4 -> só a terça entra
        self.assertEqual(manha["Dias considerados"], 1)
        self.assertAlmostEqual(manha["Variação média"], 0 - (-2))
        tarde = self._linha("variacoes", "Período", "Tarde")
        self.assertEqual(tarde["Variação média"], self.INSUF)
        self.assertEqual(tarde["Dias considerados"], 0)

    def test_pergunta_do_dia(self):
        pergunta = self._linha("pergunta_dia", "Pergunta", "Conseguiu fazer suas pausas hoje?")
        self.assertEqual(pergunta["Respostas"], "<5")
        self.assertEqual(pergunta["Sim"], self.INSUF)
        self.assertEqual(pergunta["Resultado favorável"], self.INSUF)

    def test_clima_sem_dados(self):
        sol = self._linha("clima_condicao", "Condição do tempo", "Sol")
        self.assertEqual(sol["Índice de humor"], self.INSUF)
        self.assertEqual(sol["Respostas"], 0)

    def test_respostas_por_dia(self):
        dia = self.r.tabelas["respostas_dia"].dados
        terca = dia[dia["Data"] == "17/11/2026"].iloc[0]
        self.assertEqual(terca["Saída do dia"], "<5")
        self.assertEqual(terca["Chegada"], 6)

    def test_nenhum_percentual_representa_menos_de_5(self):
        verificar_percentuais(self, self.r)

    def test_nenhum_numero_pequeno_escapa(self):
        """Varre todas as tabelas: nenhuma coluna de contagem pode mostrar 1 a 4."""
        for chave, tabela in self.r.tabelas.items():
            for coluna, formato in tabela.formatos.items():
                if formato != "int" or "dias" in coluna.lower() or "Público" in coluna:
                    continue
                for valor in tabela.dados[coluna]:
                    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
                        self.assertFalse(1 <= valor <= 4, f"{chave}/{coluna} mostra {valor}")



@unittest.skipUnless(TEM_PANDAS, MOTIVO_SKIP)
class TestCategoriasPequenasEmGrupoValido(unittest.TestCase):
    """Grupo com 5+ respostas, mas categorias com 1 a 4: nada pode identificar essas pessoas."""

    @classmethod
    def setUpClass(cls):
        from auxiliar_relatorio import carregar, gravar, linha
        from relatorio.analise import analisar
        from relatorio.configuracao import carregar_config
        from relatorio.html import gerar_html
        from relatorio.excel import gerar_excel
        from relatorio.resumo import gerar_resumo

        linhas = []
        # Chegada/Furioso n=7: motivos 3 + 1 + 1 (+2 sem motivo) -> todos < 5
        for motivo in ["Família/vida pessoal"] * 3 + ["Preocupação com o trabalho", "Sono/cansaço", "", ""]:
            linhas.append(linha("chegada", "Furioso", SEGUNDA, motivo=motivo))
        # Chegada/Feliz n=6: "Descansei bem" 5x, "Clima/dia bonito" 1x
        for motivo in ["Descansei bem"] * 5 + ["Clima/dia bonito"]:
            linhas.append(linha("chegada", "Feliz", SEGUNDA, motivo=motivo, condicao="sol", temperatura=16.0))
        # Chegada/Triste n=2 (vai para "Outras")
        linhas += [linha("chegada", "Triste", SEGUNDA) for _ in range(2)]
        # Saída do dia: pergunta do dia 6 Sim + 2 Não
        for resposta in ["Sim"] * 6 + ["Não"] * 2:
            linhas.append(linha("saida_final", "Neutro", SEGUNDA, hora="17:10:00",
                                pergunta="Conseguiu fazer suas pausas hoje?", resposta=resposta))
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        gravar(base / "entrada", linhas)
        cls.r = analisar(carregar(base / "entrada"), carregar_config())
        cls.resumo = gerar_resumo(cls.r)
        info = {"arquivos_lidos": [], "linhas_lidas": len(linhas), "duplicadas_removidas": 0, "avisos": []}
        cls.html = gerar_html(cls.r, cls.resumo, base / "r.html", info).read_text(encoding="utf-8")
        cls.xlsx = gerar_excel(cls.r, cls.resumo, base / "r.xlsx", info)
        from relatorio import analise

        cls.INSUF = analise.INSUFICIENTE

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_tabela_de_motivos_sem_percentual_para_categorias_pequenas(self):
        df = self.r.tabelas["motivos"].dados
        neg = df[df["Contexto"].str.startswith("Chegada · emoções negativas")]
        self.assertEqual(len(neg), 3)  # grupo válido (5 motivos), 3 categorias
        for _, linha in neg.iterrows():
            self.assertEqual(linha["Respostas"], "<5")
            self.assertEqual(linha["% dos motivos"], "<5")
        pos = df[df["Contexto"].str.startswith("Chegada · emoções positivas")].set_index("Motivo")
        self.assertEqual(pos.loc["Descansei bem", "Respostas"], 5)
        self.assertAlmostEqual(pos.loc["Descansei bem", "% dos motivos"], 5 / 6)
        self.assertEqual(pos.loc["Clima/dia bonito", "% dos motivos"], "<5")

    def test_principais_motivos_so_com_5_ou_mais(self):
        df = self.r.tabelas["motivos_emocao"].dados.set_index("Emoção")
        self.assertEqual(df.loc["Furioso", "Principais motivos"], self.INSUF)  # nenhum motivo com 5+
        self.assertEqual(df.loc["Feliz", "Principais motivos"], "Descansei bem (83%)")
        self.assertNotIn("Clima", df.loc["Feliz", "Principais motivos"])

    def test_grafico_de_motivos_omite_categorias_pequenas(self):
        itens = {(i["momento"], i["valencia"]): i for i in self.r.graficos["motivos"]}
        negativo = itens[("chegada", "negativa")]
        self.assertTrue(negativo["valido"])
        self.assertEqual(negativo["itens"], [])
        self.assertEqual(negativo["omitidos"], 3)
        positivo = itens[("chegada", "positiva")]
        self.assertEqual([i["motivo"] for i in positivo["itens"]], ["Descansei bem"])
        self.assertEqual(positivo["omitidos"], 1)
        self.assertIn("Categorias com menos de 5 respostas foram omitidas", self.html)
        self.assertIn("Nenhum motivo com 5 ou mais respostas", self.html)

    def test_pergunta_do_dia(self):
        linha = self.r.tabelas["pergunta_dia"].dados.iloc[0]
        self.assertAlmostEqual(linha["Sim"], 6 / 8)
        self.assertEqual(linha["Não"], "<5")  # 2 pessoas
        self.assertEqual(linha["Mais ou menos"], 0.0)
        self.assertAlmostEqual(linha["Resultado favorável"], 6 / 8)
        g = self.r.graficos["pergunta_dia"][0]
        self.assertIsNone(g["desfavoravel"][1])  # omitido do gráfico
        self.assertEqual(g["omitidas"], ["Não"])

    def test_emocoes_pequenas_viram_outras_no_grafico(self):
        g = self.r.graficos["emocoes_momento"]
        i = g["momentos"].index("Chegada")
        self.assertEqual(g["outras_nomes"][i], ["Triste"])
        self.assertAlmostEqual(g["outras"][i], 2 / 15)
        triste = g["emocoes"].index("Triste")
        self.assertIsNone(g["pct"][i][triste])  # sem segmento próprio, sem percentual
        self.assertEqual(g["contagem"][i][triste], "<5")
        tabela = self.r.tabelas["emocoes_momento"].dados.set_index("Momento")
        self.assertEqual(tabela.loc["Chegada", "Triste"], "<5")
        self.assertIn("Outras (", self.html)
        self.assertIn("menos de 5 respostas cada", self.html)

    def test_resumo_nao_cita_categorias_pequenas(self):
        texto = " ".join(self.resumo)
        for proibido in ("Família/vida pessoal", "Preocupação com o trabalho", "Sono/cansaço",
                         "Clima/dia bonito", "Triste"):
            self.assertNotIn(proibido, texto)
        self.assertIn("75%", texto)  # pergunta do dia: 6 de 8 favoráveis pode aparecer

    def test_kpis(self):
        self.assertAlmostEqual(self.r.kpis["pct_positivas"], 6 / 23)  # 6 Feliz
        self.assertAlmostEqual(self.r.kpis["pct_negativas"], 9 / 23)  # 7 Furioso + 2 Triste

    def test_percentuais_nas_tabelas(self):
        verificar_percentuais(self, self.r)

    def test_excel_segue_a_mesma_regra(self):
        from openpyxl import load_workbook

        livro = load_workbook(self.xlsx, read_only=True)
        linhas = list(livro["Motivos"].iter_rows(min_row=5, values_only=True))
        neg = [l for l in linhas if l[0] and str(l[0]).startswith("Chegada · emoções negativas")]
        self.assertEqual(len(neg), 3)
        for l in neg:
            self.assertEqual(l[3], "<5")  # Respostas
            self.assertEqual(l[4], "<5")  # % dos motivos
        pergunta = list(livro["Pergunta do dia"].iter_rows(min_row=5, max_row=5, values_only=True))[0]
        self.assertEqual(pergunta[5], "<5")  # coluna "Não"
        livro.close()


if __name__ == "__main__":
    unittest.main()
