@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: Mata qualquer servidor existente na porta 8080 (garante que sirva desta pasta)
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

:: Inicia servidor a partir desta pasta e abre o dashboard no navegador
powershell -NoProfile -Command "Start-Process python -ArgumentList '-m','http.server','8080' -WorkingDirectory '%~dp0' -WindowStyle Hidden; Start-Sleep 2; Start-Process 'http://localhost:8080/dashboard.html'"
