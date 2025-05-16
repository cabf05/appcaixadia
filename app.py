import streamlit as st
import pandas as pd

st.set_page_config(page_title="Fluxo de Caixa", layout="wide")
st.title("Sistema de Fluxo de Caixa Diário")

st.markdown(
    "Antes de fazer o upload, verifique se as datas estão no formato dd/mm/aaaa e os valores no formato brasileiro "
    "(milhares separados por ponto e decimais por vírgula). Exemplo de data: 30/01/2024; Exemplo de valor: 1.234,56."
)

# Upload de três arquivos
recebidas_file = st.file_uploader("Contas Recebidas/A Receber (CSV)", type=["csv"], key="recebidas")
pagas_file = st.file_uploader("Contas Pagas (CSV)", type=["csv"], key="pagas")
apagar_file = st.file_uploader("Contas a Pagar (CSV)", type=["csv"], key="apagar")

if recebidas_file and pagas_file and apagar_file:
    # Função auxiliar para ler CSV brasileiro com datas
    def read_brazilian_csv(uploaded_file):
        # Lê cabeçalho para identificar colunas de data
        uploaded_file.seek(0)
        header = pd.read_csv(uploaded_file, sep=';', nrows=0)
        date_cols = [col for col in header.columns if 'Data' in col]
        # Voltar ponteiro e ler todo o arquivo
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

    # Leitura dos três arquivos
    df_receb = read_brazilian_csv(recebidas_file)
    df_pagas = read_brazilian_csv(pagas_file)
    df_apagar = read_brazilian_csv(apagar_file)

    # Adicionar coluna de tipo e fluxo (negativo para saída)
    df_receb['Tipo'] = 'Recebimento'
    df_receb['Fluxo'] = df_receb['Valor líquido']

    df_pagas['Tipo'] = 'Pagamento'
    df_pagas['Fluxo'] = -df_pagas['Valor Líquido']

    df_apagar['Tipo'] = 'A Pagar'
    df_apagar['Fluxo'] = -df_apagar['Valor a pagar']

    # Consolida todos os registros
    df_all = pd.concat([df_receb, df_pagas, df_apagar], ignore_index=True)

    # Exibe tabela interativa para pesquisa e filtros
    st.subheader("Tabela de Movimentações")
    st.data_editor(df_all, use_container_width=True)

    # Identifica data mais antiga (das colunas de data carregadas)
    date_cols = [col for col in df_all.columns if df_all[col].dtype == 'datetime64[ns]']
    min_date = df_all[date_cols].min().min().date()
    st.info(f"Data mais antiga encontrada: {min_date.strftime('%d/%m/%Y')}")

    # Solicita saldo inicial na data mais antiga
    saldo_inicial = st.number_input(
        f"Informe o saldo de caixa em {min_date.strftime('%d/%m/%Y')}",
        format="%.2f"
    )

    # Prepara fluxo de caixa diário
    df_fluxo = df_all.copy()
    # Define coluna de data para agrupamento (prioriza Data vencimento)
    if 'Data vencimento' in df_fluxo.columns:
        df_fluxo['Data'] = df_fluxo['Data vencimento']
    else:
        df_fluxo['Data'] = df_fluxo[date_cols[0]]

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

    # Calcula saldo acumulado
    df_daily['Saldo Acumulado'] = saldo_inicial + df_daily['Variacao'].cumsum()

    st.subheader("Fluxo de Caixa Diário")
    st.dataframe(df_daily, use_container_width=True)

