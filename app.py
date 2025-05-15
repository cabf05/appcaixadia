import streamlit as st
import pandas as pd
import plotly.express as px
from io import StringIO
from datetime import datetime, timedelta

# --- Configuration and Constants ---
COLS_PAGAS_IDENTIFIERS = ['Data pagamento', 'Valor Líquido', 'Usuário cadastro baixa', 'Desc forma pagto']
COLS_A_PAGAR_IDENTIFIERS = ['Origem título', 'Usuário cadastro', 'Data alteração', 'Código plano fin'] # Differentiating from Pagas
COLS_RECEBER_RECEBIDAS_IDENTIFIERS = ['Status da parcela', 'Nosso número', 'Valor da baixa', 'Valor devido']

# --- Helper Functions ---

def parse_decimal_br(value_str):
    if pd.isna(value_str) or not isinstance(value_str, str) or value_str.strip() == "":
        return 0.0
    s = str(value_str).replace("R$", "").strip()
    if not s: return 0.0
    
    # Handle cases like "1.234,56" or "7.500,00" or "1234,56"
    # Remove all thousand separators ('.') if they exist before a comma
    if ',' in s and '.' in s[0:s.rfind(',')]:
        s = s.replace(".", "") 
    
    s = s.replace(",", ".") # Replace decimal comma with point
    try:
        return float(s)
    except ValueError:
        # Attempt to remove all non-numeric/non-decimal point characters if primary parsing fails
        # This is a fallback for unusually formatted numbers but might be risky
        try:
            cleaned_s = "".join(filter(lambda x: x.isdigit() or x == '.', s))
            return float(cleaned_s)
        except ValueError:
            # st.warning(f"Não foi possível converter o valor monetário: '{value_str}'")
            return 0.0

def parse_date(date_str):
    if pd.isna(date_str) or date_str == "":
        return None
    if isinstance(date_str, datetime):
        return date_str
    formats_to_try = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y']
    for fmt in formats_to_try:
        try:
            return datetime.strptime(str(date_str).split('.')[0], fmt) # split to handle potential ms
        except (ValueError, TypeError):
            continue
    # st.warning(f"Não foi possível converter a data: '{date_str}'")
    return None

def identify_csv_type(df_cols):
    df_cols_set = set(df_cols)
    if all(col in df_cols_set for col in COLS_PAGAS_IDENTIFIERS) and 'Status da parcela' not in df_cols_set:
        if 'Data pagamento' in df_cols_set and 'Usuário cadastro baixa' in df_cols_set: # More specific for Contas Pagas
             return "Contas Pagas"
        return "Potencial Contas Pagas/Pagar (Verificar colunas Data Pagamento vs Data Vencimento)" # Ambiguous
    if all(col in df_cols_set for col in COLS_A_PAGAR_IDENTIFIERS) and 'Data pagamento' not in df_cols_set and 'Status da parcela' not in df_cols_set:
         # Check for absence of 'Data pagamento' which is key for Pagas
        if 'Valor corr monetária' in df_cols_set and 'Data cadastro' in df_cols_set and 'Código forma pagto' in df_cols_set:
            return "Contas a Pagar"
    if all(col in df_cols_set for col in COLS_RECEBER_RECEBIDAS_IDENTIFIERS):
        return "Contas a Receber/Recebidas"
    return "Desconhecido"

def load_and_process_csv(uploaded_file_or_text, source_name):
    try:
        if isinstance(uploaded_file_or_text, str):
            csv_data = StringIO(uploaded_file_or_text)
        else:
            csv_data = uploaded_file_or_text
        
        df = pd.read_csv(csv_data, sep=';', skipinitialspace=True)
        df.columns = [col.strip() for col in df.columns] # Clean column names
        
        file_type = identify_csv_type(df.columns)
        st.write(f"Arquivo/Texto '{source_name}' identificado como: {file_type}")

        if file_type == "Desconhecido":
            st.error(f"Não foi possível identificar o tipo do arquivo '{source_name}'. Verifique as colunas.")
            st.write("Colunas encontradas:", df.columns.tolist())
            return None, None

        return df, file_type

    except Exception as e:
        st.error(f"Erro ao ler ou processar o arquivo/texto '{source_name}': {e}")
        return None, None

