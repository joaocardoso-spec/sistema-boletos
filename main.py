import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import time

# --- CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="Gerador de Boletos", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0b0e14; color: #ffffff; }
    .stButton>button { background-color: #238636; color: white; width: 100%; font-weight: bold; border: none; }
    .status-box { padding: 15px; border-radius: 8px; margin-bottom: 10px; font-weight: bold; }
    .ok-box { background-color: #1a2d1f; border-left: 5px solid #238636; }
    .nok-box { background-color: #2d1a1e; border-left: 5px solid #ff4b4b; }
    </style>
    """, unsafe_allow_html=True)

def init_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def get_clean_data_flexible(worksheet):
    all_values = worksheet.get_all_values()
    header_idx = 0
    # Procura a linha que contém "Key" e "Clientes" (geralmente linha 4 ou 7)
    for i, row in enumerate(all_values):
        row_clean = [str(c).strip().lower() for c in row]
        if 'key' in row_clean and 'clientes' in row_clean:
            header_idx = i
            break
    headers = [str(h).strip() for h in all_values[header_idx]]
    data = all_values[header_idx + 1:]
    return pd.DataFrame(data, columns=headers)

try:
    gc = init_connection()
    # MANTENHA SEU ID ENTRE ASPAS AQUI
    SPREADSHEET_ID = "1zOof6YDL4U8hYMiFi5zt4V_alYK6EcRvV3QKERvNlhA"
    ss = gc.open_by_key(SPREADSHEET_ID)
    
    sh_input = ss.worksheet("INPUT - BOLETOS")
    sh_output = ss.worksheet("OUTPUT - BOLETOS")
    sh_comm = ss.worksheet("COMUNICACAO - CLIENTE")
    
    df_input = get_clean_data_flexible(sh_input)
    df_input = df_input[df_input['Clientes'] != ""].copy()
    
except Exception as e:
    st.error(f"❌ Erro de Conexão: {e}")
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
    key_sel = row_sel['Key']

    st.markdown("---")
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🟦 Meta Ads")
        m_metodo = st.selectbox("Método Pagamento", ["Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanha"], key="m_m")
        m_credito = st.text_input("Crédito Atual (Meta)", value="R$ 0,00", key="m_c")
        m_data = st.text_input("Data do Saldo (Meta)", placeholder="DD/MM", key="m_d")
        m_valor = st.text_input("Gasto Diário (Meta)", value="R$ 0,00", key="m_v")

    with c2:
        st.subheader("🟩 Google Ads")
        g_metodo = st.selectbox("Método Pagamento", ["Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanha"], key="g_m")
        g_credito = st.text_input("Crédito Atual (Google)", value="R$ 0,00", key="g_c")
        g_data = st.text_input("Data do Saldo (Google)", placeholder="DD/MM", key="g_d")
        g_valor = st.text_input("Gasto Diário (Google)", value="R$ 0,00", key="g_v")

    if st.button("SALVAR E GERAR DIAGNÓSTICO"):
        with st.spinner("Sincronizando..."):
            # Achar linha exata na Coluna B
            cell = sh_input.find(str(key_sel), in_column=2)
            r_idx = cell.row
            
            # CORREÇÃO AQUI: Meta agora na I:L e Google na M:P
            sh_input.update(f"I{r_idx}:L{r_idx}", [[m_metodo, m_credito, m_data, m_valor]])
            sh_input.update(f"M{r_idx}:P{r_idx}", [[g_metodo, g_credito, g_data, g_valor]])
            
            time.sleep(3)
            
            # Puxar diagnósticos atualizados
            df_out_final = get_clean_data_flexible(sh_output)
            out_row = df_out_final[df_out_final['Key'] == key_sel].iloc[0]
            
            df_comm_final = get_clean_data_flexible(sh_comm)
            comm_row = df_comm_final[df_comm_final.iloc[:, 1] == key_sel].iloc[0]

            st.success("✅ Sincronizado com Sucesso!")
            
            st.markdown("### 📊 Verificação de Cheques")
            res_cols = st.columns(4)
            
            # Mapeamento dinâmico baseado no CSV enviado
            chks = [
                ("Check 1: Atualização", out_row.iloc[8]),  # Col I
                ("Check 2: Valor Mídia", out_row.iloc[12]), # Col M
                ("Check 3: Limite Emissão", out_row.iloc[15]), # Col P
                ("Check 4: Saldo dia 10", out_row.iloc[19])  # Col T
            ]
            
            for i, (name, val) in enumerate(chks):
                with res_cols[i]:
                    is_ok = "OK" in str(val).upper()
                    style = "ok-box" if is_ok else "nok-box"
                    st.markdown(f"<div class='status-box {style}'>{'✅' if is_ok else '❌'} {name}: {val}</div>", unsafe_allow_html=True)

            st.divider()
            st.metric("Total a Emitir", f"R$ {out_row.iloc[24]}") # Col Y
            
            st.markdown(f"**WhatsApp:** [Enviar Agora]({comm_row.iloc[10]}) | **E-mail:** [Enviar Agora]({comm_row.iloc[11]})")
            st.info(f"**Título do Arquivo:** {out_row.iloc[28]}") # Col AC
