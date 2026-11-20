"""Clima: tradução dos códigos, cache de 15 min e funcionamento sem internet."""
import json
import unittest

from tests.auxiliares import PastaTemporaria, config_teste
from quiosque.clima import ServicoClima, condicao_do_codigo, interpretar_resposta

RESPOSTA_OPEN_METEO = {
    "latitude": -29.17, "longitude": -51.18, "timezone": "America/Sao_Paulo",
    "current": {"time": "2026-11-18T07:45", "interval": 900, "temperature_2m": 16.4,
                "apparent_temperature": 15.2, "precipitation": 0.4, "weather_code": 61, "is_day": 1},
}


class TestClima(unittest.TestCase):
    def setUp(self):
        self.pasta = PastaTemporaria()
        self.config = config_teste()
        self.agora = [1_000_000.0]
        self.buscas = []

    def tearDown(self):
        self.pasta.limpar()

    def servico(self, buscar=None):
        def buscar_padrao(lat, lon):
            self.buscas.append((lat, lon))
            return RESPOSTA_OPEN_METEO
        return ServicoClima(self.pasta.caminho / "cache_clima.json", lambda: self.config,
                            buscar=buscar or buscar_padrao, relogio=lambda: self.agora[0])

    def test_codigos_do_tempo(self):
        for codigo, esperado in {0: "sol", 1: "sol", 2: "nublado", 3: "nublado", 45: "nublado", 48: "nublado",
                                 51: "chuva", 61: "chuva", 65: "chuva", 80: "chuva", 95: "chuva", 99: "chuva",
                                 71: "outro", 77: "outro", 86: "outro"}.items():
            self.assertEqual(condicao_do_codigo(codigo), esperado, codigo)
        self.assertEqual(condicao_do_codigo(None), "")

    def test_interpreta_resposta_da_api(self):
        valores = interpretar_resposta(RESPOSTA_OPEN_METEO)
        self.assertEqual(valores, {"temperatura_c": 16.4, "sensacao_termica_c": 15.2, "precipitacao_mm": 0.4,
                                   "codigo_tempo": 61, "condicao": "chuva", "dia_ou_noite": "dia"})

    def test_usa_coordenadas_do_config(self):
        self.config["clima"].update({"latitude": -23.5, "longitude": -46.6})
        self.servico().atualizar_agora()
        self.assertEqual(self.buscas, [(-23.5, -46.6)])

    def test_cache_valido_e_vencido(self):
        servico = self.servico()
        self.assertTrue(servico.atualizar_agora())
        self.assertEqual(servico.dados_para_registro()["condicao"], "chuva")
        self.agora[0] += 59 * 60
        self.assertEqual(servico.dados_para_registro()["temperatura_c"], 16.4, "ainda vale (até 60 min)")
        self.agora[0] += 2 * 60
        self.assertEqual(servico.dados_para_registro()["temperatura_c"], "", "dado velho não é usado")

    def test_sem_internet_nao_trava_e_grava_vazio(self):
        def sem_internet(lat, lon):
            raise OSError("Sem rede")
        servico = self.servico(sem_internet)
        self.assertFalse(servico.atualizar_agora())
        self.assertEqual(set(servico.dados_para_registro().values()), {""})
        self.assertIn("Sem conexão", servico.status()["ultimo_erro"])

    def test_cache_em_disco_sobrevive_ao_reinicio(self):
        self.servico().atualizar_agora()
        cache = json.loads((self.pasta.caminho / "cache_clima.json").read_text(encoding="utf-8"))
        self.assertEqual(cache["valores"]["codigo_tempo"], 61)

        def sem_internet(lat, lon):
            raise OSError("Sem rede")
        reaberto = self.servico(sem_internet)
        self.assertEqual(reaberto.dados_para_registro()["condicao"], "chuva")

    def test_clima_desligado(self):
        self.config["clima"]["ativo"] = False
        servico = self.servico()
        self.assertFalse(servico.atualizar_agora())
        self.assertEqual(self.buscas, [])
        self.assertEqual(set(servico.dados_para_registro().values()), {""})


if __name__ == "__main__":
    unittest.main()
