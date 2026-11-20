@echo off
chcp 65001 >nul
setlocal
set "ATALHO=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Termometro Emocional Eurostec.lnk"
if exist "%ATALHO%" (
  del "%ATALHO%"
  echo  [OK] O quiosque não vai mais abrir sozinho com o Windows.
) else (
  echo  O início automático já estava desligado.
)
echo.
pause
