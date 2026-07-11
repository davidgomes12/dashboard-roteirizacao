"""
Pipeline ETL - Indicador de Roteiro 2026
Automatiza todas as transformações descritas no Receita.xlsx
e gera os dados JSON para o dashboard HTML.
"""

import hashlib
import json
import os
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning)

# ============================================================
# CONFIGURAÇÃO — lida de config.json (caminhos e parâmetros)
# ============================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ETL_DIR  = os.path.join(BASE_DIR, "ETL")
DADOS_DIR = os.path.join(BASE_DIR, "Dados")

_cfg_path = os.path.join(ETL_DIR, "config.json")
with open(_cfg_path, encoding="utf-8") as _f:
    _cfg = json.load(_f)

def _resolve_path(p):
    """Expande variáveis de ambiente (%USERPROFILE%, etc.) e torna o caminho absoluto."""
    return os.path.abspath(os.path.expandvars(os.path.expanduser(p)))

ESCALA_PATH   = _resolve_path(_cfg["caminhos"]["escala"])
FROTA_PATH    = _resolve_path(_cfg["caminhos"]["frota"])
LEVITARE_PATH = _resolve_path(_cfg["caminhos"]["levitare"])
NF_PATH       = os.path.join(DADOS_DIR, "NF.xlsx")
OCORRENCIAS_PATH = os.path.join(DADOS_DIR, "Ocorrencias.xlsx")
CLIENTES_PATH = os.path.join(DADOS_DIR, "Clientes.xlsx")
OUTPUT_JSON   = os.path.join(ETL_DIR, "dashboard_data.json")

TRANSPORTADORAS_FILTRO = _cfg["filtros"]["transportadoras"]
# Códigos de transportadora a desconsiderar nas reentregas (fora da operação monitorada)
EXCLUIR_REENTREGA      = _cfg["filtros"].get("transportadoras_excluir_reentrega", [])
MOTIVO_REENTREGA       = _cfg["filtros"]["motivo_reentrega"]
UF_FILTRO              = _cfg["filtros"]["uf"]
FATOR_PESO             = _cfg["filtros"]["fator_peso"]
EMPRESA_REENTREGA          = str(_cfg["filtros"]["empresa_reentrega"]).strip()
EMPRESA_REENTREGA_LEVITARE = str(_cfg["filtros"]["empresa_reentrega_levitare"]).strip()
META_OCUPACAO          = _cfg["metas"]["ocupacao"]
META_REAL_KG           = _cfg["metas"]["real_kg"]

# Justificativa de reentrega analisada por faixa de peso (grafia exata da base)
JUST_FORA_HORARIO      = "FORA DE HORARIO"
# Limites das faixas de peso (kg) e seus rótulos de exibição
FAIXAS_PESO_LIMITES    = [20, 50, 100]
FAIXAS_PESO_LABELS     = ["0 a 20 kg", "21 a 50 kg", "51 a 100 kg", "+ 101 kg"]


# ============================================================
# CACHE PARQUET — reutiliza leitura se o arquivo não mudou
# ============================================================
def _read_excel_cached(path, **kwargs):
    """Lê Excel com cache parquet keyed pelo mtime do arquivo.

    Na segunda execução do dia (ou se o arquivo não mudou),
    usa o .parquet e ignora o .xlsx — tipicamente 10× mais rápido.
    """
    key        = hashlib.md5(path.encode()).hexdigest()[:10]
    cache_path = os.path.join(ETL_DIR, f".cache_{key}.parquet")
    meta_path  = cache_path + ".meta"
    mtime      = str(os.path.getmtime(path))

    if os.path.exists(cache_path) and os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as mf:
            if mf.read().strip() == mtime:
                print("      (cache hit — usando .parquet)")
                return pd.read_parquet(cache_path)

    df = pd.read_excel(path, **kwargs)
    try:
        df.to_parquet(cache_path, index=False)
        with open(meta_path, "w", encoding="utf-8") as mf:
            mf.write(mtime)
    except Exception:
        pass  # falha de escrita do cache é não-fatal
    return df


# ============================================================
# VALIDAÇÃO DE SCHEMA
# ============================================================
SCHEMA_ESCALA = {"ID", "DATA", "PESO", "CAPAC.", "CUSTO FRETE", "ENTREGAS",
                 "VEICULO", "FAIXA", "ROTA", "TRANSPORTADORA - MOTORISTA"}
SCHEMA_NF     = {"UF", "TRANSPORTADORA", "DATA  SAÍDA", "COD. CLIENTE", "NFF",
                 "NOME TRANSPORTADORA"}
SCHEMA_OCORR  = {"UF", "MOTIVO OCORRÊNCIA", "DOCUMENTO", "DATA INCLUSÃO",
                 "COD. CLIENTE", "DESC JUST OC", "EMPRESA"}

def _validar_schema(df, esperadas, nome):
    faltando = esperadas - set(df.columns)
    if faltando:
        raise ValueError(
            f"[SCHEMA] {nome}: colunas faltando → {sorted(faltando)}\n"
            f"         Colunas presentes: {sorted(df.columns.tolist())}"
        )


# ============================================================
# HELPERS DE AGREGAÇÃO — evita repetição dos groupby
# ============================================================
_AGG = {
    "peso":     ("PESO_AJUSTADO", "sum"),
    "capac":    ("CAPAC.",        "sum"),
    "frete":    ("CUSTO FRETE",   "sum"),
    "veiculos": ("ID",            "count"),
    "entregas": ("ENTREGAS",      "sum"),
}

