"""Testes da leitura/consolidação dos CSVs pelo relatório (deduplicação)."""
from __future__ import annotations

import csv
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
DIA = date(2026, 11, 18)


def gravar_planilha(caminho: Path, linhas: list[dict], decimal_virgula: bool = False) -> None:
    """Imita o CSV baixado da Planilha Google: separador ',', sem BOM, data 18/11/2026."""
    from quiosque.formato import COLUNAS

    with open(caminho, "w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo, delimiter=",")
        escritor.writerow(COLUNAS)
        for linha in linhas:
            valores = []
            for coluna in COLUNAS:
                valor = linha.get(coluna, "")
                if coluna == "data":
                    a, m, d = str(valor).split("-")
                    valor = f"{d}/{m}/{a}"
                if decimal_virgula and isinstance(valor, float):
                    valor = str(valor).replace(".", ",")
                valores.append(valor)
            escritor.writerow(valores)


@unittest.skipUnless(TEM_PANDAS, MOTIVO_SKIP)
class TestLeituraEDeduplicacao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_mesma_resposta_no_quiosque_e_na_planilha_conta_uma_vez(self):
        from auxiliar_relatorio import gravar, linha
        from relatorio.leitura import carregar_pasta

        locais = [linha("chegada", "Cansado", DIA, temperatura=18.4, condicao="sol") for _ in range(6)]
        gravar(self.pasta / "Q01", locais)
        # A planilha tem 4 das mesmas respostas + 1 que só existe nela
        na_planilha = [dict(l) for l in locais[:4]] + [linha("chegada", "Feliz", DIA)]
        na_planilha[0]["motivo"] = "Sono/cansaço"  # versão mais completa está na planilha
        gravar_planilha(self.pasta / "planilha_exportada.csv", na_planilha)

        r = carregar_pasta(self.pasta)
        self.assertEqual(len(r.arquivos_lidos), 2)
        self.assertEqual(r.linhas_lidas, 11)
        self.assertEqual(r.duplicadas_removidas, 4)
        self.assertEqual(len(r.dados), 7)
        self.assertEqual(r.dados["response_id"].nunique(), 7)
        completa = r.dados[r.dados["response_id"] == locais[0]["response_id"]].iloc[0]
        self.assertEqual(completa["motivo"], "Sono/cansaço")  # a versão mais completa venceu

    def test_versao_mais_completa_vence_mesmo_vindo_antes(self):
        from auxiliar_relatorio import gravar, linha
        from relatorio.leitura import carregar_pasta

        base = linha("saida_final", "Feliz", DIA, hora="17:10:00")
        completa = dict(base, motivo="Dia produtivo", pergunta_do_dia="Conseguiu fazer suas pausas hoje?",
                        resposta_pergunta_do_dia="Sim")
        gravar(self.pasta / "a_quiosque", [completa])
        gravar(self.pasta / "b_pendrive", [base])
        r = carregar_pasta(self.pasta)
        self.assertEqual(len(r.dados), 1)
        self.assertEqual(r.dados.iloc[0]["motivo"], "Dia produtivo")
        self.assertEqual(r.dados.iloc[0]["resposta_pergunta_do_dia"], "Sim")

    def test_separadores_e_decimais(self):
        from auxiliar_relatorio import gravar, linha
        from relatorio.leitura import carregar_pasta

        quiosque = linha("chegada", "Feliz", DIA, temperatura=18.4, condicao="sol")
        gravar(self.pasta, [quiosque])
        texto = next(self.pasta.glob("*.csv")).read_bytes()
        self.assertTrue(texto.startswith(b"\xef\xbb\xbf"))  # BOM
        self.assertIn("18,4".encode(), texto)  # vírgula decimal

        planilha_ponto = linha("chegada", "Neutro", DIA, temperatura=12.5)
        gravar_planilha(self.pasta / "planilha_ponto.csv", [planilha_ponto])
        planilha_virgula = linha("chegada", "Triste", DIA, temperatura=9.75)
        gravar_planilha(self.pasta / "planilha_virgula.csv", [planilha_virgula], decimal_virgula=True)

        df = carregar_pasta(self.pasta).dados.set_index("response_id")
        self.assertAlmostEqual(df.loc[quiosque["response_id"], "temperatura_c"], 18.4)
        self.assertAlmostEqual(df.loc[planilha_ponto["response_id"], "temperatura_c"], 12.5)
        self.assertAlmostEqual(df.loc[planilha_virgula["response_id"], "temperatura_c"], 9.75)
        self.assertEqual(df.loc[planilha_ponto["response_id"], "data"], DIA)  # 18/11/2026 entendido
        self.assertEqual(df.loc[planilha_ponto["response_id"], "pontuacao"], 0)

    def test_arquivo_estranho_e_ignorado_com_aviso(self):
        from auxiliar_relatorio import gravar, linha
        from relatorio.leitura import carregar_pasta

        gravar(self.pasta, [linha("chegada", "Feliz", DIA)])
        (self.pasta / "outra_coisa.csv").write_text("nome;idade\nAna;30\n", encoding="utf-8")
        (self.pasta / "vazio.csv").write_text("", encoding="utf-8")
        r = carregar_pasta(self.pasta)
        self.assertEqual(len(r.dados), 1)
        ignorados = {p.name: motivo for p, motivo in r.arquivos_ignorados}
        self.assertIn("outra_coisa.csv", ignorados)
        self.assertIn("response_id", ignorados["outra_coisa.csv"])

    def test_linha_incompleta_e_descartada(self):
        from auxiliar_relatorio import gravar, linha
        from relatorio.leitura import carregar_pasta

        ruim = linha("chegada", "Feliz", DIA)
        ruim["momento"] = "momento_inexistente"
        gravar(self.pasta, [ruim, linha("chegada", "Feliz", DIA)])
        r = carregar_pasta(self.pasta)
        self.assertEqual(len(r.dados), 1)
        self.assertEqual(r.linhas_descartadas, 1)
        self.assertTrue(r.avisos)

    def test_data_vinda_do_timestamp(self):
        from auxiliar_relatorio import linha
        from relatorio.leitura import carregar_pasta

        sem_data = linha("chegada", "Feliz", DIA)
        sem_data["data"] = ""
        gravar_planilha_sem_data = self.pasta / "planilha.csv"
        from quiosque.formato import COLUNAS

        with open(gravar_planilha_sem_data, "w", encoding="utf-8", newline="") as arquivo:
            escritor = csv.writer(arquivo)
            escritor.writerow(COLUNAS)
            escritor.writerow([sem_data.get(c, "") for c in COLUNAS])
        df = carregar_pasta(self.pasta).dados
        self.assertEqual(df.iloc[0]["data"], DIA)
        self.assertEqual(df.iloc[0]["dia_semana"], "quarta")

    def test_numeros_brasileiros(self):
        from relatorio.leitura import para_data, para_float

        self.assertAlmostEqual(para_float("18,4"), 18.4)
        self.assertAlmostEqual(para_float("18.4"), 18.4)
        self.assertAlmostEqual(para_float("1.234,5"), 1234.5)
        self.assertTrue(para_float("") != para_float(""))  # nan
        self.assertEqual(para_data("20/11/2026"), date(2026, 11, 20))
        self.assertEqual(para_data("2026-11-20"), date(2026, 11, 20))
        self.assertIsNone(para_data("ontem"))


if __name__ == "__main__":
    unittest.main()
