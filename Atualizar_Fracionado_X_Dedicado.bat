@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: Regera fracionado_x_dedicado.html a partir de Dados\Fracionado X Dedicado.xlsx
python scripts\gerar_fracionado_x_dedicado.py
if %ERRORLEVEL% NEQ 0 (
    msg * "ERRO ao gerar o Dedicado x Fracionado. Verifique se a planilha esta fechada."
    exit /b 1
)

start "" "fracionado_x_dedicado.html"
