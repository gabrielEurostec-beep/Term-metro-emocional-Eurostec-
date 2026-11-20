@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title Termômetro Emocional - Início automático

echo.
echo ============================================================
echo   Iniciar o quiosque junto com o Windows
echo ============================================================
echo.
set "ATALHO=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Termometro Emocional Eurostec.lnk"
set "ALVO=%~dp0iniciar_quiosque.bat"
set "PASTA=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:ATALHO); $s.TargetPath=$env:ALVO; $s.WorkingDirectory=$env:PASTA; $s.WindowStyle=7; $s.Description='Termometro Emocional - CIPA Eurostec'; $s.Save()"
if errorlevel 1 goto :erro_atalho
echo  [OK] O quiosque vai abrir sozinho quando este usuário entrar no Windows.
echo       (atalho criado em: %ATALHO%)
echo.

echo ------------------------------------------------------------
echo   Energia: a tela nunca desliga e o computador nunca hiberna
echo ------------------------------------------------------------
choice /c SN /n /m "Ajustar a energia agora? Recomendado para quiosques. [S/N]: "
if errorlevel 2 goto :fim
powercfg /change monitor-timeout-ac 0
powercfg /change monitor-timeout-dc 0
powercfg /change standby-timeout-ac 0
powercfg /change standby-timeout-dc 0
powercfg /change hibernate-timeout-ac 0
powercfg /change hibernate-timeout-dc 0
reg add "HKCU\Control Panel\Desktop" /v ScreenSaveActive /t REG_SZ /d 0 /f >nul
echo  [OK] Tela e suspensão configuradas para "Nunca" e proteção de tela desligada.
echo.
echo  Veja no README.md como ativar o login automático do Windows e
echo  como evitar que o Windows Update reinicie no horário de trabalho.

:fim
echo.
pause
exit /b 0

:erro_atalho
echo  [ERRO] Não foi possível criar o atalho de inicialização.
pause
exit /b 1
