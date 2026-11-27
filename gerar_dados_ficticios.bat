@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title Termômetro Emocional - Dados fictícios

echo.
echo  Gera 2 quinzenas de respostas FICTÍCIAS (2 quiosques, ~150 pessoas)
echo  na pasta "dados_ficticios", para testar o relatório.
echo.
call "ferramentas\encontrar_python.bat"
if not defined PY goto :sem_python
"%PY%" ferramentas\gerar_dados_ficticios.py --saida dados_ficticios --com-planilha
if errorlevel 1 goto :fim
echo.
choice /c SN /n /m "Gerar o relatório de teste com esses dados agora? [S/N]: "
if errorlevel 2 goto :fim
"%PY%" -m relatorio --entrada dados_ficticios
:fim
echo.
pause
exit /b 0

:sem_python
echo  [ERRO] Python não encontrado. Rode o "instalar.bat" e escolha a opção 2.
pause
exit /b 1
