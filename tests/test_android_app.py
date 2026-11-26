"""Ponto de entrada do app Android: o mesmo servidor, com pastas do tablet."""
import json
import shutil
import unittest
import urllib.error
import urllib.request

from tests.auxiliares import RAIZ, PastaTemporaria
from quiosque import android_app


class TestBootstrapAndroid(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = PastaTemporaria()
        cls.base = cls.pasta.caminho / "termometro"
        cls.web = cls.pasta.caminho / "web"
        shutil.copytree(RAIZ / "quiosque" / "web", cls.web)
        shutil.copytree(RAIZ / "assets", cls.base / "assets")
        cls.porta = android_app.iniciar(str(cls.base), str(cls.web), 0)
        cls.url = f"http://127.0.0.1:{cls.porta}"

    @classmethod
    def tearDownClass(cls):
        android_app.parar()
        cls.pasta.limpar()

    def pedir(self, caminho, corpo=None):
        dados = json.dumps(corpo).encode() if corpo is not None else None
        req = urllib.request.Request(self.url + caminho, data=dados, method="POST" if dados else "GET",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.headers.get("Content-Type"), r.read()

    def test_servidor_responde_em_localhost(self):
        status, tipo, corpo = self.pedir("/api/saude")
        self.assertEqual(status, 200)
        self.assertIn(b'"ok": true', corpo)

    def test_telas_e_marca_vem_das_pastas_do_tablet(self):
        status, tipo, corpo = self.pedir("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", tipo)
        self.assertIn(b"tela-inicio", corpo)
        status, tipo, corpo = self.pedir("/marca/logo-azul")
        self.assertEqual(tipo, "image/png")
        self.assertGreater(len(corpo), 1000)

    def test_dados_ficam_na_pasta_do_app(self):
        self.pedir("/api/respostas", {"momento": "chegada", "momento_automatico": True, "emocao": "Feliz"})
        csvs = list((self.base / "dados").glob("respostas_*.csv"))
        self.assertEqual(len(csvs), 1)
        self.assertIn("Feliz", csvs[0].read_text(encoding="utf-8-sig"))

    def test_iniciar_duas_vezes_nao_sobe_outro_servidor(self):
        self.assertEqual(android_app.iniciar(str(self.base), str(self.web), 0), self.porta)

    def test_pasta_web_respeita_a_variavel_do_app(self):
        from quiosque.config import pasta_web
        self.assertEqual(pasta_web(), self.web.resolve())


if __name__ == "__main__":
    unittest.main()
