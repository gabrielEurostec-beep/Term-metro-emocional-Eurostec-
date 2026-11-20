"""Gravação das respostas no CSV diário (a fonte da verdade do quiosque).

- Toque 1 (emoção): a resposta é CRIADA e gravada no CSV na hora, com um
  response_id único.
- Toques seguintes (motivo, pergunta do dia): ATUALIZAM a mesma linha.
- Só são aceitos valores que existem no config.json: não há como gravar
  texto livre nem qualquer dado que identifique a pessoa.
"""
from __future__ import annotations

import csv
import logging
import re
import threading
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from .config import emocao_por_nome, opcoes_motivo
from .formato import COLUNAS, MOMENTOS, VERSAO_APP, escrever_csv, ler_csv, nome_arquivo_dia
from .momentos import dia_semana, pergunta_do_dia

log = logging.getLogger("termometro.registros")

RE_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class ErroValidacao(ValueError):
    """Pedido com dados inválidos (vira HTTP 400)."""


class NaoEncontrado(LookupError):
    """response_id desconhecido (vira HTTP 404)."""


class Registros:
    def __init__(
        self,
        pasta_dados: Path,
        pasta_estado: Path,
        obter_config: Callable[[], dict],
        relogio: Callable[[], datetime],
        clima=None,
        fila=None,
    ):
        self.pasta_dados = Path(pasta_dados)
        self.pasta_estado = Path(pasta_estado)
        self.obter_config = obter_config
        self.relogio = relogio
        self.clima = clima
        self.fila = fila
        self._trava = threading.RLock()
        self._dias: dict[str, dict[str, dict]] = {}  # data -> {response_id: linha}
        self._indice: dict[str, str] = {}  # response_id -> data
        self._kiosk_do_cache = None
        self._pendentes_csv: set[str] = set()
        self.ultimo_erro_csv = ""
        self.pasta_dados.mkdir(parents=True, exist_ok=True)
        self.pasta_estado.mkdir(parents=True, exist_ok=True)
        self._procurar_recuperacoes()

    # -- arquivos -------------------------------------------------------------
    def _kiosk_id(self) -> str:
        return self.obter_config()["kiosk_id"]

    def arquivo_do_dia(self, data_iso: str) -> Path:
        return self.pasta_dados / nome_arquivo_dia(self._kiosk_id(), data_iso)

    def _arquivo_recuperacao(self, data_iso: str) -> Path:
        return self.pasta_estado / f"recuperacao_{self._kiosk_id()}_{data_iso}.csv"

    def _procurar_recuperacoes(self) -> None:
        """Ao iniciar, procura dias que não puderam ser gravados no CSV principal."""
        prefixo = f"recuperacao_{self._kiosk_id()}_"
        for caminho in self.pasta_estado.glob(f"{prefixo}*.csv"):
            data_iso = caminho.stem[len(prefixo):]
            self._carregar_dia(data_iso)
            self._pendentes_csv.add(data_iso)
        self.tentar_gravar_pendentes()

    def _verificar_troca_de_quiosque(self) -> None:
        kiosk = self._kiosk_id()
        if self._kiosk_do_cache not in (None, kiosk):
            # kiosk_id mudou na configuração: começa um cache novo.
            self.tentar_gravar_pendentes()
            self._dias.clear()
            self._indice.clear()
            self._pendentes_csv.clear()
        self._kiosk_do_cache = kiosk

    def _carregar_dia(self, data_iso: str) -> dict[str, dict]:
        self._verificar_troca_de_quiosque()
        if data_iso in self._dias:
            return self._dias[data_iso]
        linhas: dict[str, dict] = {}
        for caminho in (self.arquivo_do_dia(data_iso), self._arquivo_recuperacao(data_iso)):
            if caminho.exists():
                try:
                    for linha in ler_csv(caminho):
                        linhas[linha["response_id"]] = linha
                except (OSError, ValueError, csv.Error) as erro:
                    log.error("Não foi possível ler %s: %s", caminho, erro)
        self._dias[data_iso] = linhas
        for rid in linhas:
            self._indice[rid] = data_iso
        return linhas

    def _gravar_dia(self, data_iso: str) -> bool:
        linhas = list(self._dias[data_iso].values())
        destino = self.arquivo_do_dia(data_iso)
        ultimo_erro = None
        for espera in (0, 0.15, 0.5):  # antivírus pode prender o arquivo por instantes
            if espera:
                time.sleep(espera)
            try:
                escrever_csv(destino, linhas)
                break
            except OSError as erro:
                ultimo_erro = erro
        else:
            # Ex.: o CSV está aberto no Excel. Guardamos uma cópia de segurança
            # e tentamos de novo a cada poucos segundos.
            self.ultimo_erro_csv = (
                f"Não foi possível gravar {destino.name} ({ultimo_erro}). "
                "Feche o arquivo se ele estiver aberto no Excel."
            )
            log.error(self.ultimo_erro_csv)
            self._pendentes_csv.add(data_iso)
            try:
                escrever_csv(self._arquivo_recuperacao(data_iso), linhas)
            except OSError:
                log.exception("Falhou também a cópia de segurança do dia %s", data_iso)
            return False
        if data_iso in self._pendentes_csv:
            self._pendentes_csv.discard(data_iso)
            try:
                self._arquivo_recuperacao(data_iso).unlink()
            except OSError:
                pass
            log.info("CSV de %s gravado novamente com sucesso.", data_iso)
        if not self._pendentes_csv:
            self.ultimo_erro_csv = ""
        return True

    def tentar_gravar_pendentes(self) -> None:
        with self._trava:
            for data_iso in sorted(self._pendentes_csv):
                if data_iso in self._dias:
                    self._gravar_dia(data_iso)

    def _localizar(self, response_id: str) -> tuple[str, dict] | None:
        data_iso = self._indice.get(response_id)
        if data_iso is None:
            hoje = self.relogio().date()
            for dia in (hoje, hoje - timedelta(days=1)):
                self._carregar_dia(dia.isoformat())
            data_iso = self._indice.get(response_id)
        if data_iso is None:
            return None
        return data_iso, self._carregar_dia(data_iso)[response_id]

    def _enfileirar(self, linha: dict) -> None:
        if self.fila is not None and self.fila.configurada():
            try:
                self.fila.adicionar(linha)
            except Exception:  # a fila nunca pode impedir a gravação local
                log.exception("Não foi possível colocar a resposta na fila de envio")

    # -- operações --------------------------------------------------------
    def criar(self, dados: dict) -> tuple[dict, bool]:
        """Toque 1: cria a resposta e grava no CSV imediatamente.

        Devolve (linha, criada). Se o mesmo response_id chegar de novo
        (ex.: o navegador repetiu o pedido), devolve a linha existente.
        """
        if not isinstance(dados, dict):
            raise ErroValidacao("Pedido inválido.")
        permitidos = {"response_id", "momento", "momento_automatico", "emocao"}
        extras = set(dados) - permitidos
        if extras:
            raise ErroValidacao(f"Campo não permitido: {', '.join(sorted(extras))}.")
        config = self.obter_config()
        emocao = emocao_por_nome(config, dados.get("emocao"))
        if emocao is None:
            raise ErroValidacao("Emoção desconhecida.")
        momento = dados.get("momento")
        if momento not in MOMENTOS:
            raise ErroValidacao("Momento desconhecido.")
        automatico = dados.get("momento_automatico")
        if not isinstance(automatico, bool):
            raise ErroValidacao("'momento_automatico' deve ser verdadeiro ou falso.")
        rid = str(dados.get("response_id") or uuid.uuid4()).lower()
        if not RE_UUID.match(rid):
            raise ErroValidacao("response_id inválido.")

        with self._trava:
            existente = self._localizar(rid)
            if existente:
                return dict(existente[1]), False
            agora = self.relogio()
            data_iso = agora.date().isoformat()
            linha = {coluna: "" for coluna in COLUNAS}
            linha.update({
                "response_id": rid,
                "kiosk_id": config["kiosk_id"],
                "kiosk_local": config["kiosk_local"],
                "timestamp": agora.isoformat(timespec="seconds"),
                "data": data_iso,
                "dia_semana": dia_semana(agora),
                "hora": agora.strftime("%H:%M:%S"),
                "momento": momento,
                "momento_automatico": "sim" if automatico else "não",
                "emocao": emocao["nome"],
                "valencia": emocao["valencia"],
                "pontuacao": emocao["pontuacao"],
                "versao_app": VERSAO_APP,
            })
            if self.clima is not None:
                linha.update(self.clima.dados_para_registro())
            self._carregar_dia(data_iso)[rid] = linha
            self._indice[rid] = data_iso
            self._gravar_dia(data_iso)
            copia = dict(linha)
        self._enfileirar(copia)
        log.info("Nova resposta %s: %s / %s", rid[:8], momento, emocao["nome"])
        return copia, True

    def atualizar(self, response_id: str, dados: dict) -> dict:
        """Toques 2 e 3: completa a MESMA resposta com motivo e/ou pergunta do dia."""
        rid = str(response_id or "").lower()
        if not RE_UUID.match(rid):
            raise ErroValidacao("response_id inválido.")
        if not isinstance(dados, dict) or not dados:
            raise ErroValidacao("Nada para atualizar.")
        extras = set(dados) - {"motivo", "resposta_pergunta_do_dia"}
        if extras:
            raise ErroValidacao(f"Campo não permitido: {', '.join(sorted(extras))}.")
        config = self.obter_config()

        with self._trava:
            encontrado = self._localizar(rid)
            if not encontrado:
                raise NaoEncontrado("Resposta não encontrada.")
            data_iso, linha = encontrado
            novos = {}
            if "motivo" in dados:
                grupo = opcoes_motivo(config, linha["momento"], linha["valencia"])
                if not grupo or dados["motivo"] not in grupo["opcoes"]:
                    raise ErroValidacao("Motivo inválido para esta resposta.")
                novos["motivo"] = dados["motivo"]
            if "resposta_pergunta_do_dia" in dados:
                pdd = config["pergunta_do_dia"]
                pergunta = pergunta_do_dia(date.fromisoformat(linha["data"]), config)
                if not pergunta or linha["momento"] not in pdd.get("momentos", []):
                    raise ErroValidacao("Não há pergunta do dia para esta resposta.")
                if dados["resposta_pergunta_do_dia"] not in pdd["opcoes"]:
                    raise ErroValidacao("Resposta inválida para a pergunta do dia.")
                novos["pergunta_do_dia"] = pergunta["texto"]
                novos["resposta_pergunta_do_dia"] = dados["resposta_pergunta_do_dia"]
            linha.update(novos)
            self._gravar_dia(data_iso)
            copia = dict(linha)
        self._enfileirar(copia)
        log.info("Resposta %s atualizada: %s", rid[:8], ", ".join(novos))
        return copia

    # -- consultas ----------------------------------------------------------
    def contagem_dia(self, data_iso: str | None = None) -> int:
        data_iso = data_iso or self.relogio().date().isoformat()
        with self._trava:
            return len(self._carregar_dia(data_iso))

    def contagens_por_momento(self, data_iso: str | None = None) -> dict:
        data_iso = data_iso or self.relogio().date().isoformat()
        with self._trava:
            linhas = list(self._carregar_dia(data_iso).values())
        contagem = {m: 0 for m in MOMENTOS}
        for linha in linhas:
            if linha["momento"] in contagem:
                contagem[linha["momento"]] += 1
        contagem["total"] = len(linhas)
        return contagem

    def arquivos_csv(self) -> list[Path]:
        return sorted(self.pasta_dados.glob("respostas_*.csv"))

    def todas_as_linhas(self) -> list[dict]:
        """Todas as respostas gravadas neste quiosque (para reenviar à planilha)."""
        self.tentar_gravar_pendentes()
        linhas: dict[str, dict] = {}
        for caminho in self.arquivos_csv():
            try:
                for linha in ler_csv(caminho):
                    linhas[linha["response_id"]] = linha
            except (OSError, ValueError, csv.Error) as erro:
                log.error("Não foi possível ler %s: %s", caminho, erro)
        with self._trava:
            for dia in self._dias.values():
                for rid, linha in dia.items():
                    linhas[rid] = dict(linha)
        return list(linhas.values())

    def status(self) -> dict:
        with self._trava:
            return {
                "pasta": str(self.pasta_dados),
                "arquivos": len(self.arquivos_csv()),
                "pendentes_gravacao": sorted(self._pendentes_csv),
                "erro": self.ultimo_erro_csv,
            }
