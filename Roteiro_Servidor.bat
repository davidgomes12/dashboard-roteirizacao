@echo off
echo Iniciando servidor do Indicador de Roteiro...
cd /d "c:\Users\david.santos\OneDrive - TIROLEZ\Área de Trabalho\Projeto Indicador Roteiro\ETL"
start cmd /k "python -m http.server 8080"
timeout /t 3 /nobreak > nul
start http://localhost:8080/roteiro.html
echo Roteiro aberto no navegador. Servidor rodando em segundo plano.