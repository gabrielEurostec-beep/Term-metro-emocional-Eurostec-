"""Tela de setor: aparece só na chegada e na saída do dia, sempre, com a opção de pular."""
import unittest

from tests.auxiliares import ClimaFalso, FilaFalsa, PastaTemporaria, RelogioFalso, config_teste
from quiosque.config import PADRAO, setor_perguntado_para, validar_config, mesclar
from quiosque.formato import COLUNAS, ler_csv
from quiosque.registros import ErroValidacao, Registros

ID = "0b6f5c1e-6a0e-4f61-9d4f-0a6b1c2d3e4f"
SETORES_Q01 = ["Administrativo", "Assistência técnica", "Comercial"]


class TestRegraDaTela(unittest.TestCase):
    def test_so_chegada_e_saida_do_dia(self):
        config = config_teste(setores=SETORES_Q01)
        self.assertTrue(setor_perguntado_para(config, "chegada"))
        self.assertTrue(setor_perguntado_para(config, "saida_final"))
        self.assertFalse(setor_perguntado_para(config, "saida_almoco"))
        self.assertFalse(setor_perguntado_para(config, "volta_almoco"))

    def test_sem_setores_nao_pergunta(self):
        self.assertFalse(setor_perguntado_para(config_teste(), "chegada"))

    def test_validacao_dos_setores(self):
        self.assertEqual(validar_config(mesclar(PADRAO, {"setores": SETORES_Q01})), [])
        erros = validar_config(mesclar(PADRAO, {"setores": ["Produção", "produção "]}))
        self.assertTrue(any("aparece duas vezes" in e for e in erros))
        erros = validar_config(mesclar(PADRAO, {"setores": ["  "]}))
        self.assertTrue(any("setores[1]" in e for e in erros))
        erros = validar_config(mesclar(PADRAO, {"setor_momentos": ["almoco"]}))
        self.assertTrue(any("setor_momentos" in e for e in erros))


class TestGravacaoDoSetor(unittest.TestCase):
    def setUp(self):
        self.pasta = PastaTemporaria()
        self.config = config_teste(setores=SETORES_Q01)
        self.relogio = RelogioFalso("2026-11-18T07:45:00")
        self.reg = Registros(self.pasta.caminho / "dados", self.pasta.caminho / "estado",
                             lambda: self.config, self.relogio, clima=ClimaFalso(), fila=FilaFalsa())

    def tearDown(self):
        self.pasta.limpar()

    def csv(self):
        return ler_csv(next((self.pasta.caminho / "dados").glob("respostas_*.csv")))

    def test_colunas_novas_no_csv(self):
        self.assertIn("setor", COLUNAS)
        self.assertIn("setor_perguntado", COLUNAS)

    def test_chegada_marca_pergunta_e_aceita_setor_valido(self):
        self.reg.criar({"response_id": ID, "momento": "chegada", "momento_automatico": True, "emocao": "Feliz"})
        self.assertEqual(self.csv()[0]["setor_perguntado"], "sim")
        self.assertEqual(self.csv()[0]["setor"], "")
        self.reg.atualizar(ID, {"setor": "Comercial"})
        self.assertEqual(self.csv()[0]["setor"], "Comercial")

    def test_almoco_nao_pergunta(self):
        self.relogio.ir_para("2026-11-18T11:45:00")
        self.reg.criar({"response_id": ID, "momento": "saida_almoco", "momento_automatico": True, "emocao": "Feliz"})
        self.assertEqual(self.csv()[0]["setor_perguntado"], "não")
        with self.assertRaises(ErroValidacao):
            self.reg.atualizar(ID, {"setor": "Comercial"})

    def test_setor_fora_da_lista_do_quiosque_e_recusado(self):
        self.reg.criar({"response_id": ID, "momento": "chegada", "momento_automatico": True, "emocao": "Feliz"})
        for invalido in ("Produção", "Comercial; DROP", "", "Nome Completo da Pessoa"):
            with self.subTest(setor=invalido), self.assertRaises(ErroValidacao):
                self.reg.atualizar(ID, {"setor": invalido})

    def test_quiosque_sem_setores_nao_mostra_nem_aceita(self):
        self.config["setores"] = []
        self.reg.criar({"response_id": ID, "momento": "chegada", "momento_automatico": True, "emocao": "Feliz"})
        self.assertEqual(self.csv()[0]["setor_perguntado"], "não")
        with self.assertRaises(ErroValidacao):
            self.reg.atualizar(ID, {"setor": "Comercial"})

    def test_csv_antigo_sem_colunas_novas_continua_lendo(self):
        antigo = self.pasta.caminho / "dados" / "respostas_Q01_2026-11-01.csv"
        antigo.parent.mkdir(parents=True, exist_ok=True)
        colunas_antigas = [c for c in COLUNAS if c not in ("setor", "setor_perguntado")]
        antigo.write_text(";".join(colunas_antigas) + "\r\n" + ";".join(
            {"response_id": ID, "momento": "chegada", "emocao": "Feliz", "pontuacao": "2", "valencia": "positiva"}.get(c, "")
            for c in colunas_antigas) + "\r\n", encoding="utf-8-sig")
        linha = ler_csv(antigo)[0]
        self.assertEqual(linha["emocao"], "Feliz")
        self.assertEqual(linha.get("setor", ""), "")


if __name__ == "__main__":
    unittest.main()
