# app.py

import streamlit as st
import pandas as pd

st.set_page_config(page_title="Fluxo de Caixa", layout="wide")
st.title("Sistema de Fluxo de Caixa Diário")

# --- Funções auxiliares ---
def parse_file(uploaded, is_excel, dayfirst, dec_br):
    """Lê e normaliza um arquivo Excel ou CSV."""
    if uploaded is None:
        return None
    # Leitura inicial
    if is_excel:
        df = pd.read_excel(uploaded, engine="openpyxl", dtype=str)
    else:
        df = pd.read_csv(
            uploaded,
            sep=";",
            dtype=str,
            decimal="," if dec_br else ".",
            thousands="." if dec_br else None,
        )
    # Converter colunas de data
    for col in df.columns:
        if "Data" in col:
            df[col] = pd.to_datetime(df[col], dayfirst=dayfirst, errors="coerce")
    # Converter colunas numéricas
    for col in df.columns:
        if any(x in col for x in ["Valor", "Acréscimo", "Desconto", "Seguro", "Taxa"]):
            s = df[col].astype(str)
            if dec_br:
                s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
            df[col] = pd.to_numeric(s, errors="coerce")
    return df

# --- Uploads e opções ---
st.sidebar.header("Uploads")
with st.sidebar.expander("1. Contas Recebidas / A Receber"):
    excel_file = st.file_uploader("Arquivo Excel", type=["xls", "xlsx"], key="rec")
    rec_date_br = st.checkbox("Datas em formato brasileiro (dd/mm/aaaa)", key="rec_date")
    rec_val_br = st.checkbox("Valores em formato brasileiro (1.234,56)", key="rec_val")

with st.sidebar.expander("2. Contas Pagas"):
    paid_file = st.file_uploader("Arquivo CSV", type=["csv"], key="paid")
    paid_date_br = st.checkbox("Datas em formato brasileiro (dd/mm/aaaa)", key="paid_date")
    paid_val_br = st.checkbox("Valores em formato brasileiro (1.234,56)", key="paid_val")

with st.sidebar.expander("3. Contas a Pagar"):
    pay_file = st.file_uploader("Arquivo CSV", type=["csv"], key="pay")
    pay_date_br = st.checkbox("Datas em formato brasileiro (dd/mm/aaaa)", key="pay_date")
    pay_val_br = st.checkbox("Valores em formato brasileiro (1.234,56)", key="pay_val")

# --- Parse ---
df_rec  = parse_file(excel_file, is_excel=True,  dayfirst=rec_date_br,  dec_br=rec_val_br)
df_paid = parse_file(paid_file,   is_excel=False, dayfirst=paid_date_br, dec_br=paid_val_br)
df_pay  = parse_file(pay_file,    is_excel=False, dayfirst=pay_date_br,  dec_br=pay_val_br)

# Mostrar tabelas interativas
if df_rec is not None:
    st.subheader("Contas Recebidas / A Receber")
    st.dataframe(df_rec, use_container_width=True)

if df_paid is not None:
    st.subheader("Contas Pagas")
    st.dataframe(df_paid, use_container_width=True)

if df_pay is not None:
    st.subheader("Contas a Pagar")
    st.dataframe(df_pay, use_container_width=True)

# --- Fluxo de Caixa ---
if df_rec is not None and df_paid is not None and df_pay is not None:
    # encontrar a data inicial mais antiga
    all_dates = []
    for df in (df_rec, df_paid, df_pay):
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                all_dates.append(df[col].min())
    data_inicio = min(d for d in all_dates if pd.notnull(d))
    st.markdown(f"**Data inicial detectada:** {data_inicio.date()}")

    saldo_inicial = st.number_input(
        f"Saldo de caixa em {data_inicio.date()}",
        value=0.0,
        format="%.2f"
    )

    if st.button("Gerar Fluxo de Caixa"):
        # Entradas
        if "Data da baixa" in df_rec.columns and "Valor da baixa" in df_rec.columns:
            rec_fluxo = (
                df_rec[["Data da baixa", "Valor da baixa"]]
                .dropna()
                .rename(columns={"Data da baixa": "Data", "Valor da baixa": "Entrada"})
            )
        else:
            rec_fluxo = pd.DataFrame(columns=["Data", "Entrada"])

        # Saídas
        paid_date_col = next((c for c in df_paid.columns if "Data pagamento" in c), None)
        paid_val_col  = next((c for c in df_paid.columns if "Valor Líquido"    in c), None)
        if paid_date_col and paid_val_col:
            paid_fluxo = (
                df_paid[[paid_date_col, paid_val_col]]
                .dropna()
                .rename(columns={paid_date_col: "Data", paid_val_col: "Saída"})
            )
        else:
            paid_fluxo = pd.DataFrame(columns=["Data", "Saída"])

        # Consolidação
        fluxo = (
            pd.concat([rec_fluxo, paid_fluxo], ignore_index=True)
            .fillna(0)
            .groupby("Data", as_index=False)
            .sum()
            .sort_values("Data")
        )
        fluxo["Variação"] = fluxo["Entrada"] - fluxo["Saída"]
        fluxo["Saldo Acumulado"] = saldo_inicial + fluxo["Variação"].cumsum()

        st.subheader("Fluxo de Caixa Diário")
        st.dataframe(fluxo, use_container_width=True)
