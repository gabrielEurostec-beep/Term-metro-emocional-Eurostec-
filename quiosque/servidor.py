"""Servidor do quiosque: entrega as telas e recebe as respostas.

Escuta SOMENTE em 127.0.0.1 (o próprio computador). Só biblioteca padrão.
"""
from __future__ import annotations

import argparse
import copy
import hmac
import json
import logging
import logging.handlers
import os
import secrets
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import config as cfg
from .clima import ServicoClima
from .exportacao import exportar_csvs, listar_pendrives, pasta_exportacao_local
from .formato import MOMENTOS, VERSAO_APP
from .momentos import agora as agora_config
from .momentos import detectar_momento, pergunta_do_dia
from .registros import ErroValidacao, NaoEncontrado, Registros
from .sincronizacao import FilaEnvio

log = logging.getLogger("termometro")

HOSTS_PERMITIDOS = {"localhost", "127.0.0.1", "[::1]"}
# Tipos fixos: no Windows, o registro às vezes associa .js a "text/plain",
# o que faria o navegador recusar o script.
TIPOS = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}
EXTENSOES_LOGO = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"}
TAMANHO_MAXIMO_PEDIDO = 256 * 1024
VALIDADE_SESSAO_ADMIN_S = 30 * 60


class Aplicacao:
    """Junta configuração, gravação, fila, clima e sessões de administração."""

    def __init__(self, base: Path, iniciar_servicos: bool = True, relogio=None):
        self.base = Path(base)
        self.caminho_config = cfg.caminho_config(self.base)
        self.config = cfg.carregar_config(self.caminho_config)
        self._relogio_externo = relogio
        self._deslocamento_teste = self._ler_relogio_de_teste()
        estado = self.base / "estado"
        self.clima = ServicoClima(estado / "cache_clima.json", self.obter_config)
        self.fila = FilaEnvio(estado / "fila_envio.json", self.obter_config)
        self.registros = Registros(
            self.base / "dados", estado, self.obter_config, self.agora,
            clima=self.clima, fila=self.fila,
        )
        self._sessoes: dict[str, float] = {}
        self._tentativas_pin: list[float] = []
        self._trava = threading.Lock()
        self.encerrando = threading.Event()
        if iniciar_servicos:
            self.clima.iniciar()
            self.fila.iniciar()
            threading.Thread(target=self._laco_manutencao, name="manutencao", daemon=True).start()

    # -- utilidades -------------------------------------------------------
    def _ler_relogio_de_teste(self):
        """SÓ PARA TESTES: TERMOMETRO_DATA_HORA_TESTE=2026-11-18T07:45:00 faz o
        quiosque "viver" a partir dessa data e hora (o relógio continua andando)."""
        valor = os.environ.get("TERMOMETRO_DATA_HORA_TESTE")
        if not valor:
            return timedelta(0)
        real = agora_config(self.config)
        simulado = datetime.fromisoformat(valor).replace(tzinfo=real.tzinfo)
        log.warning("RELÓGIO DE TESTE ATIVO: %s", simulado.isoformat())
        return simulado - real

    def obter_config(self) -> dict:
        return self.config

    def agora(self):
        if self._relogio_externo:
            return self._relogio_externo()
        return agora_config(self.config) + self._deslocamento_teste

    def _laco_manutencao(self) -> None:
        while not self.encerrando.wait(10):
            self.registros.tentar_gravar_pendentes()

    # -- dados públicos para as telas ------------------------------------
    def estado_publico(self) -> dict:
        c = self.config
        momento_atual = self.agora()
        pergunta = pergunta_do_dia(momento_atual.date(), c)
        pdd = c["pergunta_do_dia"]
        return {
            "versao": VERSAO_APP,
            "kiosk": {"id": c["kiosk_id"], "local": c["kiosk_local"]},
            "agora": momento_atual.isoformat(timespec="seconds"),
            "momento_atual": detectar_momento(momento_atual, c),
            "momentos": [
                {
                    "id": mid,
                    "nome": c["momentos"][mid]["nome"],
                    "icone": c["momentos"][mid].get("icone", ""),
                    "pergunta": c["momentos"][mid]["pergunta"],
                }
                for mid in MOMENTOS
            ],
            "emocoes": [
                {k: e[k] for k in ("nome", "emoji", "cor", "cor_texto", "valencia", "acolhimento")}
                for e in c["emocoes"]
            ],
            "motivos": {
                mid: {
                    val: cfg.opcoes_motivo(c, mid, val)
                    for val in ("positiva", "negativa")
                    if cfg.opcoes_motivo(c, mid, val)
                }
                for mid in MOMENTOS
            },
            "pergunta_do_dia": (
                {
                    "texto": pergunta["texto"],
                    "opcoes": pdd["opcoes"],
                    "momentos": pdd["momentos"],
                    "mostrar_para_neutro": pdd["mostrar_para_neutro"],
                }
                if pergunta else None
            ),
            "textos": c["textos"],
            "tempos": c["tempos"],
            "contagem_hoje": self.registros.contagem_dia(momento_atual.date().isoformat()),
        }

    # -- administração ------------------------------------------------------
    def login(self, pin: str) -> str | None:
        with self._trava:
            agora = time.time()
            self._tentativas_pin = [t for t in self._tentativas_pin if agora - t < 60]
            if len(self._tentativas_pin) >= 5:
                raise PermissionError("Muitas tentativas. Aguarde 1 minuto.")
            if isinstance(pin, str) and hmac.compare_digest(pin.encode(), self.config["pin_admin"].encode()):
                self._tentativas_pin.clear()
                token = secrets.token_urlsafe(24)
                self._sessoes[token] = agora + VALIDADE_SESSAO_ADMIN_S
                return token
            self._tentativas_pin.append(agora)
            return None

    def sessao_valida(self, token: str | None) -> bool:
        with self._trava:
            agora = time.time()
            self._sessoes = {t: v for t, v in self._sessoes.items() if v > agora}
            if token and token in self._sessoes:
                self._sessoes[token] = agora + VALIDADE_SESSAO_ADMIN_S
                return True
            return False

    def status_admin(self) -> dict:
        hoje = self.agora().date().isoformat()
        return {
            "versao": VERSAO_APP,
            "kiosk": {"id": self.config["kiosk_id"], "local": self.config["kiosk_local"]},
            "agora": self.agora().strftime("%d/%m/%Y %H:%M:%S"),
            "momento_atual": detectar_momento(self.agora(), self.config),
            "contagens_hoje": self.registros.contagens_por_momento(hoje),
            "sincronizacao": self.fila.status(),
            "clima": self.clima.status(),
            "csv": self.registros.status(),
            "pendrives": listar_pendrives(),
            "windows": sys.platform == "win32",
        }

    def salvar_config(self, novo: dict) -> list[str]:
        if not isinstance(novo, dict):
            return ["Configuração inválida."]
        completo = cfg.mesclar(cfg.PADRAO, novo)
        erros = cfg.validar_config(completo)
        if erros:
            return erros
        url_antes = self.config["sincronizacao"].get("url")
        cfg.salvar_config(self.caminho_config, novo)
        self.config = completo
        log.info("Configuração atualizada pela área de administração.")
        if completo["sincronizacao"].get("url") and completo["sincronizacao"]["url"] != url_antes:
            # Planilha nova (ou configurada pela 1ª vez): manda todo o histórico.
            self.fila.adicionar_varias(self.registros.todas_as_linhas())
        self.clima.pedir_atualizacao()
        return []

    def exportar(self, destino: str | None) -> dict:
        arquivos = self.registros.arquivos_csv()
        if not arquivos:
            raise ErroValidacao("Ainda não há respostas gravadas para exportar.")
        if destino:
            letras = {p["letra"] for p in listar_pendrives()}
            if destino not in letras:
                raise ErroValidacao("Pendrive não encontrado. Conecte-o e tente de novo.")
            raiz = Path(destino + "\\")
        else:
            raiz = pasta_exportacao_local(self.base)
        return exportar_csvs(arquivos, raiz, self.config["kiosk_id"])

    def fechar_navegador_e_encerrar(self) -> None:
        """Fecha o Edge do quiosque (só no Windows) e encerra o servidor."""
        if sys.platform == "win32":
            comando = (
                "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | "
                "Where-Object { $_.CommandLine -like '*TermometroEurostec*' } | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
            )
            subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", comando],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        self.encerrando.set()

    def parar(self) -> None:
        self.encerrando.set()
        self.clima.parar()
        self.fila.parar()


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def criar_manipulador(app: Aplicacao, pasta_web: Path):
    pasta_web = pasta_web.resolve()

    class Manipulador(BaseHTTPRequestHandler):
        server_version = "TermometroEmocional/" + VERSAO_APP
        protocol_version = "HTTP/1.1"

        def log_message(self, formato, *args):  # silencia o log padrão no console
            log.debug("%s - %s", self.address_string(), formato % args)

        # -- respostas ----------------------------------------------------
        def _enviar(self, status: int, corpo: bytes, tipo: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(corpo)

        def _json(self, status: int, dados: dict) -> None:
            self._enviar(status, json.dumps(dados, ensure_ascii=False).encode("utf-8"),
                         "application/json; charset=utf-8")

        def _erro(self, status: int, mensagem: str) -> None:
            self._json(status, {"ok": False, "erro": mensagem})

        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].lower()
            if host not in HOSTS_PERMITIDOS:
                self._erro(HTTPStatus.FORBIDDEN, "Acesso permitido somente pelo próprio computador.")
                return False
            return True

        def _ler_json(self):
            if "application/json" not in (self.headers.get("Content-Type") or ""):
                raise ErroValidacao("Envie os dados em JSON.")
            tamanho = int(self.headers.get("Content-Length") or 0)
            if tamanho > TAMANHO_MAXIMO_PEDIDO:
                raise ErroValidacao("Pedido grande demais.")
            bruto = self.rfile.read(tamanho) if tamanho else b"{}"
            try:
                return json.loads(bruto.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as erro:
                raise ErroValidacao("JSON inválido.") from erro

        def _admin_ok(self) -> bool:
            if app.sessao_valida(self.headers.get("X-Admin-Token")):
                return True
            self._erro(HTTPStatus.UNAUTHORIZED, "Sessão de administração expirada. Digite o PIN novamente.")
            return False

        # -- GET ------------------------------------------------------------
        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            if not self._host_ok():
                return
            caminho = urlparse(self.path).path
            try:
                if caminho == "/api/saude":
                    return self._json(200, {"ok": True, "versao": VERSAO_APP})
                if caminho == "/api/estado":
                    return self._json(200, {"ok": True, **app.estado_publico()})
                if caminho == "/api/admin/status":
                    if self._admin_ok():
                        self._json(200, {"ok": True, **app.status_admin()})
                    return
                if caminho == "/api/admin/config":
                    if self._admin_ok():
                        self._json(200, {"ok": True, "config": app.config, "padrao": cfg.PADRAO})
                    return
                if caminho == "/logo":
                    logo = (app.base / app.config["logo"]).resolve()
                    if logo.suffix.lower() not in EXTENSOES_LOGO:
                        return self._erro(404, "Logo deve ser uma imagem.")
                    return self._arquivo(logo, checar_pasta=False)
                if caminho in ("/", "/index.html"):
                    caminho = "/index.html"
                return self._arquivo((pasta_web / caminho.lstrip("/")).resolve())
            except Exception:
                log.exception("Erro ao responder GET %s", caminho)
                self._erro(500, "Erro interno.")

        def _arquivo(self, arquivo: Path, checar_pasta: bool = True) -> None:
            if checar_pasta and pasta_web not in arquivo.parents:
                return self._erro(404, "Não encontrado.")
            if not arquivo.is_file():
                return self._erro(404, "Não encontrado.")
            tipo = TIPOS.get(arquivo.suffix.lower(), "application/octet-stream")
            self._enviar(200, arquivo.read_bytes(), tipo)

        # -- POST -----------------------------------------------------------
        def do_POST(self):
            if not self._host_ok():
                return
            caminho = urlparse(self.path).path
            try:
                dados = self._ler_json()
                if caminho == "/api/respostas":
                    linha, criada = app.registros.criar(dados)
                    return self._json(201 if criada else 200, {
                        "ok": True,
                        "response_id": linha["response_id"],
                        "contagem_hoje": app.registros.contagem_dia(linha["data"]),
                    })
                if caminho.startswith("/api/respostas/"):
                    rid = caminho.rsplit("/", 1)[-1]
                    linha = app.registros.atualizar(rid, dados)
                    return self._json(200, {
                        "ok": True,
                        "response_id": linha["response_id"],
                        "contagem_hoje": app.registros.contagem_dia(linha["data"]),
                    })
                if caminho == "/api/admin/login":
                    try:
                        token = app.login(dados.get("pin"))
                    except PermissionError as erro:
                        return self._erro(429, str(erro))
                    if not token:
                        return self._erro(401, "PIN incorreto.")
                    return self._json(200, {"ok": True, "token": token})
                if caminho.startswith("/api/admin/"):
                    if not self._admin_ok():
                        return
                    return self._post_admin(caminho, dados)
                self._erro(404, "Não encontrado.")
            except ErroValidacao as erro:
                self._erro(400, str(erro))
            except NaoEncontrado as erro:
                self._erro(404, str(erro))
            except Exception:
                log.exception("Erro ao responder POST %s", caminho)
                self._erro(500, "Erro interno. Veja o arquivo logs/quiosque.log.")

        def _post_admin(self, caminho: str, dados: dict) -> None:
            if caminho == "/api/admin/config":
                erros = app.salvar_config(dados.get("config"))
                if erros:
                    return self._json(400, {"ok": False, "erro": "Configuração com problemas.", "erros": erros})
                return self._json(200, {"ok": True})
            if caminho == "/api/admin/exportar":
                resultado = app.exportar(dados.get("destino"))
                return self._json(200, {"ok": True, **resultado})
            if caminho == "/api/admin/testar_sincronizacao":
                ok, mensagem = app.fila.testar_conexao()
                return self._json(200, {"ok": ok, "mensagem": mensagem})
            if caminho == "/api/admin/enviar_agora":
                resultado = app.fila.enviar_tudo_agora()
                return self._json(200, {"ok": resultado in ("ok", "nada"), "resultado": resultado,
                                        "status": app.fila.status()})
            if caminho == "/api/admin/reenviar_tudo":
                if not app.fila.configurada():
                    raise ErroValidacao("Configure primeiro a URL e o token da planilha.")
                linhas = app.registros.todas_as_linhas()
                app.fila.adicionar_varias(linhas)
                return self._json(200, {"ok": True, "quantidade": len(linhas)})
            if caminho == "/api/admin/atualizar_clima":
                ok = app.clima.atualizar_agora()
                return self._json(200, {"ok": ok, "clima": app.clima.status()})
            if caminho == "/api/admin/encerrar":
                self._json(200, {"ok": True})
                threading.Timer(0.5, app.fechar_navegador_e_encerrar).start()
                return
            self._erro(404, "Não encontrado.")

    return Manipulador


def criar_servidor(app: Aplicacao, porta: int, pasta_web: Path | None = None) -> ThreadingHTTPServer:
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), criar_manipulador(app, pasta_web or cfg.pasta_web()))
    servidor.daemon_threads = True
    return servidor


