import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import locale
from io import StringIO

# Configurar locale para formato monetário brasileiro
locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')

# Função para converter string monetária para float
def str_to_float(s):
    try:
        # Remove "R$" e espaços, substitui vírgula por ponto
        s = str(s).replace('R$', '').replace('.', '').replace(',', '.').strip()
        return float(s)
    except:
        return np.nan

# Função para identificar o tipo de arquivo com base nas colunas
def identify_file_type(df):
    columns = df.columns
    if 'Data pagamento' in columns:
        return 'contas_pagas'
    elif 'Status da parcela' in columns:
        return 'contas_receber'
    elif 'Data vencimento' in columns and 'Valor a pagar' in columns and 'Data pagamento' not in columns:
        return 'contas_a_pagar'
    else:
        return 'desconhecido'

# Funções para processar cada tipo de arquivo
def process_contas_pagas(df):
    df['Data'] = pd.to_datetime(df['Data pagamento'], format='%Y-%m-%d', errors='coerce')
    df['Valor'] = df['Valor Líquido'].apply(str_to_float)
    df['Tipo'] = 'Saída'
    return df[['Data', 'Valor', 'Tipo', 'Obs título']].dropna(subset=['Data', 'Valor'])

def process_contas_a_pagar(df):
    df['Data'] = pd.to_datetime(df['Data vencimento'], format='%d/%m/%Y', errors='coerce')
    df['Valor'] = df['Valor a pagar'].apply(str_to_float)
    df['Tipo'] = 'Saída (a pagar)'
    return df[['Data', 'Valor', 'Tipo', 'Obs título']].dropna(subset=['Data', 'Valor'])

def process_contas_receber(df):
    df['Data_venc'] = pd.to_datetime(df['Data vencimento'], format='%d/%m/%Y', errors='coerce')
    df['Data_baixa'] = pd.to_datetime(df['Data da baixa'], format='%d/%m/%Y', errors='coerce')
    df['Valor_original'] = df['Valor original'].apply(str_to_float)
    df['Valor_baixa'] = df['Valor da baixa'].apply(str_to_float)
    
    # Parcelas a receber
    a_receber = df[df['Status da parcela'] == 'A receber'].copy()
    a_receber['Data'] = a_receber['Data_venc']
    a_receber['Valor'] = a_receber['Valor_original']
    a_receber['Tipo'] = 'Entrada (a receber)'
    
    # Parcelas recebidas
    recebidas = df[df['Data da baixa'].notna()].copy()
    recebidas['Data'] = recebidas['Data_baixa']
    recebidas['Valor'] = recebidas['Valor_baixa']
    recebidas['Tipo'] = 'Entrada'
    
    return pd.concat([a_receber, recebidas])[['Data', 'Valor', 'Tipo', 'Observação do título']].dropna(subset=['Data', 'Valor'])

# Interface do Streamlit
st.title("Sistema de Fluxo de Caixa")

# Upload de arquivos
uploaded_files = st.file_uploader("Upload CSV files", type="csv", accept_multiple_files=True)

# Opção de colar conteúdo CSV
csv_text = st.text_area("Ou cole o conteúdo do CSV aqui (se o upload falhar):")

dataframes = []

# Processar arquivos uploadados
if uploaded_files:
    for uploaded_file in uploaded_files:
        try:
            df = pd.read_csv(uploaded_file, sep=';', encoding='utf-8')
            file_type = identify_file_type(df)
            if file_type == 'contas_pagas':
                processed_df = process_contas_pagas(df)
            elif file_type == 'contas_a_pagar':
                processed_df = process_contas_a_pagar(df)
            elif file_type == 'contas_receber':
                processed_df = process_contas_receber(df)
            else:
                st.warning(f"Arquivo {uploaded_file.name} não reconhecido. Tente colar o conteúdo manualmente.")
                continue
            dataframes.append(processed_df)
        except Exception as e:
            st.error(f"Erro ao processar {uploaded_file.name}: {e}. Tente colar o conteúdo manualmente.")

