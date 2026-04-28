"""
Pipeline ETL - Indicador de Roteiro 2026
Automatiza todas as transformações descritas no Receita.xlsx
e gera os dados JSON para o dashboard HTML.
"""

import pandas as pd
import numpy as np
import json
import os
import warnings
from datetime import datetime

warnings.filterwarnings("ignore", category=UserWarning)

# ============================================================
# CONFIGURAÇÃO DE CAMINHOS
# ============================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS_DIR = os.path.join(BASE_DIR, "Dados")
ETL_DIR = os.path.join(BASE_DIR, "ETL")
ESCALA_PATH = r"C:\Users\david.santos\TIROLEZ\Logistica - Arquivos\Roteiros\2026\Controle de Roteirização_2026.xlsx"
NF_PATH = os.path.join(DADOS_DIR, "NF.xlsx")
OCORRENCIAS_PATH = os.path.join(DADOS_DIR, "Ocorrencias.xlsx")
FROTA_PATH = r"C:\Users\david.santos\TIROLEZ\Logistica - Arquivos\FROTA LEGAL\ROTEIRIZAÇÃO\Disp. de Veiculos 2026..xlsm"
OUTPUT_JSON = os.path.join(ETL_DIR, "dashboard_data.json")

TRANSPORTADORAS_FILTRO = [30230, 30828, 31672, 31704, 31718, 31903, 31984, 60133, 60134, 60144, 60150]
MOTIVO_REENTREGA = 2014
UF_FILTRO = "SP"
FATOR_PESO = 1.10  # Peso + 10%


def load_escala():
    print("[1/5] Carregando ESCALA...")
    df = pd.read_excel(ESCALA_PATH, sheet_name="ESCALA", header=10, usecols="C:R")
    df = df.dropna(subset=["ID"])

    df["DATA"] = pd.to_datetime(df["DATA"], errors="coerce")
    df["PESO"] = pd.to_numeric(df["PESO"], errors="coerce").fillna(0)
    df["CAPAC."] = pd.to_numeric(df["CAPAC."], errors="coerce").fillna(0)
    df["CUSTO FRETE"] = pd.to_numeric(df["CUSTO FRETE"], errors="coerce").fillna(0)
    df["ENTREGAS"] = pd.to_numeric(df["ENTREGAS"], errors="coerce").fillna(0)

    # +10% no peso
    df["PESO"] = df["PESO"] * FATOR_PESO

    df["Real_Kg"] = np.where(df["PESO"] > 0, df["CUSTO FRETE"] / df["PESO"], 0)
    df["Ocupacao"] = np.where(df["CAPAC."] > 0, df["PESO"] / df["CAPAC."], 0)

    df = df.dropna(subset=["DATA"])
    df["MES_KEY"] = df["DATA"].dt.strftime("%Y-%m")
    df["DIA"] = df["DATA"].dt.strftime("%Y-%m-%d")

    print(f"   -> {len(df)} registros (peso +10%)")
    return df


def load_nf():
    print("[2/5] Carregando NF...")
    df = pd.read_excel(NF_PATH)
    df = df[df["UF"] == UF_FILTRO].copy()
    df["TRANSPORTADORA"] = pd.to_numeric(df["TRANSPORTADORA"], errors="coerce")
    df = df[df["TRANSPORTADORA"].isin(TRANSPORTADORAS_FILTRO)].copy()

    df["DATA  SAÍDA"] = pd.to_datetime(df["DATA  SAÍDA"], errors="coerce")
    df["COD. CLIENTE"] = df["COD. CLIENTE"].astype(str)
    df["CHAVE_ENTREGA"] = df["DATA  SAÍDA"].dt.strftime("%Y-%m-%d") + "_" + df["COD. CLIENTE"]
    df["MES_KEY"] = df["DATA  SAÍDA"].dt.strftime("%Y-%m")
    df["DIA"] = df["DATA  SAÍDA"].dt.strftime("%Y-%m-%d")

    print(f"   -> {len(df)} registros (SP + transportadoras)")
    return df


