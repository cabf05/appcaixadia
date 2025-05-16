import streamlit as st
import pandas as pd

st.set_page_config(page_title="Fluxo de Caixa", layout="wide")
st.title("Sistema de Fluxo de Caixa Diário")

st.markdown(
    "Antes de fazer o upload, verifique se as datas estão no formato dd/mm/aaaa e os valores no formato brasileiro "
    "(milhares separados por ponto e decimais por vírgula). Exemplo de data: 30/01/2024; Exemplo de valor: 1.234,56."
)

# Upload de três arquivos
recebidas_file = st.file_uploader(
    "Contas Recebidas/A Receber (Excel)", type=["xlsx", "xls"], key="recebidas"
)
pagas_file = st.file_uploader("Contas Pagas (CSV)", type=["csv"], key="pagas")
apagar_file = st.file_uploader("Contas a Pagar (CSV)", type=["csv"], key="apagar")

if recebidas_file and pagas_file and apagar_file:
    # Leitura de CSV brasileiro
    def read_brazilian_csv(uploaded_file):
        uploaded_file.seek(0)
        header = pd.read_csv(uploaded_file, sep=';', nrows=0)
        date_cols = [c for c in header.columns if 'Data' in c]
        uploaded_file.seek(0)
        return pd.read_csv(
            uploaded_file,
            sep=';',
            decimal=',',
            thousands='.',
            dayfirst=True,
            parse_dates=date_cols,
            infer_datetime_format=True
        )

    # Leitura de Excel brasileiro: converte datas e valores manualmente
    def read_brazilian_excel(uploaded_file):
        uploaded_file.seek(0)
        # Lê tudo como string para pós-processar
        df = pd.read_excel(uploaded_file, engine='openpyxl', dtype=str)
        # Converte colunas de data
        date_cols = [c for c in df.columns if 'Data' in c]
        for col in date_cols:
            df[col] = pd.to_datetime(df[col], format='%d/%m/%Y', dayfirst=True, errors='coerce')
        # Converte colunas de valor
        value_cols = [c for c in df.columns if 'Valor' in c]
        for col in value_cols:
            df[col] = (
                df[col]
                .str.replace(r"\.", "", regex=True)  # remove separador de milhares
                .str.replace(",", ".", regex=False)   # troca decimal
                .astype(float, errors='ignore')
            )
        return df

    # Carrega dados
    df_receb = read_brazilian_excel(recebidas_file)
    df_pagas = read_brazilian_csv(pagas_file)
    df_apagar = read_brazilian_csv(apagar_file)

    # Adiciona colunas de tipo e fluxo
    df_receb['Tipo'] = 'Recebimento'
    df_receb['Fluxo'] = df_receb.get('Valor líquido', 0)

    df_pagas['Tipo'] = 'Pagamento'
    df_pagas['Fluxo'] = -df_pagas.get('Valor Líquido', 0)

    df_apagar['Tipo'] = 'A Pagar'
    df_apagar['Fluxo'] = -df_apagar.get('Valor a pagar', 0)

    # Consolida registros
    df_all = pd.concat([df_receb, df_pagas, df_apagar], ignore_index=True)

    # Exibe tabela interativa
    st.subheader("Tabela de Movimentações")
    st.data_editor(df_all, use_container_width=True)

    # Identifica data mais antiga
    date_cols_all = [c for c in df_all.columns if df_all[c].dtype == 'datetime64[ns]']
    min_date = df_all[date_cols_all].min().min().date()
    st.info(f"Data mais antiga encontrada: {min_date.strftime('%d/%m/%Y')}")

    # Solicita saldo inicial
    saldo_inicial = st.number_input(
        f"Informe o saldo de caixa em {min_date.strftime('%d/%m/%Y')}",
        format="%.2f"
    )

    # Cria fluxo de caixa diário
    df_fluxo = df_all.copy()
    df_fluxo['Data'] = df_fluxo['Data vencimento'] if 'Data vencimento' in df_fluxo.columns else df_fluxo[date_cols_all[0]]
    df_daily = (
        df_fluxo
        .groupby('Data')
        .agg(
            Entradas=('Fluxo', lambda x: x[x > 0].sum()),
            Saidas=('Fluxo', lambda x: -x[x < 0].sum()),
            Variacao=('Fluxo', 'sum')
        )
        .reset_index()
        .sort_values('Data')
    )

    df_daily['Saldo Acumulado'] = saldo_inicial + df_daily['Variacao'].cumsum()

    st.subheader("Fluxo de Caixa Diário")
    st.dataframe(df_daily, use_container_width=True)
