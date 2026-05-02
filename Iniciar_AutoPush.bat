@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: Verifica se watcher ja esta rodando
powershell -NoProfile -Command "if (Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like '*watcher.py*' }) { Write-Host 'AutoPush ja esta rodando.' } else { Start-Process python -ArgumentList 'watcher.py' -WorkingDirectory '%~dp0' -WindowStyle Minimized; Write-Host 'AutoPush iniciado.' }"

echo.
echo Monitorando alteracoes e enviando ao GitHub automaticamente.
echo Log: %~dp0auto_push.log
echo Para parar: execute Parar_AutoPush.bat
timeout /t 4 /nobreak >nul
