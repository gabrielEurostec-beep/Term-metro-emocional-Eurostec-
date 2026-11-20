@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title Termômetro Emocional - Relatório quinzenal

echo.
echo ============================================================
echo   Relatório quinzenal - Termômetro Emocional
echo ============================================================
echo.
set "ENTRADA=%~1"
if "%ENTRADA%"=="" (
  echo  Pasta com os CSVs: "entrada_relatorio" ^(padrão^)
  echo  Dica: você também pode arrastar outra pasta para cima deste arquivo.
) else (
  echo  Pasta com os CSVs: %ENTRADA%
)
echo.
set "INICIO="
set "FIM="
set /p "INICIO=Data inicial (AAAA-MM-DD) ou Enter para usar todos os dados: "
if not "%INICIO%"=="" set /p "FIM=Data final (AAAA-MM-DD) ou Enter para ir até o último dia: "

set "ARG_ENTRADA="
set "ARG_INICIO="
set "ARG_FIM="
if not "%ENTRADA%"=="" set ARG_ENTRADA=--entrada "%ENTRADA%"
if not "%INICIO%"=="" set ARG_INICIO=--inicio %INICIO%
if not "%FIM%"=="" set ARG_FIM=--fim %FIM%
echo.

if exist "bin\TermometroRelatorio.exe" (
  "bin\TermometroRelatorio.exe" %ARG_ENTRADA% %ARG_INICIO% %ARG_FIM%
  goto :fim
)
call "ferramentas\encontrar_python.bat"
if not defined PY goto :sem_python
"%PY%" -c "import pandas, openpyxl, plotly" >nul 2>&1
if errorlevel 1 goto :sem_bibliotecas
"%PY%" -m relatorio %ARG_ENTRADA% %ARG_INICIO% %ARG_FIM%

:fim
echo.
pause
exit /b 0

:sem_python
echo  [ERRO] Python não encontrado. Rode o "instalar.bat" e escolha a opção 2.
pause
exit /b 1

:sem_bibliotecas
echo  [ERRO] Faltam as bibliotecas do relatório. Rode o "instalar.bat" e escolha a opção 2.
pause
exit /b 1
