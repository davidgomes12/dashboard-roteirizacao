@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: Executa pipeline ETL (silencioso)
python pipeline.py
if %ERRORLEVEL% NEQ 0 (
    msg * "ERRO: Verifique se os arquivos Excel estao fechados."
    exit /b 1
)

:: Mata servidor antigo, inicia novo oculto, abre navegador
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }; Start-Process python -ArgumentList '-m','http.server','8080' -WindowStyle Hidden; Start-Sleep 2; Start-Process 'http://localhost:8080/dashboard.html'"
