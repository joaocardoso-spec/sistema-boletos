import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import time
import urllib.parse
from datetime import datetime

# --- CONFIGURAÇÃO GLOBAL ---
st.set_page_config(page_title="Sistema de Boletos v3.2", layout="wide")

# CSS OTIMIZADO
st.markdown("""
    <style>
    .main { background-color: #0b0e14; color: #ffffff; }
    .stButton>button { background-color: #238636; color: white; width: 100%; font-weight: bold; height: 3.5em; border: none; }
    
    /* CSS DOS CARDS DE RESULTADO EM MASSA */
    .mass-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 20px;
    }
    .mass-title {
        font-size: 1.1em;
        font-weight: bold;
        color: white;
        margin-bottom: 10px;
        border-bottom: 1px solid #30363d;
        padding-bottom: 5px;
    }
    .mass-checks-grid {
        display: grid;
        grid-template-columns: repeat(6, 1fr);
        gap: 5px;
        margin-bottom: 15px;
    }
    .mass-check-box {
        padding: 8px;
        border-radius: 4px;
        text-align: center;
        font-size: 0.75em;
        font-weight: bold;
        color: white;
        display: flex;
        flex-direction: column;
        justify-content: center;
        min-height: 50px;
    }
    .check-ok { background-color: #1a7f37; border: 1px solid #2ea043; }
    .check-nok { background-color: #a40e26; border: 1px solid #ff4b4b; }
    
    .mass-values {
        display: flex;
        justify-content: space-between;
        margin-bottom: 15px;
        background-color: #0d1117;
        padding: 10px;
        border-radius: 6px;
    }
    .mass-val-col { width: 48%; text-align: center; }
    .mass-label { color: #8b949e; font-size: 0.8em; }
    .mass-money { color: #3fb950; font-size: 1.2em; font-weight: bold; margin: 5px 0; }
    .mass-boleto { font-size: 0.7em; background-color: #1f6feb; padding: 3px; border-radius: 3px; color: white;}
    
    /* CSS DA ABA INDIVIDUAL (LEGADO) */
    .check-card { padding: 12px; border-radius: 8px; margin-bottom: 8px; font-weight: bold; text-align: center; font-size: 0.85em; min-height: 100px; display: flex; flex-direction: column; justify-content: center; }
    .ok-card { background-color: #1a2d1f; border: 1px solid #238636; color: #73d13d; }
    .nok-card { background-color: #2d1a1e; border: 1px solid #ff4b4b; color: #ff4b4b; }
    .val-diff { font-size: 0.8em; color: #ffffff; margin-top: 5px; font-weight: normal; }
    </style>
    """, unsafe_allow_html=True)

ALLOWED_STATUS = ["OK", "DUPLICADO", "ENCERRAR"]

# --- FUNÇÕES ---
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

def safe_get(lst, idx, default=""): return lst[idx] if idx < len(lst) else default
def is_ok(val): return str(val).strip().upper() == "OK"

@st.cache_resource
def get_sheets():
    gc = init_connection()
    SPREADSHEET_ID = "1zOof6YDL4U8hYMiFi5zt4V_alYK6EcRvV3QKERvNlhA"
    ss = gc.open_by_key(SPREADSHEET_ID)
    return {
        "input": ss.worksheet("INPUT - BOLETOS"),
        "output": ss.worksheet("OUTPUT - BOLETOS"),
        "comm": ss.worksheet("COMUNICACAO - CLIENTE")
    }

try:
    sheets = get_sheets()
except Exception as e:
    st.error(f"Erro ao conectar com a planilha: {e}")
    st.stop()