def _derive(df):
    """Calcula colunas derivadas após groupby."""
    df["real_kg"]       = np.where(df["peso"] > 0, df["frete"] / df["peso"], 0)
    df["ocupacao"]      = np.where(df["capac"] > 0, df["peso"] / df["capac"] * 100, 0)
    df["media_entregas"] = np.where(df["veiculos"] > 0, df["entregas"] / df["veiculos"], 0)
    df["media_peso"]    = np.where(df["veiculos"] > 0, df["peso"] / df["veiculos"], 0)
    return df

def kpi_grain(df, by):
    """Agrega dados da escala por uma ou mais colunas e calcula KPIs derivados."""
    return _derive(df.groupby(by).agg(**_AGG).reset_index())


def _escala_kpis(df):
    """Retorna dict de KPIs globais a partir de um subconjunto de escala."""
    peso   = float(df["PESO_AJUSTADO"].sum())
    capac  = float(df["CAPAC."].sum())
    frete  = float(df["CUSTO FRETE"].sum())
    return {
        "peso_total":    round(peso, 2),
        "capac_total":   round(capac, 2),
        "frete_total":   round(frete, 2),
        "real_kg_total": round(frete / peso if peso > 0 else 0, 4),
        "ocupacao_total": round(peso / capac * 100 if capac > 0 else 0, 2),
        "qtd_veiculos":  int(len(df)),
        "qtd_entregas":  int(df["ENTREGAS"].sum()),
        "meta_ocupacao": META_OCUPACAO,
        "meta_real_kg":  META_REAL_KG,
    }


def build_escala_aggregations(df_escala):
    """Gera KPIs e agrupamentos padrão para um subconjunto de escala."""
    kpis      = _escala_kpis(df_escala)
    dia_group = _derive(kpi_grain(df_escala, "DIA").sort_values("DIA"))
    mes_group = _derive(kpi_grain(df_escala, "MES_KEY").sort_values("MES_KEY"))
    veic      = kpi_grain(df_escala, "VEICULO")
    veic_dia  = kpi_grain(df_escala, ["DIA", "VEICULO"])
    veic_mes  = kpi_grain(df_escala, ["MES_KEY", "VEICULO"])
    meses     = sorted(df_escala["MES_KEY"].unique().tolist())
    dias      = sorted(df_escala["DIA"].unique().tolist())
    return kpis, dia_group, mes_group, veic, veic_dia, veic_mes, meses, dias


# ============================================================
# LOADERS
# ============================================================
def load_escala():
    print("[1/5] Carregando ESCALA...")
    df = _read_excel_cached(ESCALA_PATH, sheet_name="ESCALA", header=10, usecols="C:R")
    df = df.dropna(subset=["ID"])

    df["DATA"]        = pd.to_datetime(df["DATA"], errors="coerce")
    df["PESO"]        = pd.to_numeric(df["PESO"], errors="coerce").fillna(0)
    df["CAPAC."]      = pd.to_numeric(df["CAPAC."], errors="coerce").fillna(0)
    df["CUSTO FRETE"] = pd.to_numeric(df["CUSTO FRETE"], errors="coerce").fillna(0)
    df["ENTREGAS"]    = pd.to_numeric(df["ENTREGAS"], errors="coerce").fillna(0)
    df["FAIXA"]       = pd.to_numeric(df["FAIXA"], errors="coerce").fillna(0)

    # Preserva PESO original; PESO_AJUSTADO (+10%) é usado nos KPIs
    df["PESO_AJUSTADO"] = df["PESO"] * FATOR_PESO

    df = df.dropna(subset=["DATA"])
    df["MES_KEY"] = df["DATA"].dt.strftime("%Y-%m")
    df["DIA"]     = df["DATA"].dt.strftime("%Y-%m-%d")

    _validar_schema(df, SCHEMA_ESCALA, "ESCALA")
    print(f"   -> {len(df)} registros (PESO_AJUSTADO = PESO × {FATOR_PESO})")
    return df


def load_nf_raw():
    """Lê NF.xlsx bruto — usado como base para load_nf e load_ocorrencias."""
    print("[2/5] Carregando NF...")
    df = _read_excel_cached(NF_PATH)
    _validar_schema(df, SCHEMA_NF, "NF")
    print(f"   -> {len(df)} registros brutos")
    return df


def load_nf(df_raw):
    """Filtra NF por UF e transportadoras."""
    df = df_raw[df_raw["UF"] == UF_FILTRO].copy()
    df["TRANSPORTADORA"] = pd.to_numeric(df["TRANSPORTADORA"], errors="coerce")
    df = df[df["TRANSPORTADORA"].isin(TRANSPORTADORAS_FILTRO)].copy()

    df["DATA  SAÍDA"]  = pd.to_datetime(df["DATA  SAÍDA"], errors="coerce")
    df["COD. CLIENTE"] = df["COD. CLIENTE"].astype(str)
    df["CHAVE_ENTREGA"] = df["DATA  SAÍDA"].dt.strftime("%Y-%m-%d") + "_" + df["COD. CLIENTE"]
    df["MES_KEY"] = df["DATA  SAÍDA"].dt.strftime("%Y-%m")
    df["DIA"]     = df["DATA  SAÍDA"].dt.strftime("%Y-%m-%d")

    print(f"   -> {len(df)} registros (SP + transportadoras)")
    return df


