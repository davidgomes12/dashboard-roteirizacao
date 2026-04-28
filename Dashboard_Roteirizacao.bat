@echo off
echo Iniciando servidor do Dashboard da Roteirização...
cd /d "c:\Users\david.santos\OneDrive - TIROLEZ\Área de Trabalho\Projeto Indicador Roteiro\ETL"
start cmd /k "python -m http.server 8080"
timeout /t 3 /nobreak > nul
start http://localhost:8080/dashboard.html
echo Dashboard aberto no navegador. Servidor rodando em segundo plano.