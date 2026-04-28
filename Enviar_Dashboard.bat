@echo off
chcp 65001 >nul
cd /d "%~dp0"
python enviar_dashboard.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERRO] Verifique os logs acima.
    pause
    exit /b 1
)
