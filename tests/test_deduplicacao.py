"""Deduplicação: reenvios e atualizações nunca duplicam respostas."""
import shutil
import subprocess
import unittest

from tests.auxiliares import RAIZ, AppsScriptFalso, ClimaFalso, PastaTemporaria, RelogioFalso, config_teste
from quiosque.registros import Registros
from quiosque.sincronizacao import ErroEnvio, FilaEnvio, chamar_apps_script

ID = "0b6f5c1e-6a0e-4f61-9d4f-0a6b1c2d3e4f"


class TestDeduplicacao(unittest.TestCase):
    def setUp(self):
        self.pasta = PastaTemporaria()
        self.planilha = AppsScriptFalso(token="segredo")
        self.config = config_teste()
        self.config["sincronizacao"].update({"url": self.planilha.url, "token": "segredo", "atraso_envio_s": 0})

    def tearDown(self):
        self.planilha.parar()
        self.pasta.limpar()

    def criar(self, chamar=chamar_apps_script):
        fila = FilaEnvio(self.pasta.caminho / "estado" / "fila.json", lambda: self.config, chamar=chamar)
        reg = Registros(self.pasta.caminho / "dados", self.pasta.caminho / "estado",
                        lambda: self.config, RelogioFalso("2026-11-18T17:10:00"), clima=ClimaFalso(), fila=fila)
        return fila, reg

    def test_fila_guarda_so_a_versao_mais_recente(self):
        fila, reg = self.criar()
        reg.criar({"response_id": ID, "momento": "saida_final", "momento_automatico": True, "emocao": "Bravo"})
        reg.atualizar(ID, {"motivo": "Cliente/pressão externa"})
        reg.atualizar(ID, {"resposta_pergunta_do_dia": "Não"})
        self.assertEqual(fila.pendentes(), 1)
        item = fila.itens[ID]
        self.assertEqual(item["versao"], 3)
        self.assertEqual(item["linha"]["resposta_pergunta_do_dia"], "Não")

    def test_resposta_perdida_no_caminho_e_reenviada_sem_duplicar(self):
        """A planilha gravou, mas a internet caiu antes da confirmação: o reenvio não duplica."""
        perder = {"sim": True}

        def chamar(url, corpo, timeout):
            resultado = chamar_apps_script(url, corpo, timeout)
            if perder["sim"]:
                perder["sim"] = False
                raise ErroEnvio("conexão caiu antes da resposta")
            return resultado

        fila, reg = self.criar(chamar)
        reg.criar({"response_id": ID, "momento": "saida_final", "momento_automatico": True, "emocao": "Feliz"})
        self.assertEqual(fila.processar_uma_vez(forcar=True), "erro")
        self.assertEqual(len(self.planilha.planilha), 1, "a planilha já tinha recebido")
        self.assertEqual(fila.processar_uma_vez(forcar=True), "ok")
        self.assertEqual(len(self.planilha.planilha), 1, "reenvio substituiu a mesma linha")
        self.assertEqual(self.planilha.pedidos, 2)

    def test_atualizacao_durante_o_envio_nao_se_perde(self):
        fila_ref = {}

        def chamar(url, corpo, timeout):
            resultado = chamar_apps_script(url, corpo, timeout)
            # enquanto a 1ª versão viajava, a pessoa tocou no motivo
            fila_ref["reg"].atualizar(ID, {"motivo": "Equipe/colegas"})
            fila_ref["chamar"] = chamar_apps_script
            return resultado

        fila, reg = self.criar(lambda u, c, t: fila_ref.get("chamar", chamar)(u, c, t))
        fila_ref["reg"] = reg
        reg.criar({"response_id": ID, "momento": "saida_final", "momento_automatico": True, "emocao": "Feliz"})
        self.assertEqual(fila.processar_uma_vez(forcar=True), "ok")
        self.assertEqual(fila.pendentes(), 1, "a versão nova continua na fila")
        self.assertEqual(fila.processar_uma_vez(forcar=True), "ok")
        self.assertEqual(self.planilha.planilha[ID]["motivo"], "Equipe/colegas")
        self.assertEqual(len(self.planilha.planilha), 1)

    def test_reenviar_tudo_nao_duplica(self):
        fila, reg = self.criar()
        for emocao in ("Feliz", "Triste", "Neutro", "Furioso"):
            reg.criar({"momento": "saida_final", "momento_automatico": True, "emocao": emocao})
        fila.enviar_tudo_agora()
        self.assertEqual(len(self.planilha.planilha), 4)
        fila.adicionar_varias(reg.todas_as_linhas())  # botão "Reenviar tudo"
        fila.enviar_tudo_agora()
        self.assertEqual(len(self.planilha.planilha), 4)
        self.assertEqual(self.planilha.pedidos, 2)


@unittest.skipUnless(shutil.which("node"), "Node.js não instalado: teste do Code.gs ignorado")
class TestCodeGs(unittest.TestCase):
    """Roda os testes do apps_script/Code.gs com uma planilha simulada (Node.js)."""

    def test_code_gs(self):
        resultado = subprocess.run(
            ["node", str(RAIZ / "tests" / "apps_script" / "testar_code_gs.js")],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
        self.assertIn("10 de 10", resultado.stdout)


if __name__ == "__main__":
    unittest.main()
