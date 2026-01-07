import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import time

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Sistema de Boletos v3", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0b0e14; color: #ffffff; }
    .stButton>button { background-color: #238636; color: white; width: 100%; font-weight: bold; border: none; height: 3.5em; }
    .check-card { padding: 15px; border-radius: 8px; margin-bottom: 10px; font-weight: bold; text-align: center; }
    .ok-card { background-color: #1a2d1f; border: 1px solid #238636; color: #73d13d; }
    .nok-card { background-color: #2d1a1e; border: 1px solid #ff4b4b; color: #ff4b4b; }
    .warning-text { color: #ffa500; font-style: italic; }
    </style>
    """, unsafe_allow_html=True)

def init_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def limpar_valor(texto):
    if not texto or texto == "": return 0
    limpo = str(texto).replace('R$', '').replace('.', '').replace(',', '.').strip()
    try: return float(limpo)
    except: return 0

def get_df_flexible(worksheet):
    all_values = worksheet.get_all_values()
    header_idx = 0
    # Procura a linha com os títulos (Key ou ID)
    for i, row in enumerate(all_values):
        row_clean = [str(c).strip().lower() for c in row]
        if 'key' in row_clean or 'id' in row_clean:
            header_idx = i
            break
    headers = [str(h).strip() for h in all_values[header_idx]]
    data = all_values[header_idx + 1:]
    df = pd.DataFrame(data, columns=headers)
    df = df.loc[:, df.columns != ''] # Remove colunas fantasmas
    return df

# --- CONEXÃO INICIAL ---
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
    st.error(f"Erro Crítico de Conexão: {e}")
    st.stop()

# --- INTERFACE ---
st.title("🚀 Gerador de Boletos Operacional")

squads = sorted([s for s in df_input['SQUAD'].unique() if s and s not in ["-", ""]])
selected_squad = st.sidebar.selectbox("Escolha sua SQUAD:", squads)

status_permitidos = ["OK", "NÃO INICIOU", "DUPLICADO", "ENCERRAR"]
df_filtered = df_input[(df_input['SQUAD'] == selected_squad) & (df_input['Status'].isin(status_permitidos))]

if df_filtered.empty:
    st.warning("Nenhum cliente disponível para esta SQUAD com os status operacionais.")
else:
    cliente_sel = st.selectbox("Selecione o Cliente:", df_filtered['Clientes'].tolist())
    row_sel = df_filtered[df_filtered['Clientes'] == cliente_sel].iloc[0]
    key_sel = str(row_sel['Key']).strip()

    st.markdown("---")
    
    # --- ÁREA DE PREENCHIMENTO ---
    st.markdown("#### 📝 Entrada de Dados")
    st.info("💡 Use a tecla **TAB** para pular entre os campos. O sistema só salva ao clicar no botão final.")
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🟦 Meta Ads")
        m_metodo = st.selectbox("Método Pagamento", ["Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanha"], key="m1")
        m_credito = st.text_input("Crédito Atual (Meta)", placeholder="0.000,00", key="m2")
        m_data = st.text_input("Data do Saldo (Meta)", placeholder="DD/MM", key="m3")
        m_valor = st.text_input("Gasto Diário (Meta)", placeholder="00,00", key="m4")

    with c2:
        st.subheader("🟩 Google Ads")
        g_metodo = st.selectbox("Método Pagamento", ["Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanha"], key="g1")
        g_credito = st.text_input("Crédito Atual (Google)", placeholder="0.000,00", key="g2")
        g_data = st.text_input("Data do Saldo (Google)", placeholder="DD/MM", key="g3")
        g_valor = st.text_input("Gasto Diário (Google)", placeholder="00,00", key="g4")
    
    # Botão de Salvar fora de Form para evitar o comportamento padrão do Enter
    if st.button("💾 SALVAR DADOS E GERAR DIAGNÓSTICO"):
        with st.spinner("Sincronizando com a planilha..."):
            try:
                # Localização da linha
                cell = sh_input.find(key_sel, in_column=2)
                r_idx = cell.row
                
                # Conversão e Limpeza
                m_c_num = limpar_valor(m_credito)
                m_v_num = limpar_valor(m_valor)
                g_c_num = limpar_valor(g_credito)
                g_v_num = limpar_valor(g_valor)
                
                # Envio para Planilha (Colunas I a P)
                sh_input.update(f"I{r_idx}:P{r_idx}", [[m_metodo, m_c_num, m_data, m_v_num, g_metodo, g_c_num, g_data, g_v_num]], value_input_option='USER_ENTERED')
                
                time.sleep(4) # Espera o Sheets processar
                
                # --- BUSCA SEGURA DE RESULTADOS ---
                df_out_final = get_df_flexible(sh_output)
                out_row_search = df_out_final[df_out_final['Key'].astype(str).str.strip() == key_sel]
                
                df_comm_final = get_df_flexible(sh_comm)
                # Verifica se a coluna é ID ou Key
                col_id = 'ID' if 'ID' in df_comm_final.columns else 'Key'
                comm_row_search = df_comm_final[df_comm_final[col_id].astype(str).str.strip() == key_sel]

                if out_row_search.empty:
                    st.error("❌ Cliente não encontrado na aba de OUTPUT. Verifique o ID na planilha.")
                else:
                    out_row = out_row_search.iloc[0]
                    st.success("✅ Dados Sincronizados!")
                    
                    # --- DIAGNÓSTICO ---
                    st.markdown("### 📊 Verificação de Cheques")
                    res_cols = st.columns(4)
                    checks_list = [
                        ("Check 1", out_row.get('Preench. FB', 'NOK')),
                        ("Check 2", out_row.get('Valor Mídia', 'NOK')),
                        ("Check 3", out_row.get('Valor a Emitir', 'NOK')),
                        ("Check 4", out_row.get('Saldo até dia 10', 'NOK'))
                    ]
                    
                    for i, (name, val) in enumerate(checks_list):
                        is_ok = "OK" in str(val).upper()
                        card_class = "ok-card" if is_ok else "nok-card"
                        with res_cols[i]:
                            st.markdown(f"<div class='check-card {card_class}'>{name}<br>{'✅ OK' if is_ok else '❌ ' + str(val)}</div>", unsafe_allow_html=True)

                    st.divider()
                    v1, v2 = st.columns([1, 2])
                    with v1:
                        st.metric("Total a Emitir", f"R$ {out_row.get('Valor a Emitir', '0,00')}")
                        st.info(f"**Título:** {out_row.get('Nome Boleto/PIX', '...')}")
                    
                    with v2:
                        st.markdown("**Ações de Envio:**")
                        if not comm_row_search.empty:
                            comm_row = comm_row_search.iloc[0]
                            wpp = str(comm_row.get('Envio Whatsapp', '')).strip()
                            mail = str(comm_row.get('Envio E-mail', '')).strip()
                            
                            if wpp and wpp != "#" and wpp != "":
                                st.link_button("📲 Enviar via WhatsApp", wpp)
                            else:
                                st.warning("⚠️ Link de WhatsApp não encontrado para este cliente.")
                                
                            if mail and mail != "#" and mail != "":
                                st.link_button("📧 Enviar via E-mail", mail)
                            else:
                                st.warning("⚠️ Link de E-mail não encontrado para este cliente.")
                        else:
                            st.error("❌ Dados de comunicação não encontrados para este ID na aba de COMUNICACAO.")

            except Exception as error:
                st.error(f"Erro ao processar diagnóstico: {error}")
