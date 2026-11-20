"""Exportar os CSVs para um pendrive (plano B da sincronização)."""
from __future__ import annotations

import logging
import os
import shutil
import string
import sys
from datetime import datetime
from pathlib import Path

log = logging.getLogger("termometro.exportacao")

TIPO_REMOVIVEL = 2  # GetDriveTypeW: DRIVE_REMOVABLE


def listar_pendrives() -> list[dict]:
    """Unidades removíveis conectadas (só no Windows). Ex.: [{"letra": "E:", "nome": "KINGSTON"}]"""
    if sys.platform != "win32":
        return []
    import ctypes

    kernel32 = ctypes.windll.kernel32
    unidades = []
    mascara = kernel32.GetLogicalDrives()
    for indice, letra in enumerate(string.ascii_uppercase):
        if not mascara & (1 << indice):
            continue
        raiz = f"{letra}:\\"
        if kernel32.GetDriveTypeW(ctypes.c_wchar_p(raiz)) != TIPO_REMOVIVEL:
            continue
        nome = ctypes.create_unicode_buffer(261)
        ok = kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(raiz), nome, 261, None, None, None, None, 0
        )
        if not ok:
            continue  # leitor de cartão vazio, por exemplo
        unidades.append({"letra": f"{letra}:", "nome": nome.value or "Pendrive"})
    return unidades


def exportar_csvs(arquivos: list[Path], destino_raiz: Path, kiosk_id: str) -> dict:
    """Copia os CSVs para <destino>/TermometroEurostec/<kiosk_id>/."""
    destino = Path(destino_raiz) / "TermometroEurostec" / kiosk_id
    destino.mkdir(parents=True, exist_ok=True)
    copiados = 0
    for arquivo in arquivos:
        shutil.copy2(arquivo, destino / arquivo.name)
        copiados += 1
    # Força a gravação no pendrive antes de a pessoa retirá-lo.
    try:
        fd = os.open(str(destino), os.O_RDONLY)
        os.fsync(fd)
        os.close(fd)
    except OSError:
        pass
    log.info("Exportados %d arquivo(s) para %s", copiados, destino)
    return {"copiados": copiados, "pasta": str(destino)}


def pasta_exportacao_local(base: Path) -> Path:
    return Path(base) / "exportacoes" / datetime.now().strftime("%Y-%m-%d_%H%M%S")
