@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title Termômetro Emocional - Instalação

echo.
echo ============================================================
echo   Termômetro Emocional - CIPA Eurostec - Instalação
echo ============================================================
echo.
echo   [1] Este computador será um QUIOSQUE (ponto de coleta)
echo   [2] Este é o computador da CIPA (gerar relatórios)
echo   [3] Os dois (por exemplo, para testar)
echo.
choice /c 123 /n /m "Digite 1, 2 ou 3: "
set "OPCAO=%errorlevel%"
if "%OPCAO%"=="1" call :quiosque
if "%OPCAO%"=="2" call :relatorio
if "%OPCAO%"=="3" call :quiosque
if "%OPCAO%"=="3" call :relatorio
echo.
echo ============================================================
echo   Instalação concluída. Consulte o README.md para os próximos passos.
echo ============================================================
echo.
pause
exit /b 0

rem ==================================================================
:quiosque
echo.
echo --- Quiosque ---------------------------------------------------
if exist "bin\TermometroQuiosque.exe" (
  echo  [OK] Executável encontrado: não é preciso instalar o Python.
  "bin\TermometroQuiosque.exe" --configurar
  goto :quiosque_inicio
)
call :garantir_python
if not defined PY exit /b 1
"%PY%" -m quiosque --configurar

:quiosque_inicio
echo.
choice /c SN /n /m "Abrir o quiosque sozinho sempre que o Windows ligar? [S/N]: "
if errorlevel 2 goto :quiosque_fim
call "configurar_inicio_automatico.bat"
:quiosque_fim
echo.
echo  Para abrir o quiosque agora: dê dois cliques em "iniciar_quiosque.bat".
exit /b 0

rem ==================================================================
:relatorio
echo.
echo --- Relatórios (computador da CIPA) ------------------------------
if not exist "entrada_relatorio" mkdir "entrada_relatorio"
if exist "bin\TermometroRelatorio.exe" (
  echo  [OK] Executável do relatório encontrado: não é preciso instalar nada.
  exit /b 0
)
call :garantir_python
if not defined PY exit /b 1
if not exist ".venv\Scripts\python.exe" (
  echo  Criando o ambiente do relatório...
  "%PY%" -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
  echo  [ERRO] Não foi possível criar a pasta .venv.
  exit /b 1
)
echo  Instalando pandas, openpyxl e plotly (precisa de internet; pode levar alguns minutos)...
".venv\Scripts\python.exe" -m pip install --upgrade pip --disable-pip-version-check -q
".venv\Scripts\python.exe" -m pip install -r requirements-relatorio.txt --disable-pip-version-check
if errorlevel 1 (
  echo  [ERRO] A instalação das bibliotecas falhou. Confira a internet e tente de novo.
  exit /b 1
)
echo  [OK] Pronto. Coloque os CSVs na pasta "entrada_relatorio" e use "gerar_relatorio.bat".
exit /b 0

rem ==================================================================
:garantir_python
call "ferramentas\encontrar_python.bat"
if defined PY (
  echo  [OK] Python encontrado: %PY%
  exit /b 0
)
echo  O Python 3.12 não foi encontrado. Tentando instalar com o winget...
where winget >nul 2>&1
if errorlevel 1 goto :python_manual
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
call "ferramentas\encontrar_python.bat"
if defined PY (
  echo  [OK] Python instalado: %PY%
  exit /b 0
)
:python_manual
echo.
echo  [AÇÃO NECESSÁRIA] Instale o Python 3.12:
echo    1. Acesse https://www.python.org/downloads/windows/
echo    2. Baixe o "Windows installer (64-bit)" da versão 3.12
echo    3. Na instalação, MARQUE "Add python.exe to PATH"
echo    4. Rode este instalar.bat de novo
echo.
exit /b 1
