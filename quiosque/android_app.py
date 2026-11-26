"""Ponto de entrada do app Android (tablet).

O app Android (Kotlin) chama estas funções pelo Chaquopy, que roda o Python
dentro do aplicativo. O servidor é o MESMO do quiosque Windows: só muda a
pasta de dados (memória interna do app) e a pasta das telas.

Uso pelo Kotlin:
    py.getModule("quiosque.android_app").callAttr("iniciar", base, web, 8080)
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from .servidor import Aplicacao, configurar_log, criar_servidor

log = logging.getLogger("termometro")

_app: Aplicacao | None = None
_servidor = None
_thread: threading.Thread | None = None
_ambiente_anterior: dict[str, str | None] = {}

_VARIAVEIS = ("TERMOMETRO_BASE", "TERMOMETRO_WEB")


def iniciar(base: str, web: str, porta: int = 8080) -> int:
    """Sobe o servidor do quiosque em 127.0.0.1 e devolve a porta usada.

    - base: pasta de dados (config/, dados/, estado/, logs/, assets/).
    - web: pasta com index.html, estilo.css, app.js e fontes.
    - porta: 8080 no app; use 0 nos testes (o sistema escolhe uma livre).
    Levanta OSError se a porta estiver ocupada e ErroConfig se o config.json
    tiver problemas.
    """
    global _app, _servidor, _thread
    if _servidor is not None:
        return _servidor.server_address[1]

    pasta_base = Path(base)
    pasta_web = Path(web)
    pasta_base.mkdir(parents=True, exist_ok=True)
    _ambiente_anterior.clear()
    _ambiente_anterior.update({nome: os.environ.get(nome) for nome in _VARIAVEIS})
    os.environ["TERMOMETRO_BASE"] = str(pasta_base)
    os.environ["TERMOMETRO_WEB"] = str(pasta_web)

    configurar_log(pasta_base)
    _app = Aplicacao(pasta_base)
    _servidor = criar_servidor(_app, porta, pasta_web)
    _thread = threading.Thread(
        target=_servidor.serve_forever,
        kwargs={"poll_interval": 0.5},
        name="quiosque-http",
        daemon=True,
    )
    _thread.start()
    log.info("Termômetro Emocional (Android) em http://127.0.0.1:%s", _servidor.server_address[1])
    return _servidor.server_address[1]


def parar() -> None:
    """Para o servidor e os envios em segundo plano (usado ao fechar o app)."""
    global _app, _servidor, _thread
    if _app is not None:
        _app.parar()
        _app.registros.tentar_gravar_pendentes()
    if _servidor is not None:
        _servidor.shutdown()
        _servidor.server_close()
    # Devolve as variáveis de ambiente ao estado de antes (não vazam para outros testes).
    for nome, valor in _ambiente_anterior.items():
        if valor is None:
            os.environ.pop(nome, None)
        else:
            os.environ[nome] = valor
    _ambiente_anterior.clear()
    _app = None
    _servidor = None
    _thread = None
