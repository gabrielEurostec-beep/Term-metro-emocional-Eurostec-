"""Fila offline: sem internet nada se perde; quando a conexão volta, tudo é enviado."""
import time
import unittest

from tests.auxiliares import AppsScriptFalso, ClimaFalso, PastaTemporaria, RelogioFalso, config_teste, porta_fechada
from quiosque.registros import Registros
from quiosque.sincronizacao import FilaEnvio

ID = "0b6f5c1e-6a0e-4f61-9d4f-0a6b1c2d3e4f"


class TestFilaOffline(unittest.TestCase):
    def setUp(self):
        self.pasta = PastaTemporaria()
        self.planilha = AppsScriptFalso(token="segredo")
        self.config = config_teste()
        self.config["sincronizacao"].update({"url": porta_fechada(), "token": "segredo", "atraso_envio_s": 0, "timeout_s": 3})
        self.arquivo_fila = self.pasta.caminho / "estado" / "fila_envio.json"
        self.fila = FilaEnvio(self.arquivo_fila, lambda: self.config)
        self.reg = Registros(self.pasta.caminho / "dados", self.pasta.caminho / "estado",
                             lambda: self.config, RelogioFalso(), clima=ClimaFalso(), fila=self.fila)

    def tearDown(self):
        self.fila.parar()
        self.planilha.parar()
        self.pasta.limpar()

    def ficar_online(self):
        self.config["sincronizacao"]["url"] = self.planilha.url

    def test_sem_internet_guarda_e_depois_envia(self):
        self.reg.criar({"response_id": ID, "momento": "chegada", "momento_automatico": True, "emocao": "Triste"})
        self.reg.atualizar(ID, {"motivo": "Família/vida pessoal"})
        self.assertEqual(self.fila.processar_uma_vez(), "erro")
        self.assertEqual(self.fila.pendentes(), 1, "criação + atualização = 1 item na fila")
        self.assertIn("Sem conexão", self.fila.status()["ultimo_erro"])
        self.assertGreater(self.fila.proxima_tentativa, time.time(), "espera antes de tentar de novo")
        # a resposta continua gravada localmente
        self.assertEqual(self.reg.contagem_dia(), 1)

        self.ficar_online()
        self.assertEqual(self.fila.processar_uma_vez(forcar=True), "ok")
        self.assertEqual(self.fila.pendentes(), 0)
        self.assertEqual(len(self.planilha.planilha), 1)
        self.assertEqual(self.planilha.planilha[ID]["motivo"], "Família/vida pessoal")
        self.assertEqual(self.fila.status()["ultimo_erro"], "")

    def test_fila_sobrevive_a_reinicio_do_computador(self):
        for emocao in ("Feliz", "Neutro", "Bravo"):
            self.reg.criar({"momento": "chegada", "momento_automatico": True, "emocao": emocao})
        self.fila.processar_uma_vez()
        self.assertTrue(self.arquivo_fila.exists())
        reaberta = FilaEnvio(self.arquivo_fila, lambda: self.config)  # simula reinício
        self.assertEqual(reaberta.pendentes(), 3)
        self.ficar_online()
        self.assertEqual(reaberta.enviar_tudo_agora(), "ok")
        self.assertEqual(len(self.planilha.planilha), 3)
        self.assertEqual(FilaEnvio(self.arquivo_fila, lambda: self.config).pendentes(), 0)

    def test_espera_cresce_com_falhas_seguidas(self):
        self.reg.criar({"momento": "chegada", "momento_automatico": True, "emocao": "Feliz"})
        esperas = []
        for _ in range(4):
            self.fila.processar_uma_vez(forcar=True)
            esperas.append(round(self.fila.proxima_tentativa - time.time()))
        self.assertEqual(esperas, sorted(esperas))
        self.assertLessEqual(esperas[-1], FilaEnvio.ESPERA_MAXIMA_S)

    def test_envio_automatico_em_segundo_plano(self):
        self.ficar_online()
        self.fila.iniciar()
        self.reg.criar({"response_id": ID, "momento": "chegada", "momento_automatico": True, "emocao": "Animado"})
        limite = time.time() + 5
        while time.time() < limite and ID not in self.planilha.planilha:
            time.sleep(0.05)
        self.assertIn(ID, self.planilha.planilha)

    def test_token_errado_mantem_na_fila(self):
        self.ficar_online()
        self.config["sincronizacao"]["token"] = "errado"
        self.reg.criar({"momento": "chegada", "momento_automatico": True, "emocao": "Feliz"})
        self.assertEqual(self.fila.processar_uma_vez(), "erro")
        self.assertIn("token inválido", self.fila.status()["ultimo_erro"])
        self.assertEqual(self.fila.pendentes(), 1)

    def test_segue_o_redirecionamento_do_google(self):
        self.assertTrue(self.planilha.redirecionar)
        self.ficar_online()
        ok, mensagem = self.fila.testar_conexao()
        self.assertTrue(ok, mensagem)
        self.assertIn("Planilha de teste", mensagem)

    def test_sem_planilha_configurada_nao_enfileira(self):
        self.config["sincronizacao"].update({"url": "", "token": ""})
        self.reg.criar({"momento": "chegada", "momento_automatico": True, "emocao": "Feliz"})
        self.assertEqual(self.fila.pendentes(), 0)
        self.assertEqual(self.fila.processar_uma_vez(), "desativada")
        self.assertEqual(self.reg.contagem_dia(), 1, "o CSV local continua sendo gravado")

    def test_atraso_junta_criacao_e_atualizacao_num_envio(self):
        self.ficar_online()
        self.config["sincronizacao"]["atraso_envio_s"] = 60
        self.reg.criar({"response_id": ID, "momento": "chegada", "momento_automatico": True, "emocao": "Cansado"})
        self.assertEqual(self.fila.processar_uma_vez(), "nada", "ainda dentro do atraso")
        self.reg.atualizar(ID, {"motivo": "Sono/cansaço"})
        self.assertEqual(self.fila.processar_uma_vez(forcar=True), "ok")
        self.assertEqual(self.planilha.pedidos, 1)
        self.assertEqual(self.planilha.planilha[ID]["motivo"], "Sono/cansaço")


if __name__ == "__main__":
    unittest.main()
