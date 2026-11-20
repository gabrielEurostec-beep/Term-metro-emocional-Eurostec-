"""Gravação imediata no toque 1, atualização pelo toque 2 e validação dos dados."""
import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

from tests.auxiliares import ClimaFalso, FilaFalsa, PastaTemporaria, RelogioFalso, config_teste
from quiosque import registros as modulo_registros
from quiosque.config import salvar_config
from quiosque.formato import COLUNAS, ler_csv
from quiosque.registros import ErroValidacao, NaoEncontrado, Registros

ID = "0b6f5c1e-6a0e-4f61-9d4f-0a6b1c2d3e4f"
ID2 = "1c7a6d2f-7b1f-4a72-8e5a-1b7c2d3e4f50"


class BaseRegistros(unittest.TestCase):
    def setUp(self):
        self.pasta = PastaTemporaria()
        self.config = config_teste()
        self.relogio = RelogioFalso("2026-11-18T07:45:12")
        self.fila = FilaFalsa()
        self.reg = self.novo_registros()

    def tearDown(self):
        self.pasta.limpar()

    def novo_registros(self):
        return Registros(
            self.pasta.caminho / "dados", self.pasta.caminho / "estado",
            lambda: self.config, self.relogio, clima=ClimaFalso(), fila=self.fila,
        )

    def csv_do_dia(self, data="2026-11-18"):
        return self.pasta.caminho / "dados" / f"respostas_Q01_{data}.csv"


class TestToque1GravaNaHora(BaseRegistros):
    def test_emocao_gravada_imediatamente_no_csv(self):
        linha, criada = self.reg.criar({"response_id": ID, "momento": "chegada", "momento_automatico": True, "emocao": "Cansado"})
        self.assertTrue(criada)
        # o CSV já existe e já tem a linha, antes de qualquer outro toque
        linhas = ler_csv(self.csv_do_dia())
        self.assertEqual(len(linhas), 1)
        gravada = linhas[0]
        self.assertEqual(gravada["response_id"], ID)
        self.assertEqual(gravada["kiosk_id"], "Q01")
        self.assertEqual(gravada["kiosk_local"], "Portaria")
        self.assertEqual(gravada["timestamp"], "2026-11-18T07:45:12-03:00")
        self.assertEqual(gravada["data"], "2026-11-18")
        self.assertEqual(gravada["dia_semana"], "quarta")
        self.assertEqual(gravada["hora"], "07:45:12")
        self.assertEqual(gravada["momento"], "chegada")
        self.assertEqual(gravada["momento_automatico"], "sim")
        self.assertEqual(gravada["emocao"], "Cansado")
        self.assertEqual(gravada["valencia"], "negativa")
        self.assertEqual(gravada["pontuacao"], -1)
        self.assertEqual(gravada["motivo"], "")
        self.assertEqual(gravada["condicao"], "chuva")
        self.assertEqual(gravada["versao_app"], "1.0.0")
        # e foi para a fila de envio da planilha
        self.assertEqual(len(self.fila.linhas), 1)

    def test_formato_do_csv_para_excel(self):
        self.reg.criar({"response_id": ID, "momento": "chegada", "momento_automatico": False, "emocao": "Feliz"})
        bruto = self.csv_do_dia().read_bytes()
        self.assertTrue(bruto.startswith(b"\xef\xbb\xbf"), "UTF-8 com BOM")
        texto = bruto.decode("utf-8-sig")
        cabecalho, linha = texto.split("\r\n")[:2]
        self.assertEqual(cabecalho.split(";"), COLUNAS)
        valores = dict(zip(COLUNAS, linha.split(";")))
        self.assertEqual(valores["temperatura_c"], "18,5", "decimal com vírgula")
        self.assertEqual(valores["precipitacao_mm"], "0,2")
        self.assertEqual(valores["momento_automatico"], "não")
        self.assertEqual(valores["pontuacao"], "2")

    def test_pontuacao_e_valencia_padrao(self):
        esperado = {"Feliz": (2, "positiva"), "Animado": (2, "positiva"), "Neutro": (0, "neutra"),
                    "Cansado": (-1, "negativa"), "Preocupado": (-1, "negativa"), "Triste": (-2, "negativa"),
                    "Bravo": (-2, "negativa"), "Furioso": (-3, "negativa")}
        for emocao, (pontos, valencia) in esperado.items():
            linha, _ = self.reg.criar({"momento": "saida_almoco", "momento_automatico": True, "emocao": emocao})
            self.assertEqual((linha["pontuacao"], linha["valencia"]), (pontos, valencia), emocao)
        self.assertEqual(len(ler_csv(self.csv_do_dia())), 8)
        self.assertEqual(self.reg.contagem_dia(), 8)

    def test_mesmo_id_nao_duplica(self):
        self.reg.criar({"response_id": ID, "momento": "chegada", "momento_automatico": True, "emocao": "Feliz"})
        _, criada = self.reg.criar({"response_id": ID, "momento": "chegada", "momento_automatico": True, "emocao": "Feliz"})
        self.assertFalse(criada)
        self.assertEqual(len(ler_csv(self.csv_do_dia())), 1)

    def test_sem_clima_campos_vazios(self):
        self.reg.clima = ClimaFalso({c: "" for c in ClimaFalso().valores})
        linha, _ = self.reg.criar({"momento": "chegada", "momento_automatico": True, "emocao": "Feliz"})
        self.assertEqual(linha["temperatura_c"], "")
        self.assertEqual(ler_csv(self.csv_do_dia())[0]["condicao"], "")


