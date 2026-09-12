@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: Regera volume_distribuicao_BR.html a partir da Base NF (Dados\NF.xlsx)
python scripts\gerar_volume_distribuicao_BR.py
if %ERRORLEVEL% NEQ 0 (
    msg * "ERRO ao gerar o Volume de Distribuicao BR. Verifique se o NF.xlsx esta fechado."
    exit /b 1
)

start "" "volume_distribuicao_BR.html"