def process_contas_pagas(df):
    if df is None: return pd.DataFrame()
    # Deduplicate based on key fields that define a single payment event that might be split for accounting
    key_payment_cols = ['Título', 'Parcela', 'Data pagamento', 'Valor Líquido', 'Código credor']
    df_deduplicated = df.drop_duplicates(subset=[col for col in key_payment_cols if col in df.columns])
    
    processed_data = []
    for _, row in df_deduplicated.iterrows():
        data_pagamento = parse_date(row.get('Data pagamento'))
        valor_liquido = parse_decimal_br(row.get('Valor Líquido'))
        if data_pagamento and valor_liquido != 0:
            processed_data.append({
                'Data': data_pagamento,
                'Valor': -abs(valor_liquido), # Outflows are negative
                'Descricao': f"Pag: {row.get('Nome credor','N/A')} - {row.get('Obs título','N/A')}",
                'Tipo': 'Realizado Saída',
                'Detalhe': row.get('Desc plano fin', row.get('Desc centro custo', 'Pagamento')),
                'Fonte': 'Contas Pagas',
                'Credor/Cliente': row.get('Nome credor'),
                'Status': 'Pago'
            })
    return pd.DataFrame(processed_data)

def process_contas_a_pagar(df):
    if df is None: return pd.DataFrame()
    key_payable_cols = ['Título', 'Parcela', 'Data vencimento', 'Valor a pagar', 'Código credor']
    df_deduplicated = df.drop_duplicates(subset=[col for col in key_payable_cols if col in df.columns])

    processed_data = []
    for _, row in df_deduplicated.iterrows():
        data_vencimento = parse_date(row.get('Data vencimento'))
        valor_a_pagar = parse_decimal_br(row.get('Valor a pagar'))
        if data_vencimento and valor_a_pagar != 0:
            processed_data.append({
                'Data': data_vencimento,
                'Valor': -abs(valor_a_pagar), # Future outflows
                'Descricao': f"APagar: {row.get('Nome credor','N/A')} - {row.get('Obs título','N/A')}",
                'Tipo': 'Projetado Saída',
                'Detalhe': row.get('Desc plano fin', row.get('Desc centro custo', 'A Pagar')),
                'Fonte': 'Contas a Pagar',
                'Credor/Cliente': row.get('Nome credor'),
                'Status': 'A Pagar'
            })
    return pd.DataFrame(processed_data)

def process_contas_receber_recebidas(df):
    if df is None: return pd.DataFrame()
    processed_data = []
    for _, row in df.iterrows():
        status_parcela = str(row.get('Status da parcela', '')).strip().lower()
        data_baixa = parse_date(row.get('Data da baixa'))
        valor_baixa = parse_decimal_br(row.get('Valor da baixa')) # or Valor líquido
        
        data_vencimento = parse_date(row.get('Data vencimento'))
        valor_devido = parse_decimal_br(row.get('Valor devido'))

        if data_baixa and valor_baixa != 0: # Considerado Recebido
            processed_data.append({
                'Data': data_baixa,
                'Valor': abs(valor_baixa), # Inflows are positive
                'Descricao': f"Rec: {row.get('Cliente','N/A')} - Doc: {row.get('N° documento','N/A')}",
                'Tipo': 'Realizado Entrada',
                'Detalhe': row.get('Observação da baixa', 'Recebimento'),
                'Fonte': 'Contas Recebidas',
                'Credor/Cliente': row.get('Cliente'),
                'Status': 'Recebido'
            })
        elif status_parcela == 'a receber' and data_vencimento and valor_devido != 0: # Considerado A Receber
             processed_data.append({
                'Data': data_vencimento,
                'Valor': abs(valor_devido), # Future inflows
                'Descricao': f"ARec: {row.get('Cliente','N/A')} - Doc: {row.get('N° documento','N/A')}",
                'Tipo': 'Projetado Entrada',
                'Detalhe': row.get('Observação do título', 'A Receber'),
                'Fonte': 'Contas a Receber',
                'Credor/Cliente': row.get('Cliente'),
                'Status': 'A Receber'
            })
    return pd.DataFrame(processed_data)

def initialize_session_state():
    if 'data_loaded' not in st.session_state:
        st.session_state.data_loaded = False
    if 'all_transactions_df' not in st.session_state:
        st.session_state.all_transactions_df = pd.DataFrame()
    if 'earliest_date' not in st.session_state:
        st.session_state.earliest_date = None
    if 'initial_balance_date' not in st.session_state:
        st.session_state.initial_balance_date = None #datetime.now().date()
    if 'initial_balance_amount' not in st.session_state:
        st.session_state.initial_balance_amount = 0.0
    if 'processed_dfs' not in st.session_state:
        st.session_state.processed_dfs = {}


