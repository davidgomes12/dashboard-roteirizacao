# -*- coding: utf-8 -*-
"""
Gera fracionado_x_dedicado.html a partir de Dados/Fracionado X Dedicado.xlsx.

Indicador "Dedicado x Fracionado": para cada romaneio embarcado em veiculo
dedicado, a base traz quanto teria custado o mesmo embarque no modal
fracionado. A diferenca (FRACIONADO - DEDICADO) e o custo evitado.

O HTML sai standalone (dados embutidos, sem servidor e sem Python) e filtra
os meses pela DATA SAIDA.

Uso:  python scripts/gerar_fracionado_x_dedicado.py
"""

import base64
import json
import os
import sys
import warnings
from datetime import datetime

import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning)

ETL_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR  = os.path.dirname(ETL_DIR)
DADOS_DIR = os.path.join(BASE_DIR, "Dados")
FONTE     = os.path.join(DADOS_DIR, "Fracionado X Dedicado.xlsx")
TEMPLATE  = os.path.join(ETL_DIR, "templates", "fracionado_x_dedicado_template.html")
OUTPUT    = os.path.join(ETL_DIR, "fracionado_x_dedicado.html")

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago",
         "set", "out", "nov", "dez"]

# Nome de saida -> possiveis grafias na planilha (acentuacao/espacos variam).
COLUNAS = {
    "data":      ["DATA  SAÍDA", "DATA SAÍDA", "DATA  SAIDA", "DATA SAIDA"],
    "romaneio":  ["NUM. ROMANEIO", "NUM ROMANEIO", "ROMANEIO"],
    "modelo":    ["MODELO_VEICULO", "MODELO VEICULO", "TIPO VEICULAR"],
    "cidade":    ["CIDADE"],
    "nff":       ["Contagem de NFF", "NFF", "QTD NF"],
    "peso":      ["Soma de PESO BRUTO", "PESO BRUTO", "PESO"],
    "valor":     ["Soma de VALOR TOTAL MERC", "VALOR TOTAL MERC", "VALOR"],
    "veiculos":  ["Unnamed: 8", "QTD VEICULOS", "VEICULOS"],
    "dedicado":  ["FRETE_DEDICADO", "FRETE DEDICADO"],
    "fracionado": ["FRETE_FRACIONADO", "FRETE FRACIONADO"],
}


def _achar(df, nomes, obrigatoria=True, rotulo=""):
    """Localiza a coluna aceitando variacoes de acento, espaco e caixa."""
    def chave(s):
        return "".join(ch for ch in str(s).upper() if ch.isalnum())

    mapa = {chave(c): c for c in df.columns}
    for n in nomes:
        if chave(n) in mapa:
            return mapa[chave(n)]
    if obrigatoria:
        sys.exit(
            f"ERRO: coluna {rotulo or nomes[0]!r} nao encontrada em {FONTE}.\n"
            f"       Colunas disponiveis: {list(df.columns)}"
        )
    return None


