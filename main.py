import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import time

# --- CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="Gestor de Boletos v11", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0b0e14; color: #ffffff; }
    .stButton>button { background-color: #238636; color: white; width: 100%; font-weight: bold; height: 3.5em; border: none; }
    .check-card { padding: 12px; border-radius: 8px; margin-bottom: 8px; font-weight: bold; text-align: center; font-size: 0.85em; min-height: 110px; display: flex; flex-direction: column; justify-content: center; }
    .ok-card { background-color: #1a2d1f; border: 1px solid #238636; color: #73d13d; }
    .nok-card { background-color: #2d1a1e; border: 1px solid #ff4b4b; color: #ff4b4b; }
    .val-diff { font-size: 0.8em; color: #cccccc; margin-top: 4px; font-weight: normal; }
    </style>
    """, unsafe_allow_html=True)

def init_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def normalizar_id(valor):
    return str(valor).replace(',', '.').strip()

def limpar_valor_monetario(texto):
    if not texto or texto == "": return 0
    limpo = str(texto).replace('R$', '').replace('.', '').replace(',', '.').strip()
    try: return float(limpo)
    except: return 0

# --- CONEXÃO ---
try:
    gc = init_connection()
    SPREADSHEET_ID = "1zOof6YDL4U8hYMiFi5zt4V_alYK6EcRvV3QKERvNlhA"
    ss = gc.open_by_key(SPREADSHEET_ID)
    sh_input = ss.worksheet("INPUT - BOLETOS")
    sh_output = ss.worksheet("OUTPUT - BOLETOS")
    sh_comm = ss.worksheet("COMUNICACAO - CLIENTE")

    # INPUT: Cabeçalhos na Linha 4 (Index 3), Dados na Linha 5
    vals_in = sh_input.get_all_values()
    df_input = pd.DataFrame(vals_in[4:], columns=vals_in[3])
    df_input = df_input[df_input.iloc[:, 2] != ""].copy()
except Exception as e:
    st.error(f"Erro ao conectar: {e}")
    st.stop()

# --- INTERFACE ---
st.title("🏦 Gestor de Faturamento e Boletos")

# Filtro Squad (Coluna F - Index 5)
squad_list = sorted([s for s in df_input.iloc[:, 5].unique() if s and s != "-"] )
selected_squad = st.sidebar.selectbox("Filtro SQUAD", squad_list)

status_ops = ["OK", "NÃO INICIOU", "DUPLICADO", "ENCERRAR"]
df_filtered = df_input[(df_input.iloc[:, 5] == selected_squad) & (df_input.iloc[:, 3].isin(status_ops))]

if df_filtered.empty:
    st.warning(f"Nenhum cliente disponível para a SQUAD {selected_squad}.")
else:
    cliente_sel = st.selectbox("Escolha o Cliente:", df_filtered.iloc[:, 2].tolist())
    row_sel = df_filtered[df_filtered.iloc[:, 2] == cliente_sel].iloc[0]
    key_orig = str(row_sel.iloc[1]).strip()
    key_norm = normalizar_id(key_orig)
