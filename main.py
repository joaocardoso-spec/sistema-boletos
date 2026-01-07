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
                        ("Check 2 (Mídia)", safe_get(final_row, 12), ""), 
                        ("Check 3 (Emissão)", safe_get(final_row, 15), ""), 
                        ("Check 4 (Meta)", safe_get(final_row, 17), "Saldo baixo" if not is_ok(safe_get(final_row, 17)) else ""), 
                        ("Check 4 (Google)", safe_get(final_row, 19), "Saldo baixo" if not is_ok(safe_get(final_row, 19)) else "")
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

                    # --- BLOCO DE ENVIO (LÓGICA PYTHON) ---
                    with r_c:
                        st.markdown("**Ações de Envio:**")
                        try:
                            # 1. Busca linha na aba Comunicacao
                            cell_comm = sheets["comm"].find(key_orig, in_column=2)
                            row_comm_idx = cell_comm.row
                            
                            # 2. Pega dados BRUTOS (sem fórmula)
                            comm_vals = sheets["comm"].row_values(row_comm_idx, value_render_option='UNFORMATTED_VALUE')
                            while len(comm_vals) < 15: comm_vals.append("")

                            val_col_c = str(comm_vals[2]).strip()  # Cliente
                            val_col_g = str(comm_vals[6]).strip()  # Contato
                            val_col_i = str(comm_vals[8]).strip()  # Email
                            val_col_j = str(comm_vals[9]).strip()  # Telefone Ajustado

                            # WhatsApp
                            if val_col_j and val_col_j not in ["-", "0", ""]:
                                texto_wpp = (
                                    f"Olá, {val_col_g}!\n\nForam enviados no e-mail {val_col_i}, os boletos das plataformas de anúncios.\n\n"
                                    f"*Observações importantes:*\n1. Não conseguimos alterar a data de vencimento dos boletos.\n"
                                    f"2. *De maneira alguma, realize o pagamento de boletos vencidos.*\n\nQualquer dúvida, estou à disposição!"
                                )
                                msg_encoded = urllib.parse.quote(texto_wpp)
                                link_wpp = f"https://wa.me/{val_col_j}?text={msg_encoded}"
                                st.link_button(f"📲 Enviar WhatsApp ({val_col_g})", link_wpp)
                            else:
                                st.warning("⚠️ Telefone não cadastrado (Col J).")

                            # Gmail
                            if val_col_i and "@" in val_col_i:
                                agora = datetime.now()
                                data_ref = agora.strftime("%m - %Y")
                                assunto = f"Boleto Anúncios - {val_col_c} | Ref. {data_ref}"
                                corpo_email = (
                                    f"Olá,\n\nEnvio anexos os boletos referentes às plataformas de mídia paga.\n\n"
                                    f"Observações importantes:\n1. Não é possível editar a data de vencimento.\n"
                                    f"2. De maneira alguma, realize o pagamento de boletos vencidos.\n\n"
                                    f"Atenciosamente,"
                                )
                                params = {"view": "cm", "fs": "1", "to": val_col_i, "cc": "financeiro@comodoplanejados.com.br", "su": assunto, "body": corpo_email}
                                query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote) 
                                link_gmail = f"https://mail.google.com/mail/?{query_string}"
                                st.link_button(f"📧 Abrir no Gmail ({val_col_i})", link_gmail)
                            else:
                                st.warning("⚠️ E-mail não cadastrado (Col I).")

                        except Exception as e:
                            st.error(f"Erro na geração dos links: {e}")

            except Exception as e:
                st.error(f"Erro no processamento geral: {e}")

