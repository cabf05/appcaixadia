import streamlit as st
import pandas as pd

st.set_page_config(page_title="Fluxo de Caixa", layout="wide")
st.title("Sistema de Fluxo de Caixa Diário")

st.markdown("Antes de fazer o upload, verifique se as datas estão no formato dd/mm/aaaa e os valores no formato brasileiro (milhares separados por ponto e decimais por vírgula). Exemplo de data: 30/01/2024; Exemplo de valor: 1.234,56.")

# Upload de três arquivos
recebidas_file = st.file_uploader("Contas Recebidas/A Receber (CSV)", type=["csv"], key="recebidas")
pagas_file = st.file_uploader("Contas Pagas (CSV)", type=["csv"], key="pagas")
apagar_file = st.file_uploader("Contas a Pagar (CSV)", type=["csv"], key="apagar")

if recebidas_file and pagas_file and apagar_file:
    # Leitura dos arquivos com formatos brasileiro
    df_receb = pd.read_csv(
        recebidas_file, sep=';', thousands='.', decimal=',', dayfirst=True,
        parse_dates=[col for col in pd.read_csv(recebidas_file, nrows=0, sep=';').columns if 'Data' in col]
    )
    df_pagas = pd.read_csv(
        pagas_file, sep=';', thousands='.', decimal=',', dayfirst=True,
        parse_dates=[col for col in pd.read_csv(pagas_file, nrows=0, sep=';').columns if 'Data' in col]
    )
    df_apagar = pd.read_csv(
        apagar_file, sep=';', thousands='.', decimal=',', dayfirst=True,
        parse_dates=[col for col in pd.read_csv(apagar_file, nrows=0, sep=';').columns if 'Data' in col]
    )

    # Padronizar colunas de data e valores já feito pelo read_csv

    # Adicionar coluna de tipo e valor de fluxo
    df_receb['Tipo'] = 'Recebimento'
    df_receb['Fluxo'] = df_receb['Valor líquido']

    df_pagas['Tipo'] = 'Pagamento'
    df_pagas['Fluxo'] = -df_pagas['Valor Líquido']

    df_apagar['Tipo'] = 'A Pagar'
    df_apagar['Fluxo'] = -df_apagar['Valor a pagar']

    # Unir todos em uma única tabela
    df_all = pd.concat([df_receb, df_pagas, df_apagar], ignore_index=True, sort=False)

    # Mostrar tabela com filtros
    st.subheader("Tabela de Movimentações")
    filtered = st.experimental_data_editor(df_all)

    # Encontrar data mais antiga nos movimentos
    date_cols = [col for col in df_all.columns if df_all[col].dtype == 'datetime64[ns]']
    min_date = df_all[date_cols].min().min().date()
    st.info(f"Data mais antiga encontrada: {min_date.strftime('%d/%m/%Y')}")

    # Solicitar saldo inicial
    saldo_inicial = st.number_input(
        f"Informe o saldo de caixa em {min_date.strftime('%d/%m/%Y')}",
        format="%.2f"
    )

    # Construir fluxo de caixa diário
    df_fluxo = df_all.copy()
    # Seleciona coluna de data principal (Data vencimento se existir)
    if 'Data vencimento' in df_fluxo.columns:
        df_fluxo['Data'] = df_fluxo['Data vencimento']
    else:
        df_fluxo['Data'] = df_fluxo[date_cols[0]]

    df_fluxo_daily = df_fluxo.groupby('Data').agg(
        Entradas=('Fluxo', lambda x: x[x > 0].sum()),
        Saidas=('Fluxo', lambda x: -x[x < 0].sum()),
        Variação=('Fluxo', 'sum')
    ).reset_index().sort_values('Data')

    # Saldo acumulado
    df_fluxo_daily['Saldo Acumulado'] = saldo_inicial + df_fluxo_daily['Variação'].cumsum()

    st.subheader("Fluxo de Caixa Diário")
    st.dataframe(df_fluxo_daily)



