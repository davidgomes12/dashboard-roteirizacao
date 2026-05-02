@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Verificando alteracoes...
git add -u

git diff --cached --quiet
if %ERRORLEVEL% EQU 0 (
    echo Nenhuma alteracao para enviar. Repositorio ja esta atualizado.
    pause
    exit /b 0
)

echo Fazendo commit...
for /f "tokens=1-3 delims=/ " %%a in ("%DATE%") do set DT=%%a/%%b/%%c
for /f "tokens=1-2 delims=:" %%a in ("%TIME%") do set TM=%%a:%%b
git commit -m "Update manual: %DT% %TM%"

echo Enviando para GitHub...
git push origin main

if %ERRORLEVEL% EQU 0 (
    echo.
    echo Sucesso! Dashboard disponivel em:
    echo https://davidgomes12.github.io/dashboard-roteirizacao/dashboard.html
) else (
    echo.
    echo ERRO no push. Verifique a conexao com a internet ou autenticacao GitHub.
)

pause
