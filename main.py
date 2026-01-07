import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import time
import urllib.parse
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Sistema de Boletos v11", layout="wide")

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

# --- CARREGAMENTO ---
try:
    gc = init_connection()
    SPREADSHEET_ID = "1zOof6YDL4U8hYMiFi5zt4V_alYK6EcRvV3QKERvNlhA"
    ss = gc.open_by_key(SPREADSHEET_ID)
    sh_input = ss.worksheet("INPUT - BOLETOS")
    sh_output = ss.worksheet("OUTPUT - BOLETOS")
    sh_comm = ss.worksheet("COMUNICACAO - CLIENTE")

    vals_in = sh_input.get_all_values()
    df_input = pd.DataFrame(vals_in[4:], columns=vals_in[3])
    df_input = df_input[df_input.iloc[:, 2] != ""].copy()
except Exception as e:
    st.error(f"Erro ao conectar com a planilha: {e}")
    st.stop()

# --- INTERFACE ---
st.title("🏦 Gestor de Boletos e Faturamento")

squad_list = sorted([s for s in df_input.iloc[:, 5].unique() if s and s != "-"] )
selected_squad = st.sidebar.selectbox("Filtro SQUAD", squad_list)

status_ops = ["OK", "NÃO INICIOU", "DUPLICADO", "ENCERRAR"]
df_filtered = df_input[(df_input.iloc[:, 5] == selected_squad) & (df_input.iloc[:, 3].isin(status_ops))]

if df_filtered.empty:
    st.warning(f"Sem clientes disponíveis para {selected_squad}.")