def _ocorrencias_por_empresa(df_ocorr, nf_raw, empresa, label):
    df = df_ocorr[df_ocorr["EMPRESA"] == empresa].copy()
    df = df[df["UF"] == UF_FILTRO].copy()
    df = df[df["MOTIVO OCORRÊNCIA"] == MOTIVO_REENTREGA].copy()

    nf_lookup = nf_raw.drop_duplicates(subset=["NFF"])[["NFF", "NOME TRANSPORTADORA", "TRANSPORTADORA"]].copy()
    nf_lookup["NFF"] = pd.to_numeric(nf_lookup["NFF"], errors="coerce")
    nf_lookup["TRANSPORTADORA"] = pd.to_numeric(nf_lookup["TRANSPORTADORA"], errors="coerce")
    df["DOCUMENTO"]  = pd.to_numeric(df["DOCUMENTO"], errors="coerce")
    df = df.merge(nf_lookup, left_on="DOCUMENTO", right_on="NFF", how="left")

    sem_match = df["NOME TRANSPORTADORA"].isna().sum()
    if sem_match > 0:
        print(f"   [AVISO] {label}: {sem_match} ocorrências sem transportadora na NF")

    # Desconsidera transportadoras fora da operação monitorada (config.json)
    if EXCLUIR_REENTREGA:
        antes = len(df)
        df = df[~df["TRANSPORTADORA"].isin(EXCLUIR_REENTREGA)].copy()
        removidas = antes - len(df)
        if removidas > 0:
            print(f"   [FILTRO] {label}: {removidas} ocorrências removidas (transportadoras excluídas)")

    df["DATA INCLUSÃO"] = pd.to_datetime(df["DATA INCLUSÃO"], errors="coerce")
    df["COD. CLIENTE"]  = df["COD. CLIENTE"].astype(str)
    df["CHAVE_ENTREGA"] = df["DATA INCLUSÃO"].dt.strftime("%Y-%m-%d") + "_" + df["COD. CLIENTE"]
    df["MES_KEY"] = df["DATA INCLUSÃO"].dt.strftime("%Y-%m")
    df["DIA"]     = df["DATA INCLUSÃO"].dt.strftime("%Y-%m-%d")
    print(f"   -> {label}: {len(df)} registros | {df['CHAVE_ENTREGA'].nunique()} reentregas")
    return df


def load_ocorrencias(nf_raw, nf_filtrado):
    print("[3/5] Carregando Ocorrências...")
    df = _read_excel_cached(OCORRENCIAS_PATH)
    _validar_schema(df, SCHEMA_OCORR, "OCORRENCIAS")
    df["EMPRESA"] = df["EMPRESA"].astype(str).str.strip().str.zfill(2)
    tirolez  = _ocorrencias_por_empresa(df, nf_raw, EMPRESA_REENTREGA,          "TIROLEZ")
    levitare = _ocorrencias_por_empresa(df, nf_raw, EMPRESA_REENTREGA_LEVITARE, "LEVITARE")
    return tirolez, levitare


def _norm_cod_cliente(serie):
    """COD. CLIENTE vem como int na Ocorrência e float (ex.: 123.0) em Clientes.
    Normaliza ambos para inteiro-string ('123') para casar no merge."""
    return pd.to_numeric(serie, errors="coerce").astype("Int64").astype(str)


def load_clientes_canal():
    """Lê Clientes.xlsx e devolve o lookup COD. CLIENTE -> NOME CANAL."""
    print("[3b/5] Carregando Clientes (canal de vendas)...")
    df = _read_excel_cached(CLIENTES_PATH)
    if "COD. CLIENTE" not in df.columns or "NOME CANAL" not in df.columns:
        print("   [AVISO] Clientes.xlsx sem 'COD. CLIENTE'/'NOME CANAL' — canal ignorado")
        return None
    df["COD. CLIENTE"] = _norm_cod_cliente(df["COD. CLIENTE"])
    lookup = df.drop_duplicates(subset=["COD. CLIENTE"])[["COD. CLIENTE", "NOME CANAL"]]
    print(f"   -> {len(lookup)} clientes com canal")
    return lookup


def add_canal(reentregas, canal_lookup):
    """Adiciona a coluna NOME CANAL às reentregas (merge por COD. CLIENTE)."""
    if canal_lookup is None or "COD. CLIENTE" not in reentregas.columns:
        return reentregas
    df = reentregas.copy()
    df["COD. CLIENTE"] = _norm_cod_cliente(df["COD. CLIENTE"])
    df = df.merge(canal_lookup, on="COD. CLIENTE", how="left")
    df["NOME CANAL"] = df["NOME CANAL"].fillna("(sem cadastro)")
    return df


def load_frota():
    print("[4/5] Carregando Disponibilidade de Frota...")
    disp = _read_excel_cached(FROTA_PATH, sheet_name="DISPONIBILIZADO")
    util = _read_excel_cached(FROTA_PATH, sheet_name="UTILIZADO")

    for d in [disp, util]:
        d["Data"] = pd.to_datetime(d["Data"], errors="coerce")
        d.dropna(subset=["Data"], inplace=True)
        d["MES_KEY"] = d["Data"].dt.strftime("%Y-%m")
        d["DIA"]     = d["Data"].dt.strftime("%Y-%m-%d")
        d["Veiculo"] = d["Veiculo"].astype(str).str.strip().str.upper()

    print(f"   -> Disponibilizado: {len(disp)} | Utilizado: {len(util)}")
    return disp, util