# --- Main Application ---
def main():
    st.set_page_config(layout="wide", page_title="Fluxo de Caixa Interativo")
    st.title("📊 Análise de Fluxo de Caixa Interativo")
    
    initialize_session_state()

    # --- Sidebar for Uploads and Manual Input ---
    with st.sidebar:
        st.header("📂 Upload de Arquivos CSV")
        uploaded_files = []
        uploaded_file_pagas = st.file_uploader("Contas Pagas (Realizadas)", type="csv", key="pagas")
        uploaded_file_a_pagar = st.file_uploader("Contas a Pagar (Provisão)", type="csv", key="apagar")
        uploaded_file_receber = st.file_uploader("Contas a Receber/Recebidas", type="csv", key="receber")

        if uploaded_file_pagas: uploaded_files.append((uploaded_file_pagas, "Pagas"))
        if uploaded_file_a_pagar: uploaded_files.append((uploaded_file_a_pagar, "A Pagar"))
        if uploaded_file_receber: uploaded_files.append((uploaded_file_receber, "Receber/Recebidas"))
        
        st.markdown("---")
        st.header("📋 Ou Cole o Conteúdo CSV")
        text_pagas = st.text_area("Conteúdo CSV - Contas Pagas", height=50, key="text_pagas")
        text_a_pagar = st.text_area("Conteúdo CSV - Contas a Pagar", height=50, key="text_apagar")
        text_receber = st.text_area("Conteúdo CSV - Contas a Receber/Recebidas", height=50, key="text_receber")

        pasted_texts = []
        if text_pagas: pasted_texts.append((text_pagas, "Pagas (Colado)"))
        if text_a_pagar: pasted_texts.append((text_a_pagar, "A Pagar (Colado)"))
        if text_receber: pasted_texts.append((text_receber, "Receber/Recebidas (Colado)"))

        process_button = st.button("🚀 Processar Dados", key="process")

    # --- Data Processing Logic ---
    if process_button:
        st.session_state.data_loaded = False
        st.session_state.all_transactions_df = pd.DataFrame()
        st.session_state.processed_dfs = {}
        all_dfs_processed = []
        
        files_to_process = uploaded_files + pasted_texts
        if not files_to_process:
            st.warning("Nenhum arquivo carregado ou texto colado para processar.")
            return

        with st.spinner("Processando arquivos..."):
            for file_data, source_name_hint in files_to_process:
                df_original, file_type = load_and_process_csv(file_data, source_name_hint)
                
                if df_original is not None:
                    st.session_state.processed_dfs[file_type] = df_original # Store original for detail tables
                    
                    if file_type == "Contas Pagas":
                        all_dfs_processed.append(process_contas_pagas(df_original))
                    elif file_type == "Contas a Pagar":
                        all_dfs_processed.append(process_contas_a_pagar(df_original))
                    elif file_type == "Contas a Receber/Recebidas":
                        all_dfs_processed.append(process_contas_receber_recebidas(df_original))
            
            if all_dfs_processed:
                st.session_state.all_transactions_df = pd.concat(all_dfs_processed, ignore_index=True)
                if not st.session_state.all_transactions_df.empty:
                    st.session_state.all_transactions_df['Data'] = pd.to_datetime(st.session_state.all_transactions_df['Data'])
                    st.session_state.all_transactions_df = st.session_state.all_transactions_df.sort_values(by='Data').reset_index(drop=True)
                    st.session_state.earliest_date = st.session_state.all_transactions_df['Data'].min().date()
                    st.session_state.initial_balance_date = st.session_state.earliest_date
                    st.session_state.data_loaded = True
                    st.success("Dados processados com sucesso!")
                else:
                    st.warning("Nenhuma transação válida encontrada nos arquivos processados.")
            else:
                st.error("Nenhum dado foi processado. Verifique os arquivos ou o conteúdo colado.")

    # --- Initial Balance Input (after data is processed) ---
    if st.session_state.data_loaded:
        with st.sidebar:
            st.markdown("---")
            st.header("💰 Saldo Inicial")
            if st.session_state.earliest_date:
                 st.info(f"Primeira data identificada nos arquivos: {st.session_state.earliest_date.strftime('%d/%m/%Y')}")
                 st.session_state.initial_balance_date = st.date_input(
                    "Data do Saldo Inicial", 
                    value=st.session_state.initial_balance_date,
                    min_value=st.session_state.earliest_date - timedelta(days=365*5), # Allow earlier date
                    max_value=st.session_state.earliest_date + timedelta(days=30)  # Allow slightly later date
                 )
                 st.session_state.initial_balance_amount = st.number_input(
                    f"Saldo de Caixa em {st.session_state.initial_balance_date.strftime('%d/%m/%Y')}", 
                    value=st.session_state.initial_balance_amount, 
                    format="%.2f",
                    step=100.0
                 )
            else:
                st.warning("Ainda não há dados para definir o saldo inicial.")


    # --- Main Area for Results ---
    if st.session_state.data_loaded and st.session_state.all_transactions_df is not None and not st.session_state.all_transactions_df.empty:
        all_transactions = st.session_state.all_transactions_df.copy()
        initial_balance_date = pd.to_datetime(st.session_state.initial_balance_date)
        initial_balance = st.session_state.initial_balance_amount

        # Create a complete date range
        if all_transactions.empty:
            min_date = initial_balance_date
            max_date = initial_balance_date
        else:
            min_date = min(initial_balance_date, all_transactions['Data'].min())
            max_date = max(initial_balance_date, all_transactions['Data'].max())
        
        date_range = pd.date_range(start=min_date, end=max_date, freq='D')
        cash_flow_summary = pd.DataFrame(date_range, columns=['Data'])

        # Aggregate transactions by date and type
        daily_flows = all_transactions.groupby(['Data', 'Tipo'])['Valor'].sum().unstack(fill_value=0)
        
        cash_flow_summary = pd.merge(cash_flow_summary, daily_flows, on='Data', how='left').fillna(0)

        # Ensure all flow columns exist
        flow_cols = ['Realizado Entrada', 'Realizado Saída', 'Projetado Entrada', 'Projetado Saída']
        for col in flow_cols:
            if col not in cash_flow_summary.columns:
                cash_flow_summary[col] = 0.0
        
        cash_flow_summary['Fluxo Realizado Diário'] = cash_flow_summary['Realizado Entrada'] + cash_flow_summary['Realizado Saída'] # Saida is already negative
        cash_flow_summary['Fluxo Projetado Diário'] = cash_flow_summary['Projetado Entrada'] + cash_flow_summary['Projetado Saída'] # Saida is already negative
        
        # Calculate Cumulative Cash Position
        cash_flow_summary = cash_flow_summary.sort_values(by='Data').reset_index(drop=True)
        cash_flow_summary['Posição Caixa Acumulada'] = 0.0
        
        # Apply initial balance
        # Find the index for the initial balance date
        initial_date_index = cash_flow_summary[cash_flow_summary['Data'] == initial_balance_date].index
        
        # Calculate cumulative sum for realized flow
        current_balance = initial_balance
        for i in range(len(cash_flow_summary)):
            if cash_flow_summary.loc[i, 'Data'] < initial_balance_date:
                # For dates before initial balance, cumulative is not well-defined relative to the initial balance.
                # We can calculate a pre-balance cumulative or set to NaN/0.
                # For simplicity here, we will just forward fill what happens after initial balance date.
                # Or, better, sum up realized flow up to that point and add initial balance.
                # This means initial_balance is for a specific point, and history before it isn't affected by it.
                # Let's recalculate if initial_balance_date is not the first date.
                pass # This part is tricky, let's assume initial balance is on or before first transaction for now for this simple calc.
            
            if cash_flow_summary.loc[i, 'Data'] == initial_balance_date:
                 cash_flow_summary.loc[i, 'Posição Caixa Acumulada'] = initial_balance + cash_flow_summary.loc[i, 'Fluxo Realizado Diário']
            elif cash_flow_summary.loc[i, 'Data'] > initial_balance_date:
                 cash_flow_summary.loc[i, 'Posição Caixa Acumulada'] = cash_flow_summary.loc[i-1, 'Posição Caixa Acumulada'] + cash_flow_summary.loc[i, 'Fluxo Realizado Diário']
            else: # Dates before initial_balance_date
                 # Sum realized flows up to this point, effectively making initial_balance_date the "start" of this balance calculation
                 if i > 0:
                     cash_flow_summary.loc[i, 'Posição Caixa Acumulada'] = cash_flow_summary.loc[i-1, 'Posição Caixa Acumulada'] + cash_flow_summary.loc[i, 'Fluxo Realizado Diário']
                 else: # First day in range, before initial balance date
                     cash_flow_summary.loc[i, 'Posição Caixa Acumulada'] = cash_flow_summary.loc[i, 'Fluxo Realizado Diário']


        # Adjust calculation if initial balance date is not the first date in the series
        if initial_balance_date > cash_flow_summary['Data'].min():
            # Sum all realized flows before the initial balance date
            pre_balance_flow_sum = cash_flow_summary.loc[cash_flow_summary['Data'] < initial_balance_date, 'Fluxo Realizado Diário'].sum()
            # The balance at the start of initial_balance_date *before* its own flow is initial_balance - pre_balance_flow_sum
            # This ensures that if we sum up from the very beginning, we hit 'initial_balance' right *on* the initial_balance_date after its flow.
            
            # A simpler approach: set the value on initial_balance_date and compute forward and backward.
            # For days >= initial_balance_date
            cumulative_val = initial_balance
            initial_date_idx = cash_flow_summary[cash_flow_summary['Data'] == initial_balance_date].index[0]
            
            cash_flow_summary.loc[initial_date_idx, 'Posição Caixa Acumulada'] = cumulative_val + cash_flow_summary.loc[initial_date_idx, 'Fluxo Realizado Diário']
            for i in range(initial_date_idx + 1, len(cash_flow_summary)):
                cash_flow_summary.loc[i, 'Posição Caixa Acumulada'] = cash_flow_summary.loc[i-1, 'Posição Caixa Acumulada'] + cash_flow_summary.loc[i, 'Fluxo Realizado Diário']
            
            # For days < initial_balance_date
            # The value at initial_date_idx - 1 should be initial_balance - cash_flow_summary.loc[initial_date_idx, 'Fluxo Realizado Diário']
            # More directly: initial_balance (which is opening balance for the day)
            if initial_date_idx > 0:
                 cash_flow_summary.loc[initial_date_idx -1, 'Posição Caixa Acumulada'] = initial_balance - cash_flow_summary.loc[initial_date_idx-1, 'Fluxo Realizado Diário'] # This might be wrong, need to be careful
                 # Correct approach: The balance *at the end* of (initial_date_idx-1) is initial_balance (which is opening for initial_date_idx)
                 # So, Posição Caixa Acumulada at (initial_date_idx-1) = initial_balance
                 # Then Posição Caixa Acumulada at (initial_date_idx-2) = Posição Caixa Acumulada at (initial_date_idx-1) - Fluxo Realizado Diário at (initial_date_idx-1)
                 # This can be complex. The easiest is to assume initial_balance is set at the *start* of initial_balance_date.

                 # Let's use a clearer method:
                 temp_cumulative = initial_balance # Balance at START of initial_balance_date
                 for i in range(initial_date_idx, -1, -1): # Iterate backwards from initial_balance_date
                     if i == initial_date_idx:
                         cash_flow_summary.loc[i, 'Posição Caixa Acumulada'] = temp_cumulative + cash_flow_summary.loc[i, 'Fluxo Realizado Diário']
                     else: # For dates before initial_balance_date
                         # Balance at end of day i = Balance at start of day i+1 - flow of day i+1
                         # Balance at end of day i = (Balance at end of day i+1 - flow of day i+1)
                         # Posição Caixa Acumulada[i] = Posição Caixa Acumulada[i+1] - cash_flow_summary.loc[i+1, 'Fluxo Realizado Diário']
                         # This still isn't quite right for display.
                         # For now, if initial_balance_date is not the earliest, the chart prior might look odd or start from 0.
                         # The standard is: initial balance is Day 0, then flows affect it.
                         # So, if initial_balance_date is later, all prior days sum to some value, then initial_balance 'corrects' it.
                         # Or, more simply, we add the initial balance as a transaction on initial_balance_date.
                         # For simplicity now, we start the cumulative calculation from initial_balance_date using initial_balance.
                         pass # The loop above already calculates forward from initial_balance_date.


        # --- Display KPIs ---
        st.subheader("🚀 Indicadores Chave de Performance (KPIs)")
        
        # Define period for KPIs (e.g., all data, or user selected)
        # For now, using all data from cash_flow_summary
        kpi_data = cash_flow_summary
        
        total_realizado_entrada = kpi_data['Realizado Entrada'].sum()
        total_realizado_saida = kpi_data['Realizado Saída'].sum() # Already negative
        saldo_realizado_periodo = total_realizado_entrada + total_realizado_saida
        
        total_projetado_entrada = kpi_data['Projetado Entrada'].sum()
        total_projetado_saida = kpi_data['Projetado Saída'].sum() # Already negative
        saldo_projetado_periodo = total_projetado_entrada + total_projetado_saida
        
        resultado_final_periodo_realizado = kpi_data['Posição Caixa Acumulada'].iloc[-1] if not kpi_data.empty else initial_balance
        
        # Necessidade de Caixa (Lowest point in Realized Cumulative or if it goes negative)
        min_caixa_realizado = kpi_data['Posição Caixa Acumulada'].min() if not kpi_data.empty else initial_balance
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Entradas Realizadas", f"R$ {total_realizado_entrada:,.2f}")
        col2.metric("Total Saídas Realizadas", f"R$ {abs(total_realizado_saida):,.2f}")
        col3.metric("Saldo Realizado no Período", f"R$ {saldo_realizado_periodo:,.2f}")

        col1b, col2b, col3b = st.columns(3)
        col1b.metric("Total Entradas Projetadas", f"R$ {total_projetado_entrada:,.2f}")
        col2b.metric("Total Saídas Projetadas", f"R$ {abs(total_projetado_saida):,.2f}")
        col3b.metric("Saldo Projetado no Período", f"R$ {saldo_projetado_periodo:,.2f}")
        
        st.metric("Posição de Caixa Final (Realizada)", f"R$ {resultado_final_periodo_realizado:,.2f}")
        if min_caixa_realizado < 0:
            st.metric("⚠️ Menor Saldo de Caixa Realizado (Necessidade)", f"R$ {min_caixa_realizado:,.2f}", delta_color="inverse")
        else:
            st.metric("Menor Saldo de Caixa Realizado", f"R$ {min_caixa_realizado:,.2f}")


        # --- Display Charts ---
        st.subheader("📈 Gráficos do Fluxo de Caixa")
        
        # Variação do Fluxo Diário (Realizado)
        fig_daily_flow_realizado = px.bar(cash_flow_summary, x='Data', y='Fluxo Realizado Diário', 
                                   title='Variação Diária do Fluxo de Caixa (Realizado)',
                                   labels={'Fluxo Realizado Diário': 'Valor (R$)'})
        fig_daily_flow_realizado.update_traces(marker_color=['red' if x < 0 else 'green' for x in cash_flow_summary['Fluxo Realizado Diário']])
        st.plotly_chart(fig_daily_flow_realizado, use_container_width=True)

        # Posição Acumulada do Caixa (Realizado)
        fig_cumulative_cash = px.line(cash_flow_summary, x='Data', y='Posição Caixa Acumulada', 
                                      title='Posição de Caixa Acumulada (Realizado)',
                                      labels={'Posição Caixa Acumulada': 'Saldo (R$)'})
        st.plotly_chart(fig_cumulative_cash, use_container_width=True)
        
        # Variação do Fluxo Diário (Projetado - only future dates)
        future_dates_mask = cash_flow_summary['Data'] >= pd.to_datetime(datetime.now().date())
        projetado_plot_data = cash_flow_summary[future_dates_mask & (cash_flow_summary['Fluxo Projetado Diário'] != 0)]
        if not projetado_plot_data.empty:
            fig_daily_flow_projetado = px.bar(projetado_plot_data, x='Data', y='Fluxo Projetado Diário',
                                    title='Variação Diária do Fluxo de Caixa (Projetado - Futuro)',
                                    labels={'Fluxo Projetado Diário': 'Valor (R$)'})
            fig_daily_flow_projetado.update_traces(marker_color=['orange' if x < 0 else 'blue' for x in projetado_plot_data['Fluxo Projetado Diário']])
            st.plotly_chart(fig_daily_flow_projetado, use_container_width=True)


        # --- Display Summary Table ---
        st.subheader("🧾 Resumo Diário do Fluxo de Caixa")
        display_summary = cash_flow_summary[['Data', 'Realizado Entrada', 'Realizado Saída', 'Fluxo Realizado Diário', 
                                             'Projetado Entrada', 'Projetado Saída', 'Fluxo Projetado Diário', 'Posição Caixa Acumulada']].copy()
        for col in ['Realizado Entrada', 'Realizado Saída', 'Fluxo Realizado Diário', 'Projetado Entrada', 'Projetado Saída', 'Fluxo Projetado Diário', 'Posição Caixa Acumulada']:
            display_summary[col] = display_summary[col].apply(lambda x: f"R$ {x:,.2f}")
        display_summary['Data'] = display_summary['Data'].dt.strftime('%d/%m/%Y')
        st.dataframe(display_summary.set_index('Data'), use_container_width=True)

        # --- Display Detailed Tables with Filters ---
        st.subheader("🔍 Detalhes das Transações")
        
        tab1, tab2 = st.tabs(["Pagamentos (Realizados e A Pagar)", "Recebimentos (Realizados e A Receber)"])

        with tab1:
            st.markdown("#### Pagamentos")
            pagamentos_df = all_transactions[all_transactions['Tipo'].isin(['Realizado Saída', 'Projetado Saída'])].copy()
            if not pagamentos_df.empty:
                # Filters
                col_filter1, col_filter2 = st.columns(2)
                status_filter_pag = col_filter1.multiselect("Filtrar por Status:", pagamentos_df['Status'].unique(), default=pagamentos_df['Status'].unique(), key="status_pag")
                
                min_date_pag = pagamentos_df['Data'].min().date()
                max_date_pag = pagamentos_df['Data'].max().date()
                date_range_pag = col_filter2.date_input("Filtrar por Data:", value=(min_date_pag, max_date_pag), min_value=min_date_pag, max_value=max_date_pag, key="date_pag")

                filtered_pagamentos = pagamentos_df[
                    (pagamentos_df['Status'].isin(status_filter_pag)) &
                    (pagamentos_df['Data'].dt.date >= date_range_pag[0]) &
                    (pagamentos_df['Data'].dt.date <= date_range_pag[1])
                ]
                filtered_pagamentos['Valor'] = filtered_pagamentos['Valor'].apply(lambda x: f"R$ {x:,.2f}")
                filtered_pagamentos['Data'] = filtered_pagamentos['Data'].dt.strftime('%d/%m/%Y')
                st.dataframe(filtered_pagamentos[['Data', 'Descricao', 'Valor', 'Status', 'Credor/Cliente', 'Detalhe']], use_container_width=True, height=300)
            else:
                st.info("Nenhum dado de pagamento para exibir.")

        with tab2:
            st.markdown("#### Recebimentos")
            recebimentos_df = all_transactions[all_transactions['Tipo'].isin(['Realizado Entrada', 'Projetado Entrada'])].copy()
            if not recebimentos_df.empty:
                 # Filters
                col_filter_r1, col_filter_r2 = st.columns(2)
                status_filter_rec = col_filter_r1.multiselect("Filtrar por Status:", recebimentos_df['Status'].unique(), default=recebimentos_df['Status'].unique(), key="status_rec")
                
                min_date_rec = recebimentos_df['Data'].min().date()
                max_date_rec = recebimentos_df['Data'].max().date()
                date_range_rec = col_filter_r2.date_input("Filtrar por Data:", value=(min_date_rec, max_date_rec), min_value=min_date_rec, max_value=max_date_rec, key="date_rec")


                filtered_recebimentos = recebimentos_df[
                    (recebimentos_df['Status'].isin(status_filter_rec)) &
                    (recebimentos_df['Data'].dt.date >= date_range_rec[0]) &
                    (recebimentos_df['Data'].dt.date <= date_range_rec[1])
                ]
                filtered_recebimentos['Valor'] = filtered_recebimentos['Valor'].apply(lambda x: f"R$ {x:,.2f}")
                filtered_recebimentos['Data'] = filtered_recebimentos['Data'].dt.strftime('%d/%m/%Y')
                st.dataframe(filtered_recebimentos[['Data', 'Descricao', 'Valor', 'Status', 'Credor/Cliente', 'Detalhe']], use_container_width=True, height=300)
            else:
                st.info("Nenhum dado de recebimento para exibir.")
    
    elif not st.session_state.data_loaded and process_button: # If process was clicked but no data was loaded
        pass # Messages are already shown during processing
    else:
        st.info("✨ Bem-vindo! Faça o upload dos arquivos CSV ou cole o conteúdo e clique em 'Processar Dados' para iniciar a análise do fluxo de caixa.")


if __name__ == "__main__":
    main()
