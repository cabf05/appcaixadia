# app.py

import streamlit as st
import pandas as pd

st.set_page_config(page_title="Fluxo de Caixa", layout="wide")
st.title("Sistema de Fluxo de Caixa Diário")

# --- Função de leitura e normalização ---
def parse_file(uploaded, is_excel, dayfirst, dec_br):
    if uploaded is None:
        return None
    # Leitura
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
    # Converter datas
    for col in df.columns:
        if "Data" in col:
            df[col] = pd.to_datetime(df[col], dayfirst=dayfirst, errors="coerce")
    # Converter valores
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
    excel_file   = st.file_uploader("Arquivo Excel", type=["xls","xlsx"], key="rec")
    rec_date_br  = st.checkbox("Datas em formato brasileiro (dd/mm/aaaa)", key="rec_date")
    rec_val_br   = st.checkbox("Valores em formato brasileiro (1.234,56)",    key="rec_val")

with st.sidebar.expander("2. Contas Pagas"):
    paid_file    = st.file_uploader("Arquivo CSV", type=["csv"], key="paid")
    paid_date_br = st.checkbox("Datas em formato brasileiro (dd/mm/aaaa)", key="paid_date")
    paid_val_br  = st.checkbox("Valores em formato brasileiro (1.234,56)",    key="paid_val")

with st.sidebar.expander("3. Contas a Pagar"):
    pay_file     = st.file_uploader("Arquivo CSV", type=["csv"], key="pay")
    pay_date_br  = st.checkbox("Datas em formato brasileiro (dd/mm/aaaa)", key="pay_date")
    pay_val_br   = st.checkbox("Valores em formato brasileiro (1.234,56)",    key="pay_val")

# --- Parse dos arquivos ---
df_rec  = parse_file(excel_file, is_excel=True,  dayfirst=rec_date_br,  dec_br=rec_val_br)
df_paid = parse_file(paid_file,   is_excel=False, dayfirst=paid_date_br, dec_br=paid_val_br)
df_pay  = parse_file(pay_file,    is_excel=False, dayfirst=pay_date_br,  dec_br=pay_val_br)

# Mostrar tabelas
if df_rec is not None:
    st.subheader("Contas Recebidas / A Receber")
    st.dataframe(df_rec, use_container_width=True)
if df_paid is not None:
    st.subheader("Contas Pagas")
    st.dataframe(df_paid, use_container_width=True)
if df_pay is not None:
    st.subheader("Contas a Pagar")
    st.dataframe(df_pay, use_container_width=True)

# --- Fluxo de Caixa Diário ---
if df_rec is not None and df_paid is not None and df_pay is not None:
    # Data inicial
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
        # --- Entradas Recebidas vs A Receber ---
        mask_rec = df_rec.get('Valor da baixa').notna() & (df_rec['Valor da baixa'] > 0)
        rec_received = (
            df_rec.loc[mask_rec, ['Data da baixa', 'Valor da baixa']]
            .rename(columns={'Data da baixa': 'Data', 'Valor da baixa': 'Entrada'})
            .dropna()
        )
        mask_prev = df_rec.get('Valor da baixa').isna() | (df_rec['Valor da baixa'] == 0)
        rec_expected = (
            df_rec.loc[mask_prev, ['Data vencimento', 'Valor devido']]
            .rename(columns={'Data vencimento': 'Data', 'Valor devido': 'Entrada'})
            .dropna()
        )
        rec_fluxo = pd.concat([rec_received, rec_expected], ignore_index=True)

        # --- Saídas Efetivas (Contas Pagas) com soma de aprop fin + aprop obra ---
        paid_date_col = next((c for c in df_paid.columns if "Data pagamento" in c), None)
        if paid_date_col:
            paid_fluxo = df_paid[[paid_date_col, 'Valor aprop fin']].copy()
            paid_fluxo['Saída'] = (
                paid_fluxo['Valor aprop fin'].fillna(0)
            )
            paid_fluxo = paid_fluxo[[paid_date_col, 'Saída']].rename(columns={paid_date_col: 'Data'}).dropna()
        else:
            paid_fluxo = pd.DataFrame(columns=['Data','Saída'])

        # --- Saídas a Realizar (Contas a Pagar) com soma de aprop fin + aprop obra ---
        pay_date_col = next((c for c in df_pay.columns if "Data vencimento" in c), None)
        if pay_date_col:
            pay_fluxo = df_pay[[pay_date_col, 'Valor aprop fin']].copy()
            pay_fluxo['Saída'] = (
                pay_fluxo['Valor aprop fin'].fillna(0)
            )
            pay_fluxo = pay_fluxo[[pay_date_col, 'Saída']].rename(columns={pay_date_col: 'Data'}).dropna()
        else:
            pay_fluxo = pd.DataFrame(columns=['Data','Saída'])

        # --- Consolidação ---
        fluxo = (
            pd.concat([rec_fluxo, paid_fluxo, pay_fluxo], ignore_index=True)
              .assign(
                  Entrada=lambda df: df.get('Entrada', 0).fillna(0),
                  Saída=lambda df: df.get('Saída',    0).fillna(0)
              )
              .groupby('Data', as_index=False)
              .agg({'Entrada':'sum','Saída':'sum'})
              .sort_values('Data')
        )
        fluxo['Variação']         = fluxo['Entrada'] - fluxo['Saída']
        fluxo['Saldo Acumulado']  = saldo_inicial + fluxo['Variação'].cumsum()

        st.subheader("Fluxo de Caixa Diário Aprimorado")
        st.dataframe(fluxo, use_container_width=True)
