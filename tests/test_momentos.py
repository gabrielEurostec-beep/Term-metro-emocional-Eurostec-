"""Detecção automática do momento do dia (inclui fora das janelas e fim de semana)."""
import unittest
from datetime import date

from tests.auxiliares import config_teste, data_hora
from quiosque.momentos import agora, detectar_momento, pergunta_do_dia


class TestDeteccaoDoMomento(unittest.TestCase):
    def setUp(self):
        self.config = config_teste()

    def momento(self, texto):
        return detectar_momento(data_hora(texto), self.config)

    def test_janelas_padrao_e_limites(self):
        # 2026-11-18 é uma quarta-feira
        casos = {
            "2026-11-18T00:00": None,          # madrugada
            "2026-11-18T04:59": None,
            "2026-11-18T05:00": "chegada",     # início faz parte da janela
            "2026-11-18T07:30": "chegada",
            "2026-11-18T09:59": "chegada",
            "2026-11-18T10:00": None,          # fim não faz parte
            "2026-11-18T11:29": None,
            "2026-11-18T11:30": "saida_almoco",
            "2026-11-18T12:19": "saida_almoco",
            "2026-11-18T12:20": "volta_almoco",  # limite entre almoço e volta
            "2026-11-18T13:59": "volta_almoco",
            "2026-11-18T14:00": None,
            "2026-11-18T16:29": None,
            "2026-11-18T16:30": "saida_final",
            "2026-11-18T17:04": "saida_final",
            "2026-11-18T23:59:59": "saida_final",  # "23:59" vale até a meia-noite
        }
        for texto, esperado in casos.items():
            with self.subTest(hora=texto):
                self.assertEqual(self.momento(texto), esperado)

    def test_fora_das_janelas_pede_escolha(self):
        for texto in ("2026-11-18T10:30", "2026-11-18T15:00", "2026-11-18T03:00"):
            self.assertIsNone(self.momento(texto), texto)

    def test_fim_de_semana_pede_escolha(self):
        self.assertIsNone(self.momento("2026-11-21T07:45"))  # sábado
        self.assertIsNone(self.momento("2026-11-22T17:00"))  # domingo
        self.assertEqual(self.momento("2026-11-23T07:45"), "chegada")  # segunda

    def test_todos_os_dias_uteis(self):
        for dia in range(16, 21):  # 16 (segunda) a 20 (sexta) de novembro de 2026
            self.assertEqual(self.momento(f"2026-11-{dia}T07:45"), "chegada")

    def test_feriado_pede_escolha(self):
        self.config["feriados"] = ["2026-11-18"]
        self.assertIsNone(self.momento("2026-11-18T07:45"))
        self.assertEqual(self.momento("2026-11-19T07:45"), "chegada")

    def test_janelas_configuraveis_por_quiosque(self):
        self.config["momentos"]["chegada"]["inicio"] = "06:30"
        self.config["momentos"]["chegada"]["fim"] = "08:00"
        self.assertIsNone(self.momento("2026-11-18T06:00"))
        self.assertEqual(self.momento("2026-11-18T06:30"), "chegada")
        self.assertIsNone(self.momento("2026-11-18T08:00"))

    def test_dias_do_expediente_configuraveis(self):
        self.config["expediente"]["dias"].append("sábado")
        self.assertEqual(self.momento("2026-11-21T07:45"), "chegada")

    def test_relogio_em_horario_de_brasilia(self):
        momento_atual = agora(self.config)
        self.assertEqual(momento_atual.utcoffset().total_seconds(), -3 * 3600)


class TestPerguntaDoDia(unittest.TestCase):
    def test_rodizio_diario(self):
        config = config_teste()
        textos = [pergunta_do_dia(date(2026, 11, d), config)["texto"] for d in range(16, 21)]
        self.assertEqual(len(set(textos)), 5, "5 dias seguidos = 5 perguntas diferentes")
        todas = {p["texto"] for p in config["pergunta_do_dia"]["perguntas"]}
        self.assertEqual(set(textos), todas)

    def test_mesma_pergunta_no_mesmo_dia(self):
        config = config_teste()
        self.assertEqual(pergunta_do_dia(date(2026, 11, 18), config), pergunta_do_dia(date(2026, 11, 18), config))
        self.assertEqual(pergunta_do_dia(date(2026, 11, 18), config), pergunta_do_dia(date(2026, 11, 23), config))

    def test_desligada(self):
        config = config_teste(pergunta_do_dia__ativa=False)
        self.assertIsNone(pergunta_do_dia(date(2026, 11, 18), config))


if __name__ == "__main__":
    unittest.main()
