@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: Verifica se servidor ja esta rodando na porta 8080
powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue; if (-not $c) { Start-Process python -ArgumentList '-m','http.server','8080' -WorkingDirectory '%~dp0' -WindowStyle Hidden; Start-Sleep 2 }; Start-Process 'http://localhost:8080/dashboard.html'"