def load_ocorrencias(nf_df):
    print("[3/5] Carregando Ocorrências...")
    df = pd.read_excel(OCORRENCIAS_PATH)
    df = df[df["UF"] == UF_FILTRO].copy()
    df = df[df["MOTIVO OCORRÊNCIA"] == MOTIVO_REENTREGA].copy()

    nf_lookup = nf_df.drop_duplicates(subset=["NFF"])[["NFF", "NOME TRANSPORTADORA"]].copy()
    nf_lookup["NFF"] = pd.to_numeric(nf_lookup["NFF"], errors="coerce")
    df["DOCUMENTO"] = pd.to_numeric(df["DOCUMENTO"], errors="coerce")
    df = df.merge(nf_lookup, left_on="DOCUMENTO", right_on="NFF", how="left")

    df["DATA INCLUSÃO"] = pd.to_datetime(df["DATA INCLUSÃO"], errors="coerce")
    df["COD. CLIENTE"] = df["COD. CLIENTE"].astype(str)
    df["CHAVE_ENTREGA"] = df["DATA INCLUSÃO"].dt.strftime("%Y-%m-%d") + "_" + df["COD. CLIENTE"]
    df["MES_KEY"] = df["DATA INCLUSÃO"].dt.strftime("%Y-%m")
    df["DIA"] = df["DATA INCLUSÃO"].dt.strftime("%Y-%m-%d")

    print(f"   -> {len(df)} registros | {df['CHAVE_ENTREGA'].nunique()} reentregas (chave distinta)")
    return df


def load_frota():
    print("[4/5] Carregando Disponibilidade de Frota...")
    disp = pd.read_excel(FROTA_PATH, sheet_name="DISPONIBILIZADO")
    util = pd.read_excel(FROTA_PATH, sheet_name="UTILIZADO")

    disp["Data"] = pd.to_datetime(disp["Data"], errors="coerce")
    util["Data"] = pd.to_datetime(util["Data"], errors="coerce")
    disp = disp.dropna(subset=["Data"])
    util = util.dropna(subset=["Data"])

    disp["MES_KEY"] = disp["Data"].dt.strftime("%Y-%m")
    disp["DIA"] = disp["Data"].dt.strftime("%Y-%m-%d")
    util["MES_KEY"] = util["Data"].dt.strftime("%Y-%m")
    util["DIA"] = util["Data"].dt.strftime("%Y-%m-%d")

    # Normalizar nome do veículo
    disp["Veiculo"] = disp["Veiculo"].astype(str).str.strip().str.upper()
    util["Veiculo"] = util["Veiculo"].astype(str).str.strip().str.upper()

    print(f"   -> Disponibilizado: {len(disp)} | Utilizado: {len(util)}")
    return disp, util


