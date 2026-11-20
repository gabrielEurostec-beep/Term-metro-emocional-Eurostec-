@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title Termômetro Emocional - Testes automáticos

call "ferramentas\encontrar_python.bat"
if not defined PY (
  echo  [ERRO] Python não encontrado. Rode o "instalar.bat" e escolha a opção 2.
  pause
  exit /b 1
)
echo  Rodando os testes automáticos...
echo.
"%PY%" -m unittest discover -s tests -t . -v
if errorlevel 1 (
  echo.
  echo  [ATENÇÃO] Algum teste falhou. Veja as mensagens acima.
) else (
  echo.
  echo  [OK] Todos os testes passaram.
)
echo.
pause
