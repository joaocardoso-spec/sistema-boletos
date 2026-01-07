import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import time

# --- CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="Sistema de Boletos - Operacional", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0b0e14; color: #ffffff; }
    .stButton>button { background-color: #238636; color: white; width: 100%; font-weight: bold; border: none; height: 3em; }
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

def limpar_valor_monetario(texto):
    if not texto: return 0
    # Converte "1.500,00" ou "R$ 1.500,00" para 1500.00
    limpo = str(texto).replace('R$', '').replace('.', '').replace(',', '.').strip()
    try: return float(limpo)
    except: return 0

# --- CONEXÃO E CARREGAMENTO ---
try:
    gc = init_connection()
    # MANTENHA O SEU ID ENTRE ASPAS ABAIXO
    SPREADSHEET_ID = "1zOof6YDL4U8hYMiFi5zt4V_alYK6EcRvV3QKERvNlhA"
    ss = gc.open_by_key(SPREADSHEET_ID)
    
    sh_input = ss.worksheet("INPUT - BOLETOS")
    sh_output = ss.worksheet("OUTPUT - BOLETOS")
    sh_comm = ss.worksheet("COMUNICACAO - CLIENTE")

    # Carrega INPUT partindo da Linha 4 (Índice 3)
    vals_input = sh_input.get_all_values()
    df_input = pd.DataFrame(vals_input[4:], columns=vals_input[3]) 
    # Filtra apenas clientes válidos (Coluna C) e limpa espaços
    df_input = df_input[df_input.iloc[:, 2] != ""].copy() 

except Exception as e:
    st.error(f"Erro de conexão: {e}")
    st.stop()

# --- INTERFACE ---
st.title("🏦 Gestão de Faturamento e Boletos")

# Filtro por SQUAD (Coluna F - Índice 5)
squad_list = sorted([s for s in df_input.iloc[:, 5].unique() if s and s != "-"] )
selected_squad = st.sidebar.selectbox("Selecione sua SQUAD", squad_list)

# Filtro de Status (Coluna D - Índice 3)
status_operacionais = ["OK", "NÃO INICIOU", "DUPLICADO", "ENCERRAR"]
df_filtered = df_input[(df_input.iloc[:, 5] == selected_squad) & (df_input.iloc[:, 3].isin(status_operacionais))]

if df_filtered.empty:
    st.warning(f"Nenhum cliente disponível para a SQUAD {selected_squad}.")
else:
    # Seleção de Cliente (Coluna C - Índice 2)
    cliente_sel = st.selectbox("Escolha o Cliente:", df_filtered.iloc[:, 2].tolist())
    row_sel = df_filtered[df_filtered.iloc[:, 2] == cliente_sel].iloc[0]
    key_sel = str(row_sel.iloc[1]).strip() # Key na Coluna B

    st.divider()
    
    # --- FORMULÁRIO DE ENTRADA (MÁSCARAS VISUAIS) ---
    st.markdown("#### ✍️ Lançamento de Dados")
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("🟦 Meta Ads")
        m_metodo = st.selectbox("Método Pag. Meta", ["Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanha"], key="met_m")
        m_credito = st.text_input("Crédito Atual Meta", placeholder="Ex: 1.500,00", key="met_c")
        m_data = st.text_input("Data do Saldo Meta", placeholder="DD/MM", key="met_d")
        m_valor = st.text_input("Gasto Diário Meta", placeholder="Ex: 50,00", key="met_v")

    with c2:
        st.subheader("🟩 Google Ads")
        g_metodo = st.selectbox("Método Pag. Google", ["Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanha"], key="goo_m")
        g_credito = st.text_input("Crédito Atual Google", placeholder="Ex: 1.500,00", key="goo_c")
        g_data = st.text_input("Data do Saldo Google", placeholder="DD/MM", key="goo_d")
        g_valor = st.text_input("Gasto Diário Google", placeholder="Ex: 50,00", key="goo_v")

    if st.button("🚀 SALVAR E GERAR DIAGNÓSTICO"):
        with st.spinner("Sincronizando..."):
            # Acha linha na Input (Busca na Coluna B)
            cell = sh_input.find(key_sel, in_column=2)
            r_idx = cell.row
            
            # Limpeza de números para o Sheets
            vals_to_update = [
                [m_metodo, limpar_valor_monetario(m_credito), m_data, limpar_valor_monetario(m_valor),
                 g_metodo, limpar_valor_monetario(g_credito), g_data, limpar_valor_monetario(g_valor)]
            ]
            
            # Atualiza Colunas I a P
            sh_input.update(f"I{r_idx}:P{r_idx}", vals_to_update, value_input_option='USER_ENTERED')
            
            time.sleep(4) # Delay para o Sheets calcular o Output

            # --- LEITURA DO OUTPUT (Linha 7 cabeçalho) ---
            data_out = sh_output.get_all_values()
            df_out_final = pd.DataFrame(data_out[7:], columns=data_out[6])
            out_row = df_out_final[df_out_final.iloc[:, 1].astype(str).str.strip() == key_sel].iloc[0]
            
            # --- LEITURA DA COMUNICAÇÃO ---
            data_comm = sh_comm.get_all_values()
            df_comm = pd.DataFrame(data_comm[4:], columns=data_comm[3])
            comm_row = df_comm[df_comm.iloc[:, 0].astype(str).str.strip() == key_sel].iloc[0]

            st.success("✅ Dados processados com sucesso!")
            
            # --- DIAGNÓSTICO DE CHEQUES ---
            st.markdown("### 📊 Verificação de Cheques")
            res_cols = st.columns(4)
            
            # Coordenadas: M(13), P(16), R(18), T(20) - Índices 12, 15, 17, 19
            checks = [
                ("Check 2: Mídia", out_row.iloc[12]),
                ("Check 3: Emissão", out_row.iloc[15]),
                ("Check 4: Saldo Meta", out_row.iloc[17]),
                ("Check 4: Saldo Google", out_row.iloc[19])
            ]
            
            for i, (name, val) in enumerate(checks):
                is_ok = "OK" in str(val).upper()
                card_class = "ok-card" if is_ok else "nok-card"
                with res_cols[i]:
                    st.markdown(f"<div class='check-card {card_class}'>{name}<br>{val}</div>", unsafe_allow_html=True)

            st.divider()
            
            v1, v2 = st.columns([1, 2])
            with v1:
                st.metric("Valor a Emitir", f"R$ {out_row.iloc[24]}") # Col Y
                # Nome do Boleto (Col AB - Índice 27) só aparece se houver valor
                nome_bol = out_row.iloc[27]
                if nome_bol and nome_bol != "":
                    st.code(f"Título: {nome_bol}", language=None)
            
            with v2:
                st.markdown("**Ações de Envio:**")
                wpp = str(comm_row.iloc[10]).strip() # Col K
                mail = str(comm_row.iloc[11]).strip() # Col L
                
                if wpp.startswith("http"): st.link_button("📲 Enviar via WhatsApp", wpp)
                else: st.warning("⚠️ WhatsApp não disponível.")
                
                if mail.startswith("http"): st.link_button("📧 Enviar via E-mail", mail)
                else: st.warning("⚠️ E-mail não disponível.")
