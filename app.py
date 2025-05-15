import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from io import StringIO

# --- Utility Functions ---
def clean_numeric_value(value):
    """Cleans and converts a string numeric value to float."""
    if pd.isna(value) or str(value).strip() == "":
        return 0.0
    try:
        s_value = str(value).replace("R$", "").replace(".", "").replace(",", ".").strip()
        return float(s_value)
    except ValueError:
        return 0.0

def parse_date_flexible(series):
    """Attempts to parse dates with multiple formats."""
    return pd.to_datetime(series, errors='coerce', dayfirst=True, infer_datetime_format=True)

# --- Data Loading and Cleaning Functions ---

def load_contas_pagas(uploaded_file):
    """Loads and cleans the 'Contas Pagas' (Paid Accounts) CSV."""
    if uploaded_file is None:
        return pd.DataFrame(), pd.DataFrame()

    try:
        df = pd.read_csv(uploaded_file, sep=';', encoding='latin1', skip_blank_lines=True, on_bad_lines='skip')
    except Exception as e:
        st.error(f"Erro ao ler o arquivo de Contas Pagas: {e}")
        return pd.DataFrame(), pd.DataFrame()

    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    # Rename columns for easier access and consistency
    rename_map_pagas = {
        'Data pagamento': 'Date',
        'Valor Líquido': 'Amount',
        'Título': 'ID_Titulo',
        'Nome credor': 'Creditor',
        'Obs título': 'Description',
        'Desc centro custo': 'CostCenter',
        'Desc plano fin': 'FinancialPlan',
        'Desc obra': 'Project',
        # Add other columns you want to display in the detail table
        'Parcela': 'Installment',
        'Origem título': 'OriginTitle',
        'Código documento': 'DocCode',
        'Nome documento': 'DocName',
        'Data vencimento': 'DueDate',
        'Data emissão': 'EmissionDate'
    }
    df.rename(columns=rename_map_pagas, inplace=True)
    
    # Ensure essential columns exist
    if 'Date' not in df.columns or 'Amount' not in df.columns:
        st.error("Arquivo de Contas Pagas não contém as colunas 'Data pagamento' ou 'Valor Líquido'.")
        return pd.DataFrame(), pd.DataFrame()

    df['Date'] = parse_date_flexible(df['Date'])
    df['Amount'] = df['Amount'].apply(clean_numeric_value)
    df = df.dropna(subset=['Date', 'Amount'])
    df = df[df['Amount'] != 0]

    # For cash flow summary, avoid double counting if a payment is listed multiple times for allocation
    # A unique payment instance can be identified by a combination of fields.
    # If 'ID_Titulo' is present, use it. Otherwise, use 'Description' and other details.
    
    # Create a composite key for uniqueness for cash flow purposes
    # This is a simplification; real-world scenarios might need more robust unique payment identification
    df['temp_id_for_cashflow'] = df['ID_Titulo'].fillna('') + '_' + \
                                 df['Date'].astype(str) + '_' + \
                                 df['Amount'].astype(str) + '_' + \
                                 df['Creditor'].fillna('') + '_' + \
                                 df['Description'].fillna('')

    cash_flow_data = df.drop_duplicates(subset=['temp_id_for_cashflow'])
    cash_flow_data = cash_flow_data[['Date', 'Amount']].copy()
    cash_flow_data['Type'] = 'Outflow_Realized'
    
    # Original detailed data for tables
    detail_columns = [col for col in rename_map_pagas.values() if col in df.columns] + ['Amount']
    detail_data = df[detail_columns].copy()
    detail_data['Source'] = 'Contas Pagas'

    return cash_flow_data, detail_data


