"""Clima pela API Open-Meteo (gratuita, sem chave), com cache em disco.

Sem internet, nada trava: a resposta é gravada com os campos de clima vazios.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable

log = logging.getLogger("termometro.clima")

URL_OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
CAMPOS_CLIMA = [
    "temperatura_c",
    "sensacao_termica_c",
    "precipitacao_mm",
    "codigo_tempo",
    "condicao",
    "dia_ou_noite",
]


def condicao_do_codigo(codigo) -> str:
    """Traduz o código de tempo (padrão WMO) para sol / nublado / chuva / outro."""
    if codigo is None or codigo == "":
        return ""
    codigo = int(codigo)
    if codigo in (0, 1):
        return "sol"  # céu limpo / predominantemente limpo
    if codigo in (2, 3, 45, 48):
        return "nublado"  # parcialmente nublado, encoberto, neblina
    if 51 <= codigo <= 67 or 80 <= codigo <= 82 or 95 <= codigo <= 99:
        return "chuva"  # garoa, chuva, pancadas, trovoada
    return "outro"  # neve, granizo e códigos desconhecidos


def buscar_open_meteo(latitude: float, longitude: float, timeout: float = 10) -> dict:
    parametros = urllib.parse.urlencode({
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,apparent_temperature,precipitation,weather_code,is_day",
        "timezone": "America/Sao_Paulo",
    })
    requisicao = urllib.request.Request(
        f"{URL_OPEN_METEO}?{parametros}",
        headers={"User-Agent": "TermometroEmocional/1.0"},
    )
    with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


def interpretar_resposta(dados: dict) -> dict:
    atual = dados["current"]
    codigo = atual.get("weather_code")
    return {
        "temperatura_c": atual.get("temperature_2m"),
        "sensacao_termica_c": atual.get("apparent_temperature"),
        "precipitacao_mm": atual.get("precipitation"),
        "codigo_tempo": codigo,
        "condicao": condicao_do_codigo(codigo),
        "dia_ou_noite": "dia" if atual.get("is_day") == 1 else "noite",
    }


class ServicoClima:
    """Atualiza o clima a cada X minutos e guarda o último valor em cache."""

    def __init__(
        self,
        caminho_cache: Path,
        obter_config: Callable[[], dict],
        buscar: Callable[..., dict] = buscar_open_meteo,
        relogio: Callable[[], float] = time.time,
    ):
        self.caminho_cache = Path(caminho_cache)
        self.obter_config = obter_config
        self.buscar = buscar
        self.relogio = relogio
        self._trava = threading.Lock()
        self._parar = threading.Event()
        self._acordar = threading.Event()
        self._thread: threading.Thread | None = None
        self.ultimo_erro = ""
        self.ultima_tentativa: float | None = None
        self.cache = self._ler_cache()

    # -- cache ---------------------------------------------------------------
    def _ler_cache(self) -> dict | None:
        try:
            with open(self.caminho_cache, "r", encoding="utf-8") as arquivo:
                cache = json.load(arquivo)
            if "obtido_em" in cache and "valores" in cache:
                return cache
        except (OSError, ValueError):
            pass
        return None

    def _gravar_cache(self, cache: dict) -> None:
        try:
            self.caminho_cache.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(self.caminho_cache.parent), suffix=".json")
            with os.fdopen(fd, "w", encoding="utf-8") as arquivo:
                json.dump(cache, arquivo, ensure_ascii=False)
            os.replace(tmp, self.caminho_cache)
        except OSError as erro:
            log.warning("Não foi possível gravar o cache do clima: %s", erro)

    # -- uso -----------------------------------------------------------------
    def atualizar_agora(self) -> bool:
        config = self.obter_config()["clima"]
        if not config.get("ativo"):
            return False
        self.ultima_tentativa = self.relogio()
        try:
            dados = self.buscar(config["latitude"], config["longitude"])
            valores = interpretar_resposta(dados)
        except Exception as erro:  # sem internet, DNS, timeout, resposta estranha...
            self.ultimo_erro = "Sem conexão com o serviço de clima (api.open-meteo.com)."
            log.info("Clima indisponível: %s: %s", type(erro).__name__, erro)
            return False
        cache = {"obtido_em": self.relogio(), "valores": valores}
        with self._trava:
            self.cache = cache
            self.ultimo_erro = ""
        self._gravar_cache(cache)
        log.info("Clima atualizado: %s", valores)
        return True

    def cache_valido(self) -> bool:
        config = self.obter_config()["clima"]
        if not config.get("ativo") or not self.cache:
            return False
        idade = self.relogio() - float(self.cache["obtido_em"])
        return 0 <= idade <= float(config["validade_max_min"]) * 60

    def dados_para_registro(self) -> dict:
        """Campos de clima para anexar à resposta (vazios se o dado for velho)."""
        with self._trava:
            if self.cache_valido():
                return {c: self.cache["valores"].get(c, "") for c in CAMPOS_CLIMA}
        return {c: "" for c in CAMPOS_CLIMA}

    def status(self) -> dict:
        obtido = self.cache["obtido_em"] if self.cache else None
        return {
            "ativo": bool(self.obter_config()["clima"].get("ativo")),
            "valido": self.cache_valido(),
            "atualizado_em": datetime.fromtimestamp(obtido).strftime("%d/%m/%Y %H:%M") if obtido else "",
            "valores": self.cache["valores"] if self.cache else {},
            "ultimo_erro": self.ultimo_erro,
        }

    # -- atualização automática ---------------------------------------------
    def iniciar(self) -> None:
        self._thread = threading.Thread(target=self._laco, name="clima", daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._parar.set()
        self._acordar.set()

    def pedir_atualizacao(self) -> None:
        self._acordar.set()

    def _laco(self) -> None:
        while not self._parar.is_set():
            ok = self.atualizar_agora()
            intervalo = float(self.obter_config()["clima"]["intervalo_min"]) * 60
            # Se falhou, tenta de novo mais cedo (2 min), sem passar do intervalo.
            espera = intervalo if ok else min(120.0, intervalo)
            self._acordar.wait(espera)
            self._acordar.clear()
