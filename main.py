import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import time

# --- CONFIGURAÇÃO DA PÁGINA ---
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

def get_clean_data_flexible(worksheet):
    all_values = worksheet.get_all_values()
    header_idx = 0
    for i, row in enumerate(all_values):
        row_clean = [str(c).strip().lower() for c in row]
        if 'key' in row_clean or 'id' in row_clean:
            header_idx = i
            break
    headers = [str(h).strip() for h in all_values[header_idx]]
    data = all_values[header_idx + 1:]
    return pd.DataFrame(data, columns=headers)

# --- CONEXÃO INICIAL ---
try:
    gc = init_connection()
    SPREADSHEET_ID = "1zOof6YDL4U8hYMiFi5zt4V_alYK6EcRvV3QKERvNlhA"
    ss = gc.open_by_key(SPREADSHEET_ID)
    sh_input = ss.worksheet("INPUT - BOLETOS")
    sh_output = ss.worksheet("OUTPUT - BOLETOS")
    sh_comm = ss.worksheet("COMUNICACAO - CLIENTE")
    
    df_input = get_clean_data_flexible(sh_input)
    df_input = df_input[df_input['Clientes'] != ""].copy()
except Exception as e:
    st.error(f"Erro na conexão: {e}")
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

    # --- FORMULÁRIO DE ENTRADA ---
    # Usar st.form permite que o usuário use Enter para navegar e enviar ao final
    with st.form("input_form"):
        st.markdown("### 📝 Preenchimento de Dados")
        c1, c2 = st.columns(2)
        
        with c1:
            st.subheader("🟦 Meta Ads")
            m_metodo = st.selectbox("Método Pagamento", ["Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanha"])
            m_credito = st.text_input("Crédito Atual (Meta)", placeholder="Ex: 1.500,00")
            m_data = st.text_input("Data do Saldo (Meta)", placeholder="DD/MM")
            m_valor = st.text_input("Gasto Diário (Meta)", placeholder="Ex: 50,00")

        with c2:
            st.subheader("🟩 Google Ads")
            g_metodo = st.selectbox("Método Pagamento", ["Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanha"])
            g_credito = st.text_input("Crédito Atual (Google)", placeholder="Ex: 1.500,00")
            g_data = st.text_input("Data do Saldo (Google)", placeholder="DD/MM")
            g_valor = st.text_input("Gasto Diário (Google)", placeholder="Ex: 50,00")
        
        submit_button = st.form_submit_button("SALVAR E GERAR DIAGNÓSTICO")

    if submit_button:
        with st.spinner("Processando..."):
            # Achar linha
            cell = sh_input.find(key_sel, in_column=2)
            r_idx = cell.row
            
            # Limpar valores para garantir que a planilha entenda como número
            m_c_num = limpar_valor(m_credito)
            m_v_num = limpar_valor(m_valor)
            g_c_num = limpar_valor(g_credito)
            g_v_num = limpar_valor(g_valor)
            
            # Salvar (I a P)
            sh_input.update(f"I{r_idx}:P{r_idx}", [[m_metodo, m_c_num, m_data, m_v_num, g_metodo, g_c_num, g_data, g_v_num]], value_input_option='USER_ENTERED')
            
            time.sleep(4) # Espera cálculos do Sheets
            
            # Puxar dados atualizados
            df_out_final = get_clean_data_flexible(sh_output)
            out_row = df_out_final[df_out_final['Key'].astype(str).str.strip() == key_sel].iloc[0]
            
            df_comm_final = get_clean_data_flexible(sh_comm)
            id_col_comm = 'ID' if 'ID' in df_comm_final.columns else 'Key'
            comm_row = df_comm_final[df_comm_final[id_col_comm].astype(str).str.strip() == key_sel].iloc[0]

            st.success("✅ Sincronizado!")
            
            # --- ÁREA DE DIAGNÓSTICO (VISUAL MELHORADO) ---
            st.markdown("---")
            st.markdown("### 📊 Diagnóstico de Verificação")
            res_cols = st.columns(4)
            
            # Nomes exatos das colunas da sua planilha de OUTPUT (conforme CSV)
            chks = [
                ("Check 1", out_row.get('Preench. FB', 'NOK')),  
                ("Check 2", out_row.get('Valor Mídia', 'NOK')), 
                ("Check 3", out_row.get('Valor a Emitir', 'NOK')), 
                ("Check 4", out_row.get('Saldo até dia 10', 'NOK'))
            ]
            
            for i, (name, val) in enumerate(chks):
                is_ok = "OK" in str(val).upper()
                card_class = "ok-card" if is_ok else "nok-card"
                with res_cols[i]:
                    st.markdown(f"<div class='check-card {card_class}'>{name}<br>{'✅ OK' if is_ok else '❌ ' + str(val)}</div>", unsafe_allow_html=True)

            # --- AÇÕES FINAIS (LINKS CLICÁVEIS) ---
            st.divider()
            v_col1, v_col2 = st.columns([1, 2])
            with v_col1:
                st.metric("Total a Emitir", f"R$ {out_row.get('Valor a Emitir', '0,00')}")
                st.info(f"**Título:** {out_row.get('Nome Boleto/PIX', '...')}")
            
            with v_col2:
                st.markdown("**Ações Disponíveis:**")
                link_whatsapp = comm_row.get('Envio Whatsapp', '#')
                link_email = comm_row.get('Envio E-mail', '#')
                
                # Botões de link clicáveis
                st.link_button("📲 Enviar Boleto via WhatsApp", link_whatsapp)
                st.link_button("📧 Enviar Boleto via E-mail", link_email)
