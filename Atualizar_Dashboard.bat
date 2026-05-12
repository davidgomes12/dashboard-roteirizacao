@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: Executa pipeline ETL
python pipeline.py
if %ERRORLEVEL% NEQ 0 (
    msg * "ERRO: Verifique se os arquivos Excel estao fechados."
    exit /b 1
)

:: Gera index.html standalone (sem servidor, sem Python)
python gerar_index.py

:: Mata servidor antigo, inicia novo oculto, abre dashboard e check de metas
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }; Start-Process python -ArgumentList '-m','http.server','8080' -WindowStyle Hidden; Start-Sleep 2; Start-Process 'http://localhost:8080/dashboard.html'; Start-Sleep 1; Start-Process 'http://localhost:8080/check_metas.html'"

:: Envia dados atualizados para o GitHub (em segundo plano, nao bloqueia)
set MSG=Dados atualizados: %DATE% %TIME:~0,8%
powershell -NoProfile -WindowStyle Hidden -Command "cd '%~dp0'; git add -u; git commit -m '%MSG%'; git push origin main"
