@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title Termômetro Emocional - Quiosque

rem ==================================================================
rem  Inicia o servidor do quiosque e abre o Edge em modo quiosque.
rem  Para sair do modo quiosque: área de administração > "Fechar o
rem  quiosque" (ou Alt+F4 com teclado).
rem ==================================================================
set "PORTA=8080"
set "ENDERECO=http://localhost:%PORTA%"

call :servidor_respondendo
if not errorlevel 1 goto :abrir_navegador

echo Iniciando o Termômetro Emocional...
if exist "bin\TermometroQuiosque.exe" goto :iniciar_exe

call "ferramentas\encontrar_python.bat"
if not defined PY goto :sem_python
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath $env:PY -ArgumentList '-m','quiosque' -WorkingDirectory (Get-Location) -WindowStyle Hidden"
goto :aguardar

:iniciar_exe
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath 'bin\TermometroQuiosque.exe' -WorkingDirectory (Get-Location) -WindowStyle Hidden"

:aguardar
set /a TENTATIVAS=0
:aguardar_laco
call :servidor_respondendo
if not errorlevel 1 goto :abrir_navegador
set /a TENTATIVAS+=1
if %TENTATIVAS% geq 40 goto :servidor_nao_iniciou
ping -n 2 127.0.0.1 >nul
goto :aguardar_laco

:abrir_navegador
set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" set "EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" goto :sem_edge
start "" "%EDGE%" --kiosk %ENDERECO% --edge-kiosk-type=fullscreen --no-first-run --user-data-dir="%LOCALAPPDATA%\TermometroEurostec\Edge" --disable-pinch --overscroll-history-navigation=0 --noerrdialogs
exit /b 0

rem ------------------------------------------------------------------
:servidor_respondendo
curl.exe -s -o nul -m 2 "%ENDERECO%/api/saude" >nul 2>&1
exit /b %errorlevel%

:sem_python
echo.
echo  [ERRO] Não encontrei o programa do quiosque.
echo  Coloque o arquivo TermometroQuiosque.exe na pasta "bin"
echo  ou rode o "instalar.bat" (opção 1). Veja o README.md.
echo.
pause
exit /b 1

:servidor_nao_iniciou
echo.
echo  [ERRO] O servidor do quiosque não respondeu.
echo  Veja o arquivo logs\quiosque.log para saber o motivo
echo  (o mais comum é um erro de digitação no config\config.json).
echo.
pause
exit /b 1

:sem_edge
echo.
echo  [ERRO] Microsoft Edge não encontrado neste computador.
echo  Instale o Edge ou abra manualmente: %ENDERECO%
echo.
pause
exit /b 1
