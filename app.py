import streamlit as st
import pandas as pd
import plotly.express as px
from io import StringIO
from datetime import datetime, timedelta

# --- Configuration and Constants ---
COLS_PAGAS_IDENTIFIERS = ['Data pagamento', 'Valor Líquido', 'Usuário cadastro baixa', 'Desc forma pagto']
COLS_A_PAGAR_IDENTIFIERS = ['Origem título', 'Usuário cadastro', 'Data alteração', 'Código plano fin']
COLS_RECEBER_RECEBIDAS_IDENTIFIERS = ['Status da parcela', 'Nosso número', 'Valor da baixa', 'Valor devido']

# --- Helper Functions ---
# (Your existing helper functions: parse_decimal_br, parse_date, identify_csv_type, etc. remain here)
def parse_decimal_br(value_str):
    if pd.isna(value_str) or not isinstance(value_str, str) or value_str.strip() == "":
        return 0.0
    s = str(value_str).replace("R$", "").strip()
    if not s: return 0.0
    if ',' in s and '.' in s[0:s.rfind(',')]:
        s = s.replace(".", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        try:
            cleaned_s = "".join(filter(lambda x: x.isdigit() or x == '.', s))
            return float(cleaned_s)
        except ValueError:
            return 0.0

def parse_date(date_str):
    if pd.isna(date_str) or date_str == "":
        return None
    if isinstance(date_str, datetime):
        return date_str
    formats_to_try = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y']
    for fmt in formats_to_try:
        try:
            return datetime.strptime(str(date_str).split('.')[0], fmt)
        except (ValueError, TypeError):
            continue
    return None

def identify_csv_type(df_cols):
    df_cols_set = set(df_cols)
    if all(col in df_cols_set for col in COLS_PAGAS_IDENTIFIERS) and 'Status da parcela' not in df_cols_set:
        if 'Data pagamento' in df_cols_set and 'Usuário cadastro baixa' in df_cols_set:
             return "Contas Pagas"
        return "Potencial Contas Pagas/Pagar (Verificar colunas Data Pagamento vs Data Vencimento)"
    if all(col in df_cols_set for col in COLS_A_PAGAR_IDENTIFIERS) and 'Data pagamento' not in df_cols_set and 'Status da parcela' not in df_cols_set:
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
        st.write(f"Arquivo/Texto '{source_name}' identificado como: {file_type}") # Feedback

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
    key_payment_cols = ['Título', 'Parcela', 'Data pagamento', 'Valor Líquido', 'Código credor']
    # Ensure all key_payment_cols actually exist in df.columns before using them in subset
    actual_subset_cols = [col for col in key_payment_cols if col in df.columns]
    if not actual_subset_cols: # if no key columns found, maybe don't deduplicate or handle error
        df_deduplicated = df
    else:
        df_deduplicated = df.drop_duplicates(subset=actual_subset_cols)

    processed_data = []
    for _, row in df_deduplicated.iterrows():
        data_pagamento = parse_date(row.get('Data pagamento'))
        valor_liquido = parse_decimal_br(row.get('Valor Líquido'))
        if data_pagamento and valor_liquido != 0: # Allow zero if it's a valid state, but typically non-zero for cash flow
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
    actual_subset_cols = [col for col in key_payable_cols if col in df.columns]
    if not actual_subset_cols:
        df_deduplicated = df
    else:
        df_deduplicated = df.drop_duplicates(subset=actual_subset_cols)

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

        if data_baixa and (valor_baixa != 0 or status_parcela not in ['a receber', 'cancelado']): # Consider 0 value if explicitly paid
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
    defaults = {
        'data_loaded': False,
        'all_transactions_df': pd.DataFrame(),
        'earliest_date': None,
        'initial_balance_date': None, # This will store the selected date value
        'initial_balance_amount': 0.0, # This will store the selected amount value
        'processed_dfs': {},
        # Keys for text_area widgets - Initialize to empty strings
        "text_pagas": "",
        "text_apagar": "",
        "text_receber": "",
        # Keys for file_uploader widgets are NO LONGER initialized here.
        # Let the st.file_uploader widgets create these keys in session_state themselves.
        # "pagas": None,       # REMOVED
        # "apagar": None,      # REMOVED
        # "receber": None,     # REMOVED
        "process": None # Or False if you are checking its state / button click
    }
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

# --- Main Application ---
def main():
    st.set_page_config(layout="wide", page_title="Fluxo de Caixa Interativo")
    st.title("📊 Análise de Fluxo de Caixa Interativo")

    initialize_session_state() # Call initialization here

    # --- Sidebar for Uploads and Manual Input ---
    with st.sidebar:
        st.header("📂 Upload de Arquivos CSV")
        # The keys "pagas", "apagar", "receber" will be automatically created in session_state
        # by these widgets if they don't exist.
        uploaded_file_pagas = st.file_uploader("Contas Pagas (Realizadas)", type="csv", key="pagas")
        uploaded_file_a_pagar = st.file_uploader("Contas a Pagar (Provisão)", type="csv", key="apagar")
        uploaded_file_receber = st.file_uploader("Contas a Receber/Recebidas", type="csv", key="receber")

        st.markdown("---")
        st.header("📋 Ou Cole o Conteúdo CSV")
        text_pagas = st.text_area("Conteúdo CSV - Contas Pagas", height=50, key="text_pagas")
        text_a_pagar = st.text_area("Conteúdo CSV - Contas a Pagar", height=50, key="text_apagar")
        text_receber = st.text_area("Conteúdo CSV - Contas a Receber/Recebidas", height=50, key="text_receber")

        process_button = st.button("🚀 Processar Dados", key="process")


    # --- Data Processing Logic ---
    if process_button:
        st.session_state.data_loaded = False
        st.session_state.all_transactions_df = pd.DataFrame() # Reset before processing
        st.session_state.processed_dfs = {}
        all_dfs_processed = []

        # Access uploaded files directly from session_state as they are now managed by widgets
        files_to_process_from_upload = []
        if st.session_state.pagas is not None: files_to_process_from_upload.append((st.session_state.pagas, "Pagas"))
        if st.session_state.apagar is not None: files_to_process_from_upload.append((st.session_state.apagar, "A Pagar"))
        if st.session_state.receber is not None: files_to_process_from_upload.append((st.session_state.receber, "Receber/Recebidas"))

        pasted_texts_to_process = []
        if st.session_state.text_pagas: pasted_texts_to_process.append((st.session_state.text_pagas, "Pagas (Colado)"))
        if st.session_state.text_apagar: pasted_texts_to_process.append((st.session_state.text_apagar, "A Pagar (Colado)"))
        if st.session_state.text_receber: pasted_texts_to_process.append((st.session_state.text_receber, "Receber/Recebidas (Colado)"))

        final_files_list = files_to_process_from_upload + pasted_texts_to_process

        if not final_files_list:
            st.warning("Nenhum arquivo carregado ou texto colado para processar.")
        else:
            with st.spinner("Processando arquivos..."):
                for file_data, source_name_hint in final_files_list:
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
                        # Set initial_balance_date only if not already set or to update if earliest_date changes
                        if st.session_state.initial_balance_date is None or st.session_state.initial_balance_date > st.session_state.earliest_date :
                            st.session_state.initial_balance_date = st.session_state.earliest_date
                        st.session_state.data_loaded = True
                        st.success("Dados processados com sucesso!")
                    else:
                        st.warning("Nenhuma transação válida encontrada nos arquivos processados.")
                        st.session_state.data_loaded = False
                else:
                    st.error("Nenhum dado foi processado. Verifique os arquivos ou o conteúdo colado.")
                    st.session_state.data_loaded = False
    
    # --- Initial Balance Input ---
    # This section should be visible if an earliest_date is known, allowing user to set/update balance
    if st.session_state.get('earliest_date'):
        with st.sidebar:
            st.markdown("---")
            st.header("💰 Saldo Inicial")
            
            current_initial_date_val = st.session_state.initial_balance_date
            if isinstance(current_initial_date_val, datetime): # Ensure it's a date object for date_input
                current_initial_date_val = current_initial_date_val.date()
            elif current_initial_date_val is None: # Default to earliest_date if still None
                 current_initial_date_val = st.session_state.earliest_date

            # Use different keys for these input widgets to avoid conflict with session state variables storing the *values*
            selected_initial_date = st.date_input(
                "Data do Saldo Inicial",
                value=current_initial_date_val,
                min_value=st.session_state.earliest_date - timedelta(days=365*10) if st.session_state.earliest_date else datetime.now().date() - timedelta(days=365*10),
                max_value=st.session_state.earliest_date + timedelta(days=365) if st.session_state.earliest_date else datetime.now().date() + timedelta(days=365),
                key="widget_initial_balance_date" # Distinct key for the widget
            )
            selected_initial_amount = st.number_input(
                f"Saldo de Caixa em {selected_initial_date.strftime('%d/%m/%Y')}",
                value=st.session_state.initial_balance_amount,
                format="%.2f",
                step=100.0,
                key="widget_initial_balance_amount" # Distinct key for the widget
            )
            # Update session state variables that store the actual values
            st.session_state.initial_balance_date = selected_initial_date
            st.session_state.initial_balance_amount = selected_initial_amount


    # --- Main Area for Results ---
    if st.session_state.get('data_loaded') and st.session_state.all_transactions_df is not None and not st.session_state.all_transactions_df.empty:
        all_transactions = st.session_state.all_transactions_df.copy()

        # Ensure initial_balance_date is datetime for calculations
        initial_balance_date_dt = pd.to_datetime(st.session_state.initial_balance_date) if st.session_state.initial_balance_date else pd.to_datetime(datetime.now().date())
        initial_balance = st.session_state.initial_balance_amount

        if all_transactions.empty: # Should not happen if data_loaded is true
            min_date_calc = initial_balance_date_dt
            max_date_calc = initial_balance_date_dt
        else:
            min_date_calc = min(initial_balance_date_dt, all_transactions['Data'].min())
            max_date_calc = max(initial_balance_date_dt, all_transactions['Data'].max())

        date_range = pd.date_range(start=min_date_calc, end=max_date_calc, freq='D')
        cash_flow_summary = pd.DataFrame(date_range, columns=['Data'])

        daily_flows = all_transactions.groupby(['Data', 'Tipo'])['Valor'].sum().unstack(fill_value=0)
        cash_flow_summary = pd.merge(cash_flow_summary, daily_flows, on='Data', how='left').fillna(0)

        flow_cols = ['Realizado Entrada', 'Realizado Saída', 'Projetado Entrada', 'Projetado Saída']
        for col in flow_cols:
            if col not in cash_flow_summary.columns:
                cash_flow_summary[col] = 0.0

        cash_flow_summary['Fluxo Realizado Diário'] = cash_flow_summary['Realizado Entrada'] + cash_flow_summary['Realizado Saída']
        cash_flow_summary['Fluxo Projetado Diário'] = cash_flow_summary['Projetado Entrada'] + cash_flow_summary['Projetado Saída']

        cash_flow_summary = cash_flow_summary.sort_values(by='Data').reset_index(drop=True)
        
        # Revised cumulative calculation
        cash_flow_summary['Posição Caixa Acumulada'] = 0.0
        balance = initial_balance 
        # Find the index corresponding to the initial balance date
        initial_date_idx = cash_flow_summary[cash_flow_summary['Data'] == initial_balance_date_dt].index
        if not initial_date_idx.empty:
            initial_date_idx = initial_date_idx[0]
            # Calculate sum of flows *before* initial_balance_date_dt to adjust the starting balance effectively
            sum_flows_before_initial = cash_flow_summary.loc[cash_flow_summary.index < initial_date_idx, 'Fluxo Realizado Diário'].sum()
            effective_start_balance = initial_balance - sum_flows_before_initial
            
            cash_flow_summary['Posição Caixa Acumulada'] = cash_flow_summary['Fluxo Realizado Diário'].cumsum() + effective_start_balance
        else: # initial_balance_date_dt is outside the range of transaction dates
            # This case needs careful handling. For now, assume it starts from initial_balance if no prior transactions.
            # Or if initial_balance_date_dt is before all transactions, flows start accumulating from that balance.
            # If after all transactions, the balance applies to future dates.
            # A simpler model: the initial balance IS the balance at the START of initial_balance_date_dt.
            # So, any flows on initial_balance_date_dt are added to it.
            # All flows prior to initial_balance_date_dt led to some balance just before initial_balance_date_dt.
            # The provided initial_balance "resets" or "defines" the balance at that specific point.

            # Simpler approach:
            current_balance = 0.0
            found_initial_date = False
            for i in range(len(cash_flow_summary)):
                if cash_flow_summary.loc[i, 'Data'] == initial_balance_date_dt:
                    current_balance = initial_balance + cash_flow_summary.loc[i, 'Fluxo Realizado Diário']
                    found_initial_date = True
                elif found_initial_date:
                    current_balance += cash_flow_summary.loc[i, 'Fluxo Realizado Diário']
                else: # Before initial date, or initial date not in range yet
                    # If initial_balance_date_dt is before any data, then current_balance starts as initial_balance.
                    if initial_balance_date_dt <= cash_flow_summary['Data'].min() and not found_initial_date:
                         current_balance = initial_balance # Assume balance is set at start of period if initial date is early
                         current_balance += cash_flow_summary.loc[i, 'Fluxo Realizado Diário']
                         if cash_flow_summary.loc[i, 'Data'] >= initial_balance_date_dt: # handles if first day is initial day
                             found_initial_date = True
                    else: # Accumulate naturally if initial date is later or not hit
                        if i > 0:
                             current_balance = cash_flow_summary.loc[i-1, 'Posição Caixa Acumulada'] + cash_flow_summary.loc[i, 'Fluxo Realizado Diário']
                        else:
                             current_balance = cash_flow_summary.loc[i, 'Fluxo Realizado Diário']


                cash_flow_summary.loc[i, 'Posição Caixa Acumulada'] = current_balance
            
            # If initial_balance_date_dt was never found in the range but transactions exist
            if not found_initial_date and not cash_flow_summary.empty:
                # If initial_balance_date_dt is before all transactions
                if initial_balance_date_dt < cash_flow_summary['Data'].min():
                    offset = initial_balance
                    cash_flow_summary['Posição Caixa Acumulada'] = cash_flow_summary['Fluxo Realizado Diário'].cumsum() + offset
                # If initial_balance_date_dt is after all transactions (this calculation might not make sense for historical view)
                # Or if no transactions at all, the balance is just initial_balance
                elif cash_flow_summary.empty:
                     cash_flow_summary.loc[0, 'Posição Caixa Acumulada'] = initial_balance # Placeholder for single balance point

        # --- Display KPIs ---
        st.subheader("🚀 Indicadores Chave de Performance (KPIs)")
        kpi_data = cash_flow_summary
        
        total_realizado_entrada = kpi_data['Realizado Entrada'].sum()
        total_realizado_saida = kpi_data['Realizado Saída'].sum() 
        saldo_realizado_periodo = total_realizado_entrada + total_realizado_saida
        
        total_projetado_entrada = kpi_data['Projetado Entrada'].sum()
        total_projetado_saida = kpi_data['Projetado Saída'].sum() 
        saldo_projetado_periodo = total_projetado_entrada + total_projetado_saida
        
        resultado_final_periodo_realizado = kpi_data['Posição Caixa Acumulada'].iloc[-1] if not kpi_data.empty else initial_balance
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
        # Ensure cash_flow_summary is not empty before plotting
        if not cash_flow_summary.empty:
            fig_daily_flow_realizado = px.bar(cash_flow_summary, x='Data', y='Fluxo Realizado Diário', 
                                    title='Variação Diária do Fluxo de Caixa (Realizado)',
                                    labels={'Fluxo Realizado Diário': 'Valor (R$)'})
            fig_daily_flow_realizado.update_traces(marker_color=['red' if x < 0 else 'green' for x in cash_flow_summary['Fluxo Realizado Diário']])
            st.plotly_chart(fig_daily_flow_realizado, use_container_width=True)

            fig_cumulative_cash = px.line(cash_flow_summary, x='Data', y='Posição Caixa Acumulada', 
                                        title='Posição de Caixa Acumulada (Realizado)',
                                        labels={'Posição Caixa Acumulada': 'Saldo (R$)'})
            st.plotly_chart(fig_cumulative_cash, use_container_width=True)
            
            future_dates_mask = cash_flow_summary['Data'] >= pd.to_datetime(datetime.now().date()) # Ensure comparison with datetime
            projetado_plot_data = cash_flow_summary[future_dates_mask & (cash_flow_summary['Fluxo Projetado Diário'] != 0)]
            if not projetado_plot_data.empty:
                fig_daily_flow_projetado = px.bar(projetado_plot_data, x='Data', y='Fluxo Projetado Diário',
                                        title='Variação Diária do Fluxo de Caixa (Projetado - Futuro)',
                                        labels={'Fluxo Projetado Diário': 'Valor (R$)'})
                fig_daily_flow_projetado.update_traces(marker_color=['orange' if x < 0 else 'blue' for x in projetado_plot_data['Fluxo Projetado Diário']])
                st.plotly_chart(fig_daily_flow_projetado, use_container_width=True)
        else:
            st.info("Nenhum dado para exibir nos gráficos.")


        # --- Display Summary Table ---
        st.subheader("🧾 Resumo Diário do Fluxo de Caixa")
        if not cash_flow_summary.empty:
            display_summary = cash_flow_summary[['Data', 'Realizado Entrada', 'Realizado Saída', 'Fluxo Realizado Diário', 
                                                'Projetado Entrada', 'Projetado Saída', 'Fluxo Projetado Diário', 'Posição Caixa Acumulada']].copy()
            for col_fmt in ['Realizado Entrada', 'Realizado Saída', 'Fluxo Realizado Diário', 'Projetado Entrada', 'Projetado Saída', 'Fluxo Projetado Diário', 'Posição Caixa Acumulada']:
                display_summary[col_fmt] = display_summary[col_fmt].apply(lambda x: f"R$ {x:,.2f}")
            display_summary['Data'] = display_summary['Data'].dt.strftime('%d/%m/%Y')
            st.dataframe(display_summary.set_index('Data'), use_container_width=True)
        else:
            st.info("Nenhum dado para exibir na tabela resumo.")


        # --- Display Detailed Tables with Filters ---
        st.subheader("🔍 Detalhes das Transações")
        tab1, tab2 = st.tabs(["Pagamentos (Realizados e A Pagar)", "Recebimentos (Realizados e A Receber)"])

        with tab1:
            st.markdown("#### Pagamentos")
            pagamentos_df = all_transactions[all_transactions['Tipo'].isin(['Realizado Saída', 'Projetado Saída'])].copy()
            if not pagamentos_df.empty:
                col_filter1, col_filter2 = st.columns(2)
                # Ensure unique default value list for multiselect
                unique_status_pag = pagamentos_df['Status'].unique().tolist()
                status_filter_pag = col_filter1.multiselect("Filtrar por Status:", unique_status_pag, default=unique_status_pag, key="status_pag_filter")
                
                min_date_pag_val = pagamentos_df['Data'].min().date()
                max_date_pag_val = pagamentos_df['Data'].max().date()
                # Ensure date_range_pag has two elements (start and end)
                date_range_pag_val = col_filter2.date_input("Filtrar por Data:", value=(min_date_pag_val, max_date_pag_val), min_value=min_date_pag_val, max_value=max_date_pag_val, key="date_pag_filter")

                if date_range_pag_val and len(date_range_pag_val) == 2:
                    filtered_pagamentos = pagamentos_df[
                        (pagamentos_df['Status'].isin(status_filter_pag)) &
                        (pagamentos_df['Data'].dt.date >= date_range_pag_val[0]) &
                        (pagamentos_df['Data'].dt.date <= date_range_pag_val[1])
                    ]
                    filtered_pagamentos_display = filtered_pagamentos[['Data', 'Descricao', 'Valor', 'Status', 'Credor/Cliente', 'Detalhe']].copy()
                    filtered_pagamentos_display['Valor'] = filtered_pagamentos_display['Valor'].apply(lambda x: f"R$ {x:,.2f}")
                    filtered_pagamentos_display['Data'] = filtered_pagamentos_display['Data'].dt.strftime('%d/%m/%Y')
                    st.dataframe(filtered_pagamentos_display, use_container_width=True, height=300)
                else:
                    st.warning("Por favor, selecione um intervalo de datas válido para filtrar pagamentos.")
            else:
                st.info("Nenhum dado de pagamento para exibir.")

        with tab2:
            st.markdown("#### Recebimentos")
            recebimentos_df = all_transactions[all_transactions['Tipo'].isin(['Realizado Entrada', 'Projetado Entrada'])].copy()
            if not recebimentos_df.empty:
                col_filter_r1, col_filter_r2 = st.columns(2)
                unique_status_rec = recebimentos_df['Status'].unique().tolist()
                status_filter_rec = col_filter_r1.multiselect("Filtrar por Status:", unique_status_rec, default=unique_status_rec, key="status_rec_filter")
                
                min_date_rec_val = recebimentos_df['Data'].min().date()
                max_date_rec_val = recebimentos_df['Data'].max().date()
                date_range_rec_val = col_filter_r2.date_input("Filtrar por Data:", value=(min_date_rec_val, max_date_rec_val), min_value=min_date_rec_val, max_value=max_date_rec_val, key="date_rec_filter")

                if date_range_rec_val and len(date_range_rec_val) == 2:
                    filtered_recebimentos = recebimentos_df[
                        (recebimentos_df['Status'].isin(status_filter_rec)) &
                        (recebimentos_df['Data'].dt.date >= date_range_rec_val[0]) &
                        (recebimentos_df['Data'].dt.date <= date_range_rec_val[1])
                    ]
                    filtered_recebimentos_display = filtered_recebimentos[['Data', 'Descricao', 'Valor', 'Status', 'Credor/Cliente', 'Detalhe']].copy()
                    filtered_recebimentos_display['Valor'] = filtered_recebimentos_display['Valor'].apply(lambda x: f"R$ {x:,.2f}")
                    filtered_recebimentos_display['Data'] = filtered_recebimentos_display['Data'].dt.strftime('%d/%m/%Y')
                    st.dataframe(filtered_recebimentos_display, use_container_width=True, height=300)
                else:
                    st.warning("Por favor, selecione um intervalo de datas válido para filtrar recebimentos.")

            else:
                st.info("Nenhum dado de recebimento para exibir.")

    elif not st.session_state.get('data_loaded') and (st.session_state.get("process") is True or process_button) :
        # This case means processing was attempted but resulted in no data_loaded
        # Messages would have been shown during processing
        pass
    else: # Initial state, no processing attempted yet
        st.info("✨ Bem-vindo! Faça o upload dos arquivos CSV ou cole o conteúdo e clique em 'Processar Dados' para iniciar a análise do fluxo de caixa.")


if __name__ == "__main__":
    main()
