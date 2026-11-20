"""Testes da identidade visual do relatório (Eurostec System).

Logo oficial acima do título, Google Sans com os pesos reais embutidos,
cores da moldura só da paleta oficial, listas com "/", títulos com ponto,
cards de número sem sombra/borda lateral, rodapé padrão e Excel em Segoe UI.
"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
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
CORES_PERMITIDAS = {
    "#0446a4", "#00aeef", "#a7f432", "#0aa1f4", "#02358e",  # Blue-brand, Blue-card, Green, degradê
    "#323232", "#575756", "#ebebeb", "#fbfbfb", "#ffffff",  # Text, Text-catalog, Border, Surface, White
}


def _sem_scripts(html: str) -> str:
    return re.sub(r"<script>.*?</script>", "", html, flags=re.S)


def _css(html: str) -> str:
    estilo = re.search(r"<style>(.*?)</style>", html, flags=re.S).group(1)
    return re.sub(r"@font-face \{.*?\}", "", estilo)


@unittest.skipUnless(TEM_BIBLIOTECAS, MOTIVO_SKIP)
class TestIdentidadeHTML(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import gerar_dados_ficticios as g
        from relatorio.analise import analisar
        from relatorio.configuracao import carregar_config
        from relatorio.excel import gerar_excel
        from relatorio.html import gerar_html
        from relatorio.leitura import carregar_pasta
        from relatorio.resumo import gerar_resumo

        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        g.gravar_quiosques(g.gerar(date(2026, 11, 20), semente=3), base / "entrada")
        r = analisar(carregar_pasta(base / "entrada").dados, carregar_config())
        resumo = gerar_resumo(r)
        info = {"arquivos_lidos": [], "linhas_lidas": 0, "duplicadas_removidas": 0, "avisos": []}
        cls.html = gerar_html(r, resumo, base / "r.html", info, RAIZ).read_text(encoding="utf-8")
        cls.html_sem_logo = gerar_html(r, resumo, base / "r2.html", info, base).read_text(encoding="utf-8")
        cls.xlsx = gerar_excel(r, resumo, base / "r.xlsx", info)
        cls.corpo = _sem_scripts(cls.html)
        cls.css = _css(cls.html)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_fontes_com_os_quatro_pesos_reais(self):
        faces = re.findall(r'@font-face \{ font-family: "Google Sans";[^}]*font-weight: (\d+);[^}]*'
                           r"src: url\(data:font/woff2;base64,[A-Za-z0-9+/=]{1000,}\)", self.html)
        self.assertEqual(sorted(faces), ["400", "500", "600", "700"])

    def test_nenhum_peso_sem_arquivo(self):
        pesos = {int(p) for p in re.findall(r"font-weight:\s*(\d+)", self.css)}
        self.assertTrue(pesos <= {400, 500, 600, 700}, pesos)
        self.assertNotRegex(self.css, r"font-weight:\s*(bolder|900|800)")
        self.assertNotIn("font-style: italic", self.css)  # não há arquivo itálico
        self.assertNotIn("<i>", self.corpo)

    def test_logo_oficial_acima_do_titulo(self):
        logo = self.corpo.index('<img class="cab-logo" src="data:image/png;base64,')
        titulo = self.corpo.index('<h1 class="cab-t">')
        self.assertLess(logo, titulo)
        self.assertNotIn("EUROSTEC<", self.corpo)
        self.assertRegex(self.css, r"\.cab-logo \{[^}]*width: calc\(var\(--T\) \* 4\.1\)")
        self.assertRegex(self.css, r"\.cab-in \{ --T: 28px;")

    def test_sem_arquivo_de_logo_o_logo_e_omitido(self):
        corpo = _sem_scripts(self.html_sem_logo)
        self.assertNotIn("cab-logo\" src", corpo)
        self.assertNotIn("EUROSTEC", corpo)  # nunca reconstruir o logo com texto
        self.assertIn('<h1 class="cab-t">', corpo)

    def test_titulo_em_dois_pesos_com_ponto(self):
        self.assertRegex(self.corpo, r'<h1 class="cab-t">Termômetro Emocional: <b>relatório de '
                                     r'\d{2}/\d{2} a \d{2}/\d{2}/\d{4}\.</b></h1>')

    def test_titulos_com_ponto_final(self):
        titulos = re.findall(r"<h[23]>(.*?)</h[23]>", self.corpo)
        self.assertGreater(len(titulos), 15)
        for titulo in titulos:
            texto = re.sub(r"<.*?>", "", titulo).strip()
            self.assertTrue(texto.endswith((".", "?", "!")), texto)

    def test_listas_com_barra_e_sem_bolinha(self):
        self.assertNotIn("•", self.corpo)
        self.assertRegex(self.css, r'\.lst li::before \{ content: "/";[^}]*font-weight: 700; color: var\(--Blue-card\)')
        self.assertIn('<ul class="lst">', self.corpo)

    def test_cores_da_moldura_so_da_paleta(self):
        cores = {c.lower() for c in re.findall(r"#[0-9a-fA-F]{6}\b", self.css)}
        self.assertTrue(cores <= CORES_PERMITIDAS, cores - CORES_PERMITIDAS)

    def test_cards_de_numero_sem_sombra_e_sem_borda_lateral(self):
        self.assertNotIn("box-shadow", self.css)
        self.assertNotIn("border-left", self.css)
        self.assertRegex(self.css, r"\.st \{ border-radius: 16px;")
        self.assertIn("linear-gradient(135deg, var(--Blue-brand) 0%, var(--Gradient-end) 100%)", self.css)
        self.assertIn('<div class="stats">', self.corpo)

    def test_destaque_verde_unico(self):
        self.assertEqual(self.corpo.count('class="dst"'), 1)
        self.assertRegex(self.css, r"\.dst \{ background: var\(--Green\); color: var\(--Blue-brand\); "
                                   r"font-size: 13px; line-height: 19px;")

    def test_tabela_e_rodape(self):
        self.assertRegex(self.css, r"thead th \{ background: var\(--Blue-brand\); color: var\(--White\); font-weight: 600;")
        self.assertIn("tbody tr:nth-child(even) th, tbody tr:nth-child(even) td { background: var(--Surface); }", self.css)
        self.assertIn("Eurostec | CIPA · Termômetro Emocional", self.corpo)
        self.assertIn("Alta performance nos define.", self.corpo)

    def test_graficos_em_google_sans(self):
        self.assertGreater(self.html.count('"family":"\\"Google Sans\\"'), 10)

    def test_excel_no_padrao_office(self):
        from openpyxl import load_workbook

        livro = load_workbook(self.xlsx)
        aba = livro["Participação"]
        cabecalho = aba.cell(row=4, column=1)
        self.assertEqual(cabecalho.fill.fgColor.rgb[-6:], "0446A4")
        self.assertTrue(cabecalho.font.bold)
        self.assertEqual(cabecalho.font.color.rgb[-6:], "FFFFFF")
        self.assertEqual(cabecalho.font.name, "Segoe UI")
        self.assertEqual(aba.cell(row=6, column=2).fill.fgColor.rgb[-6:], "FBFBFB")  # zebrado
        self.assertEqual(aba.cell(row=5, column=2).font.name, "Segoe UI")
        self.assertTrue(str(aba["A1"].value).endswith("."))
        resumo = [str(c.value) for c in livro["Resumo"]["A"] if c.value]
        self.assertTrue(any(v.startswith("/ ") for v in resumo))
        self.assertFalse(any("•" in v for v in resumo))
        livro.close()


class TestLocalizacaoDosArquivos(unittest.TestCase):
    def test_fontes_primeiro_no_executavel(self):
        from relatorio.html import localizar_fontes

        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp) / "quiosque" / "web" / "fontes"
            pasta.mkdir(parents=True)
            (pasta / "GoogleSans-Regular.woff2").write_bytes(b"x")
            sys._MEIPASS = tmp  # simula o executável do PyInstaller
            try:
                self.assertEqual(localizar_fontes(RAIZ), pasta)
            finally:
                del sys._MEIPASS
        self.assertEqual(localizar_fontes(RAIZ), RAIZ / "quiosque" / "web" / "fontes")

    def test_spec_do_executavel_embute_fontes_e_logo(self):
        spec = (RAIZ / "ferramentas" / "pyinstaller" / "relatorio.spec").read_text(encoding="utf-8")
        self.assertIn('(str(RAIZ / "quiosque" / "web" / "fontes"), "quiosque/web/fontes")', spec)
        self.assertIn('"Eurostec-logo-azul.png"', spec)


if __name__ == "__main__":
    unittest.main()
