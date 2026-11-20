# -*- mode: python ; coding: utf-8 -*-
# Gera bin/TermometroRelatorio.exe (arquivo único, com pandas, openpyxl e plotly).
# Uso: pyinstaller --noconfirm --clean --distpath bin --workpath build ferramentas/pyinstaller/relatorio.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

RAIZ = Path(SPECPATH).resolve().parent.parent

a = Analysis(
    [str(RAIZ / "ferramentas" / "pyinstaller" / "entrada_relatorio.py")],
    pathex=[str(RAIZ)],
    # plotly.min.js é embutido no HTML para o relatório abrir sem internet.
    datas=collect_data_files("plotly"),
    hiddenimports=collect_submodules("plotly.validators") + ["quiosque.formato"],
    excludes=["tkinter", "PIL", "matplotlib", "IPython", "notebook", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="TermometroRelatorio",
    console=True,
    upx=False,
    debug=False,
    strip=False,
)
