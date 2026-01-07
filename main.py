import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import time

# --- CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="Gerador de Boletos v4", layout="wide")

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

def limpar_valor_para_envio(texto):
    if not texto or texto == "": return 0
    # Limpa R$, pontos e troca vírgula por ponto para o Google entender como número
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
    
    # Carregamento bruto para evitar erros de cabeçalho
    data_input = sh_input.get_all_values()
    df_input = pd.DataFrame(data_input[7:], columns=[str(h).strip() for h in data_input[6]])
    df_input = df_input[df_input['Clientes'] != ""].copy()
except Exception as e:
    st.error(f"Erro de Conexão: {e}")
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

    st.divider()
    
    # --- ÁREA DE INPUT (SEM FORM PARA CONTROLAR O ENTER) ---
    st.markdown("#### 📝 Entrada de Dados")
    st.caption("Use a tecla **TAB** para navegar entre os campos. O Enter não salvará automaticamente.")
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🟦 Meta Ads")
        m_metodo = st.selectbox("Método Pagamento Meta", ["Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanha"], key="m_met")
        m_credito = st.text_input("Crédito Atual Meta", placeholder="Ex: 1.500,00", key="m_cre")
        m_data = st.text_input("Data do Saldo Meta", placeholder="DD/MM", key="m_dat")
        m_valor = st.text_input("Gasto Diário Meta", placeholder="Ex: 60,00", key="m_val")

    with c2:
        st.subheader("🟩 Google Ads")
        g_metodo = st.selectbox("Método Pagamento Google", ["Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanha"], key="g_met")
        g_credito = st.text_input("Crédito Atual Google", placeholder="Ex: 2.000,00", key="g_cre")
        g_data = st.text_input("Data do Saldo Google", placeholder="DD/MM", key="g_dat")
        g_valor = st.text_input("Gasto Diário Google", placeholder="Ex: 100,00", key="g_val")
    
    st.markdown("---")
    if st.button("💾 SALVAR DADOS E ATUALIZAR DIAGNÓSTICO"):
        with st.spinner("Sincronizando..."):
            # Achar linha pela Key (Coluna B)
            cell = sh_input.find(key_sel, in_column=2)
            r_idx = cell.row
            
            # Limpeza de números
            m_c = limpar_valor_para_envio(m_credito)
            m_v = limpar_valor_para_envio(m_valor)
            g_c = limpar_valor_para_envio(g_credito)
            g_v = limpar_valor_para_envio(g_valor)
            
            # Update na INPUT: Colunas I até P
            # I=Método Meta, J=Crédito Meta, K=Data Meta, L=Valor Meta, M=Método Google, N=Crédito Google, O=Data Google, P=Valor Google
            sh_input.update(f"I{r_idx}:P{r_idx}", [[m_metodo, m_c, m_data, m_v, g_metodo, g_c, g_data, g_v]], value_input_option='USER_ENTERED')
            
            time.sleep(4) # Tempo para o Sheets calcular os Checks
            
            # Puxar diagnósticos atualizados
            raw_out = sh_output.get_all_values()
            df_out = pd.DataFrame(raw_out[7:], columns=[str(h).strip() for h in raw_out[6]])
            out_row = df_out[df_out['Key'].astype(str).str.strip() == key_sel].iloc[0]
            
            raw_comm = sh_comm.get_all_values()
            df_comm = pd.DataFrame(raw_comm[4:], columns=[str(h).strip() for h in raw_comm[3]]) # Comunicação começa na linha 4
            comm_row = df_comm[df_comm.iloc[:, 0].astype(str).str.strip() == key_sel].iloc[0] # Coluna A como ID

            st.success(f"✅ Dados de {cliente_sel} atualizados!")
            
            # --- ÁREA DE DIAGNÓSTICO BASEADA NO SEU MAPEAMENTO ---
            st.markdown("### 📊 Verificação de Cheques")
            res_cols = st.columns(5)
            
            # Mapeamento conforme sua descrição:
            # Check 1: Col I e J | Check 2: Col M | Check 3: Col P | Check 4: Col R (FB) e T (GL)
            # Índices (0-based): I=8, J=9, M=12, P=15, R=17, T=19
            
            checks = [
                ("Check 1 (FB/GL)", f"{out_row.iloc[8]} / {out_row.iloc[9]}"),
                ("Check 2 (Mídia)", out_row.iloc[12]),
                ("Check 3 (Emissão)", out_row.iloc[15]),
                ("Check 4 (Saldo FB)", out_row.iloc[17]),
                ("Check 4 (Saldo GL)", out_row.iloc[19])
            ]
            
            for i, (name, val) in enumerate(checks):
                is_ok = "OK" in str(val).upper()
                card_class = "ok-card" if is_ok else "nok-card"
                with res_cols[i]:
                    st.markdown(f"<div class='check-card {card_class}'>{name}<br>{val}</div>", unsafe_allow_html=True)

            # --- AÇÕES E LINKS ---
            st.divider()
            v1, v2 = st.columns([1, 2])
            with v1:
                st.metric("Total a Emitir", f"R$ {out_row.iloc[24]}") # Coluna Y
                st.info(f"**Título:** {out_row.iloc[28]}") # Coluna AC
            
            with v2:
                st.markdown("**Ações Disponíveis:**")
                wpp = str(comm_row.iloc[10]).strip() # Coluna K
                mail = str(comm_row.iloc[11]).strip() # Coluna L
                
                if wpp.startswith("http"):
                    st.link_button("📲 Enviar via WhatsApp", wpp)
                else:
                    st.warning("⚠️ Link de WhatsApp não disponível.")
                    
                if mail.startswith("http"):
                    st.link_button("📧 Enviar via E-mail", mail)
                else:
                    st.warning("⚠️ Link de E-mail não disponível.")
