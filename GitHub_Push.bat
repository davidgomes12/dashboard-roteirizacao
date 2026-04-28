@echo off
echo Inicializando repositório Git...
cd /d "c:\Users\david.santos\OneDrive - TIROLEZ\Área de Trabalho\Projeto Indicador Roteiro\ETL"

echo Fazendo git init...
git init

echo Adicionando arquivos...
git add .

echo Fazendo commit...
git commit -m "Initial commit for dashboard"

echo Renomeando branch para main...
git branch -M main

echo Adicionando remote...
git remote add origin https://github.com/davidgomes12/dashboard-roteirizacao.git

echo Fazendo push...
git push -u origin main

echo Pronto! Verifique no GitHub: https://github.com/davidgomes12/dashboard-roteirizacao
pause