def load_levitare():
    print("[5/6] Carregando LEVITARE...")
    df = _read_excel_cached(LEVITARE_PATH, sheet_name="Base", header=0)
    df = df.rename(columns={
        "Data":                  "DATA",
        "Número de paradas":     "ENTREGAS",
        "Tipos de Equipamento":  "VEICULO",
        "Entrega Total PESO":    "PESO",
        "Capacidade":            "CAPAC.",
        "Frete":                 "CUSTO FRETE",
    })
    df["DATA"]        = pd.to_datetime(df["DATA"], errors="coerce")
    df["PESO"]        = pd.to_numeric(df["PESO"], errors="coerce").fillna(0)
    df["CAPAC."]      = pd.to_numeric(df["CAPAC."], errors="coerce").fillna(0)
    df["CUSTO FRETE"] = pd.to_numeric(df["CUSTO FRETE"], errors="coerce").fillna(0)
    df["ENTREGAS"]    = pd.to_numeric(df["ENTREGAS"], errors="coerce").fillna(0)
    df = df.dropna(subset=["DATA"])
    df["PESO_AJUSTADO"] = df["PESO"]   # sem fator de ajuste no Levitare
    df["MES_KEY"] = df["DATA"].dt.strftime("%Y-%m")
    df["DIA"]     = df["DATA"].dt.strftime("%Y-%m-%d")
    print(f"   -> {len(df)} registros | {df['DIA'].nunique()} dias")
    return df


def build_reentregas_aggrs(reentregas, nf_total, nf_dia_df, nf_mes_df,
                            nf_transp_totals, nf_transp_dia_df):
    """Gera todos os agregados de reentregas para um operador (TIROLEZ ou LEVITARE)."""
    def r(df):
        return json.loads(df.to_json(orient="records", date_format="iso"))

    total_reent   = int(reentregas["CHAVE_ENTREGA"].nunique())
    qtd_nf        = int(nf_total)
    pct_reent     = round(total_reent / qtd_nf * 100, 2) if qtd_nf > 0 else 0

    reent_transp = reentregas.groupby("NOME TRANSPORTADORA").agg(
        reentregas=("CHAVE_ENTREGA", "nunique")).reset_index().sort_values("reentregas", ascending=False)
    reent_transp = reent_transp.merge(nf_transp_totals, on="NOME TRANSPORTADORA", how="left").fillna(0)
    reent_transp["entregas"] = reent_transp["entregas"].astype(int)
    reent_transp["pct"] = np.where(
        reent_transp["entregas"] > 0,
        round(reent_transp["reentregas"] / reent_transp["entregas"] * 100, 2), 0)

    reent_just = reentregas.groupby("DESC JUST OC").agg(
        reentregas=("CHAVE_ENTREGA", "nunique")).reset_index().sort_values("reentregas", ascending=False)
    tj = reent_just["reentregas"].sum()
    reent_just["pct"] = round(reent_just["reentregas"] / tj * 100, 2) if tj > 0 else 0

    reent_transp_just = reentregas.groupby(["NOME TRANSPORTADORA", "DESC JUST OC"]).agg(
        reentregas=("CHAVE_ENTREGA", "nunique")).reset_index().sort_values("reentregas", ascending=False)

    reent_transp_dia = reentregas.groupby(["DIA", "NOME TRANSPORTADORA"]).agg(
        reentregas=("CHAVE_ENTREGA", "nunique")).reset_index()
    reent_just_dia   = reentregas.groupby(["DIA", "DESC JUST OC"]).agg(
        reentregas=("CHAVE_ENTREGA", "nunique")).reset_index()
    reent_tj_dia     = reentregas.groupby(["DIA", "NOME TRANSPORTADORA", "DESC JUST OC"]).agg(
        reentregas=("CHAVE_ENTREGA", "nunique")).reset_index().sort_values("reentregas", ascending=False)
    reent_dia = reentregas.groupby("DIA").agg(
        reentregas=("CHAVE_ENTREGA", "nunique")).reset_index().sort_values("DIA")
    reent_mes = reentregas.groupby("MES_KEY").agg(
        reentregas=("CHAVE_ENTREGA", "nunique")).reset_index().sort_values("MES_KEY")

    meses = sorted(reentregas["MES_KEY"].dropna().unique().tolist())
    dias  = sorted(reentregas["DIA"].dropna().unique().tolist())

    return {
        "kpis": {"reentregas": total_reent, "qtd_entregas_nf": qtd_nf, "pct_reentregas": pct_reent},
        "reentregas_transportadora":  r(reent_transp),
        "reentregas_justificativa":   r(reent_just),
        "reentregas_transp_just":     r(reent_transp_just),
        "reentregas_transp_dia":      r(reent_transp_dia),
        "nf_transp_dia":              r(nf_transp_dia_df),
        "reentregas_just_dia":        r(reent_just_dia),
        "reentregas_transp_just_dia": r(reent_tj_dia),
        "reentregas_dia":             r(reent_dia),
        "reentregas_mes":             r(reent_mes),
        "nf_entregas_dia":            r(nf_dia_df),
        "nf_entregas_mes":            r(nf_mes_df),
        "filtros_meses": meses,
        "filtros_dias":  dias,
    }


def _faixa_peso_label(p):
    """Classifica um peso (kg) em uma das faixas configuradas."""
    for limite, label in zip(FAIXAS_PESO_LIMITES, FAIXAS_PESO_LABELS):
        if p <= limite:
            return label
    return FAIXAS_PESO_LABELS[-1]


