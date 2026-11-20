"""Configuração: padrão válido, exemplo sincronizado, mensagens claras para erros."""
import json
import unittest

from tests.auxiliares import RAIZ, PastaTemporaria, config_teste
from quiosque.config import PADRAO, ErroConfig, carregar_config, mesclar, salvar_config, validar_config
from quiosque.momentos import FUSO_RESERVA, obter_fuso


class TestConfig(unittest.TestCase):
    def test_padrao_valido(self):
        self.assertEqual(validar_config(config_teste()), [])

    def test_exemplo_igual_ao_padrao(self):
        exemplo = json.loads((RAIZ / "config" / "config.exemplo.json").read_text(encoding="utf-8"))
        self.assertEqual(exemplo, PADRAO, "rode a geração do config.exemplo.json após mudar o padrão")

    def test_listas_e_textos_da_especificacao(self):
        self.assertEqual([e["nome"] for e in PADRAO["emocoes"]],
                         ["Feliz", "Animado", "Neutro", "Cansado", "Preocupado", "Triste", "Bravo", "Furioso"])
        self.assertEqual(len(PADRAO["motivos"]["chegada"]["negativo"]["opcoes"]), 7)
        self.assertEqual(len(PADRAO["motivos"]["chegada"]["positivo"]["opcoes"]), 5)
        self.assertEqual(len(PADRAO["motivos"]["saida_final"]["negativo"]["opcoes"]), 8)
        self.assertEqual(len(PADRAO["motivos"]["saida_final"]["positivo"]["opcoes"]), 5)
        self.assertEqual(len(PADRAO["pergunta_do_dia"]["perguntas"]), 5)
        self.assertEqual([e["nome"] for e in PADRAO["emocoes"] if e["acolhimento"]], ["Triste", "Bravo", "Furioso"])
        ligados = {m: PADRAO["momentos"][m]["perguntar_motivo"] for m in PADRAO["momentos"]}
        self.assertEqual(ligados, {"chegada": True, "saida_almoco": False, "volta_almoco": False, "saida_final": True})
        self.assertEqual(PADRAO["tempos"]["inatividade_s"], 3)
        self.assertEqual(PADRAO["tempos"]["agradecimento_s"], 1.5)
        self.assertEqual(PADRAO["tempos"]["bloqueio_novo_registro_s"], 2)
        self.assertEqual((PADRAO["clima"]["latitude"], PADRAO["clima"]["longitude"]), (-29.168, -51.179))

    def test_arquivos_oficiais_da_marca(self):
        """Design system Eurostec: logos oficiais, fundo azul oficial e Google Sans (4 pesos)."""
        for chave in ("logo", "logo_branco", "fundo_azul"):
            self.assertTrue((RAIZ / PADRAO[chave]).is_file(), PADRAO[chave])
        for peso in ("Regular", "Medium", "SemiBold", "Bold"):
            self.assertTrue((RAIZ / "quiosque" / "web" / "fontes" / f"GoogleSans-{peso}.woff2").is_file(), peso)
        css = (RAIZ / "quiosque" / "web" / "estilo.css").read_text(encoding="utf-8")
        self.assertNotIn("gradient(", css, "fundo azul deve ser a imagem oficial, não degradê em CSS")
        import re
        pesos = {int(p) for p in re.findall(r"font-weight:\s*(\d+)", css)}
        self.assertLessEqual(pesos, {400, 500, 600, 700}, "só pesos com arquivo real (sem negrito sintetizado)")

    def test_textos_da_pergunta_do_dia_sem_marcacao(self):
        """O texto da pergunta do dia vai para o CSV: não pode ter a marcação de negrito."""
        for pergunta in PADRAO["pergunta_do_dia"]["perguntas"]:
            self.assertNotIn("*", pergunta["texto"])

    def test_erros_explicados(self):
        casos = [
            ({"kiosk_id": "Quiosque 1!"}, "kiosk_id"),
            ({"pin_admin": 1234}, "pin_admin"),
            ({"momentos": {"chegada": {"inicio": "10:00", "fim": "09:00"}}}, "antes do fim"),
            ({"momentos": {"chegada": {"fim": "12:00"}}}, "sobrepostas"),
            ({"momentos": {"chegada": {"inicio": "7h30"}}}, "HH:MM"),
            ({"sincronizacao": {"url": "http://exemplo.com", "token": "x"}}, "https://"),
            ({"sincronizacao": {"url": "https://script.google.com/x/exec", "token": ""}}, "token"),
            ({"clima": {"latitude": 200}}, "latitude"),
            ({"feriados": ["25/12/2026"]}, "AAAA-MM-DD"),
        ]
        for alteracao, trecho in casos:
            with self.subTest(alteracao=alteracao):
                erros = validar_config(mesclar(PADRAO, alteracao))
                self.assertTrue(any(trecho in e for e in erros), erros)

    def test_config_parcial_completa_com_padrao(self):
        pasta = PastaTemporaria()
        try:
            caminho = pasta.caminho / "config.json"
            caminho.write_text(json.dumps({"kiosk_id": "Q02", "kiosk_local": "Produção"}), encoding="utf-8")
            config = carregar_config(caminho)
            self.assertEqual(config["kiosk_id"], "Q02")
            self.assertEqual(config["momentos"]["chegada"]["inicio"], "05:00")
        finally:
            pasta.limpar()

    def test_cria_config_se_nao_existir_e_faz_backup(self):
        pasta = PastaTemporaria()
        try:
            caminho = pasta.caminho / "config" / "config.json"
            config = carregar_config(caminho)
            self.assertTrue(caminho.exists())
            config["kiosk_local"] = "Expedição"
            salvar_config(caminho, config)
            self.assertEqual(len(list((caminho.parent / "backups").glob("config_*.json"))), 1)
        finally:
            pasta.limpar()

    def test_json_com_erro_de_digitacao(self):
        pasta = PastaTemporaria()
        try:
            caminho = pasta.caminho / "config.json"
            caminho.write_text('{"kiosk_id": "Q01",, }', encoding="utf-8")
            with self.assertRaises(ErroConfig) as contexto:
                carregar_config(caminho)
            self.assertIn("linha 1", contexto.exception.erros[0])
        finally:
            pasta.limpar()

    def test_fuso_de_reserva_no_windows_sem_base_de_fusos(self):
        self.assertIs(obter_fuso("Fuso/Inexistente"), FUSO_RESERVA)
        self.assertEqual(FUSO_RESERVA.utcoffset(None).total_seconds(), -3 * 3600)


if __name__ == "__main__":
    unittest.main()
