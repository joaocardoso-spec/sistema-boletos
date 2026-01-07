import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import time

# Configuração visual
st.set_page_config(page_title="Gerador de Boletos", layout="wide")

# Estilo Dark Mode
st.markdown("""
    <style>
    .main { background-color: #0b0e14; color: #ffffff; }
    .stButton>button { background-color: #238636; color: white; width: 100%; font-weight: bold; }
    .card-nok { background-color: #2d1a1e; border-left: 5px solid #ff4b4b; padding: 15px; border-radius: 5px; margin-bottom: 10px; }
    .card-ok { background-color: #1a2d1f; border-left: 5px solid #238636; padding: 15px; border-radius: 5px; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

def init_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

try:
    gc = init_connection()
    
    # --- ALTERAÇÃO AQUI: USANDO O ID DA PLANILHA ---
    SPREADSHEET_ID = "1zOof6YDL4U8hYMiFi5zt4V_alYK6EcRvV3QKERvNlhA" 
    ss = gc.open_by_key(SPREADSHEET_ID)
    
    # Acessando as abas
    sh_input = ss.worksheet("INPUT - BOLETOS")
    sh_output = ss.worksheet("OUTPUT - BOLETOS")
    sh_comm = ss.worksheet("COMUNICACAO - CLIENTE")
    
except Exception as e:
    st.error(f"Erro ao tentar abrir a planilha ou abas: {e}")
    st.info("DICA: Verifique se o e-mail da conta de serviço ainda está como 'Editor' na planilha.")
    st.stop()

# Carregar dados
try:
    df_input = pd.DataFrame(sh_input.get_all_records())
except Exception as e:
    st.error(f"Erro ao ler os dados da aba INPUT: {e}")
    st.stop()

# Filtros
squads = sorted([s for s in df_input['SQUAD'].unique() if s and s != '-'])
selected_squad = st.sidebar.selectbox("Filtrar por SQUAD:", squads)

status_permitidos = ["OK", "NÃO INICIOU", "DUPLICADO", "ENCERRAR"]
df_filtered = df_input[(df_input['SQUAD'] == selected_squad) & (df_input['Status'].isin(status_permitidos))]
df_filtered = df_filtered.sort_values(by='Key')

st.title(f"🚀 Operação: {selected_squad}")

if df_filtered.empty:
    st.info("Nenhum cliente operacional encontrado para esta SQUAD.")
else:
    lista_clientes = df_filtered['Clientes'].tolist()
    cliente_selecionado = st.selectbox("Selecione o Cliente:", lista_clientes)
    
    dados_c = df_filtered[df_filtered['Clientes'] == cliente_selecionado].iloc[0]
    id_cliente = dados_c['Key']

    st.markdown("---")
    
    # Interface de Input
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🟦 Meta Ads")
        m_metodo = st.selectbox("Método Pag. Meta", ["Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanhas"])
        m_credito = st.number_input("Crédito Atual Meta (R$)", value=0.0)
        m_data = st.text_input("Data do Saldo Meta", placeholder="DD/MM")
        m_valor = st.number_input("Valor Campanhas Dia Meta (R$)", value=0.0)

    with c2:
        st.subheader("🟩 Google Ads")
        g_metodo = st.selectbox("Método Pag. Google", ["Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanhas"])
        g_credito = st.number_input("Crédito Atual Google (R$)", value=0.0)
        g_data = st.text_input("Data do Saldo Google", placeholder="DD/MM")
        g_valor = st.number_input("Valor Campanhas Dia Google (R$)", value=0.0)

    if st.button("SALVAR E VERIFICAR"):
        with st.spinner("Sincronizando..."):
            cell = sh_input.find(str(id_cliente), in_column=2)
            row = cell.row
            valores = [[m_metodo, m_credito, m_data, m_valor, g_metodo, g_credito, g_data, g_valor]]
            sh_input.update(f"J{row}:Q{row}", valores)
            
            time.sleep(2)
            
            # Puxar diagnósticos
            out_all = pd.DataFrame(sh_output.get_all_records())
            out_c = out_all[out_all['Key'] == id_cliente].iloc[0]
            comm_all = pd.DataFrame(sh_comm.get_all_records())
            comm_c = comm_all[comm_all['ID'] == id_cliente].iloc[0]

            st.markdown("### 📊 Resultado")
            res_cols = st.columns(4)
            checks = [("Check 1", "CHECK 1"), ("Check 2", "CHECK 2"), ("Check 3", "CHECK 3"), ("Check 4", "CHECK 4")]
            
            for i, (label, col_name) in enumerate(checks):
                status = str(out_c.get(col_name, "NOK")).upper()
                with res_cols[i]:
                    if status == "OK": st.success(f"{label}: OK")
                    else: st.error(f"{label}: NOK")

            st.divider()
            st.metric("Valor a Emitir", f"R$ {out_c.get('Valor a Emitir', '0,00')}")
            st.markdown(f"**WhatsApp:** [Enviar]({comm_c.get('Envio Whatsapp', '#')}) | **E-mail:** [Enviar]({comm_c.get('Envio E-mail', '#')})")