def load_contas_a_pagar(uploaded_file):
    """Loads and cleans the 'Contas a Pagar' (Accounts Payable) CSV."""
    if uploaded_file is None:
        return pd.DataFrame(), pd.DataFrame()
    try:
        df = pd.read_csv(uploaded_file, sep=';', encoding='latin1', skip_blank_lines=True, on_bad_lines='skip')
    except Exception as e:
        st.error(f"Erro ao ler o arquivo de Contas a Pagar: {e}")
        return pd.DataFrame(), pd.DataFrame()

    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    rename_map_a_pagar = {
        'Data vencimento': 'Date',
        'Valor a pagar': 'Amount',
        'Título': 'ID_Titulo',
        'Nome credor': 'Creditor',
        'Obs título': 'Description',
        'Desc centro custo': 'CostCenter',
        'Desc plano fin': 'FinancialPlan',
        'Desc obra': 'Project',
        'Parcela': 'Installment',
        'Origem título': 'OriginTitle',
        'Código documento': 'DocCode',
        'Nome documento': 'DocName',
        'Data emissão': 'EmissionDate'
    }
    df.rename(columns=rename_map_a_pagar, inplace=True)

    if 'Date' not in df.columns or 'Amount' not in df.columns:
        st.error("Arquivo de Contas a Pagar não contém as colunas 'Data vencimento' ou 'Valor a pagar'.")
        return pd.DataFrame(), pd.DataFrame()

    df['Date'] = parse_date_flexible(df['Date'])
    df['Amount'] = df['Amount'].apply(clean_numeric_value)
    df = df.dropna(subset=['Date', 'Amount'])
    df = df[df['Amount'] != 0]
    
    cash_flow_data = df[['Date', 'Amount']].copy()
    cash_flow_data['Type'] = 'Outflow_Projected'

    detail_columns = [col for col in rename_map_a_pagar.values() if col in df.columns] + ['Amount']
    detail_data = df[detail_columns].copy()
    detail_data['Source'] = 'Contas a Pagar'
    
    return cash_flow_data, detail_data


def load_contas_receber_e_recebidas(uploaded_file):
    """Loads and cleans the 'Contas a Receber e Recebidas' (AR/Received) CSV."""
    if uploaded_file is None:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    try:
        df = pd.read_csv(uploaded_file, sep=';', encoding='latin1', skip_blank_lines=True, on_bad_lines='skip')
    except Exception as e:
        st.error(f"Erro ao ler o arquivo de Contas a Receber/Recebidas: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    if df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    rename_map_receber = {
        'Data da baixa': 'Date_Received',
        'Valor da baixa': 'Amount_Received',
        'Data vencimento': 'Date_Due',
        'Valor devido': 'Amount_Due', # Or 'Valor atualizado'
        'Status da parcela': 'Status',
        'Título': 'ID_Titulo',
        'Cliente': 'Customer',
        'Unidade': 'Unit',
        'Observação do título': 'Description',
        'N° documento': 'DocNumber',
        'Documento': 'DocType',
        'Parcela': 'Installment'
    }
    df.rename(columns=rename_map_receber, inplace=True)

    # Realized Inflows
    realized_inflows = pd.DataFrame()
    if 'Date_Received' in df.columns and 'Amount_Received' in df.columns:
        df['Date_Received'] = parse_date_flexible(df['Date_Received'])
        df['Amount_Received'] = df['Amount_Received'].apply(clean_numeric_value)
        
        # Assuming 'Data da baixa' being present means it's received.
        # Also check for 'Status' if available and reliable.
        # For now, if Date_Received is valid and Amount_Received > 0
        received_df = df[df['Date_Received'].notna() & (df['Amount_Received'] > 0)].copy()
        if not received_df.empty:
            realized_inflows = received_df[['Date_Received', 'Amount_Received']].copy()
            realized_inflows.rename(columns={'Date_Received': 'Date', 'Amount_Received': 'Amount'}, inplace=True)
            realized_inflows['Type'] = 'Inflow_Realized'
    
    # Projected Inflows
    projected_inflows = pd.DataFrame()
    if 'Date_Due' in df.columns and 'Amount_Due' in df.columns and 'Status' in df.columns:
        df['Date_Due'] = parse_date_flexible(df['Date_Due'])
        df['Amount_Due'] = df['Amount_Due'].apply(clean_numeric_value)
        
        # Assuming 'Status da parcela' == 'A receber' means it's a projected inflow.
        # Also check if 'Date_Received' is null for these.
        to_receive_df = df[(df['Status'] == 'A receber') & df['Date_Due'].notna() & (df['Amount_Due'] > 0)].copy()
        if not to_receive_df.empty:
            projected_inflows = to_receive_df[['Date_Due', 'Amount_Due']].copy()
            projected_inflows.rename(columns={'Date_Due': 'Date', 'Amount_Due': 'Amount'}, inplace=True)
            projected_inflows['Type'] = 'Inflow_Projected'

    # Detail data for tables
    detail_columns = [col for col in rename_map_receber.values() if col in df.columns]
    # Add amounts that might have different names in the source
    if 'Amount_Received' in df.columns: detail_columns.append('Amount_Received')
    if 'Amount_Due' in df.columns: detail_columns.append('Amount_Due')
    
    detail_data = df[list(set(detail_columns))].copy() # Use set to avoid duplicate columns if rename created overlap
    detail_data['Source'] = 'Contas a Receber/Recebidas'
            
    return realized_inflows, projected_inflows, detail_data