def _reent_faixa_peso_dia(reentregas, justificativa):
    """Reentregas de uma justificativa, por faixa de peso e por DIA.

    Nível de REENTREGA (CHAVE_ENTREGA = data+cliente): soma o PESO LIQUIDO de
    todos os documentos da mesma reentrega e a classifica numa única faixa pelo
    peso total. Assim a contagem (qtd) bate com 'reentregas_justificativa'
    (distinct CHAVE_ENTREGA) em vez de contar documentos/linhas. Granular por
    DIA para o filtro de mês.
    """
    fh = reentregas[reentregas["DESC JUST OC"] == justificativa].copy()
    fh["PESO LIQUIDO"] = pd.to_numeric(fh["PESO LIQUIDO"], errors="coerce").fillna(0)

    # Consolida documentos da mesma reentrega antes de classificar a faixa
    por_reent = (fh.groupby(["DIA", "CHAVE_ENTREGA"])
                   .agg(peso=("PESO LIQUIDO", "sum"))
                   .reset_index())
    por_reent["FAIXA_PESO"] = por_reent["peso"].apply(_faixa_peso_label)

    return (por_reent.groupby(["DIA", "FAIXA_PESO"])
              .agg(qtd=("CHAVE_ENTREGA", "nunique"), peso=("peso", "sum"))
              .reset_index()
              .sort_values(["DIA", "FAIXA_PESO"]))