# ==============================================================================
# PÁGINA 2: DASHBOARD DE STATUS (Nova Funcionalidade)
# ==============================================================================
def pagina_dashboard():
    st.title("📊 Dashboard de Status - Squads")

    # 1. Carregar Dados da OUTPUT
    with st.spinner("Carregando dados da aba OUTPUT..."):
        try:
            # Pega todos os valores
            raw_data = sheets["output"].get_all_values()
            
            # Cabeçalho na linha 7 (index 6)
            header = raw_data[6]
            
            # Dados a partir da linha 8 (index 7)
            data_rows = raw_data[7:]
            
            # Cria DataFrame
            df = pd.DataFrame(data_rows, columns=header)
            
            # Filtra linhas vazias (Key ou Cliente vazio)
            df = df[df["Key"].str.strip() != ""]
            
        except Exception as e:
            st.error(f"Erro ao ler OUTPUT: {e}")
            return

    # 2. Filtros
    squads = sorted([s for s in df["SQUAD"].unique() if s and s != "-"])
    
    c_filt, c_dummy = st.columns([1, 2])
    with c_filt:
        sel_squad = st.selectbox("Selecione a SQUAD:", squads)
    
    # Filtra DF pela Squad
    df_squad = df[df["SQUAD"] == sel_squad].copy()
    
    # 3. Preparação para Edição
    # Precisamos identificar as colunas AC e AO. 
    # Como carregamos pelo cabeçalho, vamos buscar pelo nome da coluna ou pelo índice se o nome for vazio/repetido.
    # Assumindo que o cabeçalho está correto, mas vamos garantir pegando pelo índice para segurança.
    # AC é a 29ª coluna (Index 28 no Python)
    # AO é a 41ª coluna (Index 40 no Python)
    
    # Mapeamento seguro de nomes de colunas para o Data Editor
    # Vamos criar um DF reduzido apenas com o que importa para edição
    
    # Pega os nomes das colunas de status baseados na posição
    col_name_meta = header[28] if len(header) > 28 else "Status Meta (AC)"
    col_name_google = header[40] if len(header) > 40 else "Status Google (AO)"
    
    # Cria um DF limpo para exibição
    df_editor = df_squad[["Key", "Clientes", "SQUAD"]].copy()
    
    # Adiciona as colunas de status buscando pelo índice original do DF completo
    # O df_squad tem as mesmas colunas do df original (header)
    df_editor["Status Meta"] = df_squad.iloc[:, 28] 
    df_editor["Status Google"] = df_squad.iloc[:, 40]
    
    # Adiciona índice original para podermos salvar depois (Index + 8 = Linha na planilha)
    df_editor["_original_index"] = df_squad.index
    
    st.divider()
    st.info("💡 Dica: Edite os status na tabela abaixo e clique em 'Salvar Alterações' no final.")

    # 4. Tabela Editável
    opcoes_status = ["", "EMITIDO", "ENVIADO", "NOK", "FINALIZADO", "ISENTO"]
    
    edited_df = st.data_editor(
        df_editor,
        column_config={
            "_original_index": None, # Esconde essa coluna
            "Key": st.column_config.TextColumn("ID Cliente", disabled=True),
            "Clientes": st.column_config.TextColumn("Nome Cliente", disabled=True, width="medium"),
            "SQUAD": st.column_config.TextColumn("Squad", disabled=True),
            "Status Meta": st.column_config.SelectboxColumn(
                "Status Meta (AC)",
                help="Selecione o status do boleto Meta",
                width="medium",
                options=opcoes_status,
                required=False
            ),
            "Status Google": st.column_config.SelectboxColumn(
                "Status Google (AO)",
                help="Selecione o status do boleto Google",
                width="medium",
                options=opcoes_status,
                required=False
            )
        },
        hide_index=True,
        use_container_width=True,
        key="editor_status"
    )

    # 5. Botão de Salvar
    if st.button("💾 SALVAR ALTERAÇÕES EM LOTE", type="primary"):
        # Compara o editado com o original para saber o que mudou (simples: iteramos e salvamos tudo da squad filtrada)
        # Para otimizar, poderíamos comparar, mas salvar a squad atual é seguro e rápido o suficiente.
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        updates = []
        
        try:
            total = len(edited_df)
            for i, row in edited_df.iterrows():
                # Calcula a linha real na planilha
                # O índice do DataFrame 'raw_data' começava em 0 (linha 1 da planilha).
                # Nossos dados começaram na linha 8 (index 7 do raw_data).
                # O '_original_index' guardou o índice relativo ao slice 'data_rows'.
                # Logo: Linha Real = _original_index + 8
                
                real_row = int(row["_original_index"]) + 8
                
                # Valores a salvar
                val_meta = row["Status Meta"]
                val_google = row["Status Google"]
                
                # Adiciona à lista de batch update
                # Formato gspread batch: {'range': 'AC10', 'values': [['EMITIDO']]}
                
                updates.append({
                    'range': f"AC{real_row}",
                    'values': [[val_meta]]
                })
                updates.append({
                    'range': f"AO{real_row}",
                    'values': [[val_google]]
                })

            status_text.text("Enviando dados para o Google Sheets...")
            
            # Batch update é muito mais rápido que update_cell um por um
            sheets["output"].batch_update(updates)
            
            progress_bar.progress(100)
            st.success(f"✅ Sucesso! {total} linhas processadas e status atualizados.")
            time.sleep(2)
            st.rerun()
            
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")

# ==============================================================================
# MENU LATERAL PRINCIPAL
# ==============================================================================
st.sidebar.title("Menu Principal")
pagina = st.sidebar.radio("Navegar para:", ["📝 Lançamento", "📊 Dashboard de Status"])

if pagina == "📝 Lançamento":
    pagina_lancamento()
else:
    pagina_dashboard()