def build_escala_aggregations(df_escala):
    """Gera KPIs e agrupamentos padrão para um subconjunto de escala."""
    peso_total = float(df_escala["PESO"].sum())
    capac_total = float(df_escala["CAPAC."].sum())
    frete_total = float(df_escala["CUSTO FRETE"].sum())
    real_kg_total = frete_total / peso_total if peso_total > 0 else 0
    ocupacao_total = peso_total / capac_total if capac_total > 0 else 0
    qtd_veiculos = int(len(df_escala))
    qtd_entregas = int(df_escala["ENTREGAS"].sum())

    kpis = {
        "peso_total": round(peso_total, 2),
        "capac_total": round(capac_total, 2),
        "frete_total": round(frete_total, 2),
        "real_kg_total": round(real_kg_total, 4),
        "ocupacao_total": round(ocupacao_total * 100, 2),
        "qtd_veiculos": qtd_veiculos,
        "qtd_entregas": qtd_entregas,
        "meta_ocupacao": 80,
        "meta_real_kg": 0.67,
    }

    # Por dia
    dia_group = df_escala.groupby("DIA").agg(
        peso=("PESO", "sum"), capac=("CAPAC.", "sum"), frete=("CUSTO FRETE", "sum"),
        veiculos=("ID", "count"), entregas=("ENTREGAS", "sum"),
    ).reset_index()
    dia_group["real_kg"] = np.where(dia_group["peso"] > 0, dia_group["frete"] / dia_group["peso"], 0)
    dia_group["ocupacao"] = np.where(dia_group["capac"] > 0, dia_group["peso"] / dia_group["capac"] * 100, 0)
    dia_group = dia_group.sort_values("DIA")

    # Por mês
    mes_group = df_escala.groupby("MES_KEY").agg(
        peso=("PESO", "sum"), capac=("CAPAC.", "sum"), frete=("CUSTO FRETE", "sum"),
        veiculos=("ID", "count"), entregas=("ENTREGAS", "sum"),
    ).reset_index()
    mes_group["real_kg"] = np.where(mes_group["peso"] > 0, mes_group["frete"] / mes_group["peso"], 0)
    mes_group["ocupacao"] = np.where(mes_group["capac"] > 0, mes_group["peso"] / mes_group["capac"] * 100, 0)
    mes_group = mes_group.sort_values("MES_KEY")

    # Por veículo
    veiculo_group = df_escala.groupby("VEICULO").agg(
        peso=("PESO", "sum"), capac=("CAPAC.", "sum"), frete=("CUSTO FRETE", "sum"),
        veiculos=("ID", "count"), entregas=("ENTREGAS", "sum"),
    ).reset_index()
    veiculo_group["real_kg"] = np.where(veiculo_group["peso"] > 0, veiculo_group["frete"] / veiculo_group["peso"], 0)
    veiculo_group["ocupacao"] = np.where(veiculo_group["capac"] > 0, veiculo_group["peso"] / veiculo_group["capac"] * 100, 0)

    # Por veículo + dia
    veiculo_dia = df_escala.groupby(["DIA", "VEICULO"]).agg(
        peso=("PESO", "sum"), capac=("CAPAC.", "sum"), frete=("CUSTO FRETE", "sum"),
        veiculos=("ID", "count"), entregas=("ENTREGAS", "sum"),
    ).reset_index()
    veiculo_dia["real_kg"] = np.where(veiculo_dia["peso"] > 0, veiculo_dia["frete"] / veiculo_dia["peso"], 0)
    veiculo_dia["ocupacao"] = np.where(veiculo_dia["capac"] > 0, veiculo_dia["peso"] / veiculo_dia["capac"] * 100, 0)

    # Por veículo + mês
    veiculo_mes = df_escala.groupby(["MES_KEY", "VEICULO"]).agg(
        peso=("PESO", "sum"), capac=("CAPAC.", "sum"), frete=("CUSTO FRETE", "sum"),
        veiculos=("ID", "count"), entregas=("ENTREGAS", "sum"),
    ).reset_index()
    veiculo_mes["real_kg"] = np.where(veiculo_mes["peso"] > 0, veiculo_mes["frete"] / veiculo_mes["peso"], 0)
    veiculo_mes["ocupacao"] = np.where(veiculo_mes["capac"] > 0, veiculo_mes["peso"] / veiculo_mes["capac"] * 100, 0)

    meses = sorted(df_escala["MES_KEY"].unique().tolist())
    dias = sorted(df_escala["DIA"].unique().tolist())

    return kpis, dia_group, mes_group, veiculo_group, veiculo_dia, veiculo_mes, meses, dias


