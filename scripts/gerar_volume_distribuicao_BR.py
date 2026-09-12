"""
Gera o HTML de Volume de Distribuicao BR (volume_distribuicao_BR.html) a partir da Base NF.

Grão do dataset: DIA x EMPRESA x TRANSPORTADORA x LOCAL(cliente+uf+cidade).
Regra da base: 1 LINHA = 1 NOTA FISCAL. Nada e deduplicado, para que a pagina
feche exatamente com os totais da Base NF (Qtd NF, Peso Bruto e Valor).
  - NFF      -> contagem de linhas dentro do grao
  - PESO/VAL -> soma das linhas, sem nenhum descarte
  - ENTREGAS -> CHAVE_ENTREGA = DIA + COD. CLIENTE + COD. TRANSPORTADORA,
                contada no navegador (uma entrega pode cruzar varias linhas do
                grao). Difere do dashboard, que usa so DIA + COD. CLIENTE.

Saida: volume_distribuicao_BR.html (standalone, dados embutidos).
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
NF_PATH   = os.path.join(DADOS_DIR, "NF.xlsx")
TEMPLATE  = os.path.join(ETL_DIR, "templates", "volume_distribuicao_BR_template.html")
OUTPUT    = os.path.join(ETL_DIR, "volume_distribuicao_BR.html")
CACHE     = os.path.join(ETL_DIR, ".cache_volume_distribuicao_BR.pkl")

# Clientes internos (transferencias entre unidades Tirolez) excluidos da
# consulta por definicao do negocio em 12/09/2026. Comparacao por NOME CLIENTE
# em maiuscula e sem espacos nas pontas; a base grava o nome truncado em 15
# caracteres, por isso "TIROLEZ CD RAPO" e "TIROLEZ F REGIN".
CLIENTES_EXCLUIDOS = {
    "TIROLEZ ARAPUA",
    "TIROLEZ CAXAMBU",
    "TIROLEZ CD RAPO",
    "TIROLEZ F REGIN",
    "TIROLEZ LINS",
    "TIROLEZ MATRIZ",
    "TIROLEZ MONTE",
    "TIROLEZ TIROS",
}

# UF -> macrorregiao do IBGE. "US" aparece na base como destino de exportacao.
REGIAO_POR_UF = {
    "AC": "Norte", "AM": "Norte", "AP": "Norte", "PA": "Norte",
    "RO": "Norte", "RR": "Norte", "TO": "Norte",
    "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste",
    "PB": "Nordeste", "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste",
    "SE": "Nordeste",
    "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MS": "Centro-Oeste",
    "MT": "Centro-Oeste",
    "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    "PR": "Sul", "RS": "Sul", "SC": "Sul",
    "US": "Exterior",
}

COLS = ["EMPRESA", "NFF", "DATA  SAÍDA", "COD. CLIENTE", "NOME CLIENTE",
        "UF", "CIDADE", "TRANSPORTADORA", "NOME TRANSPORTADORA",
        "VALOR TOTAL MERC", "PESO BRUTO"]


def carregar_nf():
    """Le a NF com cache pickle keyed pelo mtime do .xlsx + assinatura de COLS.

    COLS entra na chave porque acrescentar uma coluna nao muda o mtime do Excel:
    sem isso o cache antigo (sem a coluna nova) seria reaproveitado e o script
    quebraria com KeyError.
    """
    meta = CACHE + ".meta"
    assinatura = str(os.path.getmtime(NF_PATH)) + "|" + "|".join(COLS)
    if os.path.exists(CACHE) and os.path.exists(meta):
        with open(meta, encoding="utf-8") as f:
            if f.read().strip() == assinatura:
                print("   (cache hit)")
                return pd.read_pickle(CACHE)
    print("   lendo NF.xlsx (pode demorar ~1 min)...")
    df = pd.read_excel(NF_PATH, usecols=COLS)
    df.to_pickle(CACHE)
    with open(meta, "w", encoding="utf-8") as f:
        f.write(assinatura)
    return df


def _fmt_cod(serie):
    """COD. CLIENTE vira string.

    A base traz 4 registros gravados como texto com ponto (ex.: '3.188'); como
    nao da para saber se o ponto e separador de milhar (3188 ja pertence a outro
    cliente), o codigo e mantido como veio, sem fundir com nenhum outro.
    """
    v = pd.to_numeric(serie, errors="coerce")
    quebrados = int(((v % 1) != 0).sum())
    if quebrados:
        print(f"   [AVISO] {quebrados} linhas com COD. CLIENTE nao inteiro "
              f"(mantidos como estao): {sorted(v[(v % 1) != 0].unique())}")
    return v.map(lambda x: "" if pd.isna(x)
                 else (str(int(x)) if float(x).is_integer() else ("%g" % x)))


def _cod_transp(cod, nome):
    """Codigo da transportadora como string.

    Vem como float na base. As 18 linhas sem codigo caem num bucket proprio por
    NOME ("S/<nome>") em vez de virarem um unico "sem codigo": fundi-las
    juntaria transportadoras diferentes na chave de entrega.
    """
    v = pd.to_numeric(cod, errors="coerce")
    fora = int(v.isna().sum())
    if fora:
        print(f"   [AVISO] {fora} linhas sem COD. TRANSPORTADORA "
              f"-> chaveadas pelo nome")
    return pd.Series(
        [("S/" + n) if pd.isna(x) else str(int(x)) for x, n in zip(v, nome)],
        index=cod.index)


def _codes(serie):
    """Fatora uma serie em (codigos int, categorias list)."""
    cat = serie.astype("category")
    return cat.cat.codes.astype(int), [str(x) for x in cat.cat.categories]


def construir_dataset(df):
    df = df.copy()
    df["DATA  SAÍDA"] = pd.to_datetime(df["DATA  SAÍDA"], errors="coerce")
    df = df[df["DATA  SAÍDA"].notna()]

    df["DIA"]      = df["DATA  SAÍDA"].dt.strftime("%Y-%m-%d")
    df["EMPRESA"]  = df["EMPRESA"].astype(str).str.strip().str.zfill(2)
    df["TNOME"]    = df["NOME TRANSPORTADORA"].fillna("(SEM TRANSPORTADORA)").astype(str).str.strip()
    df["TCOD"]     = _cod_transp(df["TRANSPORTADORA"], df["TNOME"])
    df["COD"]      = _fmt_cod(df["COD. CLIENTE"])
    df["CLIENTE"]  = df["NOME CLIENTE"].fillna("(SEM NOME)").astype(str).str.strip()
    df["UF"]       = df["UF"].fillna("--").astype(str).str.strip()
    df["CIDADE"]   = df["CIDADE"].fillna("(SEM CIDADE)").astype(str).str.strip()
    df["PESO BRUTO"]       = pd.to_numeric(df["PESO BRUTO"], errors="coerce").fillna(0)
    df["VALOR TOTAL MERC"] = pd.to_numeric(df["VALOR TOTAL MERC"], errors="coerce").fillna(0)

    # --- exclusao dos clientes internos Tirolez ---------------------------
    alvo = df["CLIENTE"].str.upper()
    fora = alvo.isin(CLIENTES_EXCLUIDOS)
    if fora.any():
        print(f"   [EXCLUIDOS] {int(fora.sum()):,} linhas de "
              f"{alvo[fora].nunique()} clientes internos removidas "
              f"(-{df.loc[fora, 'PESO BRUTO'].sum():,.0f} kg, "
              f"-R$ {df.loc[fora, 'VALOR TOTAL MERC'].sum():,.0f})")
    # avisa se surgir uma unidade Tirolez que ainda nao esta na lista
    novos = sorted(set(alvo[alvo.str.startswith("TIROLEZ")]) - CLIENTES_EXCLUIDOS)
    if novos:
        print(f"   [ATENCAO] nome(s) TIROLEZ fora da lista de exclusao: {novos}")
    df = df[~fora]

    # --- 1 linha da base = 1 nota fiscal ----------------------------------
    # Definicao do negocio (12/09/2026): NAO deduplicar. Cada linha da
    # exportacao conta como uma NF e seu peso/valor entram integralmente no
    # total, para que a pagina feche exatamente com a soma da Base NF.
    # Efeito colateral conhecido: 3 notas (NFF 10668, 10627 e 10220 da empresa
    # 09, julho) aparecem 18.392x cada na origem e por isso pesam 18.392x aqui.
    print(f"   [BASE] {len(df):,} linhas = {len(df):,} notas fiscais "
          f"(sem deduplicacao, por definicao)")

    # --- dimensao LOCAL: cliente + uf + cidade (13 clientes atendem >1 cidade) ---
    locais = (df[["COD", "CLIENTE", "UF", "CIDADE"]]
              .drop_duplicates()
              .sort_values(["CLIENTE", "CIDADE"])
              .reset_index(drop=True))
    locais["REGIAO"] = locais["UF"].map(REGIAO_POR_UF).fillna("(SEM REGIÃO)")
    sem_reg = sorted(locais.loc[locais["UF"].map(REGIAO_POR_UF).isna(), "UF"].unique())
    if sem_reg:
        print(f"   [ATENCAO] UF sem regiao mapeada: {sem_reg}")
    locais["LOC"] = locais.index
    df = df.merge(locais, on=["COD", "CLIENTE", "UF", "CIDADE"], how="left")

    # --- dimensao TRANSPORTADORA: chaveada pelo CODIGO, nao pelo nome ---
    # A chave de entrega usa o codigo, e 3 nomes carregam 2 codigos cada
    # (filiais). Agrupar por nome fundiria essas filiais e derrubaria a
    # contagem de entregas; por isso o grao guarda o indice do codigo.
    transps = (df[["TCOD", "TNOME"]]
               .drop_duplicates()
               .sort_values(["TNOME", "TCOD"])
               .reset_index(drop=True))
    dup = transps["TNOME"].duplicated(keep=False)
    transps["ROTULO"] = transps["TNOME"].where(
        ~dup, transps["TNOME"] + " (" + transps["TCOD"] + ")")
    transps["TRI"] = transps.index
    df = df.merge(transps[["TCOD", "TNOME", "TRI"]], on=["TCOD", "TNOME"], how="left")
    if int(dup.sum()):
        print(f"   [TRANSP] {len(transps)} codigos / {transps['TNOME'].nunique()} nomes "
              f"-> {int(dup.sum())} rotulos com o codigo anexado para desambiguar")

    # --- agregacao no grao ---
    g = (df.groupby(["DIA", "EMPRESA", "TRI", "LOC"], sort=True)
           .agg(nff=("NFF", "size"),
                peso=("PESO BRUTO", "sum"),
                valor=("VALOR TOTAL MERC", "sum"))
           .reset_index())

    dias_cat,  dias   = _codes(g["DIA"])
    emp_cat,   emps   = _codes(g["EMPRESA"])
    tr_cat = g["TRI"].astype(int)
    transp = transps["ROTULO"].tolist()

    cod_cat,   cods    = _codes(locais["COD"])
    nome_cat,  nomes   = _codes(locais["CLIENTE"])
    uf_cat,    ufs     = _codes(locais["UF"])
    cid_cat,   cidades = _codes(locais["CIDADE"])
    reg_cat,   regioes = _codes(locais["REGIAO"])

    dados = {
        "gerado": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "dims": {
            "dias":    dias,
            "emps":    emps,
            "transp":     transp,
            "transpCod":  transps["TCOD"].tolist(),
            "cods":    cods,
            "nomes":   nomes,
            "ufs":     ufs,
            "cidades": cidades,
            "regioes": regioes,
        },
        # dimensao local -> indices nas dims de cliente/uf/cidade
        "loc": {
            "cod":  cod_cat.tolist(),
            "nome": nome_cat.tolist(),
            "uf":   uf_cat.tolist(),
            "cid":  cid_cat.tolist(),
            "reg":  reg_cat.tolist(),
        },
        # fatos colunares
        "f": {
            "d": dias_cat.tolist(),
            "e": emp_cat.tolist(),
            "t": tr_cat.tolist(),
            "l": g["LOC"].astype(int).tolist(),
            "n": g["nff"].astype(int).tolist(),
            "p": [round(float(x), 3) for x in g["peso"]],   # PESO BRUTO tem 3 casas
            "v": [round(float(x), 2) for x in g["valor"]],
        },
    }

    print(f"   -> {len(g):,} linhas no grao | {len(locais):,} locais | "
          f"{len(dias)} dias ({dias[0]} a {dias[-1]})")
    print(f"   -> NF {len(df):,} | "
          f"entregas {df['DIA'].str.cat([df['COD'], df['TCOD']], sep='_').nunique():,} | "
          f"peso {df['PESO BRUTO'].sum():,.0f} kg | "
          f"valor R$ {df['VALOR TOTAL MERC'].sum():,.0f}")
    return dados


def logo_b64():
    p = os.path.join(ETL_DIR, "logo_tirolez.png")
    if not os.path.exists(p):
        return ""
    with open(p, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def main():
    print("[1/3] Carregando Base NF...")
    df = carregar_nf()
    print(f"   -> {len(df):,} registros brutos")

    print("[2/3] Montando dataset...")
    dados = construir_dataset(df)
    dados["logo"] = logo_b64()

    print("[3/3] Gerando HTML...")
    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()
    if "/*__DADOS__*/" not in html:
        sys.exit("ERRO: template sem o marcador /*__DADOS__*/")
    payload = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    html = html.replace("/*__DADOS__*/", payload)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)
    mb = os.path.getsize(OUTPUT) / 1024 / 1024
    print(f"   -> {OUTPUT} ({mb:.1f} MB)")


if __name__ == "__main__":
    main()
