@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title Termômetro Emocional - Gerar executáveis

echo.
echo  Gera bin\TermometroQuiosque.exe e bin\TermometroRelatorio.exe com o PyInstaller.
echo  Rode UMA VEZ num computador Windows com Python 3.12 e internet.
echo  Depois copie a pasta inteira (com a pasta bin) para os quiosques:
echo  eles não vão precisar de Python.
echo.
call "ferramentas\encontrar_python.bat"
if not defined PY (
  echo  [ERRO] Python 3.12 não encontrado. Rode o "instalar.bat" opção 2 antes.
  pause
  exit /b 1
)
if not exist ".venv-build\Scripts\python.exe" "%PY%" -m venv .venv-build
set "PYB=.venv-build\Scripts\python.exe"
"%PYB%" -m pip install --upgrade pip --disable-pip-version-check -q
"%PYB%" -m pip install pyinstaller -r requirements-relatorio.txt --disable-pip-version-check
if errorlevel 1 goto :erro
"%PYB%" -m PyInstaller --noconfirm --clean --distpath bin --workpath build ferramentas\pyinstaller\quiosque.spec
if errorlevel 1 goto :erro
"%PYB%" -m PyInstaller --noconfirm --clean --distpath bin --workpath build ferramentas\pyinstaller\relatorio.spec
if errorlevel 1 goto :erro
echo.
echo  [OK] Executáveis gerados na pasta "bin".
pause
exit /b 0

:erro
echo.
echo  [ERRO] A geração falhou. Veja as mensagens acima.
pause
exit /b 1