# ==============================================================================
# TELA 1: LANÇAMENTO INDIVIDUAL (Intacta)
# ==============================================================================
def pagina_lancamento():
    st.title("🏦 Gestor de Boletos - Lançamento Individual")

    vals_in = sheets["input"].get_all_values()
    df_input = pd.DataFrame(vals_in[4:], columns=vals_in[3])
    df_input = df_input[df_input.iloc[:, 2] != ""].copy()

    squad_list = sorted([s for s in df_input.iloc[:, 5].unique() if s and s != "-"] )
    selected_squad = st.sidebar.selectbox("Filtro SQUAD (Lançamento)", squad_list)

    df_filtered = df_input[(df_input.iloc[:, 5] == selected_squad) & (df_input.iloc[:, 3].isin(ALLOWED_STATUS))]

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
                    # 1. Update Input
                    cell_in = sheets["input"].find(key_orig, in_column=2)
                    r_in = cell_in.row
                    sheets["input"].update(f"I{r_in}:P{r_in}", [[m_met, limpar_valor_monetario(m_cre), m_dat, limpar_valor_monetario(m_val),
                                                          g_met, limpar_valor_monetario(g_cre), g_dat, limpar_valor_monetario(g_val)]], value_input_option='USER_ENTERED')
                    
                    time.sleep(4) 

                    # 2. Get Output
                    data_out = sheets["output"].get_all_values()
                    match_idx = -1
                    for i, r in enumerate(data_out[7:]):
                        if len(r) > 1 and normalizar_id(r[1]) == key_norm:
                            match_idx = i + 8
                            out_row_data = r
                            break

                    if match_idx == -1:
                        st.error("❌ Key não encontrada na aba OUTPUT.")
                    else:
                        # 3. Update Output Triggers
                        sheets["output"].update_cell(match_idx, 26, out_row_data[24]) 
                        sheets["output"].update_cell(match_idx, 38, out_row_data[36]) 
                        
                        time.sleep(2)
                        final_row = sheets["output"].row_values(match_idx)

                        st.success(f"✅ Dados de {cliente_sel} atualizados!")
                        
                        st.markdown("### 📊 Auditoria de Cheques")
                        cols = st.columns(6)
                        
                        checks = [
                            ("Check 1: FB", safe_get(final_row, 8), ""), 
                            ("Check 1: GL", safe_get(final_row, 9), ""), 
                            ("Check 2 (Mídia)", safe_get(final_row, 12), f"Acordado: {safe_get(final_row, 10)} | Lançado: {safe_get(final_row, 11)}" if not is_ok(safe_get(final_row, 12)) else ""), 
                            ("Check 3 (Emissão)", safe_get(final_row, 15), f"Acordado: {safe_get(final_row, 13)} | Soma: {safe_get(final_row, 14)}" if not is_ok(safe_get(final_row, 15)) else ""), 
                            ("Check 4 (Meta)", safe_get(final_row, 17), "Saldo não durará até dia 10" if not is_ok(safe_get(final_row, 17)) else ""), 
                            ("Check 4 (Google)", safe_get(final_row, 19), "Saldo não durará até dia 10" if not is_ok(safe_get(final_row, 19)) else "")
                        ]
                        
                        for i, (name, val, diff) in enumerate(checks):
                            ok_status = is_ok(val)
                            cl = "ok-card" if ok_status else "nok-card"
                            with cols[i]:
                                st.markdown(f"""<div class='check-card {cl}'>{name}<br>{val}<div class='val-diff'>{diff}</div></div>""", unsafe_allow_html=True)

                        st.divider()
                        l_c, r_c = st.columns(2)
                        
                        with l_c:
                            st.metric("A Emitir (Meta Ads)", f"R$ {safe_get(final_row, 24)}") 
                            st.metric("A Emitir (Google Ads)", f"R$ {safe_get(final_row, 36)}") 
                            if len(final_row) > 27 and final_row[27]: st.info(f"**Boleto Meta:** {final_row[27]}") 
                            if len(final_row) > 39 and final_row[39]: st.info(f"**Boleto Google:** {final_row[39]}") 

                        with r_c:
                            st.markdown("**Ações de Envio:**")
                            try:
                                cell_comm = sheets["comm"].find(key_orig, in_column=2)
                                row_comm_idx = cell_comm.row
                                comm_vals = sheets["comm"].row_values(row_comm_idx, value_render_option='UNFORMATTED_VALUE')
                                while len(comm_vals) < 15: comm_vals.append("")

                                val_col_c = str(comm_vals[2]).strip()
                                val_col_g = str(comm_vals[6]).strip()
                                val_col_i = str(comm_vals[8]).strip()
                                val_col_j = str(comm_vals[9]).strip()

                                if val_col_j and val_col_j != "-" and val_col_j != "0":
                                    texto_wpp = (
                                        f"Olá, {val_col_g}!\n\n"
                                        f"Foram enviados no e-mail {val_col_i}, os boletos das plataformas de anúncios.\n\n"
                                        f"*Observações importantes:*\n"
                                        f"1. Não conseguimos alterar a data de vencimento dos boletos.\n"
                                        f"2. *De maneira alguma, realize o pagamento de boletos vencidos.*\n\n"
                                        f"Qualquer dúvida, estou à disposição!"
                                    )
                                    msg_encoded = urllib.parse.quote(texto_wpp)
                                    link_wpp = f"https://wa.me/{val_col_j}?text={msg_encoded}"
                                    st.link_button(f"📲 Enviar WhatsApp ({val_col_g})", link_wpp)
                                else:
                                    st.warning("⚠️ Telefone não cadastrado.")

                                if val_col_i and "@" in val_col_i:
                                    agora = datetime.now()
                                    data_ref = agora.strftime("%m - %Y")
                                    assunto = f"Boleto Anúncios - {val_col_c} | Ref. {data_ref}"
                                    corpo_email = (
                                        f"Olá,\n\n"
                                        f"Envio anexos os boletos referentes às plataformas de mídia paga.\n\n"
                                        f"Observações importantes:\n"
                                        f"1. Não é possível editar a data de vencimento do boleto gerado na plataforma.\n"
                                        f"2. De maneira alguma, realize o pagamento de boletos vencidos.\n\n"
                                        f"Atenciosamente,"
                                    )
                                    params = {"view": "cm", "fs": "1", "to": val_col_i, "cc": "financeiro@comodoplanejados.com.br", "su": assunto, "body": corpo_email}
                                    query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote) 
                                    link_gmail = f"https://mail.google.com/mail/?{query_string}"
                                    st.link_button(f"📧 Abrir no Gmail ({val_col_i})", link_gmail)
                                else:
                                    st.warning("⚠️ E-mail não cadastrado.")

                            except Exception as e:
                                st.error(f"Erro na geração dos links: {e}")

                except Exception as e:
                    st.error(f"Erro no processamento geral: {e}")


