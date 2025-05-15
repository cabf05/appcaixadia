# app.py
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Cash Flow Dashboard", layout="wide")
st.title("Fluxo de Caixa: Realizado e a Realizar")

# Upload dos arquivos
pagas_file = st.sidebar.file_uploader(
    "Upload CSV de Contas Pagas (realizado)", type=["csv"]
)
pagar_file = st.sidebar.file_uploader(
    "Upload CSV de Contas a Pagar (a realizar)", type=["csv"]
)
rec_file = st.sidebar.file_uploader(
    "Upload CSV de Contas Recebidas/Receber (realizado e a realizar)", type=["csv"]
)

if pagas_file and pagar_file and rec_file:
    # Leitura dos CSVs com separador ';'
    df_pagas = pd.read_csv(
        pagas_file,
        sep=';',
        parse_dates=['Data pagamento'],
        dayfirst=True,
        dtype=str,
        low_memory=False
    )
    df_pagar = pd.read_csv(
        pagar_file,
        sep=';',
        parse_dates=['Data vencimento'],
        dayfirst=True,
        dtype=str,
        low_memory=False
    )
    df_rec = pd.read_csv(
        rec_file,
        sep=';',
        parse_dates=['Data da baixa', 'Data vencimento'],
        dayfirst=True,
        dtype=str,
        low_memory=False
    )

    # --- Fluxos realizados ---
    # Pagamentos realizados (usar Valor Líquido)
    out_real = df_pagas[['Data pagamento', 'Valor Líquido']].dropna(subset=['Data pagamento'])
    out_real = out_real.rename(
        columns={'Data pagamento': 'date', 'Valor Líquido': 'amount'}
    )
    out_real['amount'] = (
        out_real['amount']
        .str.replace(r"\.", "", regex=True)
        .str.replace(",", ".")
        .astype(float)
        * -1
    )
    out_real['type'] = 'Pagamento Realizado'

    # Recebimentos realizados
    in_real = df_rec.dropna(subset=['Data da baixa'])[['Data da baixa', 'Valor da baixa']]
    in_real = in_real.rename(
        columns={'Data da baixa': 'date', 'Valor da baixa': 'amount'}
    )
    in_real['amount'] = (
        in_real['amount']
        .str.replace(r"[^0-9,]", "", regex=True)
        .str.replace(",", ".")
        .astype(float)
    )
    in_real['type'] = 'Recebimento Realizado'

    # --- Fluxos a realizar ---
    # Pagamentos a realizar
    out_forecast = df_pagar[['Data vencimento', 'Valor a pagar']]
    out_forecast = out_forecast.rename(
        columns={'Data vencimento': 'date', 'Valor a pagar': 'amount'}
    )
    out_forecast['amount'] = (
        out_forecast['amount']
        .str.replace(r"\.", "", regex=True)
        .str.replace(",", ".")
        .astype(float)
        * -1
    )
    out_forecast['type'] = 'Pagamento a Realizar'

    # Recebimentos a realizar (sem data de baixa)
    rec_forecast = df_rec[df_rec['Data da baixa'].isna()][['Data vencimento', 'Valor original']]
    rec_forecast = rec_forecast.rename(
        columns={'Data vencimento': 'date', 'Valor original': 'amount'}
    )
    rec_forecast['amount'] = (
        rec_forecast['amount']
        .str.replace(r"[^0-9,]", "", regex=True)
        .str.replace(",", ".")
        .astype(float)
    )
    rec_forecast['type'] = 'Recebimento a Realizar'

    # Consolidar fluxos
    df_flow = pd.concat([out_real, in_real, out_forecast, rec_forecast], ignore_index=True)
    df_flow = df_flow.dropna(subset=['date']).sort_values('date')

    # Data inicial e saldo inicial
    primeira_data = df_flow['date'].min().date()
    st.sidebar.write(f"Primeira data identificada: {primeira_data}")
    saldo_inicial = st.sidebar.number_input(
        f"Saldo de caixa em {primeira_data}",
        value=0.0,
        step=0.01
    )

    # Agrupar por dia
    daily = df_flow.groupby('date')['amount'].sum().reset_index()
    daily = daily.set_index('date').asfreq('D', fill_value=0).reset_index()
    daily['Cumulativo'] = daily['amount'].cumsum() + saldo_inicial

    # Gráficos
    st.subheader('Fluxo Diário')
    st.line_chart(daily.set_index('date')['amount'])

    st.subheader('Posição Acumulada')
    st.line_chart(daily.set_index('date')['Cumulativo'])

    # Variação diária
    st.subheader('Variação Diária')
    df_var = daily.rename(columns={'amount': 'Fluxo Diário'})
    st.dataframe(df_var[['date', 'Fluxo Diário']])

    # Tabela resumo
    st.subheader('Resumo Diário')
    resumo = daily.rename(
        columns={'amount': 'Fluxo Diário', 'Cumulativo': 'Saldo Acumulado'}
    )
    st.dataframe(resumo)

    # Detalhamento e filtros
    st.subheader('Detalhamento de Lançamentos')
    tipos = st.multiselect(
        'Filtrar por Tipo',
        options=df_flow['type'].unique(),
        default=list(df_flow['type'].unique())
    )
    df_filt = df_flow[df_flow['type'].isin(tipos)]
    st.dataframe(df_filt)

    # KPIs
    st.subheader('KPIs')
    necessidade_caixa = resumo['Saldo Acumulado'].min()
    resultado_final = resumo['Saldo Acumulado'].iloc[-1] - saldo_inicial
    st.metric('Necessidade de Caixa (mínimo)', f"{necessidade_caixa:.2f}")
    st.metric('Resultado Final no Período', f"{resultado_final:.2f}")

else:
    st.info('Faça o upload dos três arquivos CSV para visualizar o dashboard.')



