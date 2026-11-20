"""Envio das respostas para a Planilha Google (Web App do Google Apps Script).

- Cada resposta (e cada atualização) entra numa FILA gravada em disco
  (estado/fila_envio.json). Se o computador desligar ou ficar sem internet,
  nada se perde: o envio é refeito automaticamente depois.
- A fila guarda só a versão mais recente de cada response_id. Na planilha,
  o Apps Script substitui a linha que já existe com o mesmo response_id,
  então reenviar nunca duplica registros.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable

log = logging.getLogger("termometro.sincronizacao")


class ErroEnvio(Exception):
    pass


def chamar_apps_script(url: str, corpo: dict, timeout: float) -> dict:
    """Faz o POST para o Web App e devolve a resposta (JSON) já conferida."""
    dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
    requisicao = urllib.request.Request(
        url,
        data=dados,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "TermometroEmocional/1.0",
        },
    )
    try:
        # O Google responde com um redirecionamento (302); o urllib o segue
        # sozinho e busca o resultado com GET, que é o comportamento esperado.
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            texto = resposta.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as erro:
        raise ErroEnvio(f"A planilha respondeu com erro HTTP {erro.code}.") from erro
    except (urllib.error.URLError, OSError) as erro:
        motivo = getattr(erro, "reason", erro)
        raise ErroEnvio(f"Sem conexão com a planilha ({motivo}).") from erro
    try:
        resultado = json.loads(texto)
    except ValueError as erro:
        raise ErroEnvio(
            "A planilha respondeu algo inesperado. Confira se a URL termina em /exec e "
            "se o App da Web foi publicado com acesso para 'Qualquer pessoa'."
        ) from erro
    if not isinstance(resultado, dict) or not resultado.get("ok"):
        mensagem = resultado.get("erro") if isinstance(resultado, dict) else None
        raise ErroEnvio(f"A planilha recusou o envio: {mensagem or 'erro desconhecido'}.")
    return resultado


class FilaEnvio:
    """Fila offline com reenvio automático e sem duplicar registros."""

    ESPERA_MAXIMA_S = 300  # no máximo 5 min entre tentativas quando há falhas

    def __init__(
        self,
        caminho: Path,
        obter_config: Callable[[], dict],
        chamar: Callable[[str, dict, float], dict] = chamar_apps_script,
        relogio: Callable[[], float] = time.time,
    ):
        self.caminho = Path(caminho)
        self.obter_config = obter_config
        self.chamar = chamar
        self.relogio = relogio
        self._trava = threading.RLock()
        self._envio = threading.Lock()  # um envio por vez
        self._parar = threading.Event()
        self._acordar = threading.Event()
        self._thread: threading.Thread | None = None
        self.falhas_seguidas = 0
        self.proxima_tentativa = 0.0
        self.ultimo_erro = ""
        self.ultimo_envio_ok: float | None = None
        self.itens: dict[str, dict] = {}
        self.enviados_total = 0
        self.enviados_por_dia: dict[str, int] = {}
        self._carregar()

    # -- persistência -------------------------------------------------------
    def _carregar(self) -> None:
        try:
            with open(self.caminho, "r", encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
        except FileNotFoundError:
            return
        except (OSError, ValueError) as erro:
            # Arquivo corrompido: guarda uma cópia para análise e começa vazio.
            log.error("Fila de envio ilegível (%s); salvando cópia e recomeçando.", erro)
            try:
                os.replace(self.caminho, self.caminho.with_suffix(".corrompido.json"))
            except OSError:
                pass
            return
        self.itens = {item["linha"]["response_id"]: item for item in dados.get("itens", [])}
        self.enviados_total = int(dados.get("enviados_total", 0))
        self.enviados_por_dia = dict(dados.get("enviados_por_dia", {}))
        self.ultimo_envio_ok = dados.get("ultimo_envio_ok")

    def _gravar(self) -> None:
        dados = {
            "itens": list(self.itens.values()),
            "enviados_total": self.enviados_total,
            "enviados_por_dia": dict(sorted(self.enviados_por_dia.items())[-30:]),
            "ultimo_envio_ok": self.ultimo_envio_ok,
        }
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.caminho.parent), prefix=".fila_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as arquivo:
            json.dump(dados, arquivo, ensure_ascii=False)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(tmp, self.caminho)

    # -- uso -----------------------------------------------------------------
    def configurada(self) -> bool:
        sinc = self.obter_config()["sincronizacao"]
        return bool(sinc.get("url")) and bool(sinc.get("token"))

    def adicionar(self, linha: dict) -> None:
        self.adicionar_varias([linha])

    def adicionar_varias(self, linhas: list[dict]) -> None:
        """Coloca (ou substitui) respostas na fila. A mais recente sempre vence."""
        if not linhas:
            return
        agora = self.relogio()
        with self._trava:
            for linha in linhas:
                rid = linha["response_id"]
                anterior = self.itens.get(rid)
                self.itens[rid] = {
                    "linha": dict(linha),
                    "versao": (anterior["versao"] + 1) if anterior else 1,
                    "adicionado_em": agora,
                }
            self._gravar()
        self._acordar.set()

    def pendentes(self) -> int:
        with self._trava:
            return len(self.itens)

    def _lote_pronto(self, forcar: bool) -> list[dict]:
        sinc = self.obter_config()["sincronizacao"]
        limite = self.relogio() - float(sinc.get("atraso_envio_s", 0))
        lote = []
        with self._trava:
            for item in self.itens.values():
                if forcar or item["adicionado_em"] <= limite:
                    lote.append({"linha": dict(item["linha"]), "versao": item["versao"]})
                    if len(lote) >= int(sinc.get("tamanho_lote", 50)):
                        break
        return lote

    def processar_uma_vez(self, forcar: bool = False) -> str:
        """Tenta enviar um lote. Devolve: 'desativada', 'nada', 'ok' ou 'erro'."""
        if not self.configurada():
            return "desativada"
        with self._envio:
            lote = self._lote_pronto(forcar)
            if not lote:
                return "nada"
            sinc = self.obter_config()["sincronizacao"]
            corpo = {"token": sinc["token"], "acao": "gravar", "linhas": [i["linha"] for i in lote]}
            try:
                self.chamar(sinc["url"], corpo, float(sinc.get("timeout_s", 30)))
            except Exception as erro:
                with self._trava:
                    self.falhas_seguidas += 1
                    espera = min(self.ESPERA_MAXIMA_S, 10 * 2 ** (self.falhas_seguidas - 1))
                    self.proxima_tentativa = self.relogio() + espera
                    self.ultimo_erro = str(erro)
                log.warning("Envio falhou (%s). Nova tentativa em %ss.", erro, espera)
                return "erro"
            with self._trava:
                hoje = datetime.now().date().isoformat()
                for item in lote:
                    rid = item["linha"]["response_id"]
                    atual = self.itens.get(rid)
                    # Se a resposta mudou enquanto enviávamos, a versão nova fica na fila.
                    if atual and atual["versao"] == item["versao"]:
                        del self.itens[rid]
                self.enviados_total += len(lote)
                self.enviados_por_dia[hoje] = self.enviados_por_dia.get(hoje, 0) + len(lote)
                self.falhas_seguidas = 0
                self.proxima_tentativa = 0.0
                self.ultimo_erro = ""
                self.ultimo_envio_ok = self.relogio()
                self._gravar()
            log.info("Enviadas %d resposta(s) para a planilha.", len(lote))
            return "ok"

    def enviar_tudo_agora(self) -> str:
        """Envia todos os pendentes, ignorando a espera (botão do admin)."""
        resultado = "nada"
        while self.pendentes():
            resultado = self.processar_uma_vez(forcar=True)
            if resultado != "ok":
                break
        return resultado

    def testar_conexao(self) -> tuple[bool, str]:
        sinc = self.obter_config()["sincronizacao"]
        if not sinc.get("url") or not sinc.get("token"):
            return False, "Preencha a URL e o token da planilha na configuração."
        try:
            resposta = self.chamar(sinc["url"], {"token": sinc["token"], "acao": "ping"}, float(sinc.get("timeout_s", 30)))
        except Exception as erro:
            return False, str(erro)
        nome = resposta.get("planilha", "")
        return True, f"Conectado à planilha {nome}".strip() + "."

    def status(self) -> dict:
        with self._trava:
            hoje = datetime.now().date().isoformat()
            return {
                "configurada": self.configurada(),
                "pendentes": len(self.itens),
                "enviados_hoje": self.enviados_por_dia.get(hoje, 0),
                "enviados_total": self.enviados_total,
                "ultimo_envio_ok": (
                    datetime.fromtimestamp(self.ultimo_envio_ok).strftime("%d/%m/%Y %H:%M:%S")
                    if self.ultimo_envio_ok else ""
                ),
                "ultimo_erro": self.ultimo_erro,
                "proxima_tentativa_em_s": max(0, round(self.proxima_tentativa - self.relogio())) if self.falhas_seguidas else 0,
            }

    # -- envio automático -------------------------------------------------
    def iniciar(self) -> None:
        self._thread = threading.Thread(target=self._laco, name="sincronizacao", daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._parar.set()
        self._acordar.set()

    def _quanto_esperar(self) -> float:
        if not self.configurada():
            return 30.0
        agora = self.relogio()
        if self.falhas_seguidas and agora < self.proxima_tentativa:
            return self.proxima_tentativa - agora
        with self._trava:
            if not self.itens:
                return 60.0
            mais_antigo = min(i["adicionado_em"] for i in self.itens.values())
        atraso = float(self.obter_config()["sincronizacao"].get("atraso_envio_s", 0))
        return max(0.0, mais_antigo + atraso - agora)

    def _laco(self) -> None:
        while not self._parar.is_set():
            espera = self._quanto_esperar()
            if espera > 0:
                self._acordar.wait(min(espera, 60.0))
                self._acordar.clear()
                continue
            try:
                if self.processar_uma_vez() in ("nada", "desativada"):
                    self._parar.wait(1)
            except Exception:  # nunca deixar a thread morrer
                log.exception("Erro inesperado no envio")
                self._parar.wait(10)