# ============================================================
# KPIs PRINCIPAIS
# ============================================================
def build_kpis(escala, nf, nf_raw, reentregas, frota_disp, frota_util):
    print("\n[ETL] Calculando KPIs...")

    kpis = _escala_kpis(escala)

    total_reentregas  = int(reentregas["CHAVE_ENTREGA"].nunique())
    qtd_entregas_nf   = int(nf["CHAVE_ENTREGA"].nunique())
    pct_reentregas    = (total_reentregas / qtd_entregas_nf * 100) if qtd_entregas_nf > 0 else 0

    kpis["reentregas"]      = total_reentregas
    kpis["qtd_entregas_nf"] = qtd_entregas_nf
    kpis["pct_reentregas"]  = round(pct_reentregas, 2)

    # === ESCALA: por dia / mês / veículo ===
    dia_group  = kpi_grain(escala, "DIA").sort_values("DIA")
    mes_group  = kpi_grain(escala, "MES_KEY").sort_values("MES_KEY")
    veic_group = kpi_grain(escala, "VEICULO")
    veic_dia   = kpi_grain(escala, ["DIA",     "VEICULO"])
    veic_mes   = kpi_grain(escala, ["MES_KEY", "VEICULO"])

    # === FAIXAS DE KM ===
    def _faixa_grains(df_sub):
        return (
            kpi_grain(df_sub, "VEICULO"),
            kpi_grain(df_sub, ["DIA",     "VEICULO"]),
            kpi_grain(df_sub, ["MES_KEY", "VEICULO"]),
        )

    dist_0_100_veic, dist_0_100_dia, dist_0_100_mes = _faixa_grains(escala[escala["FAIXA"].isin([1, 2])])
    dist_100p_veic,  dist_100p_dia,  dist_100p_mes  = _faixa_grains(escala[escala["FAIXA"] >= 3])

    # === REENTREGAS ===
    nf_transp = nf.groupby("NOME TRANSPORTADORA").agg(
        entregas=("CHAVE_ENTREGA", "nunique"),
    ).reset_index()

    reent_transp = reentregas.groupby("NOME TRANSPORTADORA").agg(
        reentregas=("CHAVE_ENTREGA", "nunique"),
    ).reset_index().sort_values("reentregas", ascending=False)
    reent_transp = reent_transp.merge(nf_transp, on="NOME TRANSPORTADORA", how="left").fillna(0)
    reent_transp["entregas"] = reent_transp["entregas"].astype(int)
    reent_transp["pct"] = np.where(
        reent_transp["entregas"] > 0,
        round(reent_transp["reentregas"] / reent_transp["entregas"] * 100, 2),
        0,
    )

    reent_just = reentregas.groupby("DESC JUST OC").agg(
        reentregas=("CHAVE_ENTREGA", "nunique"),
    ).reset_index().sort_values("reentregas", ascending=False)
    tj = reent_just["reentregas"].sum()
    reent_just["pct"] = round(reent_just["reentregas"] / tj * 100, 2) if tj > 0 else 0

    reent_transp_just = reentregas.groupby(["NOME TRANSPORTADORA", "DESC JUST OC"]).agg(
        reentregas=("CHAVE_ENTREGA", "nunique"),
    ).reset_index().sort_values("reentregas", ascending=False)

    # Granular por DIA
    reent_transp_dia_g    = reentregas.groupby(["DIA", "NOME TRANSPORTADORA"]).agg(reentregas=("CHAVE_ENTREGA", "nunique")).reset_index()
    nf_transp_dia_g       = nf.groupby(["DIA", "NOME TRANSPORTADORA"]).agg(entregas=("CHAVE_ENTREGA", "nunique")).reset_index()
    reent_just_dia_g      = reentregas.groupby(["DIA", "DESC JUST OC"]).agg(reentregas=("CHAVE_ENTREGA", "nunique")).reset_index()
    reent_transp_just_dia_g = reentregas.groupby(["DIA", "NOME TRANSPORTADORA", "DESC JUST OC"]).agg(reentregas=("CHAVE_ENTREGA", "nunique")).reset_index()

    reent_dia = reentregas.groupby("DIA").agg(reentregas=("CHAVE_ENTREGA", "nunique")).reset_index().sort_values("DIA")
    reent_mes = reentregas.groupby("MES_KEY").agg(reentregas=("CHAVE_ENTREGA", "nunique")).reset_index().sort_values("MES_KEY")
    nf_dia    = nf.groupby("DIA").agg(qtd_entregas=("CHAVE_ENTREGA", "nunique")).reset_index().sort_values("DIA")
    nf_mes    = nf.groupby("MES_KEY").agg(qtd_entregas=("CHAVE_ENTREGA", "nunique")).reset_index().sort_values("MES_KEY")

    # === FORA DE HORÁRIO: peso das reentregas por faixa (granular por DIA) ===
    # Analisa o peso líquido das reentregas cuja justificativa é "FORA DE HORARIO",
    # distribuído em três faixas de peso. Nível de linha/ocorrência (cada documento
    # tem seu PESO LIQUIDO), granular por DIA para o filtro de mês do dashboard.
    reent_fh_peso_dia = _reent_faixa_peso_dia(reentregas, JUST_FORA_HORARIO)

    # === REENTREGAS POR CANAL DE VENDAS (granular por DIA) ===
    # reentregas = CHAVE_ENTREGA distinta (data+cliente); peso = soma do PESO LIQUIDO
    # de todos os documentos da reentrega. Peso médio é recalculado no dashboard
    # após o filtro de mês (peso_total / reentregas), para não distorcer médias.
    if "NOME CANAL" in reentregas.columns:
        _rc = reentregas.copy()
        _rc["peso"] = pd.to_numeric(_rc.get("PESO LIQUIDO", 0), errors="coerce").fillna(0)
        reent_canal_dia = _rc.groupby(["DIA", "NOME CANAL"]).agg(
            reentregas=("CHAVE_ENTREGA", "nunique"),
            peso=("peso", "sum"),
        ).reset_index()
    else:
        reent_canal_dia = pd.DataFrame(columns=["DIA", "NOME CANAL", "reentregas", "peso"])

    # Reentregas FORA DE HORARIO por canal e dia (reentregas distintas + peso)
    if "NOME CANAL" in reentregas.columns:
        _fh = reentregas[reentregas["DESC JUST OC"] == JUST_FORA_HORARIO].copy()
        _fh["peso"] = pd.to_numeric(_fh.get("PESO LIQUIDO", 0), errors="coerce").fillna(0)
        reent_canal_fh_dia = _fh.groupby(["DIA", "NOME CANAL"]).agg(
            reentregas=("CHAVE_ENTREGA", "nunique"),
            peso=("peso", "sum"),
        ).reset_index()
    else:
        reent_canal_fh_dia = pd.DataFrame(columns=["DIA", "NOME CANAL", "reentregas", "peso"])

    # Entregas (NF) por canal e dia — base para o % de reentrega por canal
    if "NOME CANAL" in nf.columns:
        nf_canal_dia = nf.groupby(["DIA", "NOME CANAL"]).agg(
            entregas=("CHAVE_ENTREGA", "nunique"),
        ).reset_index()
    else:
        nf_canal_dia = pd.DataFrame(columns=["DIA", "NOME CANAL", "entregas"])

    # === FROTA ===
    total_disp    = len(frota_disp)
    total_util    = len(frota_util)
    pct_util_geral = round(total_util / total_disp * 100, 2) if total_disp > 0 else 0

    def _frota_merge(d_grp, u_grp, by):
        d = d_grp.groupby(by).size().reset_index(name="disponibilizado")
        u = u_grp.groupby(by).size().reset_index(name="utilizado")
        m = d.merge(u, on=by, how="left").fillna(0)
        m["utilizado"] = m["utilizado"].astype(int)
        m["pct"] = round(m["utilizado"] / m["disponibilizado"] * 100, 2)
        return m

    frota_transp    = _frota_merge(frota_disp, frota_util, "Transportadora").sort_values("disponibilizado", ascending=False)
    frota_veic      = _frota_merge(frota_disp, frota_util, "Veiculo").sort_values("disponibilizado", ascending=False)
    frota_dia       = _frota_merge(frota_disp, frota_util, "DIA").sort_values("DIA")
    frota_mes       = _frota_merge(frota_disp, frota_util, "MES_KEY").sort_values("MES_KEY")
    frota_transp_dia = _frota_merge(frota_disp, frota_util, ["DIA", "Transportadora"])
    frota_veic_dia   = _frota_merge(frota_disp, frota_util, ["DIA", "Veiculo"])

    meses_disponiveis = sorted(escala["MES_KEY"].unique().tolist())
    dias_disponiveis  = sorted(escala["DIA"].unique().tolist())
    meses_reent = sorted(reentregas["MES_KEY"].dropna().unique().tolist())
    dias_reent  = sorted(reentregas["DIA"].dropna().unique().tolist())
    meses_frota = sorted(frota_disp["MES_KEY"].dropna().unique().tolist())
    dias_frota  = sorted(frota_disp["DIA"].dropna().unique().tolist())

    def r(df):
        return json.loads(df.to_json(orient="records", date_format="iso"))

    return {
        "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "kpis":     kpis,
        "filtros":  {
            "meses": meses_disponiveis, "dias": dias_disponiveis,
            "meses_reent": meses_reent, "dias_reent": dias_reent,
            "meses_frota": meses_frota, "dias_frota": dias_frota,
        },
        "por_dia":          r(dia_group),
        "por_mes":          r(mes_group),
        "por_veiculo":      r(veic_group),
        "por_veiculo_dia":  r(veic_dia),
        "por_veiculo_mes":  r(veic_mes),
        "dist_0_100_veic":  r(dist_0_100_veic),
        "dist_0_100_dia":   r(dist_0_100_dia),
        "dist_0_100_mes":   r(dist_0_100_mes),
        "dist_100p_veic":   r(dist_100p_veic),
        "dist_100p_dia":    r(dist_100p_dia),
        "dist_100p_mes":    r(dist_100p_mes),
        "reentregas_transportadora":  r(reent_transp),
        "reentregas_justificativa":   r(reent_just),
        "reentregas_transp_just":     r(reent_transp_just),
        "reentregas_transp_dia":      r(reent_transp_dia_g),
        "nf_transp_dia":              r(nf_transp_dia_g),
        "reentregas_just_dia":        r(reent_just_dia_g),
        "reentregas_transp_just_dia": r(reent_transp_just_dia_g),
        "reentregas_dia":             r(reent_dia),
        "reentregas_mes":             r(reent_mes),
        "nf_entregas_dia":            r(nf_dia),
        "nf_entregas_mes":            r(nf_mes),
        "reent_fh_peso_dia":          r(reent_fh_peso_dia),
        "reentregas_canal_dia":       r(reent_canal_dia),
        "reent_canal_fh_dia":         r(reent_canal_fh_dia),
        "nf_canal_dia":               r(nf_canal_dia),
        "frota_kpis":          {"total_disp": total_disp, "total_util": total_util, "pct_util": pct_util_geral},
        "frota_transportadora": r(frota_transp),
        "frota_veiculo":        r(frota_veic),
        "frota_dia":            r(frota_dia),
        "frota_mes":            r(frota_mes),
        "frota_transp_dia":     r(frota_transp_dia),
        "frota_veic_dia":       r(frota_veic_dia),
    }


