@echo off
chcp 65001 >nul

powershell -NoProfile -Command "$procs = Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like '*watcher.py*' }; if ($procs) { $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; Write-Host 'AutoPush encerrado.' } else { Write-Host 'AutoPush nao estava rodando.' }"

timeout /t 2 /nobreak >nul
