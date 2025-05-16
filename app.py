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

    # … (continuação do código acima, até o botão)

    if st.button("Gerar Fluxo de Caixa"):
        # --- Entradas (Contas Recebidas/A Receber) ---
        rec = df_rec.copy()

        # As duas situações: já recebidas (Valor da baixa) vs a receber (Valor devido)
        rec['Data_Fluxo'] = rec.apply(
            lambda r: r['Data da baixa']
            if pd.notnull(r.get('Valor da baixa')) and r.get('Valor da baixa') != 0
            else r.get('Data de vencimento'),
            axis=1
        )
        rec['Valor_Fluxo'] = rec.apply(
            lambda r: r['Valor da baixa']
            if pd.notnull(r.get('Valor da baixa')) and r.get('Valor da baixa') != 0
            else r.get('Valor devido'),
            axis=1
        )
        rec_fluxo = (
            rec[['Data_Fluxo', 'Valor_Fluxo']]
            .dropna(subset=['Data_Fluxo', 'Valor_Fluxo'])
            .rename(columns={'Data_Fluxo': 'Data', 'Valor_Fluxo': 'Entrada'})
        )

        # --- Saídas Efetivas (Contas Pagas) ---
        paid = df_paid.copy()
        paid_date_col = next((c for c in paid.columns if "Data pagamento" in c), None)
        paid_val_col  = next((c for c in paid.columns if "Valor Líquido"    in c), None)
        if paid_date_col and paid_val_col:
            paid_fluxo = (
                paid[[paid_date_col, paid_val_col]]
                .dropna()
                .rename(columns={paid_date_col: 'Data', paid_val_col: 'Saída'})
            )
        else:
            paid_fluxo = pd.DataFrame(columns=['Data', 'Saída'])

        # --- Saídas a Realizar (Contas a Pagar) ---
        pay = df_pay.copy()
        pay_date_col = next((c for c in pay.columns if "Data vencimento" in c), None)
        pay_val_col  = next((c for c in pay.columns if "Valor a pagar"    in c), None)
        if pay_date_col and pay_val_col:
            pay_fluxo = (
                pay[[pay_date_col, pay_val_col]]
                .dropna()
                .rename(columns={pay_date_col: 'Data', pay_val_col: 'Saída'})
            )
        else:
            pay_fluxo = pd.DataFrame(columns=['Data', 'Saída'])

        # --- Consolidação do Fluxo Diário ---
        fluxo = (
            pd.concat([rec_fluxo, paid_fluxo, pay_fluxo], ignore_index=True)
              # Entradas -> coluna 'Entrada', Saídas -> coluna 'Saída'
            .assign(
                Entrada=lambda df: df.get('Entrada', 0).fillna(0),
                Saída=lambda df: df.get('Saída', 0).fillna(0)
            )
            .groupby('Data', as_index=False)
            .agg({'Entrada': 'sum', 'Saída': 'sum'})
            .sort_values('Data')
        )
        fluxo['Variação'] = fluxo['Entrada'] - fluxo['Saída']
        fluxo['Saldo Acumulado'] = saldo_inicial + fluxo['Variação'].cumsum()

        st.subheader("Fluxo de Caixa Diário Aprimorado")
        st.dataframe(fluxo, use_container_width=True)
