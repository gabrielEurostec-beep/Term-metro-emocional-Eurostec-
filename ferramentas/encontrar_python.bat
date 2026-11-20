@echo off
rem ------------------------------------------------------------------
rem  Procura o Python 3.12 (ou mais novo) e guarda o caminho em PY.
rem  Usado pelos outros arquivos .bat. Não precisa abrir este arquivo.
rem ------------------------------------------------------------------
set "PY="
set "RAIZ_TERMOMETRO=%~dp0.."
if exist "%RAIZ_TERMOMETRO%\.venv\Scripts\python.exe" set "PY=%RAIZ_TERMOMETRO%\.venv\Scripts\python.exe"
if defined PY goto :eof

for /f "delims=" %%i in ('py -3 -c "import sys; print(sys.executable if sys.version_info >= (3, 12) else '')" 2^>nul') do set "PY=%%i"
if defined PY goto :eof

for /f "delims=" %%i in ('python -c "import sys; print(sys.executable if sys.version_info >= (3, 12) else '')" 2^>nul') do set "PY=%%i"
if defined PY goto :eof

for %%v in (314 313 312) do (
  if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe"
  if not defined PY if exist "%ProgramFiles%\Python%%v\python.exe" set "PY=%ProgramFiles%\Python%%v\python.exe"
)
goto :eof
