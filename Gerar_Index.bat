@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   GERAR HTML STANDALONE
echo   index.html        - uso interativo
echo   apresentacao.html - modo automatico (pen drive / TV)
echo ============================================================
echo.
python scripts\gerar_index.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERRO] Falha ao gerar arquivos.
    pause
    exit /b 1
)
echo Deseja abrir a apresentacao agora? [S/N]
set /p resp="> "
if /i "%resp%"=="S" start "" "%~dp0apresentacao.html"
echo.
pause
