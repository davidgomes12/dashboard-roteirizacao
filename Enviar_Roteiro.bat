@echo off
chcp 65001 >nul
cd /d "%~dp0"
python scripts\enviar_roteiro.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERRO] Verifique os logs acima.
    pause
    exit /b 1
)
