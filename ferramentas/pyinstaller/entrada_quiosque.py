"""Ponto de entrada do executável TermometroQuiosque.exe (PyInstaller)."""
import sys

from quiosque.servidor import main

if __name__ == "__main__":
    sys.exit(main())