else:
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
                # 1. SALVAR NA INPUT (Colunas I até P)
                cell_in = sh_input.find(key_orig, in_column=2)
                r_in = cell_in.row
                sh_input.update(f"I{r_in}:P{r_in}", [[m_met, limpar_valor_monetario(m_cre), m_dat, limpar_valor_monetario(m_val),
                                                      g_met, limpar_valor_monetario(g_cre), g_dat, limpar_valor_monetario(g_val)]], value_input_option='USER_ENTERED')
                
                time.sleep(4) 

                # 2. GATILHOS NA OUTPUT
                data_out = sh_output.get_all_values()
                match_idx = -1
                for i, r in enumerate(data_out[7:]):
                    if normalizar_id(r[1]) == key_norm:
                        match_idx = i + 8
                        out_row_data = r
                        break

                if match_idx == -1:
                    st.error("❌ Key não encontrada na aba OUTPUT.")
                else:
                    # Copia Y(24) para Z(25) e AK(36) para AL(37)
                    sh_output.update_cell(match_idx, 26, out_row_data[24]) 
                    sh_output.update_cell(match_idx, 38, out_row_data[36]) 
                    
                    time.sleep(2)
                    final_row = sh_output.row_values(match_idx)

                    st.success(f"✅ Dados de {cliente_sel} atualizados!")
                    
                    # --- DIAGNÓSTICO ---
                    st.markdown("### 📊 Auditoria de Cheques")
                    cols = st.columns(6)
                    
                    def is_ok(val): return str(val).strip().upper() == "OK"

                    checks = [
                        ("Check 1: FB", final_row[8], ""), 
                        ("Check 1: GL", final_row[9], ""), 
                        ("Check 2 (Mídia)", final_row[12], f"Acordado: {final_row[10]} | Lançado: {final_row[11]}" if not is_ok(final_row[12]) else ""), 
                        ("Check 3 (Emissão)", final_row[15], f"Acordado: {final_row[13]} | Soma: {final_row[14]}" if not is_ok(final_row[15]) else ""), 
                        ("Check 4 (Meta)", final_row[17], "Saldo não durará até dia 10" if not is_ok(final_row[17]) else ""), 
                        ("Check 4 (Google)", final_row[19], "Saldo não durará até dia 10" if not is_ok(final_row[19]) else "")
                    ]
                    
                    for i, (name, val, diff) in enumerate(checks):
                        ok_status = is_ok(val)
                        cl = "ok-card" if ok_status else "nok-card"
                        with cols[i]:
                            st.markdown(f"""<div class='check-card {cl}'>{name}<br>{val}<div class='val-diff'>{diff}</div></div>""", unsafe_allow_html=True)

                    st.divider()
                    l_c, r_c = st.columns(2)
                    
                    with l_c:
                        st.metric("A Emitir (Meta Ads)", f"R$ {final_row[24]}") 
                        st.metric("A Emitir (Google Ads)", f"R$ {final_row[36]}") 
                        if len(final_row) > 27 and final_row[27]: st.info(f"**Boleto Meta:** {final_row[27]}") 
                        if len(final_row) > 39 and final_row[39]: st.info(f"**Boleto Google:** {final_row[39]}") 

                    # --- BLOCO DE ENVIO COM FÓRMULAS REPLICADAS ---
                    with r_c:
                        st.markdown("**Ações de Envio:**")
                        try:
                            # 1. Busca linha na aba Comunicacao
                            cell_comm = sh_comm.find(key_orig, in_column=2)
                            row_comm_idx = cell_comm.row
                            
                            # 2. Pega dados BRUTOS (sem fórmula)
                            comm_vals = sh_comm.row_values(row_comm_idx, value_render_option='UNFORMATTED_VALUE')
                            while len(comm_vals) < 15: comm_vals.append("")

                            # 3. Mapeamento das Colunas (A=0, B=1, etc.)
                            val_col_c = str(comm_vals[2]).strip()  # Cliente (Nome)
                            val_col_g = str(comm_vals[6]).strip()  # Contato (Nome)
                            val_col_i = str(comm_vals[8]).strip()  # Email Financeiro
                            val_col_j = str(comm_vals[9]).strip()  # Telefone Ajustado (Melhor que H)

                            # ----------------------------------------
                            # LÓGICA DO WHATSAPP (Igual Fórmula)
                            # ----------------------------------------
                            if val_col_j and val_col_j != "-" and val_col_j != "0":
                                # Montagem exata do texto da fórmula
                                texto_wpp = (
                                    f"Olá, {val_col_g}!\n\n"
                                    f"Foram enviados no e-mail {val_col_i}, os boletos das plataformas de anúncios.\n\n"
                                    f"*Observações importantes:*\n"
                                    f"1. Não conseguimos alterar a data de vencimento dos boletos, por isso pedimos que o pagamento seja feito o mais rápido possível.\n"
                                    f"2. *De maneira alguma, realize o pagamento de boletos vencidos, sob pena de perder o valor adicionado indefinidamente.*\n\n"
                                    f"Qualquer dúvida, estou à disposição!"
                                )
                                msg_encoded = urllib.parse.quote(texto_wpp)
                                link_wpp = f"https://wa.me/{val_col_j}?text={msg_encoded}"
                                
                                st.link_button(f"📲 Enviar WhatsApp ({val_col_g})", link_wpp)
                            else:
                                st.warning("⚠️ Telefone não cadastrado (Col J).")

                            # ----------------------------------------
                            # LÓGICA DO GMAIL (Igual Fórmula)
                            # ----------------------------------------
                            if val_col_i and "@" in val_col_i:
                                # Variáveis de data para o Assunto
                                agora = datetime.now()
                                data_ref = agora.strftime("%m - %Y") # Ex: 01 - 2025
                                
                                # Montagem do Assunto e Corpo
                                assunto = f"Boleto Anúncios - {val_col_c} | Ref. {data_ref}"
                                corpo_email = (
                                    f"Olá,\n\n"
                                    f"Envio anexos os boletos referentes às plataformas de mídia paga.\n\n"
                                    f"Observações importantes:\n\n"
                                    f"1. Não é possível editar a data de vencimento do boleto gerado na plataforma e, por isto, pedimos para que o pagamento seja feito o mais rápido possível.\n"
                                    f"2. De maneira alguma, realize o pagamento de boletos vencidos, sob pena de perder o valor adicionado indefinidamente.\n\n"
                                    f"Ficamos à disposição para quaisquer esclarecimentos.\n\n"
                                    f"Obrigada!\n\n"
                                    f"Atenciosamente,"
                                )
                                
                                # Codificação para URL
                                params = {
                                    "view": "cm",
                                    "fs": "1",
                                    "to": val_col_i,
                                    "cc": "financeiro@comodoplanejados.com.br",
                                    "su": assunto,
                                    "body": corpo_email
                                }
                                # Cria a Query String corretamente
                                query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote) 
                                link_gmail = f"https://mail.google.com/mail/?{query_string}"
                                
                                st.link_button(f"📧 Abrir no Gmail ({val_col_i})", link_gmail)
                            else:
                                st.warning("⚠️ E-mail não cadastrado (Col I).")

                        except Exception as e:
                            st.error(f"Erro na geração dos links: {e}")

            except Exception as e:
                st.error(f"Erro no processamento geral: {e}")