class TestToque2Atualiza(BaseRegistros):
    def test_motivo_atualiza_a_mesma_linha(self):
        self.reg.criar({"response_id": ID, "momento": "chegada", "momento_automatico": True, "emocao": "Cansado"})
        self.relogio.ir_para("2026-11-18T07:45:15")
        self.reg.atualizar(ID, {"motivo": "Sono/cansaço"})
        linhas = ler_csv(self.csv_do_dia())
        self.assertEqual(len(linhas), 1, "atualiza, não cria outra linha")
        self.assertEqual(linhas[0]["response_id"], ID)
        self.assertEqual(linhas[0]["motivo"], "Sono/cansaço")
        self.assertEqual(linhas[0]["hora"], "07:45:12", "mantém a hora do 1º toque")
        self.assertEqual(self.fila.linhas[-1]["motivo"], "Sono/cansaço", "atualização também vai para a planilha")

    def test_pergunta_do_dia_na_saida(self):
        self.relogio.ir_para("2026-11-18T17:01:00")
        self.reg.criar({"response_id": ID, "momento": "saida_final", "momento_automatico": True, "emocao": "Feliz"})
        self.reg.atualizar(ID, {"motivo": "Dia produtivo"})
        self.reg.atualizar(ID, {"resposta_pergunta_do_dia": "Sim"})
        linha = ler_csv(self.csv_do_dia())[0]
        self.assertEqual(linha["motivo"], "Dia produtivo")
        self.assertTrue(linha["pergunta_do_dia"].endswith("?"))
        self.assertEqual(linha["resposta_pergunta_do_dia"], "Sim")

    def test_atualizacao_depois_de_reiniciar_o_quiosque(self):
        self.reg.criar({"response_id": ID, "momento": "chegada", "momento_automatico": True, "emocao": "Triste"})
        outro = self.novo_registros()  # simula o servidor reiniciado
        self.assertEqual(outro.contagem_dia(), 1)
        outro.atualizar(ID, {"motivo": "Saúde/dor"})
        self.assertEqual(ler_csv(self.csv_do_dia())[0]["motivo"], "Saúde/dor")


