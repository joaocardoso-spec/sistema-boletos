import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import time

st.set_page_config(page_title="Gerador de Boletos", layout="wide")

# Estilo Dark Mode
st.markdown("""
    <style>
    .main { background-color: #0b0e14; color: #ffffff; }
    .stButton>button { background-color: #238636; color: white; width: 100%; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

def init_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

try:
    gc = init_connection()
    
    # --- COLOQUE O ID DA SUA PLANILHA AQUI ---
    # O ID é a parte entre /d/ e /edit na URL da sua planilha
    SPREADSHEET_ID = "COLE_AQUI_O_ID_DA_SUA_PLANILHA" 
    
    ss = gc.open_by_key(1zOof6YDL4U8hYMiFi5zt4V_alYK6EcRvV3QKERvNlhA)
    
    # Acessando as abas
    sh_input = ss.worksheet("INPUT - BOLETOS")
    sh_output = ss.worksheet("OUTPUT - BOLETOS")
    sh_comm = ss.worksheet("COMUNICACAO - CLIENTE")
    
except Exception as e:
    st.error(f"❌ ERRO DE CONEXÃO: {repr(e)}")
    st.info("Verifique se o ID da planilha está correto e se o e-mail do serviço foi compartilhado como EDITOR.")
    st.stop()

# --- FUNÇÃO PARA LER DADOS A PARTIR DA LINHA 7 ---
def get_data_from_row_7(worksheet):
    # Puxa todos os valores da aba
    all_values = worksheet.get_all_values()
    # A linha 7 é o índice 6 (porque começa em 0)
    headers = all_values[6] 
    data = all_values[7:]
    return pd.DataFrame(data, columns=headers)

try:
    df_input = get_data_from_row_7(sh_input)
    # Remove linhas onde a Key está vazia
    df_input = df_input[df_input['Key'] != ""]
except Exception as e:
    st.error(f"❌ ERRO AO LER ABAS: {repr(e)}")
    st.write("DICA: Verifique se os nomes das abas estão idênticos na planilha e no código.")
    st.stop()

# --- INTERFACE ---
st.title("🚀 Sistema Operacional de Boletos")

squads = sorted([s for s in df_input['SQUAD'].unique() if s and s != '-' and s != ""])
selected_squad = st.sidebar.selectbox("Filtrar por SQUAD:", squads)

status_permitidos = ["OK", "NÃO INICIOU", "DUPLICADO", "ENCERRAR"]
df_filtered = df_input[(df_input['SQUAD'] == selected_squad) & (df_input['Status'].isin(status_permitidos))]

if df_filtered.empty:
    st.warning(f"Nenhum cliente ativo encontrado para a SQUAD: {selected_squad}")
else:
    cliente_selecionado = st.selectbox("Selecione o Cliente:", df_filtered['Clientes'].tolist())
    dados_c = df_filtered[df_filtered['Clientes'] == cliente_selecionado].iloc[0]
    id_cliente = dados_c['Key']

    st.divider()
    
    # Inputs (Meta e Google)
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🟦 Meta Ads")
        m_metodo = st.selectbox("Método Pag. Meta", ["Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanhas"])
        m_credito = st.text_input("Crédito Atual Meta", value="0,00")
        m_data = st.text_input("Data do Saldo Meta", placeholder="DD/MM")
        m_valor = st.text_input("Gasto Diário Meta", value="0,00")

    with c2:
        st.subheader("🟩 Google Ads")
        g_metodo = st.selectbox("Método Pag. Google", ["Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanhas"])
        g_credito = st.text_input("Crédito Atual Google", value="0,00")
        g_data = st.text_input("Data do Saldo Google", placeholder="DD/MM")
        g_valor = st.text_input("Gasto Diário Google", value="0,00")

    if st.button("SALVAR E PROCESSAR"):
        with st.spinner("Sincronizando..."):
            # Localiza a linha correta pela Key (Coluna B)
            cell = sh_input.find(str(id_cliente), in_column=2)
            row_idx = cell.row
            
            # Atualiza colunas J até Q (Método até Valor Google)
            valores = [[m_metodo, m_credito, m_data, m_valor, g_metodo, g_credito, g_data, g_valor]]
            sh_input.update(f"J{row_idx}:Q{row_idx}", valores)
            
            time.sleep(3) # Tempo para a planilha calcular
            
            # Puxa diagnósticos do OUTPUT e COMUNICACAO
            df_out = get_data_from_row_7(sh_output)
            out_c = df_out[df_out['Key'] == id_cliente].iloc[0]
            
            df_comm = get_data_from_row_7(sh_comm)
            # Na aba de comunicação o título da coluna de ID parece ser 'ID' em vez de 'Key'
            id_col_comm = 'ID' if 'ID' in df_comm.columns else 'Key'
            comm_c = df_comm[df_comm[id_col_comm] == id_cliente].iloc[0]

            st.success("✅ Dados atualizados!")
            
            # Exibição dos Checks
            st.markdown("### 📊 Diagnóstico")
            res_cols = st.columns(4)
            for i, chk in enumerate(["CHECK 1", "CHECK 2", "CHECK 3", "CHECK 4"]):
                status = str(out_c.get(chk, "NOK")).upper()
                with res_cols[i]:
                    if "OK" in status and "NOK" not in status:
                        st.success(f"{chk}: OK")
                    else:
                        st.error(f"{chk}: NOK")

            st.divider()
            st.metric("Valor a Emitir Total", f"R$ {out_c.get('Valor a Emitir', '0,00')}")
            
            # Links de Ação
            st.markdown(f"**WhatsApp:** [Enviar Agora]({comm_c.get('Envio Whatsapp', '#')})")
            st.markdown(f"**E-mail:** [Enviar Agora]({comm_c.get('Envio E-mail', '#')})")