# Processar conteúdo colado
if csv_text:
    try:
        df = pd.read_csv(StringIO(csv_text), sep=';', encoding='utf-8')
        file_type = identify_file_type(df)
        if file_type == 'contas_pagas':
            processed_df = process_contas_pagas(df)
        elif file_type == 'contas_a_pagar':
            processed_df = process_contas_a_pagar(df)
        elif file_type == 'contas_receber':
            processed_df = process_contas_receber(df)
        else:
            st.error("Conteúdo CSV não reconhecido.")
        dataframes.append(processed_df)
    except Exception as e:
        st.error(f"Erro ao processar o conteúdo colado: {e}")

# Verificar se há dados para processar
if dataframes:
    # Combinar todos os DataFrames
    all_data = pd.concat(dataframes)
    all_data['Data'] = pd.to_datetime(all_data['Data'], errors='coerce')
    all_data = all_data.dropna(subset=['Data', 'Valor'])
    
    if not all_data.empty:
        # Identificar a primeira data
        first_date = all_data['Data'].min()
        st.write(f"A primeira data identificada é: {first_date.strftime('%d/%m/%Y')}")
        
        # Solicitar saldo inicial
        saldo_inicial = st.number_input(f"Informe o saldo de caixa em {first_date.strftime('%d/%m/%Y')}:", value=0.0)
        
        # Calcular fluxo de caixa
        fluxo_diario = all_data.groupby(['Data', 'Tipo']).agg({'Valor': 'sum'}).reset_index()
        fluxo_pivot = fluxo_diario.pivot(index='Data', columns='Tipo', values='Valor').fillna(0)
        
        # Calcular entradas e saídas
        fluxo_pivot['Entradas'] = fluxo_pivot.get('Entrada', 0) + fluxo_pivot.get('Entrada (a receber)', 0)
        fluxo_pivot['Saídas'] = fluxo_pivot.get('Saída', 0) + fluxo_pivot.get('Saída (a pagar)', 0)
        fluxo_pivot['Fluxo_Diario'] = fluxo_pivot['Entradas'] - fluxo_pivot['Saídas']
        
        # Ordenar por data e calcular saldo acumulado
        fluxo_pivot = fluxo_pivot.sort_index()
        fluxo_pivot['Saldo_Acumulado'] = saldo_inicial + fluxo_pivot['Fluxo_Diario'].cumsum()
        
        # Gráfico de linha
        st.subheader("Gráfico de Fluxo de Caixa")
        fig = px.line(fluxo_pivot, x=fluxo_pivot.index, y=['Fluxo_Diario', 'Saldo_Acumulado'],
                      title='Fluxo de Caixa Diário e Saldo Acumulado',
                      labels={'value': 'Valor (R$)', 'Data': 'Data', 'variable': 'Legenda'})
        st.plotly_chart(fig)
        
        # Tabela resumo
        st.subheader("Resumo do Fluxo de Caixa")
        resumo = fluxo_pivot[['Entradas', 'Saídas', 'Fluxo_Diario', 'Saldo_Acumulado']]
        st.dataframe(resumo.style.format({"Entradas": "R$ {:.2f}", "Saídas": "R$ {:.2f}", 
                                          "Fluxo_Diario": "R$ {:.2f}", "Saldo_Acumulado": "R$ {:.2f}"}))
        
        # Tabela detalhada com filtro
        st.subheader("Detalhes das Movimentações")
        filtro_tipo = st.selectbox("Filtrar por tipo:", ["Todos"] + list(all_data['Tipo'].unique()))
        if filtro_tipo != "Todos":
            detalhes = all_data[all_data['Tipo'] == filtro_tipo]
        else:
            detalhes = all_data
        st.dataframe(detalhes.style.format({"Valor": "R$ {:.2f}"}))
        
        # KPIs
        st.subheader("KPIs")
        saldo_minimo = fluxo_pivot['Saldo_Acumulado'].min()
        saldo_final = fluxo_pivot['Saldo_Acumulado'].iloc[-1]
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Necessidade de Caixa (Saldo Mínimo)", locale.currency(saldo_minimo, grouping=True))
        with col2:
            st.metric("Resultado Final no Período", locale.currency(saldo_final, grouping=True))
    else:
        st.error("Nenhum dado válido foi encontrado nos arquivos ou no conteúdo colado.")
else:
    st.write("Por favor, faça o upload dos arquivos CSV ou cole o conteúdo.")