# ============================================================
# MAIN
# ============================================================
def _validar_caminhos():
    erros = []
    if not os.path.isdir(DADOS_DIR):
        erros.append(f"Pasta 'Dados/' não encontrada: {DADOS_DIR}\n"
                     "  → Crie a pasta e coloque NF.xlsx e Ocorrencias.xlsx nela.")
    else:
        for path, nome in [(NF_PATH, "NF.xlsx"), (OCORRENCIAS_PATH, "Ocorrencias.xlsx"),
                           (CLIENTES_PATH, "Clientes.xlsx")]:
            if not os.path.exists(path):
                erros.append(f"Arquivo não encontrado: {path}")
    for path, nome in [
        (ESCALA_PATH,   "ESCALA   (config.json → caminhos.escala)"),
        (FROTA_PATH,    "FROTA    (config.json → caminhos.frota)"),
        (LEVITARE_PATH, "LEVITARE (config.json → caminhos.levitare)"),
    ]:
        if not os.path.exists(path):
            erros.append(f"Arquivo não encontrado: {path}\n  → Verifique o caminho em config.json ({nome})")
    if erros:
        print("\n[ERRO] Problemas encontrados antes de iniciar o ETL:")
        for e in erros:
            print(f"  • {e}")
        raise SystemExit(1)


