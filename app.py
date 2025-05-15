# app.py
import streamlit as st
import pandas as pd
import numpy as np
from io import StringIO

st.set_page_config(page_title="Fluxo de Caixa", layout="wide")

st.title("💰 Fluxo de Caixa Realizado e a Realizar")

# --- File uploads and paste fallback ---
st.sidebar.header("Importar dados")
uploaded = st.sidebar.file_uploader(
    "Faça upload de um ou mais CSVs", type=["csv"], accept_multiple_files=True
)

paste_area = st.sidebar.checkbox("Não conseguiu fazer upload? Copiar/colar CSV:")
pasted = None
if paste_area:
    pasted = st.sidebar.text_area("Cole o conteúdo CSV aqui", height=200)

if not uploaded and not pasted:
    st.info("Faça upload de ao menos um CSV de contas pagas ou recebidas, ou cole o conteúdo.")
    st.stop()

# --- Detection & normalization ---
def normalize_paid(df):
    # pagos: expect columns like 'Data pagamento', 'Valor Líquido' or 'Valor a pagar'
    date_col = next((c for c in df.columns if "Data pagamento" in c), None)
    amt_col  = next((c for c in df.columns if "Valor Líquido" in c), None) or \
               next((c for c in df.columns if "Valor a pagar" in c), None)
    if date_col and amt_col:
        out = pd.DataFrame({
            "date": pd.to_datetime(df[date_col], dayfirst=True, errors="coerce"),
            "amount": df[amt_col].astype(str).str.replace(r"[^\d,.-]", "", regex=True)
                             .str.replace(".", "", regex=False)
                             .str.replace(",", ".", regex=False)
                             .astype(float) * -1.0
        })
        return out.dropna(subset=["date"])
    raise ValueError("Não é arquivo de pagamentos")

def normalize_received(df):
    # recebidos: expect 'Data da baixa', 'Valor da baixa'
    date_col = next((c for c in df.columns if "Data da baixa" in c), None)
    amt_col  = next((c for c in df.columns if "Valor da baixa" in c), None) or \
               next((c for c in df.columns if "Valor devido" in c), None)
    if date_col and amt_col:
        out = pd.DataFrame({
            "date": pd.to_datetime(df[date_col], dayfirst=True, errors="coerce"),
            "amount": df[amt_col].astype(str).str.replace(r"[^\d,.-]", "", regex=True)
                             .str.replace(".", "", regex=False)
                             .str.replace(",", ".", regex=False)
                             .astype(float)
        })
        return out.dropna(subset=["date"])
    raise ValueError("Não é arquivo de recebimentos")

# read all sources
all_flows = []
errors = []
sources = []

# helper to read a file-like or pasted
def try_normalize(df, name=""):
    for func in (normalize_paid, normalize_received):
        try:
            norm = func(df)
            norm["source"] = name
            return norm
        except Exception:
            continue
    raise ValueError(f"Falha na detecção do modelo: {name}")

# handle uploaded files
for f in uploaded:
    try:
        df = pd.read_csv(f, sep=None, engine="python", dtype=str)
        norm = try_normalize(df, f.name)
        all_flows.append(norm)
    except Exception as e:
        errors.append(f"{f.name}: {e}")

# handle pasted text
if pasted:
    try:
        df = pd.read_csv(StringIO(pasted), sep=None, engine="python", dtype=str)
        norm = try_normalize(df, "pasted")
        all_flows.append(norm)
    except Exception as e:
        errors.append(f"Pasted area: {e}")

if errors:
    st.sidebar.error("Erros na leitura:\n" + "\n".join(errors))

if not all_flows:
    st.error("Nenhum arquivo reconhecido. Ajuste o separador, ou reveja o modelo CSV.")
    st.stop()

flows = pd.concat(all_flows, ignore_index=True)
flows = flows.sort_values("date")

# --- Initial balance input ---
min_date = flows["date"].min().date()
st.sidebar.markdown(f"**Data inicial detectada:** {min_date}")
initial_balance = st.sidebar.number_input(
    f"Saldo de caixa em {min_date}", value=0.0, step=100.0, format="%.2f"
)

# --- Prepare daily aggregates ---
flows["date"] = pd.to_datetime(flows["date"]).dt.date
daily = flows.groupby("date")["amount"].sum().rename("net_flow").to_frame()
# ensure full date index
idx = pd.date_range(min_date, flows["date"].max(), freq="D").date
daily = daily.reindex(idx, fill_value=0.0)
daily["entries"] = daily["net_flow"].clip(lower=0)
daily["exits"]   = (-daily["net_flow"].clip(upper=0))
daily["cum_balance"] = initial_balance + daily["net_flow"].cumsum()
daily["eod_balance"] = initial_balance + daily["net_flow"].cumsum()

# day‐to‐day variation of cum_balance
daily["cum_variation"] = daily["cum_balance"].diff().fillna(0)

# --- KPIs ---
total_net = daily["net_flow"].sum()
min_cum  = daily["cum_balance"].min()
final_bal = daily["cum_balance"].iloc[-1]

st.sidebar.markdown("### KPIs do Período")
st.sidebar.metric("Resultado líquido", f"R$ {total_net:,.2f}")
st.sidebar.metric("Mínimo acumulado (necessidade)", f"R$ {min_cum:,.2f}")
st.sidebar.metric("Saldo final", f"R$ {final_bal:,.2f}")

# --- Charts ---
st.subheader("Fluxo Diário e Posição Acumulada")
chart_df = daily[["net_flow", "cum_balance"]]
st.line_chart(chart_df)

st.subheader("Variação Diária da Posição Acumulada")
st.line_chart(daily["cum_variation"].to_frame("variação"))

# --- Summary table ---
st.subheader("Resumo Diário")
st.dataframe(
    daily.reset_index().rename(columns={
        "index": "Data",
        "entries": "Entradas",
        "exits": "Saídas",
        "eod_balance": "Saldo Fim Dia",
        "cum_balance": "Saldo Acumulado"
    })[["index","entries","exits","eod_balance","cum_balance"]]
    .rename(columns={"index":"Data"}),
    width=800
)

# --- Raw flows with filter ---
st.subheader("Detalhamento de Movimentos")
srcs = flows["source"].unique().tolist()
sel = st.multiselect("Fonte", srcs, default=srcs)
filtered = flows[flows["source"].isin(sel)]
st.dataframe(filtered.sort_values("date"), width=900)
