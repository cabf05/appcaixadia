import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from io import StringIO

# Function to convert monetary string to float
def str_to_float(s):
    try:
        # Remove "R$", remove dots (thousands), replace comma with dot for decimal
        s = str(s).replace('R$', '').replace('.', '').replace(',', '.').strip()
        return float(s)
    except:
        return np.nan

# Function to format value as Brazilian currency
def format_currency(value):
    # Format with comma as thousands separator, then swap to Brazilian style
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# Function to identify file type based on columns
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

# Functions to process each file type
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
    
    # Receivables pending
    a_receber = df[df['Status da parcela'] == 'A receber'].copy()
    a_receber['Data'] = a_receber['Data_venc']
    a_receber['Valor'] = a_receber['Valor_original']
    a_receber['Tipo'] = 'Entrada (a receber)'
    
    # Receivables paid
    recebidas = df[df['Data da baixa'].notna()].copy()
    recebidas['Data'] = recebidas['Data_baixa']
    recebidas['Valor'] = recebidas['Valor_baixa']
    recebidas['Tipo'] = 'Entrada'
    
    return pd.concat([a_receber, recebidas])[['Data', 'Valor', 'Tipo', 'Observação do título']].dropna(subset=['Data', 'Valor'])

# Streamlit Interface
st.title("Sistema de Fluxo de Caixa")

# File upload
uploaded_files = st.file_uploader("Upload CSV files", type="csv", accept_multiple_files=True)

# Option to paste CSV content
csv_text = st.text_area("Or paste CSV content here (if upload fails):")

dataframes = []

# Process uploaded files
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
                st.warning(f"File {uploaded_file.name} not recognized. Try pasting the content manually.")
                continue
            dataframes.append(processed_df)
        except Exception as e:
            st.error(f"Error processing {uploaded_file.name}: {e}. Try pasting the content manually.")

# Process pasted content
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
            st.error("CSV content not recognized.")
        dataframes.append(processed_df)
    except Exception as e:
        st.error(f"Error processing pasted content: {e}")

# Check if there’s data to process
if dataframes:
    # Combine all DataFrames
    all_data = pd.concat(dataframes)
    all_data['Data'] = pd.to_datetime(all_data['Data'], errors='coerce')
    all_data = all_data.dropna(subset=['Data', 'Valor'])
    
    if not all_data.empty:
        # Identify the earliest date
        first_date = all_data['Data'].min()
        st.write(f"The earliest date identified is: {first_date.strftime('%d/%m/%Y')}")
        
        # Request initial balance
        saldo_inicial = st.number_input(f"Enter the cash balance on {first_date.strftime('%d/%m/%Y')}:", value=0.0)
        
        # Calculate cash flow
        fluxo_diario = all_data.groupby(['Data', 'Tipo']).agg({'Valor': 'sum'}).reset_index()
        fluxo_pivot = fluxo_diario.pivot(index='Data', columns='Tipo', values='Valor').fillna(0)
        
        # Calculate inflows and outflows
        fluxo_pivot['Entradas'] = fluxo_pivot.get('Entrada', 0) + fluxo_pivot.get('Entrada (a receber)', 0)
        fluxo_pivot['Saídas'] = fluxo_pivot.get('Saída', 0) + fluxo_pivot.get('Saída (a pagar)', 0)
        fluxo_pivot['Fluxo_Diario'] = fluxo_pivot['Entradas'] - fluxo_pivot['Saídas']
        
        # Sort by date and calculate cumulative balance
        fluxo_pivot = fluxo_pivot.sort_index()
        fluxo_pivot['Saldo_Acumulado'] = saldo_inicial + fluxo_pivot['Fluxo_Diario'].cumsum()
        
        # Line chart
        st.subheader("Cash Flow Chart")
        fig = px.line(fluxo_pivot, x=fluxo_pivot.index, y=['Fluxo_Diario', 'Saldo_Acumulado'],
                      title='Daily Cash Flow and Cumulative Balance',
                      labels={'value': 'Value (R$)', 'Data': 'Date', 'variable': 'Legend'})
        st.plotly_chart(fig)
        
        # Summary table
        st.subheader("Cash Flow Summary")
        resumo = fluxo_pivot[['Entradas', 'Saídas', 'Fluxo_Diario', 'Saldo_Acumulado']]
        st.dataframe(resumo.style.format({
            "Entradas": lambda x: f"R$ {format_currency(x)}",
            "Saídas": lambda x: f"R$ {format_currency(x)}",
            "Fluxo_Diario": lambda x: f"R$ {format_currency(x)}",
            "Saldo_Acumulado": lambda x: f"R$ {format_currency(x)}"
        }))
        
        # Detailed table with filter
        st.subheader("Transaction Details")
        filtro_tipo = st.selectbox("Filter by type:", ["Todos"] + list(all_data['Tipo'].unique()))
        if filtro_tipo != "Todos":
            detalhes = all_data[all_data['Tipo'] == filtro_tipo]
        else:
            detalhes = all_data
        st.dataframe(detalhes.style.format({"Valor": lambda x: f"R$ {format_currency(x)}"}))
        
        # KPIs
        st.subheader("KPIs")
        saldo_minimo = fluxo_pivot['Saldo_Acumulado'].min()
        saldo_final = fluxo_pivot['Saldo_Acumulado'].iloc[-1]
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Cash Need (Minimum Balance)", f"R$ {format_currency(saldo_minimo)}")
        with col2:
            st.metric("Final Result in Period", f"R$ {format_currency(saldo_final)}")
    else:
        st.error("No valid data found in the files or pasted content.")
else:
    st.write("Please upload CSV files or paste the content.")