class TestNadaQueIdentifique(BaseRegistros):
    """Só valores das listas do config são aceitos: impossível gravar texto livre."""

    def test_recusa_campos_extras(self):
        for extra in ({"nome": "João"}, {"matricula": "123"}, {"cracha": "9"}, {"foto": "x"}):
            with self.subTest(extra=extra), self.assertRaises(ErroValidacao):
                self.reg.criar({"momento": "chegada", "momento_automatico": True, "emocao": "Feliz", **extra})
        self.reg.criar({"response_id": ID, "momento": "chegada", "momento_automatico": True, "emocao": "Feliz"})
        with self.assertRaises(ErroValidacao):
            self.reg.atualizar(ID, {"motivo": "Descansei bem", "comentario": "texto livre"})

    def test_recusa_valores_fora_das_listas(self):
        with self.assertRaises(ErroValidacao):
            self.reg.criar({"momento": "chegada", "momento_automatico": True, "emocao": "Eufórico"})
        with self.assertRaises(ErroValidacao):
            self.reg.criar({"momento": "lanche", "momento_automatico": True, "emocao": "Feliz"})
        with self.assertRaises(ErroValidacao):
            self.reg.criar({"momento": "chegada", "momento_automatico": "sim", "emocao": "Feliz"})
        with self.assertRaises(ErroValidacao):
            self.reg.criar({"response_id": "meu-nome", "momento": "chegada", "momento_automatico": True, "emocao": "Feliz"})
        self.reg.criar({"response_id": ID, "momento": "chegada", "momento_automatico": True, "emocao": "Feliz"})
        with self.assertRaises(ErroValidacao):
            self.reg.atualizar(ID, {"motivo": "Escrevi qualquer coisa"})
        with self.assertRaises(ErroValidacao):
            self.reg.atualizar(ID, {"motivo": "Sono/cansaço"})  # é da lista NEGATIVA; a emoção foi positiva
        with self.assertRaises(ErroValidacao):
            self.reg.atualizar(ID, {"resposta_pergunta_do_dia": "Sim"})  # pergunta do dia só na saída
        self.assertEqual(ler_csv(self.csv_do_dia())[0]["motivo"], "")

    def test_motivo_so_onde_esta_ligado(self):
        self.reg.criar({"response_id": ID, "momento": "saida_almoco", "momento_automatico": True, "emocao": "Triste"})
        with self.assertRaises(ErroValidacao):
            self.reg.atualizar(ID, {"motivo": "Sono/cansaço"})
        self.reg.criar({"response_id": ID2, "momento": "chegada", "momento_automatico": True, "emocao": "Neutro"})
        with self.assertRaises(ErroValidacao):
            self.reg.atualizar(ID2, {"motivo": "Prefiro não dizer"})

    def test_id_desconhecido(self):
        with self.assertRaises(NaoEncontrado):
            self.reg.atualizar(ID, {"motivo": "Financeiro"})


class TestCsvBloqueado(BaseRegistros):
    """Se o CSV estiver aberto no Excel, nada se perde."""

    def test_copia_de_seguranca_e_regravacao(self):
        original = modulo_registros.escrever_csv
        bloqueado = {"sim": True}

        def escrever(caminho, linhas):
            if bloqueado["sim"] and "dados" in str(caminho):
                raise PermissionError("arquivo em uso")
            return original(caminho, linhas)

        with mock.patch.object(modulo_registros, "escrever_csv", escrever), mock.patch("time.sleep"):
            self.reg.criar({"response_id": ID, "momento": "chegada", "momento_automatico": True, "emocao": "Feliz"})
            recuperacao = self.pasta.caminho / "estado" / "recuperacao_Q01_2026-11-18.csv"
            self.assertTrue(recuperacao.exists())
            self.assertIn("Excel", self.reg.status()["erro"])
            self.assertEqual(self.reg.contagem_dia(), 1)
            bloqueado["sim"] = False
            self.reg.tentar_gravar_pendentes()
        self.assertEqual(len(ler_csv(self.csv_do_dia())), 1)
        self.assertFalse(recuperacao.exists())
        self.assertEqual(self.reg.status()["erro"], "")


