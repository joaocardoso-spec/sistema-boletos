import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import time
import urllib.parse
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Sistema de Boletos v2.0", layout="wide")

# CSS Global
st.markdown("""
    <style>
    .main { background-color: #0b0e14; color: #ffffff; }
    .stButton>button { background-color: #238636; color: white; width: 100%; font-weight: bold; height: 3.5em; border: none; }
    .check-card { padding: 12px; border-radius: 8px; margin-bottom: 8px; font-weight: bold; text-align: center; font-size: 0.85em; min-height: 100px; display: flex; flex-direction: column; justify-content: center; }
    .ok-card { background-color: #1a2d1f; border: 1px solid #238636; color: #73d13d; }
    .nok-card { background-color: #2d1a1e; border: 1px solid #ff4b4b; color: #ff4b4b; }
    .val-diff { font-size: 0.8em; color: #ffffff; margin-top: 5px; font-weight: normal; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES DE SUPORTE ---
def init_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def normalizar_id(valor):
    return str(valor).replace(',', '.').strip()

def limpar_valor_monetario(texto):
    if not texto: return 0
    limpo = str(texto).replace('R$', '').replace('.', '').replace(',', '.').strip()
    try: return float(limpo)
    except: return 0

# --- CONEXÃO INICIAL (Cacheada) ---
# Usamos st.cache_resource para não reconectar toda hora
@st.cache_resource
def get_sheets():
    try:
        gc = init_connection()
        SPREADSHEET_ID = "1zOof6YDL4U8hYMiFi5zt4V_alYK6EcRvV3QKERvNlhA"
        ss = gc.open_by_key(SPREADSHEET_ID)
        return {
            "input": ss.worksheet("INPUT - BOLETOS"),
            "output": ss.worksheet("OUTPUT - BOLETOS"),
            "comm": ss.worksheet("COMUNICACAO - CLIENTE")
        }
    except Exception as e:
        st.error(f"Erro crítico de conexão: {e}")
        st.stop()

sheets = get_sheets()

# ==============================================================================
# PÁGINA 1: LANÇAMENTO (Código Original Refatorado)
# ==============================================================================
def pagina_lancamento():
    st.title("🏦 Gestor de Boletos - Lançamento")
    
    # Recarrega dados da INPUT para garantir frescor
    vals_in = sheets["input"].get_all_values()
    # Cabeçalho na linha 4 (index 3), Dados na linha 5 (index 4) conforme original
    df_input = pd.DataFrame(vals_in[4:], columns=vals_in[3])
    df_input = df_input[df_input.iloc[:, 2] != ""].copy()

    squad_list = sorted([s for s in df_input.iloc[:, 5].unique() if s and s != "-"] )
    selected_squad = st.sidebar.selectbox("Filtro SQUAD (Lançamento)", squad_list)

    status_ops = ["OK", "NÃO INICIOU", "DUPLICADO", "ENCERRAR"]
    # Coluna 5 é Squad, Coluna 3 é Status
    df_filtered = df_input[(df_input.iloc[:, 5] == selected_squad) & (df_input.iloc[:, 3].isin(status_ops))]

    if df_filtered.empty:
        st.warning(f"Sem clientes disponíveis para {selected_squad} na aba INPUT.")
        return

    cliente_sel = st.selectbox("Selecione o Cliente:", df_filtered.iloc[:, 2].tolist())
    row_sel = df_filtered[df_filtered.iloc[:, 2] == cliente_sel].iloc[0]
    key_orig = str(row_sel.iloc[1]).strip()
    key_norm = normalizar_id(key_orig)

    st.divider()
    st.markdown("#### ✍️ Preenchimento de Dados")
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🟦 Meta Ads")
        m_met = st.selectbox("Método Pagamento", ["Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanha"], key="v1")
        m_cre = st.text_input("Crédito Atual Meta", placeholder="Ex: 1.500,00", key="v2")
        m_dat = st.text_input("Data do Saldo Meta", placeholder="DD/MM", key="v3")
        m_val = st.text_input("Gasto Diário Meta", placeholder="Ex: 50,00", key="v4")
    with c2:
        st.subheader("🟩 Google Ads")
        g_met = st.selectbox("Método Pagamento ", ["Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanha"], key="v5")
        g_cre = st.text_input("Crédito Atual Google", placeholder="Ex: 1.500,00", key="v6")
        g_dat = st.text_input("Data do Saldo Google", placeholder="DD/MM", key="v7")
        g_val = st.text_input("Gasto Diário Google", placeholder="Ex: 50,00", key="v8")

    if st.button("💾 SALVAR E GERAR DIAGNÓSTICO"):
        with st.spinner("Sincronizando..."):
            try:
                # 1. SALVAR NA INPUT
                cell_in = sheets["input"].find(key_orig, in_column=2)
                r_in = cell_in.row
                sheets["input"].update(f"I{r_in}:P{r_in}", [[m_met, limpar_valor_monetario(m_cre), m_dat, limpar_valor_monetario(m_val),
                                                      g_met, limpar_valor_monetario(g_cre), g_dat, limpar_valor_monetario(g_val)]], value_input_option='USER_ENTERED')
                time.sleep(3) 

                # 2. GATILHOS NA OUTPUT
                data_out = sheets["output"].get_all_values()
                # Cabeçalho na linha 7 (index 6), dados começam na linha 8 (index 7)
                # O ID está na coluna B (index 1)
                match_idx = -1
                for i, r in enumerate(data_out[7:]):
                    if len(r) > 1 and normalizar_id(r[1]) == key_norm:
                        match_idx = i + 8 # Linha real na planilha (1-based)
                        out_row_data = r
                        break

                if match_idx == -1:
                    st.error("❌ Key não encontrada na aba OUTPUT.")
                else:
                    # Copia Y(24) para Z(25) e AK(36) para AL(37)
                    sheets["output"].update_cell(match_idx, 26, out_row_data[24]) 
                    sheets["output"].update_cell(match_idx, 38, out_row_data[36]) 
                    
                    time.sleep(2)
                    final_row = sheets["output"].row_values(match_idx)

                    st.success(f"✅ Dados de {cliente_sel} atualizados!")
                    
                    # --- DIAGNÓSTICO ---
                    st.markdown("### 📊 Auditoria de Cheques")
                    cols = st.columns(6)
                    
                    def is_ok(val): return str(val).strip().upper() == "OK"

                    # Proteção de index para evitar erro se a linha for curta
                    def safe_get(lst, idx, default=""): return lst[idx] if idx < len(lst) else default

                    checks = [
                        ("Check 1: FB", safe_get(final_row, 8), ""), 
                        ("Check 1: GL", safe_get(final_row, 9), ""), 
                        ("Check 2 (Mídia)", safe_get(final_row, 12),