def carregar():
    if not os.path.exists(FONTE):
        sys.exit(f"ERRO: arquivo nao encontrado: {FONTE}")

    bruto = pd.read_excel(FONTE, sheet_name=0)
    bruto.columns = [str(c).strip() for c in bruto.columns]

    df = pd.DataFrame()
    for saida, nomes in COLUNAS.items():
        col = _achar(bruto, nomes, obrigatoria=(saida != "veiculos"), rotulo=saida)
        if col is not None:
            df[saida] = bruto[col]

    if "veiculos" not in df.columns:
        # Sem a coluna marcadora, cada romaneio conta como um veiculo.
        print("   [AVISO] coluna de contagem de veiculos ausente — "
              "assumindo 1 veiculo por romaneio")
        df["veiculos"] = 1

    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    invalidas = int(df["data"].isna().sum())
    if invalidas:
        print(f"   [AVISO] {invalidas} linhas sem DATA SAIDA valida foram descartadas")
        df = df[df["data"].notna()]
    if df.empty:
        sys.exit("ERRO: nenhuma linha com DATA SAIDA valida.")

    for c in ("nff", "peso", "valor", "veiculos", "dedicado", "fracionado"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    df["modelo"] = df["modelo"].astype(str).str.strip().str.upper()
    df["cidade"] = df["cidade"].astype(str).str.strip().str.upper()
    df["romaneio"] = df["romaneio"].astype(str).str.strip()

    # Custo evitado = o que o fracionado teria custado menos o frete dedicado.
    # Negativo significa que o dedicado saiu mais caro naquele romaneio.
    df["evitado"] = df["fracionado"] - df["dedicado"]

    return df.sort_values("data").reset_index(drop=True)


def construir_dataset(df):
    dt = df["data"].dt

    linhas = []
    for r in df.itertuples(index=False):
        linhas.append([
            r.data.strftime("%Y-%m"),            # 0 competencia (DATA SAIDA)
            r.data.strftime("%d/%m/%Y"),         # 1 data
            r.romaneio,                          # 2
            r.modelo,                            # 3
            r.cidade,                            # 4
            int(r.nff),                          # 5
            round(float(r.peso), 3),             # 6
            round(float(r.valor), 2),            # 7
            int(r.veiculos),                     # 8
            round(float(r.dedicado), 2),         # 9
            round(float(r.fracionado), 2),       # 10
        ])

    competencias = []
    for comp, g in df.groupby(dt.strftime("%Y-%m"), sort=True):
        ano, mes = comp.split("-")
        competencias.append({
            "id": comp,
            "rotulo": f"{MESES[int(mes) - 1]}/{ano[2:]}",
            "mes": MESES[int(mes) - 1],
            "ano": ano,
            "evitado": round(float(g["evitado"].sum()), 2),
            "dedicado": round(float(g["dedicado"].sum()), 2),
            "fracionado": round(float(g["fracionado"].sum()), 2),
            "peso": round(float(g["peso"].sum()), 1),
            "veiculos": int(g["veiculos"].sum()),
            "romaneios": int(len(g)),
        })

    dias = dt.strftime("%d/%m/%Y")
    dados = {
        "gerado": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "periodo": f"{dias.iloc[0]} a {dias.iloc[-1]}",
        "colunas": ["comp", "data", "romaneio", "modelo", "cidade", "nff",
                    "peso", "valor", "veiculos", "dedicado", "fracionado"],
        "competencias": competencias,
        "modelos": sorted(df["modelo"].unique().tolist()),
        "linhas": linhas,
    }

    ult = competencias[-1]
    print(f"   -> {len(linhas):,} romaneios | {len(competencias)} competencias "
          f"({competencias[0]['rotulo']} a {ult['rotulo']})")
    print(f"   -> custo evitado no periodo: R$ {df['evitado'].sum():,.0f} "
          f"| dedicado R$ {df['dedicado'].sum():,.0f} "
          f"| fracionado R$ {df['fracionado'].sum():,.0f}")
    print(f"   -> ultima competencia ({ult['rotulo']}): "
          f"R$ {ult['evitado']:,.0f} evitados | {ult['veiculos']} veiculos "
          f"| {ult['peso']:,.0f} kg")
    return dados


def logo_b64():
    p = os.path.join(ETL_DIR, "logo_tirolez.png")
    if not os.path.exists(p):
        return ""
    with open(p, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def main():
    print("[1/3] Lendo Fracionado X Dedicado.xlsx...")
    df = carregar()
    print(f"   -> {len(df):,} linhas validas")

    print("[2/3] Montando dataset...")
    dados = construir_dataset(df)
    dados["logo"] = logo_b64()

    print("[3/3] Gerando HTML...")
    if not os.path.exists(TEMPLATE):
        sys.exit(f"ERRO: template nao encontrado: {TEMPLATE}")
    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()
    if "/*__DADOS__*/" not in html:
        sys.exit("ERRO: template sem o marcador /*__DADOS__*/")
    payload = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    html = html.replace("/*__DADOS__*/", payload)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)
    kb = os.path.getsize(OUTPUT) / 1024
    print(f"   -> {OUTPUT} ({kb:.0f} KB)")


if __name__ == "__main__":
    main()