# ==============================================================================
# TELA 2: ATUALIZAÇÃO EM MASSA (Corrigida: Data e Botões)
# ==============================================================================
def pagina_atualizacao_massa():
    st.title("🚀 Atualização em Massa - Boletos")

    vals_in = sheets["input"].get_all_values()
    df_input = pd.DataFrame(vals_in[4:], columns=vals_in[3])
    df_input = df_input[df_input.iloc[:, 2] != ""].copy()
    
    df_input["_row_idx"] = df_input.index + 5 

    squad_list = sorted([s for s in df_input.iloc[:, 5].unique() if s and s != "-"] )
    selected_squad = st.sidebar.selectbox("Filtro SQUAD (Massa)", squad_list)

    df_filtered = df_input[(df_input.iloc[:, 5] == selected_squad) & (df_input.iloc[:, 3].isin(ALLOWED_STATUS))]

    if df_filtered.empty:
        st.warning("Nenhum cliente disponível.")
        return

    st.info("📝 Preencha os campos. Clientes em branco serão ignorados.")

    inputs = {}
    with st.form("form_massa"):
        for i, row in df_filtered.iterrows():
            with st.expander(f"👤 {row['Clientes']}", expanded=True):
                c1, c2 = st.columns(2)
                row_key = str(i)
                with c1:
                    st.markdown("**🟦 Meta Ads**")
                    inputs[f"m_met_{row_key}"] = st.selectbox("Método", ["", "Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanha"], key=f"m1_{row_key}")
                    inputs[f"m_cre_{row_key}"] = st.text_input("Crédito", placeholder="R$ 0,00", key=f"m2_{row_key}")
                    inputs[f"m_dat_{row_key}"] = st.text_input("Data", placeholder="DD/MM", key=f"m3_{row_key}")
                    inputs[f"m_val_{row_key}"] = st.text_input("Gasto Diário", placeholder="R$ 0,00", key=f"m4_{row_key}")
                with c2:
                    st.markdown("**🟩 Google Ads**")
                    inputs[f"g_met_{row_key}"] = st.selectbox("Método", ["", "Boleto", "PIX", "Cartão Pós", "Cartão Pré", "Sem Campanha"], key=f"g1_{row_key}")
                    inputs[f"g_cre_{row_key}"] = st.text_input("Crédito", placeholder="R$ 0,00", key=f"g2_{row_key}")
                    inputs[f"g_dat_{row_key}"] = st.text_input("Data", placeholder="DD/MM", key=f"g3_{row_key}")
                    inputs[f"g_val_{row_key}"] = st.text_input("Gasto Diário", placeholder="R$ 0,00", key=f"g4_{row_key}")
        
        btn_enviar = st.form_submit_button("🚀 ENVIAR ATUALIZAÇÕES", type="primary")

    if btn_enviar:
        with st.status("Processando...", expanded=True) as status:
            updates = []
            clients_meta = [] 
            
            # 1. Coleta Inputs
            for i, row in df_filtered.iterrows():
                row_key = str(i)
                has_data = (
                    inputs[f"m_met_{row_key}"] != "" or inputs[f"m_cre_{row_key}"] != "" or
                    inputs[f"g_met_{row_key}"] != "" or inputs[f"g_cre_{row_key}"] != ""
                )
                
                if has_data:
                    real_row = row["_row_idx"]
                    data_row = [
                        inputs[f"m_met_{row_key}"], limpar_valor_monetario(inputs[f"m_cre_{row_key}"]), inputs[f"m_dat_{row_key}"], limpar_valor_monetario(inputs[f"m_val_{row_key}"]),
                        inputs[f"g_met_{row_key}"], limpar_valor_monetario(inputs[f"g_cre_{row_key}"]), inputs[f"g_dat_{row_key}"], limpar_valor_monetario(inputs[f"g_val_{row_key}"])
                    ]
                    updates.append({'range': f"I{real_row}:P{real_row}", 'values': [data_row]})
                    clients_meta.append({'key': normalizar_id(row['Key']), 'name': row['Clientes']})

            if not updates:
                st.warning("Nada preenchido."); return

            # 2. Envia (CORREÇÃO DE DATA AQUI: value_input_option='USER_ENTERED')
            sheets["input"].batch_update(updates, value_input_option='USER_ENTERED')
            
            status.write("Enviado! Calculando (4s)...")
            time.sleep(4)
            
            # 3. Baixa Output e Comm
            status.write("Baixando resultados...")
            all_out = sheets["output"].get_all_values()
            all_comm = sheets["comm"].get_all_values()
            status.update(label="Concluído!", state="complete", expanded=False)

            st.divider()
            st.markdown("## 🎉 Resultados")
            
            # 4. Gera Cards HTML
            for client in clients_meta:
                c_key = client['key']
                c_name = client['name']
                
                # Busca nas listas baixadas
                out_row = next((r for r in all_out[7:] if len(r) > 1 and normalizar_id(r[1]) == c_key), None)
                comm_row = next((r for r in all_comm if len(r) > 2 and normalizar_id(r[1]) == c_key), None)
                
                if out_row:
                    # Checks
                    checks_data = [
                        ("FB", safe_get(out_row, 8)), ("GL", safe_get(out_row, 9)),
                        ("Mídia", safe_get(out_row, 12)), ("Emissão", safe_get(out_row, 15)),
                        ("Meta", safe_get(out_row, 17)), ("Google", safe_get(out_row, 19))
                    ]
                    
                    checks_html_str = ""
                    for name, val in checks_data:
                        cls = "check-ok" if is_ok(val) else "check-nok"
                        checks_html_str += f"<div class='mass-check-box {cls}'>{name}<br>{val}</div>"

                    # Valores
                    val_meta = str(safe_get(out_row, 24)).replace("R$", "").strip()
                    val_google = str(safe_get(out_row, 36)).replace("R$", "").strip()
                    txt_meta = safe_get(out_row, 27)
                    txt_google = safe_get(out_row, 39)

                    # Botões (Lógica REPLICADA DA INDIVIDUAL)
                    btns_html = ""
                    if comm_row:
                         val_col_c = str(comm_row[2]).strip()
                         val_col_g = str(comm_row[6]).strip()
                         val_col_i = str(comm_row[8]).strip()
                         val_col_j = str(comm_row[9]).strip()
                         
                         # --- Lógica WPP ---
                         if val_col_j and val_col_j not in ["-", "0", ""]:
                             # Texto idêntico à aba individual
                             texto_wpp = (
                                f"Olá, {val_col_g}!\n\n"
                                f"Foram enviados no e-mail {val_col_i}, os boletos das plataformas de anúncios.\n\n"
                                f"*Observações importantes:*\n"
                                f"1. Não conseguimos alterar a data de vencimento dos boletos.\n"
                                f"2. *De maneira alguma, realize o pagamento de boletos vencidos.*\n\n"
                                f"Qualquer dúvida, estou à disposição!"
                             )
                             link = f"https://wa.me/{val_col_j}?text={urllib.parse.quote(texto_wpp)}"
                             btns_html += f"<a href='{link}' target='_blank' style='text-decoration:none; flex:1;'><button style='background-color:#238636;color:white;border:none;padding:12px;border-radius:6px;width:100%;cursor:pointer;font-weight:bold;margin-right:5px;'>WhatsApp</button></a>"
                         
                         # --- Lógica Gmail ---
                         if val_col_i and "@" in val_col_i:
                             agora = datetime.now()
                             data_ref = agora.strftime("%m - %Y")
                             assunto = f"Boleto Anúncios - {val_col_c} | Ref. {data_ref}"
                             corpo_email = (
                                f"Olá,\n\n"
                                f"Envio anexos os boletos referentes às plataformas de mídia paga.\n\n"
                                f"Observações importantes:\n"
                                f"1. Não é possível editar a data de vencimento do boleto.\n"
                                f"2. De maneira alguma, realize o pagamento de boletos vencidos.\n\n"
                                f"Atenciosamente,"
                             )
                             params = {"view": "cm", "fs": "1", "to": val_col_i, "cc": "financeiro@comodoplanejados.com.br", "su": assunto, "body": corpo_email}
                             qs = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
                             link = f"https://mail.google.com/mail/?{qs}"
                             btns_html += f"<a href='{link}' target='_blank' style='text-decoration:none; flex:1;'><button style='background-color:#cf222e;color:white;border:none;padding:12px;border-radius:6px;width:100%;cursor:pointer;font-weight:bold;margin-left:5px;'>Gmail</button></a>"

                    # HTML Card
                    html_card = f"""
                    <div class="mass-card">
                        <div class="mass-title">{c_name}</div>
                        <div style="font-size:0.8em; margin-bottom:5px; color:#aaa;">📊 Auditoria de Cheques</div>
                        <div class="mass-checks-grid">
                            {checks_html_str}
                        </div>
                        <div class="mass-values">
                            <div class="mass-val-col">
                                <div class="mass-label">Meta Ads</div>
                                <div class="mass-money">R$ {val_meta}</div>
                                <div class="mass-boleto">{txt_meta if txt_meta else 'Sem Boleto'}</div>
                            </div>
                            <div style="border-left:1px solid #30363d;"></div>
                            <div class="mass-val-col">
                                <div class="mass-label">Google Ads</div>
                                <div class="mass-money">R$ {val_google}</div>
                                <div class="mass-boleto">{txt_google if txt_google else 'Sem Boleto'}</div>
                            </div>
                        </div>
                        <div style="display:flex; justify-content:space-between;">
                            {btns_html}
                        </div>
                    </div>
                    """
                    st.markdown(html_card, unsafe_allow_html=True)
                    
                    # Trigger visual Output
                    match_idx_out = -1
                    for idx, r in enumerate(all_out[7:]):
                         if len(r) > 1 and normalizar_id(r[1]) == c_key:
                             match_idx_out = idx + 8; break
                    
                    if match_idx_out != -1:
                        sheets["output"].update_cell(match_idx_out, 26, safe_get(out_row, 24))
                        sheets["output"].update_cell(match_idx_out, 38, safe_get(out_row, 36))


