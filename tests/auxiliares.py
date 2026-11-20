"""Ferramentas comuns dos testes automáticos (relógio, clima e planilha falsos)."""
from __future__ import annotations

import copy
import json
import logging
import shutil
import sys
import tempfile
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from quiosque.config import PADRAO  # noqa: E402
from quiosque.momentos import FUSO_RESERVA  # noqa: E402

# Sem mensagens de log no meio do resultado dos testes.
logging.getLogger("termometro").addHandler(logging.NullHandler())


def config_teste(**alteracoes) -> dict:
    config = copy.deepcopy(PADRAO)
    for caminho, valor in alteracoes.items():
        alvo = config
        partes = caminho.split("__")
        for parte in partes[:-1]:
            alvo = alvo[parte]
        alvo[partes[-1]] = valor
    return config


def data_hora(texto: str) -> datetime:
    """'2026-11-18T07:45' → datetime no fuso de Brasília."""
    return datetime.fromisoformat(texto).replace(tzinfo=FUSO_RESERVA)


class RelogioFalso:
    def __init__(self, inicio: str = "2026-11-18T07:45:00"):
        self.atual = data_hora(inicio)

    def __call__(self) -> datetime:
        return self.atual

    def ir_para(self, texto: str) -> None:
        self.atual = data_hora(texto)


class ClimaFalso:
    def __init__(self, valores=None):
        self.valores = valores if valores is not None else {
            "temperatura_c": 18.46, "sensacao_termica_c": 17.0, "precipitacao_mm": 0.2,
            "codigo_tempo": 61, "condicao": "chuva", "dia_ou_noite": "dia",
        }

    def dados_para_registro(self):
        return dict(self.valores)


class FilaFalsa:
    def __init__(self):
        self.linhas = []

    def configurada(self):
        return True

    def adicionar(self, linha):
        self.linhas.append(dict(linha))


class PastaTemporaria:
    def __init__(self):
        self.caminho = Path(tempfile.mkdtemp(prefix="termometro-teste-"))

    def limpar(self):
        shutil.rmtree(self.caminho, ignore_errors=True)


class AppsScriptFalso:
    """Imita o Web App do Google: token, upsert por response_id e redirecionamento 302."""

    def __init__(self, token: str = "segredo", redirecionar: bool = True):
        self.token = token
        self.redirecionar = redirecionar
        self.planilha: dict[str, dict] = {}
        self.pedidos = 0
        self._resultados: dict[str, bytes] = {}
        falso = self

        class Manipulador(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _responder(self, status, corpo: bytes, extra=None):
                self.send_response(status)
                for chave, valor in (extra or {}).items():
                    self.send_header(chave, valor)
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            def do_POST(self):
                falso.pedidos += 1
                tamanho = int(self.headers.get("Content-Length") or 0)
                corpo = json.loads(self.rfile.read(tamanho) or b"{}")
                if corpo.get("token") != falso.token:
                    resultado = {"ok": False, "erro": "token inválido"}
                elif corpo.get("acao") == "ping":
                    resultado = {"ok": True, "planilha": "Planilha de teste"}
                else:
                    inseridas = atualizadas = 0
                    for linha in corpo.get("linhas", []):
                        if linha["response_id"] in falso.planilha:
                            atualizadas += 1
                        else:
                            inseridas += 1
                        falso.planilha[linha["response_id"]] = linha
                    resultado = {"ok": True, "inseridas": inseridas, "atualizadas": atualizadas}
                dados = json.dumps(resultado).encode()
                if falso.redirecionar:  # como o Google: 302 para buscar o resultado com GET
                    chave = str(len(falso._resultados))
                    falso._resultados[chave] = dados
                    self._responder(302, b"", {"Location": f"/resultado/{chave}"})
                else:
                    self._responder(200, dados, {"Content-Type": "application/json"})

            def do_GET(self):
                chave = self.path.rsplit("/", 1)[-1]
                self._responder(200, falso._resultados.get(chave, b"{}"), {"Content-Type": "application/json"})

        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), Manipulador)
        self.url = f"http://127.0.0.1:{self.servidor.server_address[1]}/macros/s/teste/exec"
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()

    def parar(self):
        self.servidor.shutdown()
        self.servidor.server_close()


def porta_fechada() -> str:
    """URL de um endereço sem ninguém escutando (simula 'sem internet')."""
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{porta}/exec"