def main():
    print("=" * 60)
    print("  PIPELINE ETL - INDICADOR ROTEIRO 2026")
    print("=" * 60)

    _validar_caminhos()

    escala      = load_escala()
    nf_raw      = load_nf_raw()          # lido uma única vez
    nf          = load_nf(nf_raw)
    reentregas, reentregas_levi = load_ocorrencias(nf_raw, nf)
    canal_lookup = load_clientes_canal()
    nf              = add_canal(nf, canal_lookup)
    reentregas      = add_canal(reentregas, canal_lookup)
    reentregas_levi = add_canal(reentregas_levi, canal_lookup)
    frota_disp, frota_util = load_frota()
    df_levitare = load_levitare()

    data = build_kpis(escala, nf, nf_raw, reentregas, frota_disp, frota_util)

    # === VESPERTINA ===
    print("[6/6] Processando Vespertina...")
    escala["ROTA"] = escala["ROTA"].astype(str).str.strip().str.upper()
    escala["TRANSPORTADORA - MOTORISTA"] = escala["TRANSPORTADORA - MOTORISTA"].astype(str).str.strip().str.upper()
    vesp    = escala[escala["ROTA"] == "VESPERTINA"].copy()
    vesp_tl = vesp[vesp["TRANSPORTADORA - MOTORISTA"] == "TL"].copy()
    print(f"   -> Vespertina: {len(vesp)} registros | TL: {len(vesp_tl)} registros")

    def r(df):
        return json.loads(df.to_json(orient="records", date_format="iso"))

    v_kpis, v_dia, v_mes, v_veic, v_veic_dia, v_veic_mes, v_meses, v_dias = build_escala_aggregations(vesp)
    data["vesp_kpis"]            = v_kpis
    data["vesp_por_dia"]         = r(v_dia)
    data["vesp_por_mes"]         = r(v_mes)
    data["vesp_por_veiculo"]     = r(v_veic)
    data["vesp_por_veiculo_dia"] = r(v_veic_dia)
    data["vesp_por_veiculo_mes"] = r(v_veic_mes)
    data["filtros"]["meses_vesp"] = v_meses
    data["filtros"]["dias_vesp"]  = v_dias

    _empty_df = pd.DataFrame()
    _empty_kpis = {
        "peso_total": 0, "capac_total": 0, "frete_total": 0,
        "real_kg_total": 0, "ocupacao_total": 0,
        "qtd_veiculos": 0, "qtd_entregas": 0,
        "meta_ocupacao": META_OCUPACAO, "meta_real_kg": META_REAL_KG,
    }

    if len(vesp_tl) > 0:
        tl_kpis, tl_dia, tl_mes, tl_veic, tl_veic_dia, tl_veic_mes, tl_meses, tl_dias = build_escala_aggregations(vesp_tl)
    else:
        tl_kpis = _empty_kpis
        tl_dia = tl_mes = tl_veic = tl_veic_dia = tl_veic_mes = _empty_df

    data["vesp_tl_kpis"]            = tl_kpis
    data["vesp_tl_por_veiculo"]     = r(tl_veic)
    data["vesp_tl_por_veiculo_dia"] = r(tl_veic_dia)
    data["vesp_tl_por_veiculo_mes"] = r(tl_veic_mes)
    data["vesp_tl_por_dia"]         = r(tl_dia)
    data["vesp_tl_por_mes"]         = r(tl_mes)

    # === FRESCAL ===
    fresc = escala[escala["ROTA"] == "FRESCAL"].copy()
    print(f"   -> Frescal: {len(fresc)} registros")
    if len(fresc) == 0:
        rotas = sorted(escala["ROTA"].dropna().unique().tolist())
        print(f"   [AVISO] Nenhuma linha ROTA='FRESCAL'. Valores encontrados: {rotas}")

    if len(fresc) > 0:
        f_kpis, f_dia, f_mes, f_veic, f_veic_dia, f_veic_mes, f_meses, f_dias = \
            build_escala_aggregations(fresc)
    else:
        f_kpis  = _empty_kpis
        f_dia   = f_mes = f_veic = f_veic_dia = f_veic_mes = _empty_df
        f_meses = []
        f_dias  = []

    data["fresc_kpis"]            = f_kpis
    data["fresc_por_dia"]         = r(f_dia)
    data["fresc_por_mes"]         = r(f_mes)
    data["fresc_por_veiculo"]     = r(f_veic)
    data["fresc_por_veiculo_dia"] = r(f_veic_dia)
    data["fresc_por_veiculo_mes"] = r(f_veic_mes)
    data["filtros"]["meses_fresc"] = f_meses
    data["filtros"]["dias_fresc"]  = f_dias

    # === LEVITARE REENTREGAS ===
    levi_nf_dia = (df_levitare.groupby("DIA")["ENTREGAS"].sum()
                   .reset_index().rename(columns={"ENTREGAS": "qtd_entregas"})
                   .sort_values("DIA"))
    levi_nf_mes = (df_levitare.groupby("MES_KEY")["ENTREGAS"].sum()
                   .reset_index().rename(columns={"ENTREGAS": "qtd_entregas"})
                   .sort_values("MES_KEY"))
    levi_nf_total = int(df_levitare["ENTREGAS"].sum())
    _empty_transp = pd.DataFrame(columns=["NOME TRANSPORTADORA", "entregas"])
    _empty_transp_dia = pd.DataFrame(columns=["DIA", "NOME TRANSPORTADORA", "entregas"])

    levi_reent_block = build_reentregas_aggrs(
        reentregas_levi, levi_nf_total,
        levi_nf_dia, levi_nf_mes,
        _empty_transp, _empty_transp_dia,
    )
    data["levi_reent_kpis"]                  = levi_reent_block["kpis"]
    data["levi_reentregas_transportadora"]   = levi_reent_block["reentregas_transportadora"]
    data["levi_reentregas_justificativa"]    = levi_reent_block["reentregas_justificativa"]
    data["levi_reentregas_transp_just"]      = levi_reent_block["reentregas_transp_just"]
    data["levi_reentregas_transp_dia"]       = levi_reent_block["reentregas_transp_dia"]
    data["levi_nf_transp_dia"]               = levi_reent_block["nf_transp_dia"]
    data["levi_reentregas_just_dia"]         = levi_reent_block["reentregas_just_dia"]
    data["levi_reentregas_transp_just_dia"]  = levi_reent_block["reentregas_transp_just_dia"]
    data["levi_reentregas_dia"]              = levi_reent_block["reentregas_dia"]
    data["levi_reentregas_mes"]              = levi_reent_block["reentregas_mes"]
    data["levi_nf_entregas_dia"]             = levi_reent_block["nf_entregas_dia"]
    data["levi_nf_entregas_mes"]             = levi_reent_block["nf_entregas_mes"]
    data["filtros"]["meses_levi_reent"]      = levi_reent_block["filtros_meses"]
    data["filtros"]["dias_levi_reent"]       = levi_reent_block["filtros_dias"]

    # === LEVITARE ROTEIRO ===
    lv_kpis, lv_dia, lv_mes, lv_veic, lv_veic_dia, lv_veic_mes, lv_meses, lv_dias = \
        build_escala_aggregations(df_levitare)
    data["levitare_kpis"]            = lv_kpis
    data["levitare_por_dia"]         = r(lv_dia)
    data["levitare_por_mes"]         = r(lv_mes)
    data["levitare_por_veiculo"]     = r(lv_veic)
    data["levitare_por_veiculo_dia"] = r(lv_veic_dia)
    data["levitare_por_veiculo_mes"] = r(lv_veic_mes)
    data["filtros"]["meses_levitare"] = lv_meses
    data["filtros"]["dias_levitare"]  = lv_dias

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    k  = data["kpis"]
    vk = data["vesp_kpis"]
    print(f"\n[OK] JSON salvo em: {OUTPUT_JSON}")
    print(f"     Ocupação={k['ocupacao_total']}% | R$/Kg={k['real_kg_total']}")
    print(f"     Peso ajustado={k['peso_total']:,.0f} kg (+{int((FATOR_PESO-1)*100)}%) | Veículos={k['qtd_veiculos']}")
    print(f"     Reentregas={k['reentregas']} ({k['pct_reentregas']}%) [distinct CHAVE]")
    print(f"     Entregas NF={k['qtd_entregas_nf']}")
    fk = data["fresc_kpis"]
    print(f"     Vespertina: {vk['qtd_veiculos']} veículos | Ocupação={vk['ocupacao_total']}%")
    print(f"     Frescal: {fk['qtd_veiculos']} veículos | Ocupação={fk['ocupacao_total']}%")
    print("=" * 60)


if __name__ == "__main__":
    main()
