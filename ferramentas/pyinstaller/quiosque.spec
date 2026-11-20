# -*- mode: python ; coding: utf-8 -*-
# Gera bin/TermometroQuiosque.exe (arquivo único, sem precisar de Python).
# Uso: pyinstaller --noconfirm --clean --distpath bin --workpath build ferramentas/pyinstaller/quiosque.spec
from pathlib import Path

RAIZ = Path(SPECPATH).resolve().parent.parent

a = Analysis(
    [str(RAIZ / "ferramentas" / "pyinstaller" / "entrada_quiosque.py")],
    pathex=[str(RAIZ)],
    datas=[(str(RAIZ / "quiosque" / "web"), "quiosque/web")],
    hiddenimports=[],
    excludes=["tkinter", "pandas", "numpy", "plotly", "openpyxl", "PIL", "relatorio"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="TermometroQuiosque",
    console=True,
    upx=False,
    debug=False,
    strip=False,
)