def build_kpis(escala, nf, reentregas, frota_disp, frota_util):
    print("\n[ETL] Calculando KPIs...")

    peso_total = float(escala["PESO"].sum())
    capac_total = float(escala["CAPAC."].sum())
    frete_total = float(escala["CUSTO FRETE"].sum())
    real_kg_total = frete_total / peso_total if peso_total > 0 else 0
    ocupacao_total = peso_total / capac_total if capac_total > 0 else 0
    qtd_veiculos = int(len(escala))
    qtd_entregas_escala = int(escala["ENTREGAS"].sum())

    # Reentregas = contagem DISTINTA de CHAVE_ENTREGA
    total_reentregas = int(reentregas["CHAVE_ENTREGA"].nunique())
    qtd_entregas_nf = int(nf["CHAVE_ENTREGA"].nunique())
    pct_reentregas = (total_reentregas / qtd_entregas_nf * 100) if qtd_entregas_nf > 0 else 0

    kpis = {
        "peso_total": round(peso_total, 2),
        "capac_total": round(capac_total, 2),
        "frete_total": round(frete_total, 2),
        "real_kg_total": round(real_kg_total, 4),
        "ocupacao_total": round(ocupacao_total * 100, 2),
        "qtd_veiculos": qtd_veiculos,
        "qtd_entregas": qtd_entregas_escala,
        "reentregas": total_reentregas,
        "qtd_entregas_nf": qtd_entregas_nf,
        "pct_reentregas": round(pct_reentregas, 2),
        "meta_ocupacao": 80,
        "meta_real_kg": 0.67,
    }

    # === POR DIA (ESCALA) ===
    dia_group = escala.groupby("DIA").agg(
        peso=("PESO", "sum"), capac=("CAPAC.", "sum"), frete=("CUSTO FRETE", "sum"),
        veiculos=("ID", "count"), entregas=("ENTREGAS", "sum"),
    ).reset_index()
    dia_group["real_kg"] = np.where(dia_group["peso"] > 0, dia_group["frete"] / dia_group["peso"], 0)
    dia_group["ocupacao"] = np.where(dia_group["capac"] > 0, dia_group["peso"] / dia_group["capac"] * 100, 0)
    dia_group = dia_group.sort_values("DIA")

    # === POR MÊS (ESCALA) ===
    mes_group = escala.groupby("MES_KEY").agg(
        peso=("PESO", "sum"), capac=("CAPAC.", "sum"), frete=("CUSTO FRETE", "sum"),
        veiculos=("ID", "count"), entregas=("ENTREGAS", "sum"),
    ).reset_index()
    mes_group["real_kg"] = np.where(mes_group["peso"] > 0, mes_group["frete"] / mes_group["peso"], 0)
    mes_group["ocupacao"] = np.where(mes_group["capac"] > 0, mes_group["peso"] / mes_group["capac"] * 100, 0)
    mes_group = mes_group.sort_values("MES_KEY")

    # === POR VEÍCULO (ESCALA) ===
    veiculo_group = escala.groupby("VEICULO").agg(
        peso=("PESO", "sum"), capac=("CAPAC.", "sum"), frete=("CUSTO FRETE", "sum"),
        veiculos=("ID", "count"), entregas=("ENTREGAS", "sum"),
    ).reset_index()
    veiculo_group["real_kg"] = np.where(veiculo_group["peso"] > 0, veiculo_group["frete"] / veiculo_group["peso"], 0)
    veiculo_group["ocupacao"] = np.where(veiculo_group["capac"] > 0, veiculo_group["peso"] / veiculo_group["capac"] * 100, 0)
    veiculo_group["media_entregas"] = np.where(veiculo_group["veiculos"] > 0, veiculo_group["entregas"] / veiculo_group["veiculos"], 0)
    veiculo_group["media_peso"] = np.where(veiculo_group["veiculos"] > 0, veiculo_group["peso"] / veiculo_group["veiculos"], 0)

    # === POR VEÍCULO + DIA ===
    veiculo_dia = escala.groupby(["DIA", "VEICULO"]).agg(
        peso=("PESO", "sum"), capac=("CAPAC.", "sum"), frete=("CUSTO FRETE", "sum"),
        veiculos=("ID", "count"), entregas=("ENTREGAS", "sum"),
    ).reset_index()
    veiculo_dia["real_kg"] = np.where(veiculo_dia["peso"] > 0, veiculo_dia["frete"] / veiculo_dia["peso"], 0)
    veiculo_dia["ocupacao"] = np.where(veiculo_dia["capac"] > 0, veiculo_dia["peso"] / veiculo_dia["capac"] * 100, 0)
    veiculo_dia["media_entregas"] = np.where(veiculo_dia["veiculos"] > 0, veiculo_dia["entregas"] / veiculo_dia["veiculos"], 0)
    veiculo_dia["media_peso"] = np.where(veiculo_dia["veiculos"] > 0, veiculo_dia["peso"] / veiculo_dia["veiculos"], 0)

    # === POR VEÍCULO + MÊS ===
    veiculo_mes = escala.groupby(["MES_KEY", "VEICULO"]).agg(
        peso=("PESO", "sum"), capac=("CAPAC.", "sum"), frete=("CUSTO FRETE", "sum"),
        veiculos=("ID", "count"), entregas=("ENTREGAS", "sum"),
    ).reset_index()
    veiculo_mes["real_kg"] = np.where(veiculo_mes["peso"] > 0, veiculo_mes["frete"] / veiculo_mes["peso"], 0)
    veiculo_mes["ocupacao"] = np.where(veiculo_mes["capac"] > 0, veiculo_mes["peso"] / veiculo_mes["capac"] * 100, 0)
    veiculo_mes["media_entregas"] = np.where(veiculo_mes["veiculos"] > 0, veiculo_mes["entregas"] / veiculo_mes["veiculos"], 0)
    veiculo_mes["media_peso"] = np.where(veiculo_mes["veiculos"] > 0, veiculo_mes["peso"] / veiculo_mes["veiculos"], 0)

    # === DISTRIBUIÇÃO POR FAIXA DE KM ===
    escala["FAIXA"] = pd.to_numeric(escala["FAIXA"], errors="coerce").fillna(0)

    def _agg_veic(df_sub):
        cols = {"peso": ("PESO", "sum"), "capac": ("CAPAC.", "sum"), "frete": ("CUSTO FRETE", "sum"),
                "veiculos": ("ID", "count"), "entregas": ("ENTREGAS", "sum")}
        veic = df_sub.groupby("VEICULO").agg(**cols).reset_index()
        dia = df_sub.groupby(["DIA", "VEICULO"]).agg(**cols).reset_index()
        mes = df_sub.groupby(["MES_KEY", "VEICULO"]).agg(**cols).reset_index()
        for d in [veic, dia, mes]:
            d["real_kg"] = np.where(d["peso"] > 0, d["frete"] / d["peso"], 0)
            d["ocupacao"] = np.where(d["capac"] > 0, d["peso"] / d["capac"] * 100, 0)
            d["media_entregas"] = np.where(d["veiculos"] > 0, d["entregas"] / d["veiculos"], 0)
            d["media_peso"] = np.where(d["veiculos"] > 0, d["peso"] / d["veiculos"], 0)
        return veic, dia, mes

    dist_0_100_veic, dist_0_100_dia, dist_0_100_mes = _agg_veic(escala[escala["FAIXA"].isin([1, 2])])
    dist_100p_veic, dist_100p_dia, dist_100p_mes = _agg_veic(escala[escala["FAIXA"] >= 3])

    # === REENTREGAS (contagem distinta CHAVE) ===
    # Entregas NF por transportadora (para calcular % real)
    nf_transp = nf.groupby("NOME TRANSPORTADORA").agg(
        entregas=("CHAVE_ENTREGA", "nunique"),
    ).reset_index()

    reent_transp = reentregas.groupby("NOME TRANSPORTADORA").agg(
        reentregas=("CHAVE_ENTREGA", "nunique"),
    ).reset_index().sort_values("reentregas", ascending=False)
    reent_transp = reent_transp.merge(nf_transp, on="NOME TRANSPORTADORA", how="left").fillna(0)
    reent_transp["entregas"] = reent_transp["entregas"].astype(int)
    reent_transp["pct"] = round(reent_transp["reentregas"] / reent_transp["entregas"] * 100, 2).where(reent_transp["entregas"] > 0, 0)

    reent_just = reentregas.groupby("DESC JUST OC").agg(
        reentregas=("CHAVE_ENTREGA", "nunique"),
    ).reset_index().sort_values("reentregas", ascending=False)
    tj = reent_just["reentregas"].sum()
    reent_just["pct"] = round(reent_just["reentregas"] / tj * 100, 2) if tj > 0 else 0

    reent_transp_just = reentregas.groupby(["NOME TRANSPORTADORA", "DESC JUST OC"]).agg(
        reentregas=("CHAVE_ENTREGA", "nunique"),
    ).reset_index().sort_values("reentregas", ascending=False)

    # Granular por DIA para filtros no dashboard
    reent_transp_dia_g = reentregas.groupby(["DIA", "NOME TRANSPORTADORA"]).agg(
        reentregas=("CHAVE_ENTREGA", "nunique"),
    ).reset_index()

    nf_transp_dia_g = nf.groupby(["DIA", "NOME TRANSPORTADORA"]).agg(
        entregas=("CHAVE_ENTREGA", "nunique"),
    ).reset_index()

    reent_just_dia_g = reentregas.groupby(["DIA", "DESC JUST OC"]).agg(
        reentregas=("CHAVE_ENTREGA", "nunique"),
    ).reset_index()

    reent_transp_just_dia_g = reentregas.groupby(["DIA", "NOME TRANSPORTADORA", "DESC JUST OC"]).agg(
        reentregas=("CHAVE_ENTREGA", "nunique"),
    ).reset_index()

    reent_dia = reentregas.groupby("DIA").agg(
        reentregas=("CHAVE_ENTREGA", "nunique"),
    ).reset_index().sort_values("DIA")

    reent_mes = reentregas.groupby("MES_KEY").agg(
        reentregas=("CHAVE_ENTREGA", "nunique"),
    ).reset_index().sort_values("MES_KEY")

    nf_dia = nf.groupby("DIA").agg(qtd_entregas=("CHAVE_ENTREGA", "nunique")).reset_index().sort_values("DIA")
    nf_mes = nf.groupby("MES_KEY").agg(qtd_entregas=("CHAVE_ENTREGA", "nunique")).reset_index().sort_values("MES_KEY")

    meses_disponiveis = sorted(escala["MES_KEY"].unique().tolist())
    dias_disponiveis = sorted(escala["DIA"].unique().tolist())
    meses_reent = sorted(reentregas["MES_KEY"].dropna().unique().tolist())
    dias_reent = sorted(reentregas["DIA"].dropna().unique().tolist())

    def df_to_records(df):
        return json.loads(df.to_json(orient="records", date_format="iso"))

    # === FROTA: DISPONIBILIZADO vs UTILIZADO ===
    # Total geral
    total_disp = len(frota_disp)
    total_util = len(frota_util)
    pct_util_geral = round(total_util / total_disp * 100, 2) if total_disp > 0 else 0

    # Por transportadora
    frota_disp_transp = frota_disp.groupby("Transportadora").size().reset_index(name="disponibilizado")
    frota_util_transp = frota_util.groupby("Transportadora").size().reset_index(name="utilizado")
    frota_transp = frota_disp_transp.merge(frota_util_transp, on="Transportadora", how="left").fillna(0)
    frota_transp["utilizado"] = frota_transp["utilizado"].astype(int)
    frota_transp["pct"] = round(frota_transp["utilizado"] / frota_transp["disponibilizado"] * 100, 2)
    frota_transp = frota_transp.sort_values("disponibilizado", ascending=False)

    # Por veículo (tipo)
    frota_disp_veic = frota_disp.groupby("Veiculo").size().reset_index(name="disponibilizado")
    frota_util_veic = frota_util.groupby("Veiculo").size().reset_index(name="utilizado")
    frota_veic = frota_disp_veic.merge(frota_util_veic, on="Veiculo", how="left").fillna(0)
    frota_veic["utilizado"] = frota_veic["utilizado"].astype(int)
    frota_veic["pct"] = round(frota_veic["utilizado"] / frota_veic["disponibilizado"] * 100, 2)
    frota_veic = frota_veic.sort_values("disponibilizado", ascending=False)

    # Por dia
    frota_disp_dia = frota_disp.groupby("DIA").size().reset_index(name="disponibilizado")
    frota_util_dia = frota_util.groupby("DIA").size().reset_index(name="utilizado")
    frota_dia = frota_disp_dia.merge(frota_util_dia, on="DIA", how="left").fillna(0)
    frota_dia["utilizado"] = frota_dia["utilizado"].astype(int)
    frota_dia["pct"] = round(frota_dia["utilizado"] / frota_dia["disponibilizado"] * 100, 2)
    frota_dia = frota_dia.sort_values("DIA")

    # Por mês
    frota_disp_mes = frota_disp.groupby("MES_KEY").size().reset_index(name="disponibilizado")
    frota_util_mes = frota_util.groupby("MES_KEY").size().reset_index(name="utilizado")
    frota_mes = frota_disp_mes.merge(frota_util_mes, on="MES_KEY", how="left").fillna(0)
    frota_mes["utilizado"] = frota_mes["utilizado"].astype(int)
    frota_mes["pct"] = round(frota_mes["utilizado"] / frota_mes["disponibilizado"] * 100, 2)
    frota_mes = frota_mes.sort_values("MES_KEY")

    # Por transportadora + dia
    frota_disp_td = frota_disp.groupby(["DIA", "Transportadora"]).size().reset_index(name="disponibilizado")
    frota_util_td = frota_util.groupby(["DIA", "Transportadora"]).size().reset_index(name="utilizado")
    frota_transp_dia = frota_disp_td.merge(frota_util_td, on=["DIA", "Transportadora"], how="left").fillna(0)
    frota_transp_dia["utilizado"] = frota_transp_dia["utilizado"].astype(int)
    frota_transp_dia["pct"] = round(frota_transp_dia["utilizado"] / frota_transp_dia["disponibilizado"] * 100, 2)

    # Por veículo + dia
    frota_disp_vd = frota_disp.groupby(["DIA", "Veiculo"]).size().reset_index(name="disponibilizado")
    frota_util_vd = frota_util.groupby(["DIA", "Veiculo"]).size().reset_index(name="utilizado")
    frota_veic_dia = frota_disp_vd.merge(frota_util_vd, on=["DIA", "Veiculo"], how="left").fillna(0)
    frota_veic_dia["utilizado"] = frota_veic_dia["utilizado"].astype(int)
    frota_veic_dia["pct"] = round(frota_veic_dia["utilizado"] / frota_veic_dia["disponibilizado"] * 100, 2)

    meses_frota = sorted(frota_disp["MES_KEY"].dropna().unique().tolist())
    dias_frota = sorted(frota_disp["DIA"].dropna().unique().tolist())

    return {
        "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "kpis": kpis,
        "filtros": {"meses": meses_disponiveis, "dias": dias_disponiveis, "meses_reent": meses_reent, "dias_reent": dias_reent, "meses_frota": meses_frota, "dias_frota": dias_frota},
        "por_dia": df_to_records(dia_group),
        "por_mes": df_to_records(mes_group),
        "por_veiculo": df_to_records(veiculo_group),
        "por_veiculo_dia": df_to_records(veiculo_dia),
        "por_veiculo_mes": df_to_records(veiculo_mes),
        "dist_0_100_veic": df_to_records(dist_0_100_veic),
        "dist_0_100_dia": df_to_records(dist_0_100_dia),
        "dist_0_100_mes": df_to_records(dist_0_100_mes),
        "dist_100p_veic": df_to_records(dist_100p_veic),
        "dist_100p_dia": df_to_records(dist_100p_dia),
        "dist_100p_mes": df_to_records(dist_100p_mes),
        "reentregas_transportadora": df_to_records(reent_transp),
        "reentregas_justificativa": df_to_records(reent_just),
        "reentregas_transp_just": df_to_records(reent_transp_just),
        "reentregas_transp_dia": df_to_records(reent_transp_dia_g),
        "nf_transp_dia": df_to_records(nf_transp_dia_g),
        "reentregas_just_dia": df_to_records(reent_just_dia_g),
        "reentregas_transp_just_dia": df_to_records(reent_transp_just_dia_g),
        "reentregas_dia": df_to_records(reent_dia),
        "reentregas_mes": df_to_records(reent_mes),
        "nf_entregas_dia": df_to_records(nf_dia),
        "nf_entregas_mes": df_to_records(nf_mes),
        "frota_kpis": {"total_disp": total_disp, "total_util": total_util, "pct_util": pct_util_geral},
        "frota_transportadora": df_to_records(frota_transp),
        "frota_veiculo": df_to_records(frota_veic),
        "frota_dia": df_to_records(frota_dia),
        "frota_mes": df_to_records(frota_mes),
        "frota_transp_dia": df_to_records(frota_transp_dia),
        "frota_veic_dia": df_to_records(frota_veic_dia),
    }