# ---------------------------------------------------------------------------
# Linha de comando
# ---------------------------------------------------------------------------

def configurar_log(base: Path) -> None:
    pasta = base / "logs"
    pasta.mkdir(parents=True, exist_ok=True)
    formato = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    arquivo = logging.handlers.RotatingFileHandler(
        pasta / "quiosque.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    arquivo.setFormatter(formato)
    console = logging.StreamHandler()
    console.setFormatter(formato)
    raiz = logging.getLogger("termometro")
    raiz.setLevel(logging.INFO)
    raiz.handlers[:] = [arquivo, console]


def assistente_configuracao(base: Path) -> int:
    """Perguntas simples para criar o config.json deste quiosque."""
    caminho = cfg.caminho_config(base)
    atual = {}
    if caminho.exists():
        try:
            atual = json.loads(caminho.read_text(encoding="utf-8-sig"))
        except ValueError:
            print("Aviso: o config.json atual tem erro; vou criar um novo.")
    completo = cfg.mesclar(cfg.PADRAO, atual)

    def perguntar(texto, padrao, validar):
        while True:
            resposta = input(f"{texto} [{padrao}]: ").strip() or padrao
            erro = validar(resposta)
            if not erro:
                return resposta
            print("  -> " + erro)

    print()
    print("=== Configuração deste quiosque ===")
    print("Pressione Enter para manter o valor entre colchetes.")
    print()
    completo["kiosk_id"] = perguntar(
        "Código do quiosque (ex.: Q01, Q02...)", completo["kiosk_id"],
        lambda v: None if cfg.RE_KIOSK.match(v) else "Use só letras, números, - ou _ (até 20).",
    )
    completo["kiosk_local"] = perguntar(
        "Local do quiosque (ex.: Portaria, Produção)", completo["kiosk_local"],
        lambda v: None if v.strip() else "Preencha o local.",
    )
    completo["pin_admin"] = perguntar(
        "PIN da administração (4 a 8 números)", completo["pin_admin"],
        lambda v: None if v.isdigit() and 4 <= len(v) <= 8 else "Use de 4 a 8 números.",
    )
    erros = cfg.validar_config(completo)
    if erros:
        print("Problemas na configuração:")
        for erro in erros:
            print(" - " + erro)
        return 1
    novo = copy.deepcopy(atual)
    novo.update({k: completo[k] for k in ("kiosk_id", "kiosk_local", "pin_admin")})
    if not atual:
        novo = completo
    cfg.salvar_config(caminho, novo)
    print()
    print(f"Configuração salva em {caminho}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Termômetro Emocional — servidor do quiosque")
    parser.add_argument("--base", help="pasta principal (padrão: automática)")
    parser.add_argument("--porta", type=int, help="porta (padrão: a do config.json, 8080)")
    parser.add_argument("--configurar", action="store_true", help="assistente para criar o config.json")
    args = parser.parse_args(argv)

    base = Path(args.base).resolve() if args.base else cfg.pasta_base()
    if args.configurar:
        return assistente_configuracao(base)

    configurar_log(base)
    try:
        app = Aplicacao(base)
    except cfg.ErroConfig as erro:
        log.error("Não foi possível iniciar: o config.json tem problemas:")
        for item in erro.erros:
            log.error("  - %s", item)
        return 2
    porta = args.porta or int(app.config["porta"])
    try:
        servidor = criar_servidor(app, porta)
    except OSError as erro:
        log.error("A porta %s já está em uso (o quiosque já está aberto?): %s", porta, erro)
        return 3
    threading.Thread(target=lambda: (app.encerrando.wait(), servidor.shutdown()), daemon=True).start()
    log.info("Termômetro Emocional %s — quiosque %s (%s) em http://localhost:%s",
             VERSAO_APP, app.config["kiosk_id"], app.config["kiosk_local"], porta)
    try:
        servidor.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        app.parar()
        app.registros.tentar_gravar_pendentes()
        servidor.server_close()
        log.info("Servidor encerrado.")
    return 0