# --- Main Application ---
st.set_page_config(layout="wide", page_title="Fluxo de Caixa Detalhado")
st.title("📊 Análise de Fluxo de Caixa")

st.sidebar.header("Upload de Arquivos CSV")
paid_file = st.sidebar.file_uploader("1. Contas Pagas (CSV)", type="csv")
payable_file = st.sidebar.file_uploader("2. Contas a Pagar (CSV)", type="csv")
receivable_file = st.sidebar.file_uploader("3. Contas a Receber/Recebidas (CSV)", type="csv")

if paid_file and payable_file and receivable_file:
    paid_cash, paid_details = load_contas_pagas(paid_file)
    payable_cash, payable_details = load_contas_a_pagar(payable_file)
    received_cash, to_receive_cash, receivable_details = load_contas_receber_e_recebidas(receivable_file)

    all_cash_flows = pd.concat([paid_cash, payable_cash, received_cash, to_receive_cash], ignore_index=True)
    all_cash_flows = all_cash_flows.dropna(subset=['Date']) # Ensure date is valid

    all_detail_tables = pd.concat([paid_details, payable_details, receivable_details], ignore_index=True)
    if 'Date' not in all_detail_tables.columns and 'Date_Due' in all_detail_tables.columns: # Handle merged details
        all_detail_tables['Date'] = all_detail_tables['Date_Due'] # Or a coalesce logic
    if 'Amount' not in all_detail_tables.columns and 'Amount_Due' in all_detail_tables.columns:
         all_detail_tables['Amount'] = all_detail_tables['Amount_Due']


    if not all_cash_flows.empty:
        min_date_data = all_cash_flows['Date'].min()
        max_date_data = all_cash_flows['Date'].max()

        st.sidebar.markdown("---")
        st.sidebar.header("Saldo Inicial")
        initial_date_prompt = min_date_data - pd.Timedelta(days=1)
        initial_cash_date = st.sidebar.date_input(f"Data do Saldo Inicial de Caixa (antes de {min_date_data.strftime('%d/%m/%Y')})", 
                                                  initial_date_prompt)
        initial_cash_balance = st.sidebar.number_input("Saldo Inicial de Caixa (R$)", value=0.0, format="%.2f")

        # --- Cash Flow Aggregation ---
        daily_summary = all_cash_flows.groupby(['Date', 'Type'])['Amount'].sum().unstack(fill_value=0)
        
        # Ensure all types of flow columns exist
        for col_type in ['Inflow_Realized', 'Outflow_Realized', 'Inflow_Projected', 'Outflow_Projected']:
            if col_type not in daily_summary.columns:
                daily_summary[col_type] = 0.0
        
        # Create a full date range
        if pd.isna(initial_cash_date) or pd.isna(min_date_data) or pd.isna(max_date_data):
            st.error("Datas inválidas para processamento. Verifique os arquivos ou o saldo inicial.")
        else:
            full_date_range = pd.date_range(start=initial_cash_date, end=max_date_data, freq='D')
            daily_summary = daily_summary.reindex(full_date_range, fill_value=0.0)
            daily_summary.index.name = 'Date'

            # Calculate daily net flows
            daily_summary['Net_Realized_Flow'] = daily_summary['Inflow_Realized'] - daily_summary['Outflow_Realized']
            daily_summary['Net_Projected_Flow'] = daily_summary['Inflow_Projected'] - daily_summary['Outflow_Projected']
            daily_summary['Net_Overall_Flow'] = daily_summary['Net_Realized_Flow'] + daily_summary['Net_Projected_Flow']

            # Calculate accumulated cash position
            daily_summary['Accumulated_Cash'] = 0.0
            # Set initial balance for the first day (which is initial_cash_date)
            daily_summary.loc[initial_cash_date, 'Accumulated_Cash'] = initial_cash_balance
            # Add the net flow of the first data day (min_date_data) to the initial balance
            # The accumulation should start effectively from min_date_data
            
            # Correct accumulation logic:
            # Create a temporary series for accumulation starting from initial_cash_date
            # The balance on initial_cash_date IS the initial_cash_balance
            # The balance on min_date_data is initial_cash_balance + Net_Overall_Flow on min_date_data
            # (if initial_cash_date is min_date_data -1day)
            
            temp_cash_series = daily_summary['Net_Overall_Flow'].copy()
            temp_cash_series.loc[initial_cash_date] += initial_cash_balance 
            daily_summary['Accumulated_Cash'] = temp_cash_series.cumsum()
            
            # If initial_cash_date is not in daily_summary (because no transactions on that day)
            # we need to insert it or adjust.
            # Simpler: start accumulation from the first actual transaction day after applying initial balance
            if initial_cash_date not in daily_summary.index:
                 # Insert the initial balance day if it's not there
                initial_row = pd.DataFrame(0, index=[initial_cash_date], columns=daily_summary.columns)
                initial_row.loc[initial_cash_date, 'Accumulated_Cash'] = initial_cash_balance
                daily_summary = pd.concat([initial_row, daily_summary]).sort_index()
                daily_summary = daily_summary[~daily_summary.index.duplicated(keep='first')] # Keep the one with balance

            # Recalculate cumulative sum after ensuring initial balance is set correctly
            # The first day's (initial_cash_date) 'Net_Overall_Flow' should be considered 0 for accumulation if it's before any transaction
            # Let's reset Net_Overall_Flow for initial_cash_date if it's truly before any data
            # This part is tricky, ensuring the initial balance is anchored correctly.
            # A robust way:
            accumulated = []
            current_balance = initial_cash_balance
            # Iterate over sorted dates >= initial_cash_date
            for date_val in daily_summary.index:
                if date_val == initial_cash_date:
                    accumulated.append(current_balance) # Balance at end of initial_cash_date
                    # Add flow of initial_cash_date if any (usually 0 unless transactions start this day)
                    current_balance += daily_summary.loc[date_val, 'Net_Overall_Flow'] 
                elif date_val > initial_cash_date:
                    current_balance += daily_summary.loc[date_val, 'Net_Overall_Flow']
                    accumulated.append(current_balance)
                # else: # dates before initial_cash_date, should not happen with current date range
                #    accumulated.append(0) 

            daily_summary = daily_summary[daily_summary.index >= initial_cash_date].copy() # Ensure we only have relevant dates
            daily_summary['Accumulated_Cash'] = accumulated


            # --- Display Charts ---
            st.header("Fluxo de Caixa Visualizado")
            
            # Filter out the initial balance date for plotting flows if it has no actual flow data
            plot_data = daily_summary[daily_summary.index >= min_date_data].copy()

            fig_daily_flow = px.bar(plot_data, x=plot_data.index, y='Net_Overall_Flow', 
                                    title="Variação Diária do Fluxo de Caixa (Líquido Total)",
                                    labels={'Net_Overall_Flow': 'Fluxo Líquido (R$)', 'Date': 'Data'})
            fig_daily_flow.update_layout(xaxis_title="Data", yaxis_title="Fluxo Líquido (R$)")
            st.plotly_chart(fig_daily_flow, use_container_width=True)

            fig_accumulated_cash = px.line(daily_summary, x=daily_summary.index, y='Accumulated_Cash', 
                                           title="Posição Acumulada do Caixa por Dia",
                                           labels={'Accumulated_Cash': 'Saldo Acumulado (R$)', 'Date': 'Data'},
                                           markers=True)
            fig_accumulated_cash.update_layout(xaxis_title="Data", yaxis_title="Saldo Acumulado (R$)")
            st.plotly_chart(fig_accumulated_cash, use_container_width=True)

            # --- Display Summary Table ---
            st.header("Resumo Diário do Fluxo de Caixa")
            
            summary_table_display = daily_summary[daily_summary.index >= min_date_data].copy()
            summary_table_display.rename(columns={
                'Inflow_Realized': 'Entradas Realizadas (R$)',
                'Outflow_Realized': 'Saídas Realizadas (R$)',
                'Net_Realized_Flow': 'Saldo Realizado Dia (R$)',
                'Inflow_Projected': 'Entradas Projetadas (R$)',
                'Outflow_Projected': 'Saídas Projetadas (R$)',
                'Net_Projected_Flow': 'Saldo Projetado Dia (R$)',
                'Net_Overall_Flow': 'Saldo Total Dia (R$)',
                'Accumulated_Cash': 'Caixa Acumulado (R$)'
            }, inplace=True)
            
            # Formatting for display
            columns_to_format = [col for col in summary_table_display.columns if 'R$' in col]
            for col in columns_to_format:
                summary_table_display[col] = summary_table_display[col].map('{:,.2f}'.format)
            
            st.dataframe(summary_table_display.style.set_sticky(axis="index"), use_container_width=True)

            # --- KPIs ---
            st.header("Indicadores Chave de Desempenho (KPIs)")
            
            future_dates = daily_summary.index[daily_summary.index > pd.Timestamp.today().normalize()]
            min_future_cash = daily_summary.loc[future_dates, 'Accumulated_Cash'].min() if not future_dates.empty else np.nan
            
            if pd.notna(min_future_cash) and min_future_cash < 0:
                st.metric(label="🚨 Necessidade de Caixa Futura Identificada", 
                          value=f"R$ {min_future_cash:,.2f}",
                          help="Menor saldo de caixa projetado para o futuro.")
            elif pd.notna(min_future_cash):
                 st.metric(label="Menor Saldo de Caixa Futuro Projetado", 
                          value=f"R$ {min_future_cash:,.2f}")


            total_realized_in = daily_summary['Inflow_Realized'].sum()
            total_realized_out = daily_summary['Outflow_Realized'].sum()
            net_realized_period = total_realized_in - total_realized_out

            total_projected_in = daily_summary['Inflow_Projected'].sum()
            total_projected_out = daily_summary['Outflow_Projected'].sum()
            net_projected_period = total_projected_in - total_projected_out
            
            final_accumulated_cash = daily_summary['Accumulated_Cash'].iloc[-1] if not daily_summary.empty else initial_cash_balance
            overall_result_period = final_accumulated_cash - initial_cash_balance

            col1, col2, col3 = st.columns(3)
            col1.metric("Resultado Líquido Realizado no Período", f"R$ {net_realized_period:,.2f}")
            col2.metric("Resultado Líquido Projetado no Período", f"R$ {net_projected_period:,.2f}")
            col3.metric("Resultado Total no Período (Impacto no Caixa)", f"R$ {overall_result_period:,.2f}")

            st.metric("Saldo Final de Caixa Projetado", f"R$ {final_accumulated_cash:,.2f}")


            # --- Detailed Tables with Filters ---
            st.header("Detalhes das Transações")

            # Prepare combined details
            if not all_detail_tables.empty:
                # Standardize date column for filtering
                if 'Date' not in all_detail_tables.columns: # Handle merged details
                    if 'Date_Due' in all_detail_tables.columns:
                        all_detail_tables['Effective_Date'] = all_detail_tables['Date_Due']
                    if 'Date_Received' in all_detail_tables.columns:
                        all_detail_tables['Effective_Date'] = all_detail_tables['Effective_Date'].fillna(all_detail_tables['Date_Received'])
                    if 'DueDate' in all_detail_tables.columns: # from paid/payable
                         all_detail_tables['Effective_Date'] = all_detail_tables['Effective_Date'].fillna(all_detail_tables['DueDate'])
                else:
                    all_detail_tables['Effective_Date'] = all_detail_tables['Date']
                
                all_detail_tables['Effective_Date'] = parse_date_flexible(all_detail_tables['Effective_Date'])

                # General filter for all details
                st.subheader("Filtrar Transações Detalhadas")
                min_filter_date = all_detail_tables['Effective_Date'].min() if not all_detail_tables['Effective_Date'].isna().all() else min_date_data
                max_filter_date = all_detail_tables['Effective_Date'].max() if not all_detail_tables['Effective_Date'].isna().all() else max_date_data
                
                if pd.NaT not in [min_filter_date, max_filter_date]: # Check if dates are valid
                    filter_date_range = st.date_input(
                        "Selecione o período para os detalhes:",
                        value=(min_filter_date, max_filter_date),
                        min_value=min_filter_date,
                        max_value=max_filter_date,
                        key="detail_date_filter"
                    )
                else:
                    st.warning("Datas insuficientes nos detalhes para filtro. Exibindo tudo.")
                    filter_date_range = (None, None)

                search_term = st.text_input("Buscar por termo (Ex: Nome, Descrição, Centro de Custo):", key="detail_search")

                filtered_details = all_detail_tables.copy()
                if filter_date_range and filter_date_range[0] and filter_date_range[1]:
                     start_date_filter, end_date_filter = pd.to_datetime(filter_date_range[0]), pd.to_datetime(filter_date_range[1])
                     filtered_details = filtered_details[
                        (filtered_details['Effective_Date'] >= start_date_filter) &
                        (filtered_details['Effective_Date'] <= end_date_filter)
                    ]

                if search_term:
                    # Search across multiple relevant text columns
                    # Ensure columns exist and are string type before applying .str.contains
                    search_cols = ['Creditor', 'Customer', 'Description', 'CostCenter', 'FinancialPlan', 'Project', 'ID_Titulo', 'Unit', 'DocNumber', 'DocType', 'OriginTitle']
                    existing_search_cols = [col for col in search_cols if col in filtered_details.columns]
                    
                    # Convert relevant columns to string to avoid errors with .str.contains on non-string types
                    for col in existing_search_cols:
                        filtered_details[col] = filtered_details[col].astype(str)

                    mask = pd.Series([False] * len(filtered_details))
                    for col in existing_search_cols:
                        mask |= filtered_details[col].str.contains(search_term, case=False, na=False)
                    filtered_details = filtered_details[mask]
                
                # Clean up amounts for display
                amount_cols_detail = ['Amount', 'Amount_Received', 'Amount_Due']
                for acd in amount_cols_detail:
                    if acd in filtered_details.columns:
                        filtered_details[acd] = filtered_details[acd].apply(lambda x: f"{x:,.2f}" if pd.notna(x) and isinstance(x, (int,float)) else x)
                
                st.dataframe(filtered_details, use_container_width=True)

            else:
                st.info("Não foi possível carregar dados detalhados.")
    else:
        st.info("Aguardando o upload de todos os arquivos CSV para processamento.")

else:
    st.info("Por favor, faça o upload dos três arquivos CSV para iniciar a análise.")

st.sidebar.markdown("---")
st.sidebar.info("""
Esta aplicação ajuda a visualizar o fluxo de caixa com base nos arquivos CSV fornecidos.
- **Contas Pagas**: Transações já efetuadas (saídas).
- **Contas a Pagar**: Compromissos futuros (saídas projetadas).
- **Contas a Receber/Recebidas**: Valores já recebidos e a receber (entradas realizadas e projetadas).
""")