def main():
    print("=" * 60)
    print("  PIPELINE ETL - INDICADOR ROTEIRO 2026")
    print("=" * 60)
    escala = load_escala()
    nf_full = pd.read_excel(NF_PATH)
    nf = load_nf()
    reentregas = load_ocorrencias(nf_full)
    frota_disp, frota_util = load_frota()
    data = build_kpis(escala, nf, reentregas, frota_disp, frota_util)

    # === VESPERTINA ===
    print("[5/5] Processando Vespertina...")
    escala["ROTA"] = escala["ROTA"].astype(str).str.strip().str.upper()
    escala["TRANSPORTADORA - MOTORISTA"] = escala["TRANSPORTADORA - MOTORISTA"].astype(str).str.strip().str.upper()
    vesp = escala[escala["ROTA"] == "VESPERTINA"].copy()
    vesp_tl = vesp[vesp["TRANSPORTADORA - MOTORISTA"] == "TL"].copy()
    print(f"   -> Vespertina: {len(vesp)} registros | TL: {len(vesp_tl)} registros")

    def df_to_records(df):
        return json.loads(df.to_json(orient="records", date_format="iso"))

    v_kpis, v_dia, v_mes, v_veic, v_veic_dia, v_veic_mes, v_meses, v_dias = build_escala_aggregations(vesp)
    data["vesp_kpis"] = v_kpis
    data["vesp_por_dia"] = df_to_records(v_dia)
    data["vesp_por_mes"] = df_to_records(v_mes)
    data["vesp_por_veiculo"] = df_to_records(v_veic)
    data["vesp_por_veiculo_dia"] = df_to_records(v_veic_dia)
    data["vesp_por_veiculo_mes"] = df_to_records(v_veic_mes)
    data["filtros"]["meses_vesp"] = v_meses
    data["filtros"]["dias_vesp"] = v_dias

    # TL (Tirolez / Levitare)
    if len(vesp_tl) > 0:
        tl_kpis, tl_dia, tl_mes, tl_veic, tl_veic_dia, tl_veic_mes, tl_meses, tl_dias = build_escala_aggregations(vesp_tl)
    else:
        tl_kpis = {"peso_total":0,"capac_total":0,"frete_total":0,"real_kg_total":0,"ocupacao_total":0,"qtd_veiculos":0,"qtd_entregas":0,"meta_ocupacao":80,"meta_real_kg":0.67}
        tl_dia = tl_mes = tl_veic = tl_veic_dia = tl_veic_mes = pd.DataFrame()
    data["vesp_tl_kpis"] = tl_kpis
    data["vesp_tl_por_veiculo"] = df_to_records(tl_veic) if len(vesp_tl) > 0 else []
    data["vesp_tl_por_veiculo_dia"] = df_to_records(tl_veic_dia) if len(vesp_tl) > 0 else []
    data["vesp_tl_por_veiculo_mes"] = df_to_records(tl_veic_mes) if len(vesp_tl) > 0 else []
    data["vesp_tl_por_dia"] = df_to_records(tl_dia) if len(vesp_tl) > 0 else []
    data["vesp_tl_por_mes"] = df_to_records(tl_mes) if len(vesp_tl) > 0 else []

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    k = data["kpis"]
    vk = data["vesp_kpis"]
    print(f"\n[OK] JSON salvo em: {OUTPUT_JSON}")
    print(f"     Ocupação={k['ocupacao_total']}% | R$/Kg={k['real_kg_total']}")
    print(f"     Peso={k['peso_total']:,.0f} kg (+10%) | Veículos={k['qtd_veiculos']}")
    print(f"     Reentregas={k['reentregas']} ({k['pct_reentregas']}%) [distinct CHAVE]")
    print(f"     Entregas NF={k['qtd_entregas_nf']}")
    print(f"     Vespertina: {vk['qtd_veiculos']} veículos | Ocupação={vk['ocupacao_total']}%")
    print("=" * 60)

if __name__ == "__main__":
    main()
