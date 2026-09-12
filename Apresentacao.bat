@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ================================================================
echo   SERVIDOR DE APRESENTACAO - ROTEIRIZACAO 2026
echo   Rede local (porta 5050) + Tunel publico (Cloudflare)
echo ================================================================
echo.
python scripts\servidor_apresentacao.py
pause