class TestApiHttp(unittest.TestCase):
    """O mesmo fluxo pela API do servidor (como o navegador faz)."""

    @classmethod
    def setUpClass(cls):
        from quiosque.servidor import Aplicacao, criar_servidor

        cls.pasta = PastaTemporaria()
        import shutil
        from tests.auxiliares import RAIZ
        shutil.copytree(RAIZ / "assets", cls.pasta.caminho / "assets")
        config = config_teste()
        salvar_config(cls.pasta.caminho / "config" / "config.json", config, fazer_backup=False)
        cls.relogio = RelogioFalso("2026-11-18T07:45:00")
        cls.app = Aplicacao(cls.pasta.caminho, iniciar_servicos=False, relogio=cls.relogio)
        cls.servidor = criar_servidor(cls.app, 0)
        cls.url = f"http://127.0.0.1:{cls.servidor.server_address[1]}"
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()
        cls.pasta.limpar()

    def pedir(self, caminho, corpo=None, cabecalhos=None):
        dados = json.dumps(corpo).encode() if corpo is not None else None
        req = urllib.request.Request(self.url + caminho, data=dados, method="POST" if dados else "GET",
                                     headers={"Content-Type": "application/json", **(cabecalhos or {})})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as erro:
            return erro.code, json.loads(erro.read() or b"{}")

    def test_fluxo_completo_pela_api(self):
        status, estado = self.pedir("/api/estado")
        self.assertEqual(status, 200)
        self.assertEqual(estado["momento_atual"], "chegada")
        antes = estado["contagem_hoje"]
        status, r = self.pedir("/api/respostas", {"response_id": ID, "momento": "chegada", "momento_automatico": True, "emocao": "Preocupado"})
        self.assertEqual(status, 201)
        self.assertEqual(r["contagem_hoje"], antes + 1)
        csv = self.pasta.caminho / "dados" / "respostas_Q01_2026-11-18.csv"
        self.assertEqual(ler_csv(csv)[-1]["emocao"], "Preocupado")
        status, r = self.pedir(f"/api/respostas/{ID}", {"motivo": "Financeiro"})
        self.assertEqual(status, 200)
        self.assertEqual([l["motivo"] for l in ler_csv(csv) if l["response_id"] == ID], ["Financeiro"])
        status, r = self.pedir("/api/respostas", {"momento": "chegada", "momento_automatico": True, "emocao": "Feliz", "nome": "x"})
        self.assertEqual(status, 400)

    def test_estado_publico_nao_expoe_pin_nem_token(self):
        _, estado = self.pedir("/api/estado")
        texto = json.dumps(estado)
        self.assertNotIn("pin_admin", texto)
        self.assertNotIn("token", texto)
        self.assertNotIn("pontuacao", texto)

    def test_somente_localhost(self):
        status, r = self.pedir("/api/estado", cabecalhos={"Host": "quiosque.empresa.com"})
        self.assertEqual(status, 403)
        endereco = self.servidor.server_address[0]
        self.assertEqual(endereco, "127.0.0.1")

    def test_administracao_exige_pin(self):
        status, _ = self.pedir("/api/admin/status")
        self.assertEqual(status, 401)
        status, _ = self.pedir("/api/admin/login", {"pin": "0000"})
        self.assertEqual(status, 401)
        status, r = self.pedir("/api/admin/login", {"pin": "2468"})
        self.assertEqual(status, 200)
        token = {"X-Admin-Token": r["token"]}
        status, s = self.pedir("/api/admin/status", cabecalhos=token)
        self.assertEqual(status, 200)
        for chave in ("contagens_hoje", "sincronizacao", "clima", "csv"):
            self.assertIn(chave, s)
        status, r = self.pedir("/api/admin/config", {"config": {"kiosk_id": "Q 01!"}}, token)
        self.assertEqual(status, 400)
        self.assertTrue(r["erros"])

    def test_arquivos_oficiais_da_marca(self):
        for caminho, tipo in (("/marca/logo-azul", "image/png"), ("/marca/logo-branco", "image/png"),
                              ("/marca/fundo-azul", "image/jpeg"), ("/fontes/GoogleSans-Bold.woff2", "font/woff2")):
            with urllib.request.urlopen(self.url + caminho, timeout=5) as r:
                self.assertEqual(r.headers["Content-Type"], tipo, caminho)
                self.assertGreater(len(r.read()), 1000)

    def test_arquivos_das_telas(self):
        for caminho, tipo in (("/", "text/html"), ("/app.js", "application/javascript"), ("/estilo.css", "text/css")):
            with urllib.request.urlopen(self.url + caminho, timeout=5) as r:
                self.assertIn(tipo, r.headers["Content-Type"])
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(self.url + "/../config/config.json", timeout=5)


if __name__ == "__main__":
    unittest.main()
