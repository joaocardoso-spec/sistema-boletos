import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import time

# --- CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="Gerador de Boletos v7", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0b0e14; color: #ffffff; }
    .stButton>button { background-color: #238636; color: white; width: 100%; font-weight: bold; height: 3.5em; border: none; }
    .check-card { padding: 12px; border-radius: 8px; margin-bottom: 8px; font-weight: bold; text-align: center; font-size: 0.9em; }
    .ok-card { background-color: #1a2d1f; border: 1px solid #238636; color: #73d13d; }
    .nok-card { background-color: #2d1a1e; border: 1px solid #ff4b4b; color: #ff4b4b; }
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
    if not texto: return 0
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

    # Input: Cabeçalho na Linha 4 (Índice 3)
    vals_in = sh_input.get_all_values()
    df_input = pd.DataFrame(vals_in[4:], columns=vals_in[3])
    df_input = df_input[df_input.iloc[:, 2] != ""].copy()
except Exception as e:
    st.error(f"Erro ao conectar com as abas: {e}")
    st.stop()

# --- INTERFACE ---
st.title("🏦 Gestão de Faturamento e Boletos")

# Filtro de SQUAD (Coluna F - Índice 5)
squad_list = sorted([s for s in df_input.iloc[:, 5].unique() if s and s != "-"] )
selected_squad = st.sidebar.selectbox("Selecione sua SQUAD", squad_list)

status_ops = ["OK", "NÃO INICIOU", "DUPLICADO", "ENCERRAR"]
df_filtered = df_input[(df_input.iloc[:, 5] == selected_squad) & (df_input.iloc[:, 3].isin(status_ops))]

if df_filtered.empty:
    st.warning(f"Nenhum cliente disponível para a SQUAD {selected_squad}.")
else:
    cliente_sel = st.selectbox("Escolha o Cliente:", df_filtered.iloc[:, 2].tolist())
    row_sel = df_filtered[df_filtered.iloc[:, 2] == cliente_sel].iloc[0]
    
    key_original = str(row_sel.iloc[1]).strip()
    key_normalizada = normalizar_id(key_original)

    st.divider()
    st.markdown("#### ✍️ Lançamento de Dados")
    st.info("💡 Use **TAB** para navegar. O sistema só salva ao clicar no botão abaixo.")
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🟦 Meta Ads")
        m_metodo = st.selectbox("Método Pagamento", ["Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanha"], key="met1")
        m_credito = st.text_input("Crédito Atual Meta", placeholder="Ex: 1.500,00", key="met2")
        m_data = st.text_input("Data do Saldo Meta", placeholder="DD/MM", key="met3")
        m_valor = st.text_input("Gasto Diário Meta", placeholder="Ex: 50,00", key="met4")
    with c2:
        st.subheader("🟩 Google Ads")
        g_metodo = st.selectbox("Método Pagamento", ["Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanha"], key="goo1")
        g_credito = st.text_input("Crédito Atual Google", placeholder="Ex: 1.500,00", key="goo2")
        g_data = st.text_input("Data do Saldo Google", placeholder="DD/MM", key="goo3")
        g_valor = st.text_input("Gasto Diário Google", placeholder="Ex: 50,00", key="goo4")

    if st.button("🚀 SALVAR DADOS E VERIFICAR CHEQUES"):
        with st.spinner("Atualizando planilha..."):
            try:
                cell = sh_input.find(key_original, in_column=2)
                r_idx = cell.row
                
                vals = [[m_metodo, limpar_valor_monetario(m_credito), m_data, limpar_valor_monetario(m_valor),
                         g_metodo, limpar_valor_monetario(g_credito), g_data, limpar_valor_monetario(g_valor)]]
                
                # Atualiza I a P (Índices 9 a 16)
                sh_input.update(f"I{r_idx}:P{r_idx}", vals, value_input_option='USER_ENTERED')
                
                time.sleep(4) 

                # --- BUSCA NO OUTPUT (Cabeçalho na Linha 7) ---
                data_out = sh_output.get_all_values()
                df_out = pd.DataFrame(data_out[7:], columns=data_out[6])
                df_out.iloc[:, 1] = df_out.iloc[:, 1].apply(normalizar_id)
                res_out = df_out[df_out.iloc[:, 1] == key_normalizada]

                # --- BUSCA NA COMUNICAÇÃO (Cabeçalho na Linha 4) ---
                data_comm = sh_comm.get_all_values()
                df_comm = pd.DataFrame(data_comm[4:], columns=data_comm[3])
                df_comm.iloc[:, 0] = df_comm.iloc[:, 0].apply(normalizar_id)
                res_comm = df_comm[df_comm.iloc[:, 0] == key_normalizada]

                if res_out.empty:
                    st.error(f"❌ ID '{key_original}' não encontrado na aba OUTPUT.")
                else:
                    out_row = res_out.iloc[0]
                    st.success(f"✅ Dados de {cliente_sel} salvos!")
                    
                    # --- DIAGNÓSTICO (Colunas M, P, R, T) ---
                    st.markdown("### 📊 Verificação de Cheques")
                    cols = st.columns(4)
                    checks = [
                        ("Check 2: Mídia", out_row.iloc[12]), # Col M
                        ("Check 3: Emissão", out_row.iloc[15]), # Col P
                        ("Check 4: Meta", out_row.iloc[17]), # Col R
                        ("Check 4: Google", out_row.iloc[19])  # Col T
                    ]
                    for i, (name, val) in enumerate(checks):
                        is_ok = "OK" in str(val).upper()
                        cl = "ok-card" if is_ok else "nok-card"
                        with cols[i]:
                            st.markdown(f"<div class='check-card {cl}'>{name}<br>{val}</div>", unsafe_allow_html=True)

                    st.divider()
                    v1, v2 = st.columns([1, 2])
                    with v1:
                        st.metric("Total a Emitir", f"R$ {out_row.iloc[24]}") # Col Y
                        nome_bol = str(out_row.iloc[27]).strip() # Col AB
                        if nome_bol: st.info(f"**Título:** {nome_bol}")
                    
                    with v2:
                        st.markdown("**Ações de Envio:**")
                        # Se não houver dados de comunicação, avisa em vez de quebrar
                        if not res_comm.empty:
                            comm_row = res_comm.iloc[0]
                            wpp = str(comm_row.iloc[10]).strip() # Col K
                            mail = str(comm_row.iloc[11]).strip() # Col L
                            if wpp.startswith("http"): st.link_button("📲 WhatsApp", wpp)
                            else: st.warning("⚠️ Link de WhatsApp não cadastrado.")
                            if mail.startswith("http"): st.link_button("📧 E-mail", mail)
                            else: st.warning("⚠️ Link de E-mail não cadastrado.")
                        else:
                            st.warning("ℹ️ Este cliente não possui dados na aba de Comunicação.")

            except Exception as e:
                st.error(f"Ocorreu um problema ao processar: {e}")