# ==============================================================================
# TELA 3: DASHBOARD STATUS (Mantida V2.3)
# ==============================================================================
def pagina_dashboard():
    st.title("📊 Dashboard de Status - Squads")
    with st.spinner("Carregando dados..."):
        try:
            raw_out = sheets["output"].get_all_values()
            header = raw_out[6] 
            data_rows = raw_out[7:] 
            df_out = pd.DataFrame(data_rows, columns=header)
            df_final = df_out[(df_out.iloc[:, 1].str.strip() != "") & (df_out.iloc[:, 3].isin(ALLOWED_STATUS))].copy()
        except Exception as e: st.error(str(e)); return

    squads = sorted([s for s in df_final["SQUAD"].unique() if s and s != "-"])
    if not squads: st.warning("Sem dados."); return
    sel_squad = st.sidebar.selectbox("Filtro SQUAD (Dashboard)", squads)
    df_squad = df_final[df_final["SQUAD"] == sel_squad].copy()
    
    st.divider()
    df_editor = pd.DataFrame()
    df_editor["Key"] = df_squad.iloc[:, 1]
    df_editor["Clientes"] = df_squad.iloc[:, 2]
    df_editor["Status Meta"] = df_squad.iloc[:, 28]
    df_editor["Status Google"] = df_squad.iloc[:, 40]
    df_editor["_original_index"] = df_squad.index

    opcoes = ["", "EMITIDO", "ENVIADO", "NOK", "FINALIZADO", "ISENTO"]
    edited = st.data_editor(df_editor, column_config={"_original_index":None, "Status Meta":st.column_config.SelectboxColumn(options=opcoes), "Status Google":st.column_config.SelectboxColumn(options=opcoes)}, hide_index=True, use_container_width=True)

    if st.button("💾 SALVAR STATUS EM LOTE", type="primary"):
        updates = []
        for i, row in edited.iterrows():
            real_row = int(row["_original_index"]) + 8
            updates.append({'range': f"AC{real_row}", 'values': [[row["Status Meta"]]]})
            updates.append({'range': f"AO{real_row}", 'values': [[row["Status Google"]]]})
        if updates: sheets["output"].batch_update(updates); st.success("Atualizado!"); time.sleep(1); st.rerun()

# ==============================================================================
# NAVEGAÇÃO
# ==============================================================================
st.sidebar.title("Menu")
pagina = st.sidebar.radio("Ir para:", ["📝 Lançamento Individual", "🚀 Atualização em Massa", "📊 Dashboard Status"])

if pagina == "📝 Lançamento Individual": pagina_lancamento()
elif pagina == "🚀 Atualização em Massa": pagina_atualizacao_massa()
else: pagina_dashboard()
