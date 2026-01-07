import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import time

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Gerador de Boletos v2", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0b0e14; color: #ffffff; }
    .stButton>button { background-color: #238636; color: white; width: 100%; font-weight: bold; border: none; }
    .check-card { padding: 15px; border-radius: 8px; margin-bottom: 10px; font-weight: bold; text-align: center; }
    .ok-card { background-color: #1a2d1f; border: 1px solid #238636; color: #73d13d; }
    .nok-card { background-color: #2d1a1e; border: 1px solid #ff4b4b; color: #ff4b4b; }
    </style>
    """, unsafe_allow_html=True)

def init_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def limpar_valor(texto):
    if not texto: return 0
    limpo = str(texto).replace('R$', '').replace('.', '').replace(',', '.').strip()
    try: return float(limpo)
    except: return 0

def get_df_flexible(worksheet):
    all_values = worksheet.get_all_values()
    header_idx = 0
    for i, row in enumerate(all_values):
        row_clean = [str(c).strip().lower() for c in row]
        if 'key' in row_clean and 'clientes' in row_clean:
            header_idx = i
            break
    headers = [str(h).strip() for h in all_values[header_idx]]
    data = all_values[header_idx + 1:]
    df = pd.DataFrame(data, columns=headers)
    df = df.loc[:, df.columns != ''] # Remove colunas sem título
    return df

# --- CONEXÃO ---
try:
    gc = init_connection()
    SPREADSHEET_ID = "1zOof6YDL4U8hYMiFi5zt4V_alYK6EcRvV3QKERvNlhA"
    ss = gc.open_by_key(SPREADSHEET_ID)
    sh_input = ss.worksheet("INPUT - BOLETOS")
    sh_output = ss.worksheet("OUTPUT - BOLETOS")
    sh_comm = ss.worksheet("COMUNICACAO - CLIENTE")
    
    df_input = get_df_flexible(sh_input)
    df_input = df_input[df_input['Clientes'] != ""].copy()
except Exception as e:
    st.error(f"Erro de conexão: {e}")
    st.stop()

# --- INTERFACE ---
st.title("🚀 Operação de Geração de Boletos")

squads = sorted([s for s in df_input['SQUAD'].unique() if s and s not in ["-", ""]])
selected_squad = st.sidebar.selectbox("Escolha sua SQUAD:", squads)

status_permitidos = ["OK", "NÃO INICIOU", "DUPLICADO", "ENCERRAR"]
df_filtered = df_input[(df_input['SQUAD'] == selected_squad) & (df_input['Status'].isin(status_permitidos))]

if df_filtered.empty:
    st.warning("Nenhum cliente disponível nesta SQUAD.")
else:
    cliente_sel = st.selectbox("Selecione o Cliente:", df_filtered['Clientes'].tolist())
    row_sel = df_filtered[df_filtered['Clientes'] == cliente_sel].iloc[0]
    key_sel = str(row_sel['Key']).strip()

    st.divider()
    
    # --- FORMULÁRIO COM NAVEGAÇÃO POR ENTER ---
    with st.form("main_form"):
        st.markdown("### 📝 Preenchimento Operacional")
        col_meta, col_google = st.columns(2)
        
        with col_meta:
            st.subheader("🟦 Meta Ads")
            # Adicionado keys únicas para evitar o erro de DuplicateElementId
            m_metodo = st.selectbox("Método Pagamento Meta", ["Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanha"], key="meta_m")
            m_credito = st.text_input("Crédito Atual Meta", placeholder="Ex: 1.200,50", key="meta_c")
            m_data = st.text_input("Data do Saldo Meta", placeholder="DD/MM", key="meta_d")
            m_valor = st.text_input("Gasto Diário Meta", placeholder="Ex: 45,00", key="meta_v")

        with col_google:
            st.subheader("🟩 Google Ads")
            g_metodo = st.selectbox("Método Pagamento Google", ["Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanha"], key="google_m")
            g_credito = st.text_input("Crédito Atual Google", placeholder="Ex: 850,00", key="google_c")
            g_data = st.text_input("Data do Saldo Google", placeholder="DD/MM", key="google_d")
            g_valor = st.text_input("Gasto Diário Google", placeholder="Ex: 30,00", key="google_v")
        
        # Botão de salvar OBRIGATORIAMENTE dentro do form
        submit = st.form_submit_button("💾 SALVAR E GERAR DIAGNÓSTICO")

    if submit:
        with st.spinner("Sincronizando com a planilha..."):
            cell = sh_input.find(key_sel, in_column=2)
            r_idx = cell.row
            
            # Limpeza para envio numérico
            m_c_val = limpar_valor(m_credito)
            m_v_val = limpar_valor(m_valor)
            g_c_val = limpar_valor(g_credito)
            g_v_val = limpar_valor(g_valor)
            
            # Envio para as colunas I até P (Meta e Google)
            sh_input.update(f"I{r_idx}:P{r_idx}", [[m_metodo, m_c_val, m_data, m_v_val, g_metodo, g_c_val, g_data, g_v_val]], value_input_option='USER_ENTERED')
            
            time.sleep(4) # Tempo para processamento do Sheets
            
            # Puxar diagnósticos atualizados
            df_out_final = get_df_flexible(sh_output)
            out_row = df_out_final[df_out_final['Key'].astype(str).str.strip() == key_sel].iloc[0]
            
            df_comm_final = get_df_flexible(sh_comm)
            id_col_comm = 'ID' if 'ID' in df_comm_final.columns else 'Key'
            comm_row = df_comm_final[df_comm_final[id_col_comm].astype(str).str.strip() == key_sel].iloc[0]

            st.success("✅ Sincronizado com Sucesso!")
            
            # --- ÁREA DE DIAGNÓSTICO ---
            st.markdown("---")
            st.markdown("### 📊 Verificação de Cheques")
            res_cols = st.columns(4)
            
            # Puxando valores reais das colunas de Check na aba Output
            checks = [
                ("Check 1: Atualização", out_row.get('Preench. FB', 'NOK')),  
                ("Check 2: Valor Mídia", out_row.get('Valor Mídia', 'NOK')), 
                ("Check 3: Limite Emissão", out_row.get('Valor a Emitir', 'NOK')), 
                ("Check 4: Saldo dia 10", out_row.get('Saldo até dia 10', 'NOK'))
            ]
            
            for i, (name, val) in enumerate(checks):
                is_ok = "OK" in str(val).upper()
                card_class = "ok-card" if is_ok else "nok-card"
                with res_cols[i]:
                    st.markdown(f"<div class='check-card {card_class}'>{name}<br>{'✅ OK' if is_ok else '❌ ' + str(val)}</div>", unsafe_allow_html=True)

            # --- AÇÕES E LINKS ---
            st.divider()
            v1, v2 = st.columns([1, 2])
            with v1:
                st.metric("Total a Emitir", f"R$ {out_row.get('Valor a Emitir', '0,00')}")
                st.info(f"**Título:** {out_row.get('Nome Boleto/PIX', '...')}")
            
            with v2:
                st.markdown("**Ações de Envio:**")
                # st.link_button cria botões clicáveis que redirecionam para os links da planilha
                st.link_button("📲 Enviar Boleto via WhatsApp", comm_row.get('Envio Whatsapp', '#'))
                st.link_button("📧 Enviar Boleto via E-mail", comm_row.get('Envio E-mail', '#'))
