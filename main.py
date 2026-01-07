import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import time

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Gerador de Boletos", layout="wide")

def init_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# FUNÇÃO PARA TRANSFORMAR TEXTO EM NÚMERO QUE A PLANILHA ENTENDE
def limpar_valor(texto):
    if not texto: return 0
    # Remove R$, espaços e pontos de milhar, troca vírgula por ponto
    limpo = str(texto).replace('R$', '').replace('.', '').replace(',', '.').strip()
    try:
        return float(limpo)
    except:
        return 0

def get_clean_data_flexible(worksheet):
    all_values = worksheet.get_all_values()
    header_idx = 0
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
    SPREADSHEET_ID = "1zOof6YDL4U8hYMiFi5zt4V_alYK6EcRvV3QKERvNlhA"
    ss = gc.open_by_key(SPREADSHEET_ID)
    sh_input = ss.worksheet("INPUT - BOLETOS")
    sh_output = ss.worksheet("OUTPUT - BOLETOS")
    sh_comm = ss.worksheet("COMUNICACAO - CLIENTE")
    df_input = get_clean_data_flexible(sh_input)
    df_input = df_input[df_input['Clientes'] != ""].copy()
except Exception as e:
    st.error(f"❌ Erro: {e}")
    st.stop()

# --- INTERFACE ---
st.title("🚀 Operação de Geração de Boletos")

squads = sorted([s for s in df_input['SQUAD'].unique() if s and s not in ["-", ""]])
selected_squad = st.sidebar.selectbox("Escolha sua SQUAD:", squads)

status_permitidos = ["OK", "NÃO INICIOU", "DUPLICADO", "ENCERRAR"]
df_filtered = df_input[(df_input['SQUAD'] == selected_squad) & (df_input['Status'].isin(status_permitidos))]

if df_filtered.empty:
    st.warning("Nenhum cliente disponível.")
else:
    cliente_sel = st.selectbox("Selecione o Cliente:", df_filtered['Clientes'].tolist())
    row_sel = df_filtered[df_filtered['Clientes'] == cliente_sel].iloc[0]
    key_sel = row_sel['Key']

    st.divider()
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🟦 Meta Ads")
        m_metodo = st.selectbox("Método Pagamento", ["Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanha"], key="m_m")
        m_credito = st.text_input("Crédito Atual (Meta)", value="0,00")
        m_data = st.text_input("Data do Saldo (Meta)", placeholder="DD/MM")
        m_valor = st.text_input("Gasto Diário (Meta)", value="0,00")

    with c2:
        st.subheader("🟩 Google Ads")
        g_metodo = st.selectbox("Método Pagamento", ["Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanha"], key="g_m")
        g_credito = st.text_input("Crédito Atual (Google)", value="0,00")
        g_data = st.text_input("Data do Saldo (Google)", placeholder="DD/MM")
        g_valor = st.text_input("Gasto Diário (Google)", value="0,00")

    if st.button("SALVAR E GERAR DIAGNÓSTICO"):
        with st.spinner("Sincronizando..."):
            cell = sh_input.find(str(key_sel), in_column=2)
            r_idx = cell.row
            
            # Limpeza dos valores antes de enviar
            m_c_num = limpar_valor(m_credito)
            m_v_num = limpar_valor(m_valor)
            g_c_num = limpar_valor(g_credito)
            g_v_num = limpar_valor(g_valor)
            
            # Montagem das linhas para atualizar
            # Usamos value_input_option='USER_ENTERED' para que o Google entenda os números
            sh_input.update(f"I{r_idx}:L{r_idx}", [[m_metodo, m_c_num, m_data, m_v_num]], value_input_option='USER_ENTERED')
            sh_input.update(f"M{r_idx}:P{r_idx}", [[g_metodo, g_c_num, g_data, g_v_num]], value_input_option='USER_ENTERED')
            
            time.sleep(3)
            
            # Recarrega Output para mostrar os checks
            df_out_final = get_clean_data_flexible(sh_output)
            out_row = df_out_final[df_out_final['Key'] == key_sel].iloc[0]
            
            df_comm_final = get_clean_data_flexible(sh_comm)
            comm_row = df_comm_final[df_comm_final.iloc[:, 1] == key_sel].iloc[0]

            st.success("✅ Sincronizado!")
            
            # Exibição dos Checks
            res_cols = st.columns(4)
            chks = [
                ("Check 1", out_row.iloc[8]),  # Col I
                ("Check 2", out_row.iloc[12]), # Col M
                ("Check 3", out_row.iloc[15]), # Col P
                ("Check 4", out_row.iloc[19])  # Col T
            ]
            
            for i, (name, val) in enumerate(chks):
                with res_cols[i]:
                    is_ok = "OK" in str(val).upper()
                    st.markdown(f"**{name}**")
                    st.write("✅ OK" if is_ok else f"❌ {val}")

            st.divider()
            st.metric("Total a Emitir", f"R$ {out_row.iloc[24]}")
            st.markdown(f"**Links:** [WhatsApp]({comm_row.iloc[10]}) | [E-mail]({comm_row.iloc[11]})")
