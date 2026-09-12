# Dashboard da Roteirização

Dashboard interativo para indicadores de roteirização da Tirolez.

## Acesso Online

Acesse o dashboard em: [https://davidgomes12.github.io/dashboard-roteirizacao/dashboard.html](https://davidgomes12.github.io/dashboard-roteirizacao/dashboard.html)

## Como Usar Localmente

1. Instale Python 3.x
2. Execute: `python -m http.server 8080`
3. Abra: `http://localhost:8080/dashboard.html`

## Atualização de Dados

Para atualizar os dados online:
1. Execute `python scripts/pipeline.py` (ou o atalho `Atualizar_Dashboard.bat`) para gerar `dashboard_data.json`
2. Faça commit e push para o repositório GitHub

## Tecnologias

- HTML/CSS/JavaScript
- Chart.js
- Dados em JSON
## Estrutura de Pastas (ETL/)

```
ETL/
├── *.bat / *.vbs      atalhos de uso diario (clique duplo) - rodam sempre a partir da raiz do ETL
├── *.html             paginas publicadas (dashboard, index, metas, apresentacao, frescal, volume_distribuicao_BR)
├── dashboard.css/.js  fontes do dashboard
├── dashboard_data.json  saida do pipeline
├── logo_*.png         logos usados pelos HTMLs (precisam ficar na raiz)
├── config.json        caminhos das fontes de dados e parametros
├── scripts/           pipeline.py, gerar_index.py, gerar_volume_distribuicao_BR.py,
│                      enviar_dashboard.py, servidor_apresentacao.py, watcher.py
├── templates/         templates puros de HTML (volume_distribuicao_BR_template.html)
├── bin/               cloudflared.exe (tunel da apresentacao)
├── docs/              README.md, INSTRUCOES_GitHub.txt
└── arquivo/           material antigo/auxiliar (_backup_paleta, _check.js, Receita.xlsx, Vaca Branca.png)
```

Os scripts em `scripts/` resolvem os caminhos sozinhos (sobem um nivel ate a raiz do ETL),
entao podem ser chamados de qualquer lugar: `python scripts/gerar_index.py`.
